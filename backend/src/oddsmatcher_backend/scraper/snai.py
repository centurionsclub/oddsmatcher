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

        # ── Phase 2: Get all events (no filter — endpoint returns all events) ──
        # avvenimentiPrematch returns all events globally in avvenimentoFeMap.
        # The events have codiceManifestazione we use to filter for our leagues.
        # Events do NOT contain odds — odds need a separate call.
        logger.info("[Snai] Fetching all events via avvenimentiPrematch…")
        all_events: list[dict] = []
        EVENTS_URL = f"{PFX}/palinsesto/prematch/avvenimentiPrematch?codiceManifestazione=1"

        async with httpx.AsyncClient(
            headers=_SNAI_HEADERS, timeout=30, follow_redirects=True, proxy=proxy_url,
        ) as client:
            try:
                resp = await client.get(EVENTS_URL)
                resp.raise_for_status()
                data = resp.json()

                # ── CRITICAL: log ALL top-level keys to discover co-returned odds data ──
                if isinstance(data, dict):
                    logger.info("[Snai] avvenimentiPrematch ALL top-level keys: %s", list(data.keys()))
                    for k, v in list(data.items())[:25]:
                        if isinstance(v, dict):
                            first_val = next(iter(v.values()), None) if v else None
                            fkeys = list(first_val.keys())[:8] if isinstance(first_val, dict) else str(type(first_val))
                            logger.info("[Snai] top[%r] = dict(%d entries) | first-entry keys=%s",
                                        k, len(v), fkeys)
                        elif isinstance(v, list):
                            logger.info("[Snai] top[%r] = list(%d items)", k, len(v))
                        else:
                            logger.info("[Snai] top[%r] = %s: %s", k, type(v).__name__, str(v)[:100])

                avm = data.get("avvenimentoFeMap") or {}
                all_events = list(avm.values()) if isinstance(avm, dict) else []
                logger.info("[Snai] Got %d total events from avvenimentoFeMap", len(all_events))
                if all_events:
                    logger.info("[Snai] First event keys: %s | preview=%.600s",
                                list(all_events[0].keys()),
                                _json.dumps(all_events[0], ensure_ascii=False)[:600])

                # Stash full data for potential co-returned odds parsing
                self._avvenimenti_data = data  # type: ignore[attr-defined]
            except Exception as exc:
                logger.error("[Snai] events fetch failed: %s", exc)
                return []

        # Filter events for our leagues
        our_events: dict[int, list[dict]] = {}  # manif_id → events for that league
        for ev in all_events:
            if not isinstance(ev, dict):
                continue
            manif_id = ev.get("codiceManifestazione")
            if manif_id and int(manif_id) in manif_to_league:
                our_events.setdefault(int(manif_id), []).append(ev)

        for manif_id, evs in our_events.items():
            lg, sk = manif_to_league[manif_id]
            logger.info("[Snai] %s (manif=%d): %d events", lg, manif_id, len(evs))

        # ── Phase 3: Find odds endpoint using first event IDs ─────────────
        # Events have codiceAvvenimento and codicePalinsesto — use these to find odds
        working_odds_template: str | None = None
        first_ev_for_odds: dict | None = None

        # Find first event from our leagues
        for manif_id, evs in our_events.items():
            if evs:
                first_ev_for_odds = evs[0]
                break

        if first_ev_for_odds is None:
            logger.warning("[Snai] No events found for our leagues in the global event list")
            return []

        codice_palinsesto = first_ev_for_odds.get("codicePalinsesto")
        codice_avvenimento = first_ev_for_odds.get("codiceAvvenimento")
        event_id = first_ev_for_odds.get("eventId")
        logger.info("[Snai] Probing odds endpoints for event codicePalinsesto=%s codiceAvvenimento=%s eventId=%s",
                    codice_palinsesto, codice_avvenimento, event_id)

        # Derive key and discipline from event
        event_key = first_ev_for_odds.get("key", f"{codice_palinsesto}-{codice_avvenimento}")
        codice_disciplina = first_ev_for_odds.get("codiceDisciplina", 1)
        codice_manifestazione = first_ev_for_odds.get("codiceManifestazione")

        odds_probe_candidates: list[tuple[str, str]] = [
            # ── scommessePrematch (plural) ──
            (f"{PFX}/palinsesto/prematch/scommessePrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
             f"{PFX}/palinsesto/prematch/scommessePrematch?codicePalinsesto={{palinsesto}}&codiceAvvenimento={{avvenimento}}"),
            (f"{PFX}/palinsesto/prematch/scommessePrematch?codicePalinsesto={codice_palinsesto}",
             f"{PFX}/palinsesto/prematch/scommessePrematch?codicePalinsesto={{palinsesto}}"),
            (f"{PFX}/palinsesto/prematch/scommessePrematch?codiceAvvenimento={codice_avvenimento}",
             f"{PFX}/palinsesto/prematch/scommessePrematch?codiceAvvenimento={{avvenimento}}"),
            (f"{PFX}/palinsesto/prematch/scommessePrematch?eventId={event_id}",
             f"{PFX}/palinsesto/prematch/scommessePrematch?eventId={{eventId}}"),
            (f"{PFX}/palinsesto/prematch/scommessePrematch?key={event_key}",
             f"{PFX}/palinsesto/prematch/scommessePrematch?key={{key}}"),
            # with discipline code
            (f"{PFX}/palinsesto/prematch/scommessePrematch?codiceDisciplina={codice_disciplina}&codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
             f"{PFX}/palinsesto/prematch/scommessePrematch?codiceDisciplina={{disc}}&codicePalinsesto={{palinsesto}}&codiceAvvenimento={{avvenimento}}"),
            # ── avvenimentoPrematch (singular — event detail with odds?) ──
            (f"{PFX}/palinsesto/prematch/avvenimentoPrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
             f"{PFX}/palinsesto/prematch/avvenimentoPrematch?codicePalinsesto={{palinsesto}}&codiceAvvenimento={{avvenimento}}"),
            (f"{PFX}/palinsesto/prematch/avvenimentoPrematch?eventId={event_id}",
             f"{PFX}/palinsesto/prematch/avvenimentoPrematch?eventId={{eventId}}"),
            # ── Fe (frontend) variants ──
            (f"{PFX}/palinsesto/prematch/scommessaFePrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
             f"{PFX}/palinsesto/prematch/scommessaFePrematch?codicePalinsesto={{palinsesto}}&codiceAvvenimento={{avvenimento}}"),
            (f"{PFX}/palinsesto/prematch/quotaFePrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
             f"{PFX}/palinsesto/prematch/quotaFePrematch?codicePalinsesto={{palinsesto}}&codiceAvvenimento={{avvenimento}}"),
            (f"{PFX}/palinsesto/prematch/dettaglioFePrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
             f"{PFX}/palinsesto/prematch/dettaglioFePrematch?codicePalinsesto={{palinsesto}}&codiceAvvenimento={{avvenimento}}"),
            (f"{PFX}/palinsesto/prematch/avvenimentoFePrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
             f"{PFX}/palinsesto/prematch/avvenimentoFePrematch?codicePalinsesto={{palinsesto}}&codiceAvvenimento={{avvenimento}}"),
            # ── path-based with key ──
            (f"{PFX}/palinsesto/prematch/scommessePrematch/{event_key}",
             f"{PFX}/palinsesto/prematch/scommessePrematch/{{key}}"),
            (f"{PFX}/palinsesto/prematch/dettaglioPrematch/{event_key}",
             f"{PFX}/palinsesto/prematch/dettaglioPrematch/{{key}}"),
            (f"{PFX}/palinsesto/prematch/{event_key}",
             f"{PFX}/palinsesto/prematch/{{key}}"),
            # ── path-based numeric ──
            (f"{PFX}/palinsesto/prematch/scommessePrematch/{codice_palinsesto}/{codice_avvenimento}",
             f"{PFX}/palinsesto/prematch/scommessePrematch/{{palinsesto}}/{{avvenimento}}"),
            (f"{PFX}/palinsesto/prematch/dettaglioPrematch/{codice_palinsesto}/{codice_avvenimento}",
             f"{PFX}/palinsesto/prematch/dettaglioPrematch/{{palinsesto}}/{{avvenimento}}"),
            # ── lettura-scommessa-sport service ──
            (f"https://{API_HOST}/api/lettura-scommessa-sport/palinsesto/prematch/scommessePrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
             f"https://{API_HOST}/api/lettura-scommessa-sport/palinsesto/prematch/scommessePrematch?codicePalinsesto={{palinsesto}}&codiceAvvenimento={{avvenimento}}"),
            (f"https://{API_HOST}/api/lettura-scommessa-sport/palinsesto/prematch/scommessaFePrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
             f"https://{API_HOST}/api/lettura-scommessa-sport/palinsesto/prematch/scommessaFePrematch?codicePalinsesto={{palinsesto}}&codiceAvvenimento={{avvenimento}}"),
            # ── lettura-quota-sport service ──
            (f"https://{API_HOST}/api/lettura-quota-sport/palinsesto/prematch/scommessePrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
             f"https://{API_HOST}/api/lettura-quota-sport/palinsesto/prematch/scommessePrematch?codicePalinsesto={{palinsesto}}&codiceAvvenimento={{avvenimento}}"),
            (f"https://{API_HOST}/api/lettura-quota-sport/palinsesto/prematch/quotaFePrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
             f"https://{API_HOST}/api/lettura-quota-sport/palinsesto/prematch/quotaFePrematch?codicePalinsesto={{palinsesto}}&codiceAvvenimento={{avvenimento}}"),
            # ── dettaglio (without palinsesto/prematch middle path) ──
            (f"{PFX}/palinsesto/prematch/dettaglioPrematch?codiceAvvenimento={codice_avvenimento}",
             f"{PFX}/palinsesto/prematch/dettaglioPrematch?codiceAvvenimento={{avvenimento}}"),
            (f"{PFX}/palinsesto/prematch/dettaglioPrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
             f"{PFX}/palinsesto/prematch/dettaglioPrematch?codicePalinsesto={{palinsesto}}&codiceAvvenimento={{avvenimento}}"),
            # ── top-level service paths (without intermediate palinsesto/prematch) ──
            (f"https://{API_HOST}/api/lettura-palinsesto-sport/scommessePrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
             f"https://{API_HOST}/api/lettura-palinsesto-sport/scommessePrematch?codicePalinsesto={{palinsesto}}&codiceAvvenimento={{avvenimento}}"),
            # ── with codiceManifestazione ──
            (f"{PFX}/palinsesto/prematch/scommessePrematch?codiceManifestazione={codice_manifestazione}&codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
             f"{PFX}/palinsesto/prematch/scommessePrematch?codiceManifestazione={{manif}}&codicePalinsesto={{palinsesto}}&codiceAvvenimento={{avvenimento}}"),
        ]

        async with httpx.AsyncClient(
            headers=_SNAI_HEADERS, timeout=15, follow_redirects=True, proxy=proxy_url,
        ) as client:
            for probe_url, url_template in odds_probe_candidates:
                try:
                    resp = await client.get(probe_url)
                    status = resp.status_code
                    text = resp.text[:400]
                    logger.info("[Snai] ODDS PROBE %s → %d | %s",
                                probe_url[:120], status, text)
                    if status == 200:
                        if any(kw in resp.text for kw in (
                            "scommesse", "quota", "betGroup", "mercato", "market",
                            "esito", "outcome", "odds", "price", "infoTipoScommessa",
                            "quotaMap", "scommessaMap",
                        )):
                            logger.info("[Snai] ✅ Odds URL found: %s", probe_url)
                            working_odds_template = url_template
                            break
                        else:
                            # 200 but no odds keywords — log full body for analysis
                            logger.info("[Snai] 200 but no odds keywords | full=%.800s", resp.text)
                    elif status not in (404, 403):
                        # Unexpected status — might be useful
                        logger.info("[Snai] Unexpected status %d for %s", status, probe_url[:100])
                except Exception as exc:
                    logger.info("[Snai] ODDS PROBE error %s: %s", probe_url[:80], str(exc)[:100])

        # ── Phase 3b: Discovery probes (find other available endpoints) ──────
        if working_odds_template is None:
            logger.warning("[Snai] No odds endpoint found — trying discovery probes")
            async with httpx.AsyncClient(
                headers=_SNAI_HEADERS, timeout=15, follow_redirects=True, proxy=proxy_url,
            ) as client:
                discovery_urls = [
                    # Spring Boot actuator (would list ALL endpoints)
                    f"https://{API_HOST}/actuator",
                    f"https://{API_HOST}/actuator/mappings",
                    f"https://{API_HOST}/api/lettura-palinsesto-sport/actuator",
                    f"https://{API_HOST}/api/lettura-palinsesto-sport/actuator/mappings",
                    # Service roots (might return endpoint listings)
                    f"https://{API_HOST}/api/",
                    f"https://{API_HOST}/api/lettura-palinsesto-sport/",
                    f"https://{API_HOST}/api/lettura-palinsesto-sport/palinsesto/prematch/",
                    # Different service names at the API gateway level
                    f"https://{API_HOST}/api/scommessa/palinsesto/prematch/scommessePrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
                    f"https://{API_HOST}/api/quota/palinsesto/prematch/quotePrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
                    f"https://{API_HOST}/api/lettura-palinsesto-sport/scommessa/prematch/scommessePrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
                    f"https://{API_HOST}/api/lettura-palinsesto-sport/quota/prematch/quotePrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
                    # Different top-level path components
                    f"{PFX}/palinsesto/prematch/palinsestoPrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
                    f"{PFX}/palinsesto/prematch/infoAvvenimentoPrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
                    f"{PFX}/palinsesto/prematch/quotePrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
                    f"{PFX}/palinsesto/prematch/infoTipoScommessaPrematch",
                    # avvenimentiPrematch for a SPECIFIC manifestazione (Serie A = 209)
                    f"{PFX}/palinsesto/prematch/avvenimentiPrematch?codiceManifestazione=209",
                    # Different host variants
                    f"https://snai.flutterseatech.it/api/lettura-palinsesto-sport/palinsesto/prematch/scommessePrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
                    f"https://api-snai.flutterseatech.it/api/lettura-palinsesto-sport/palinsesto/prematch/scommessePrematch?codicePalinsesto={codice_palinsesto}&codiceAvvenimento={codice_avvenimento}",
                ]
                for disc_url in discovery_urls:
                    try:
                        resp = await client.get(disc_url)
                        logger.info("[Snai] DISCOVERY %s → %d | %.400s",
                                    disc_url[:120], resp.status_code, resp.text)
                        if resp.status_code == 200:
                            if any(kw in resp.text for kw in (
                                "scommesse", "quota", "betGroup", "mercato",
                                "esito", "outcome", "odds", "infoTipoScommessa",
                                "quotaMap", "scommessaMap", "mappings",
                            )):
                                logger.info("[Snai] ✅ DISCOVERY hit: %s | %.800s",
                                            disc_url, resp.text)
                    except Exception as exc:
                        logger.info("[Snai] DISCOVERY error %s: %s",
                                    disc_url[:80], str(exc)[:80])

        if working_odds_template is None:
            logger.warning("[Snai] No working odds endpoint found — logging full first event for analysis")
            if first_ev_for_odds:
                logger.info("[Snai] Full first event: %s",
                            _json.dumps(first_ev_for_odds, ensure_ascii=False)[:2000])
            return []

        # ── Phase 4: Fetch odds for all our events and parse ──────────────
        all_results: list[MatchOdds] = []

        async with httpx.AsyncClient(
            headers=_SNAI_HEADERS, timeout=20, follow_redirects=True, proxy=proxy_url,
        ) as client:
            for manif_id, evs in our_events.items():
                lg, sk = manif_to_league[manif_id]
                logger.info("[Snai] Fetching odds for %s (%d events)…", lg, len(evs))
                league_rows: list[MatchOdds] = []
                for ev in evs[:50]:  # cap at 50 events per league to avoid timeout
                    palinsesto = ev.get("codicePalinsesto")
                    avvenimento = ev.get("codiceAvvenimento")
                    ev_id = ev.get("eventId")
                    ev_key = ev.get("key", f"{palinsesto}-{avvenimento}")
                    ev_disc = ev.get("codiceDisciplina", 1)
                    ev_manif = ev.get("codiceManifestazione")
                    url = working_odds_template.format(
                        palinsesto=palinsesto, avvenimento=avvenimento, eventId=ev_id,
                        key=ev_key, disc=ev_disc, manif=ev_manif,
                    )
                    try:
                        resp = await client.get(url)
                        if resp.status_code != 200:
                            continue
                        odds_data = resp.json()
                        # Log structure of first odds response per league
                        if not league_rows and isinstance(odds_data, dict):
                            logger.info("[Snai] %s odds structure keys: %s | preview=%.400s",
                                        lg, list(odds_data.keys())[:10],
                                        _json.dumps(odds_data, ensure_ascii=False)[:400])
                        rows = _parse_snai_events(odds_data, lg, sk)
                        league_rows.extend(rows)
                    except Exception as exc:
                        logger.debug("[Snai] %s event odds error: %s", lg, exc)
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
