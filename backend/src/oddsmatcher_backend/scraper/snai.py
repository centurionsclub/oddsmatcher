"""Snai Italy pregame odds scraper.

Strategy:
  Phase 1 — httpx to alberaturaPrematch → competition tree (disc/manif IDs). ✅
  Phase 2 — httpx probe of many event endpoint patterns (no Playwright needed).
             The first URL that returns a 200 with event-like content is used
             for all remaining competitions.

API base: https://betting-snai.flutterseatech.it/api/lettura-palinsesto-sport
"""

import json as _json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)

BASE_URL = "https://www.snai.it"
API_HOST = "betting-snai.flutterseatech.it"
API_BASE = f"https://{API_HOST}/api/lettura-palinsesto-sport"
BOOKMAKER = "Snai"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_SNAI_HEADERS = {
    "User-Agent": _UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "it-IT,it;q=0.9",
    "Referer": "https://www.snai.it/",
    "Origin": "https://www.snai.it",
}

# codiceDisciplina (int) → our sport key
SPORT_CODE_MAP: dict[int, str] = {
    1: "calcio",
    2: "basket",
    3: "tennis",
}

# Each entry: (our_league_name, [keywords_ALL_must_appear_in_descrizione])
LEAGUE_PATTERNS: dict[str, list[tuple[str, list[str]]]] = {
    "calcio": [
        ("Serie A",           ["ITA", "Serie A"]),
        ("Serie B",           ["ITA", "Serie B"]),
        ("Premier League",    ["ENG", "Premier"]),
        ("La Liga",           ["ESP", "Primera"]),
        ("Bundesliga",        ["GER", "Bundesliga"]),
        ("Ligue 1",           ["FRA", "Ligue 1"]),
        ("Champions League",  ["Champions League"]),
        ("Europa League",     ["Europa League"]),
        ("Conference League", ["Conference"]),
    ],
    "tennis": [
        ("Roland Garros",    ["Roland Garros"]),
        ("Wimbledon",        ["Wimbledon"]),
        ("US Open",          ["US Open"]),
        ("Australian Open",  ["Australian Open"]),
        ("Amburgo",          ["Amburgo"]),
        ("Ginevra",          ["Ginevra"]),
        ("Rabat",            ["Rabat"]),
        ("Strasburgo",       ["Strasburgo"]),
    ],
    "basket": [
        ("NBA",            ["NBA"]),
        ("Serie A Basket", ["ITA", "Serie A"]),
        ("Eurolega",       ["Eurolega"]),
    ],
}

ALBERATURA_URL = f"{API_BASE}/palinsesto/prematch/alberaturaPrematch"


def _match_league(descrizione: str, sport_key: str) -> str | None:
    for league_name, keywords in LEAGUE_PATTERNS.get(sport_key, []):
        if all(kw in descrizione for kw in keywords):
            return league_name
    return None


def _parse_date(s: str) -> str | None:
    if not s:
        return None
    FMTS = [
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y%m%d %H:%M:%S",
    ]
    for fmt in FMTS:
        try:
            dt = datetime.strptime(s.strip()[:19], fmt)
            off = 2 if 3 <= dt.month <= 10 else 1
            return dt.replace(tzinfo=timezone(timedelta(hours=off))).astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        return s


def _parse_snai_events(data: Any, league_name: str, sport_key: str) -> list[MatchOdds]:
    """Parse Snai API event response."""
    results: list[MatchOdds] = []
    if not data:
        return results

    # Log top-level structure for discovery
    if isinstance(data, dict):
        logger.info("[Snai] %s response top keys: %s", league_name, list(data.keys())[:12])

    events: list = []
    if isinstance(data, list):
        events = data
    elif isinstance(data, dict):
        # avvenimentoFeMap / avvenimentiMap: dict keyed by event ID → convert to list
        for map_key in ("avvenimentoFeMap", "avvenimentiMap", "avvenimentiFeMap",
                        "eventMap", "avvenimentiFe"):
            avm = data.get(map_key)
            if isinstance(avm, dict) and avm:
                events = list(avm.values())
                logger.info("[Snai] %s: found %d events in %s", league_name, len(events), map_key)
                break
        if not events:
            for key in ("avvenimenti", "eventi", "events", "data", "result",
                        "matches", "fixtures", "palinsesto", "avv",
                        "avvenimentiList", "listaAvvenimenti", "items"):
                val = data.get(key)
                if isinstance(val, list) and val:
                    events = val
                    break
                if isinstance(val, dict):
                    for k2 in ("avvenimenti", "eventi", "events", "avv", "list", "items"):
                        v2 = val.get(k2)
                        if isinstance(v2, list) and v2:
                            events = v2
                            break
                    if events:
                        break
            # Try nested under any single key
            if not events:
                for val in data.values():
                    if isinstance(val, list) and val and isinstance(val[0], dict):
                        sample = val[0]
                        if any(k in sample for k in ("descrizione", "description", "name",
                                                       "dataOra", "startDate", "scommesse",
                                                       "quota", "betGroupList")):
                            events = val
                            break
    if events:
        first = events[0] if isinstance(events[0], dict) else {}
        logger.info("[Snai] %s: first event keys=%s | preview=%.300s",
                    league_name, list(first.keys())[:12],
                    _json.dumps(first, ensure_ascii=False)[:300])

    for ev in events:
        if not isinstance(ev, dict):
            continue

        name_raw = (
            ev.get("descrizione") or ev.get("description") or
            ev.get("eventDescription") or ev.get("name") or
            ev.get("da") or ev.get("en") or ""
        )
        name = re.sub(r"\s+[-–v]\s+", " - ", str(name_raw)).strip()
        if not name:
            continue

        time_raw = (
            ev.get("dataOra") or ev.get("data") or ev.get("startTime") or
            ev.get("startDate") or ev.get("eventDate") or ev.get("ts") or ""
        )
        event_time = _parse_date(str(time_raw)) if time_raw else None
        match_url = f"{BASE_URL}/scommesse/"

        parts = name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else name
        away = parts[1].strip() if len(parts) == 2 else ""

        mkts_raw = (
            ev.get("scommesse") or ev.get("mercati") or ev.get("markets") or
            ev.get("quote") or ev.get("odds") or ev.get("betGroupList") or []
        )
        if isinstance(mkts_raw, dict):
            mkts_raw = list(mkts_raw.values())

        for mkt in mkts_raw:
            if not isinstance(mkt, dict):
                continue

            mname = str(
                mkt.get("descrizione") or mkt.get("description") or
                mkt.get("name") or mkt.get("tipo") or mkt.get("marketName") or ""
            ).strip()

            if any(kw in mname for kw in ("1X2", "Esito Finale", "Finale", "Risultato Finale",
                                           "1 X 2", "Match Result", "Testa a Testa")):
                sels_raw = (
                    mkt.get("esiti") or mkt.get("selections") or
                    mkt.get("outcomes") or mkt.get("quote") or
                    mkt.get("betList") or []
                )
                if isinstance(sels_raw, dict):
                    sels_raw = list(sels_raw.values())
                odds_dict: dict[str, float] = {}
                OUTCOME_MAP = {
                    "1": "1", "Casa": "1", "Home": "1",
                    "X": "X", "Pareggio": "X", "Draw": "X",
                    "2": "2", "Ospite": "2", "Away": "2",
                }
                for sel in sels_raw:
                    if not isinstance(sel, dict):
                        continue
                    lbl = str(
                        sel.get("descrizione") or sel.get("esito") or
                        sel.get("name") or sel.get("outcome") or sel.get("label") or ""
                    ).strip()
                    canonical = OUTCOME_MAP.get(lbl, lbl)
                    q_raw = sel.get("quota") or sel.get("odds") or sel.get("price") or sel.get("q")
                    try:
                        q = float(q_raw) if q_raw is not None else None
                        if q and q > 1.0:
                            odds_dict[canonical] = q
                    except (TypeError, ValueError):
                        pass
                if odds_dict:
                    results.append(MatchOdds(
                        sport=sport_key, league=league_name,
                        home_team=home, away_team=away,
                        event_name=name, event_time=event_time,
                        match_url=match_url, market="1X2",
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                    ))

            elif any(kw in mname for kw in ("Doppia Chance", "Double Chance")):
                sels_raw = (
                    mkt.get("esiti") or mkt.get("selections") or
                    mkt.get("outcomes") or []
                )
                if isinstance(sels_raw, dict):
                    sels_raw = list(sels_raw.values())
                DC_MAP = {"1X": "1X", "X2": "X2", "12": "12"}
                odds_dc: dict[str, float] = {}
                for sel in sels_raw:
                    lbl = str(sel.get("descrizione") or sel.get("esito") or sel.get("name") or "").strip()
                    canonical = DC_MAP.get(lbl, lbl)
                    q_raw = sel.get("quota") or sel.get("odds") or sel.get("price")
                    try:
                        q = float(q_raw) if q_raw is not None else None
                        if q and q > 1.0:
                            odds_dc[canonical] = q
                    except (TypeError, ValueError):
                        pass
                if odds_dc:
                    results.append(MatchOdds(
                        sport=sport_key, league=league_name,
                        home_team=home, away_team=away,
                        event_name=name, event_time=event_time,
                        match_url=match_url, market="DC",
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dc}],
                    ))

            elif any(kw in mname for kw in ("Over/Under", "U/O", "Totale Gol", "Over Under")):
                sp_m = re.search(r"(\d+[.,]\d+)", mname)
                if not sp_m:
                    continue
                sp = sp_m.group(1).replace(",", ".")
                if sp not in {"1.5", "2.5", "3.5"}:
                    continue
                sels_raw = mkt.get("esiti") or mkt.get("selections") or mkt.get("outcomes") or []
                if isinstance(sels_raw, dict):
                    sels_raw = list(sels_raw.values())
                SIDE_MAP = {"Over": "Over", "Oltre": "Over", "Under": "Under", "Meno": "Under"}
                odds_uo: dict[str, float] = {}
                for sel in sels_raw:
                    lbl = str(sel.get("descrizione") or sel.get("esito") or sel.get("name") or "").strip()
                    side = SIDE_MAP.get(lbl)
                    q_raw = sel.get("quota") or sel.get("odds") or sel.get("price")
                    try:
                        q = float(q_raw) if q_raw is not None else None
                        if side and q and q > 1.0:
                            odds_uo[f"{side} {sp}"] = q
                    except (TypeError, ValueError):
                        pass
                if odds_uo:
                    results.append(MatchOdds(
                        sport=sport_key, league=league_name,
                        home_team=home, away_team=away,
                        event_name=name, event_time=event_time,
                        match_url=match_url, market=f"Over/Under {sp}",
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_uo}],
                    ))

    return results


class SnaiScraper:
    """Snai scraper — httpx only.

    Phase 1: alberaturaPrematch → competition IDs ✅
    Phase 2: probe event endpoint patterns via httpx (no Playwright — avoids timeout).
    """

    bookmaker_name = BOOKMAKER

    async def scrape_all(self) -> list[MatchOdds]:
        return await self._run(sport=None)

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        return await self._run(sport=sport)

    async def _run(self, sport: str | None) -> list[MatchOdds]:
        proxy_url = os.environ.get("PROXY_URL")
        if proxy_url:
            import urllib.parse as _up
            p = _up.urlparse(proxy_url)
            logger.info("[Snai] Using proxy: %s:%s", p.hostname, p.port)

        PFX = API_BASE  # https://betting-snai.flutterseatech.it/api/lettura-palinsesto-sport

        # ── Phase 1: Competition tree ────────────────────────────────────
        logger.info("[Snai] Fetching alberaturaPrematch…")
        competitions: list[tuple[str, str, int, int]] = []
        try:
            async with httpx.AsyncClient(
                headers=_SNAI_HEADERS, timeout=30, follow_redirects=True, proxy=proxy_url,
            ) as client:
                resp = await client.get(ALBERATURA_URL)
                resp.raise_for_status()
                alberatura_raw = resp.json()
                logger.info("[Snai] alberaturaPrematch ok, top keys: %s",
                            list(alberatura_raw.keys())[:8] if isinstance(alberatura_raw, dict) else "?")
                competitions = self._find_competitions(alberatura_raw, sport)
                logger.info("[Snai] %d competitions found", len(competitions))
        except Exception as exc:
            logger.error("[Snai] alberaturaPrematch failed: %s", exc)
            return []

        if not competitions:
            return []

        # Build a set of manifestazione IDs we care about → (league_name, sport_key)
        manif_to_league: dict[int, tuple[str, str]] = {
            manif: (lg, sk) for lg, sk, _, manif in competitions
        }
        disc_to_manif: dict[int, list[int]] = {}
        for lg, sk, disc, manif in competitions:
            disc_to_manif.setdefault(disc, []).append(manif)

        # ── Phase 2: Get events for each league via schedaManifestazione ────
        # Swagger-confirmed endpoint: /palinsesto/prematch/schedaManifestazione/{filter}/{key}
        # where filter is a time filter (try "T" = tutti, "0", "1") and key is the
        # manifestazione key from alberaturaPrematch manifestazioneMap dict keys.
        # Also try schedaManifestazioneSpeciale/{filter}/{disc}/{manif} (uses numeric IDs).
        #
        # Fallback: per-event via schedaAvvenimento/{key} using event keys from avvenimentiPrematch.

        all_results: list[MatchOdds] = []
        SCHEDA_AVVENIMENTO = f"{PFX}/palinsesto/prematch/schedaAvvenimento/{{key}}"
        SCHEDA_MANIF_SPECIALE = f"{PFX}/palinsesto/prematch/schedaManifestazioneSpeciale/{{filter}}/{{disc}}/{{manif}}"
        SCHEDA_MANIF = f"{PFX}/palinsesto/prematch/schedaManifestazione/{{filter}}/{{key}}"

        async with httpx.AsyncClient(
            headers=_SNAI_HEADERS, timeout=30, follow_redirects=True, proxy=proxy_url,
        ) as client:
            # ── Step 2a: Try schedaManifestazioneSpeciale to get all events per league ──
            # This is the most efficient: one request per league, returns full event+odds data.
            # Filter values to try: "T" (tutti), "0", "1", "all"
            working_manif_filter: str | None = None
            first_comp = competitions[0]
            first_lg, first_sk, first_disc, first_manif = first_comp

            for f_val in ("T", "0", "1", "all", "prematch"):
                url = SCHEDA_MANIF_SPECIALE.format(filter=f_val, disc=first_disc, manif=first_manif)
                try:
                    resp = await client.get(url)
                    text = resp.text[:200]
                    logger.info("[Snai] schedaManifestazioneSpeciale filter=%s → %d | %s",
                                f_val, resp.status_code, text)
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, dict):
                            logger.info("[Snai] ManifestazioneSpeciale top keys: %s | preview=%.600s",
                                        list(data.keys())[:12],
                                        _json.dumps(data, ensure_ascii=False)[:600])
                        working_manif_filter = f_val
                        break
                except Exception as e:
                    logger.info("[Snai] schedaManifestazioneSpeciale filter=%s error: %s", f_val, e)

            if working_manif_filter is not None:
                # Fetch all leagues using schedaManifestazioneSpeciale
                logger.info("[Snai] Using schedaManifestazioneSpeciale (filter=%s)", working_manif_filter)
                for lg, sk, disc, manif in competitions:
                    url = SCHEDA_MANIF_SPECIALE.format(filter=working_manif_filter, disc=disc, manif=manif)
                    try:
                        resp = await client.get(url)
                        if resp.status_code != 200:
                            logger.info("[Snai] %s: schedaManifestazioneSpeciale → %d", lg, resp.status_code)
                            continue
                        data = resp.json()
                        rows = _parse_snai_events(data, lg, sk)
                        logger.info("[Snai] %s (schedaManifestazioneSpeciale): %d rows", lg, len(rows))
                        all_results.extend(rows)
                    except Exception as exc:
                        logger.error("[Snai] %s schedaManifestazioneSpeciale error: %s", lg, exc)

            else:
                # ── Step 2b: Fallback — get event keys from avvenimentiPrematch then
                #            fetch each event via schedaAvvenimento/{key} ──────────────
                logger.info("[Snai] schedaManifestazioneSpeciale failed — fetching events via avvenimentiPrematch")
                all_events: list[dict] = []
                EVENTS_URL = f"{PFX}/palinsesto/prematch/avvenimentiPrematch"
                try:
                    resp = await client.get(EVENTS_URL)
                    resp.raise_for_status()
                    data = resp.json()
                    if isinstance(data, dict):
                        logger.info("[Snai] avvenimentiPrematch top keys: %s", list(data.keys()))
                    avm = data.get("avvenimentoFeMap") or {}
                    all_events = list(avm.values()) if isinstance(avm, dict) else []
                    logger.info("[Snai] Got %d total events", len(all_events))
                    if all_events:
                        logger.info("[Snai] First event: %s",
                                    _json.dumps(all_events[0], ensure_ascii=False)[:300])
                except Exception as exc:
                    logger.error("[Snai] avvenimentiPrematch failed: %s", exc)
                    return []

                # Filter for our leagues
                our_events: dict[int, list[dict]] = {}
                for ev in all_events:
                    if not isinstance(ev, dict):
                        continue
                    mid = ev.get("codiceManifestazione")
                    if mid and int(mid) in manif_to_league:
                        our_events.setdefault(int(mid), []).append(ev)
                for mid, evs in our_events.items():
                    lg, sk = manif_to_league[mid]
                    logger.info("[Snai] %s: %d events", lg, len(evs))

                # Fetch each event via schedaAvvenimento/{key}
                logger.info("[Snai] Fetching odds per event via schedaAvvenimento…")

                # First probe one event to confirm the endpoint works
                test_ev = next((evs[0] for evs in our_events.values() if evs), None)
                if test_ev:
                    test_key = test_ev.get("key", f"{test_ev.get('codicePalinsesto')}-{test_ev.get('codiceAvvenimento')}")
                    test_url = SCHEDA_AVVENIMENTO.format(key=test_key)
                    try:
                        r = await client.get(test_url)
                        logger.info("[Snai] schedaAvvenimento TEST %s → %d | preview=%.600s",
                                    test_url, r.status_code, r.text[:600])
                    except Exception as e:
                        logger.info("[Snai] schedaAvvenimento test error: %s", e)

                for mid, evs in our_events.items():
                    lg, sk = manif_to_league[mid]
                    league_rows: list[MatchOdds] = []
                    for ev in evs[:40]:  # cap to avoid timeout
                        ev_key = ev.get("key", f"{ev.get('codicePalinsesto')}-{ev.get('codiceAvvenimento')}")
                        url = SCHEDA_AVVENIMENTO.format(key=ev_key)
                        try:
                            resp = await client.get(url)
                            if resp.status_code != 200:
                                continue
                            odds_data = resp.json()
                            if not league_rows and isinstance(odds_data, dict):
                                logger.info("[Snai] %s first event keys: %s | preview=%.500s",
                                            lg, list(odds_data.keys())[:10],
                                            _json.dumps(odds_data, ensure_ascii=False)[:500])
                            rows = _parse_snai_events(odds_data, lg, sk)
                            league_rows.extend(rows)
                        except Exception as exc:
                            logger.debug("[Snai] %s event %s error: %s", lg, ev_key, exc)
                    logger.info("[Snai] %s: %d rows from %d events", lg, len(league_rows), len(evs))
                    all_results.extend(league_rows)

        # Deduplicate by (event_name, market)
        seen: dict[tuple[str, str], MatchOdds] = {}
        for r in all_results:
            seen[(r.event_name, r.market)] = r
        deduped = list(seen.values())
        n_events = len({r.event_name for r in deduped})
        logger.info("[Snai] Total: %d events, %d rows", n_events, len(deduped))
        return deduped

    def _find_competitions(
        self, alberatura: dict, sport_filter: str | None
    ) -> list[tuple[str, str, int, int]]:
        """
        Parse manifestazioneMap to find competitions we want.
        Returns list of (league_name, sport_key, codiceDisciplina, codiceManifestazione).
        """
        out: list[tuple[str, str, int, int]] = []
        if not isinstance(alberatura, dict):
            return out

        manif_map = alberatura.get("manifestazioneMap", {})
        if not isinstance(manif_map, dict):
            logger.warning("[Snai] manifestazioneMap missing or wrong type")
            return out

        logger.info("[Snai] manifestazioneMap has %d entries", len(manif_map))
        seen_leagues: set[str] = set()

        for key, entry in manif_map.items():
            if not isinstance(entry, dict):
                continue

            disc_id = entry.get("codiceDisciplina")
            manif_id = entry.get("codiceManifestazione")
            descrizione = str(entry.get("descrizione") or "").strip()

            if not disc_id or not manif_id or not descrizione:
                continue

            sport_key = SPORT_CODE_MAP.get(int(disc_id))
            if not sport_key:
                continue

            if sport_filter and sport_key != sport_filter:
                continue

            league_name = _match_league(descrizione, sport_key)
            if league_name and league_name not in seen_leagues:
                out.append((league_name, sport_key, int(disc_id), int(manif_id)))
                seen_leagues.add(league_name)
                logger.info("[Snai] Matched: %r → %r (disc=%s manif=%s)",
                            descrizione, league_name, disc_id, manif_id)

        return out
