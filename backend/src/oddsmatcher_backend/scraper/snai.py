"""Snai Italy pregame odds scraper.

Strategy:
  Phase 1 — httpx alberaturaPrematch → competition tree (disc/manif IDs). ✅
  Phase 2 — httpx avvenimentiPrematch → event keys per league.
  Phase 3 — httpx schedaAvvenimento/{key} per event → full odds.

API base: https://betting-snai.flutterseatech.it/api/lettura-palinsesto-sport

Response format (schedaAvvenimento):
  {
    "avvenimentoFe":    { "descrizione": "Team A - Team B", "data": "...", ... },
    "scommessaMap":     { "36211-18742-3": { "codiceScommessa": 3, "descrizione": "Esito Finale 1X2" }, ... },
    "infoAggiuntivaMap":{ "key": { "codiceScommessa": 3, "esitoList": [{"descrizione":"1","quota":185,"stato":0},...] }, ... }
  }
  Note: quota is integer × 100 (185 → 1.85). stato: 0=active, 1=suspended.
"""

import json as _json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from oddsmatcher_backend.scraper.models import MatchOdds

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

# Each entry: (our_league_name, [include_keywords], [exclude_keywords_optional])
# A competition matches when ALL include keywords are present AND NO exclude keyword is present.
LEAGUE_PATTERNS: dict[str, list[tuple]] = {
    "calcio": [
        ("Serie A",           ["ITA", "Serie A"]),
        ("Serie B",           ["ITA", "Serie B"]),
        ("Premier League",    ["ENG", "Premier"]),
        # Snai: "ESP Liga" = La Liga, "ESP Liga Adelante" = Serie B España → exclude "Adelante"
        ("La Liga",           ["ESP", "Liga"],          ["Adelante", "Segunda"]),
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
        # "WNBA" contains "NBA" → match WNBA first, then NBA with exclusion
        ("WNBA",           ["WNBA"]),
        ("NBA",            ["NBA"],                     ["WNBA"]),
        ("Serie A Basket", ["ITA", "Serie A"]),
        ("Eurolega",       ["Eurolega"]),
    ],
}

ALBERATURA_URL = f"{API_BASE}/palinsesto/prematch/alberaturaPrematch"
AVVENIMENTI_URL = f"{API_BASE}/palinsesto/prematch/avvenimentiPrematch"
SCHEDA_AVVENIMENTO = f"{API_BASE}/palinsesto/prematch/schedaAvvenimento/{{key}}"


def _match_league(descrizione: str, sport_key: str) -> str | None:
    for entry in LEAGUE_PATTERNS.get(sport_key, []):
        league_name = entry[0]
        keywords    = entry[1]
        excludes    = entry[2] if len(entry) > 2 else []
        if all(kw in descrizione for kw in keywords) and not any(ex in descrizione for ex in excludes):
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


def _parse_schedaAvvenimento(
    data: dict, league_name: str, sport_key: str
) -> list[MatchOdds]:
    """Parse schedaAvvenimento response (Sisal nested format).

    Top-level keys: avvenimentoFe, scommessaMap, infoAggiuntivaMap.
    scommessaMap key = "{codicePalinsesto}-{codiceAvvenimento}-{codiceScommessa}"
      value: { "codiceScommessa": int, "descrizione": "Esito Finale 1X2", ... }
    infoAggiuntivaMap key = "{palette}-{event}-{scommessa}-{infoAgg}"
      value: { "codiceScommessa": int, "esitoList": [{"descrizione":"1","quota":185,"stato":0},...] }
    quota is integer × 100 (e.g. 185 → 1.85), stato 0=active 1=suspended.
    """
    results: list[MatchOdds] = []
    if not isinstance(data, dict):
        return results

    # ── Event metadata ─────────────────────────────────────────────────
    avv = data.get("avvenimentoFe") or {}
    name_raw = str(avv.get("descrizione") or "").strip()
    name = re.sub(r"\s+[-–]\s+", " - ", name_raw)
    if not name:
        return results

    time_raw = avv.get("data") or avv.get("dataOra") or ""
    event_time = _parse_date(str(time_raw)) if time_raw else None
    match_url = f"{BASE_URL}/scommesse/"

    parts = name.split(" - ", 1)
    home = parts[0].strip() if len(parts) == 2 else name
    away = parts[1].strip() if len(parts) == 2 else ""

    # ── Market name lookup ─────────────────────────────────────────────
    # scommessaMap keys are "{codicePalinsesto}-{codiceAvvenimento}-{codiceScommessa}"
    # but infoAggiuntivaMap.codiceScommessa is just the integer part → key by that
    scommessa_map = data.get("scommessaMap") or {}
    scommessa_names: dict[str, str] = {}
    for s_key, s_val in scommessa_map.items():
        if isinstance(s_val, dict):
            desc = str(
                s_val.get("descrizione") or
                s_val.get("descrizioneScommessa") or ""
            ).strip()
            cod = s_val.get("codiceScommessa")
            if desc and cod is not None:
                scommessa_names[str(cod)] = desc

    # ── Iterate infoAggiuntivaMap (one entry per market × sub-market) ──
    info_agg_map = data.get("infoAggiuntivaMap") or {}
    for ia_key, ia_val in info_agg_map.items():
        if not isinstance(ia_val, dict):
            continue

        # Try field first; fall back to 3rd segment of ia_key
        # ia_key format: "{codicePalinsesto}-{codiceAvvenimento}-{codiceScommessa}-{infoAgg}"
        cod_s = str(ia_val.get("codiceScommessa") or "")
        if not cod_s:
            _kp = ia_key.split("-")
            cod_s = _kp[2] if len(_kp) >= 4 else ""

        mname = scommessa_names.get(cod_s, "")
        if not mname:
            continue

        # API returns esitoList (array), quota is integer × 100
        esiti = ia_val.get("esitoList") or []

        OUTCOME_MAP = {
            "1": "1", "CASA": "1", "HOME": "1",
            "X": "X", "PAREGGIO": "X", "DRAW": "X",
            "2": "2", "OSPITE": "2", "AWAY": "2",
        }

        # Use upper-case for case-insensitive matching
        _mname_up = mname.upper()

        # ── 1X2 (full-time result only) ───────────────────────────────
        # Match "1X2 ESITO FINALE" / "ESITO FINALE 1X2" / "TESTA A TESTA RISULTATO"
        # Exclude half-time, corners, handicap, combo (MARCATORE, SCARTO, HANDICAP, ANGOLO, CORNER)
        _is_1x2 = (
            ("ESITO FINALE" in _mname_up and "TEMPO" not in _mname_up)
            or _mname_up in ("TESTA A TESTA RISULTATO", "TESTA A TESTA")
            or (_mname_up == "ESITO INCONTRO 1X2 SENZA SCARTO")
        )
        if _is_1x2:
            odds_dict: dict[str, float] = {}
            _unmatched_lbls: list[str] = []
            for e in esiti:
                if not isinstance(e, dict):
                    continue
                lbl = str(
                    e.get("descrizione") or e.get("descrizioneEsito") or
                    e.get("esito") or ""
                ).strip().upper()
                canonical = OUTCOME_MAP.get(lbl)
                if not canonical:
                    _unmatched_lbls.append(lbl)
                    continue
                q_raw = e.get("quota")
                try:
                    q = float(q_raw) / 100 if q_raw is not None else None
                    if q and q > 1.0:
                        odds_dict[canonical] = q
                except (TypeError, ValueError):
                    pass
            if _unmatched_lbls:
                logger.info("[Snai] DIAG_1X2 %s ia_key=%s unmatched=%s got=%s",
                            name, ia_key, _unmatched_lbls, list(odds_dict.keys()))
            if len(odds_dict) >= 2:
                results.append(MatchOdds(
                    sport=sport_key, league=league_name,
                    home_team=home, away_team=away,
                    event_name=name, event_time=event_time,
                    match_url=match_url, market="1X2",
                    bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                ))

        # ── Double Chance ────────────────────────────────────────────
        # Exclude "DOPPIA CHANCE TEMPO X" (first-half DC) and similar variants
        elif ("DOPPIA CHANCE" in _mname_up or "DOUBLE CHANCE" in _mname_up) \
                and "TEMPO" not in _mname_up and "1°" not in _mname_up and "2°" not in _mname_up:
            DC_MAP = {"1X": "1X", "X2": "X2", "12": "12"}
            odds_dc: dict[str, float] = {}
            for e in esiti:
                if not isinstance(e, dict):
                    continue
                lbl = str(e.get("descrizione") or e.get("descrizioneEsito") or e.get("esito") or "").strip().upper()
                canonical = DC_MAP.get(lbl)
                if not canonical:
                    continue
                q_raw = e.get("quota")
                try:
                    q = float(q_raw) / 100 if q_raw is not None else None
                    if q and q > 1.0:
                        odds_dc[canonical] = q
                except (TypeError, ValueError):
                    pass
            if len(odds_dc) >= 2:
                results.append(MatchOdds(
                    sport=sport_key, league=league_name,
                    home_team=home, away_team=away,
                    event_name=name, event_time=event_time,
                    match_url=match_url, market="DC",
                    bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dc}],
                ))

        # ── Over/Under ───────────────────────────────────────────────
        # Snai market name: " UNDER/OVER" (no spread in name).
        # Spread is encoded in the last segment of ia_key: e.g. "...-7989-250" → 2.5
        # Also matches "UNDER/OVER X.X" variants from other leagues.
        # Exclude COMBO, QUARTO, TEMPO (half-time), SQUADRA, CORNER.
        elif ("OVER/UNDER" in _mname_up or "UNDER/OVER" in _mname_up) \
                and "COMBO" not in _mname_up \
                and "QUARTO" not in _mname_up \
                and "TEMPO" not in _mname_up \
                and "SQUADRA" not in _mname_up \
                and "CORNER" not in _mname_up:
            # Try to get spread from market name first
            sp_m = re.search(r"(\d+[.,]\d+)", mname)
            if sp_m:
                sp = sp_m.group(1).replace(",", ".")
            else:
                # Fall back to ia_key last segment: "...-7989-250" → 250 → "2.5"
                key_parts = ia_key.rsplit("-", 1)
                if len(key_parts) == 2 and key_parts[1].isdigit():
                    raw_sp = int(key_parts[1])
                    sp = f"{raw_sp / 100:.4g}"  # 250→"2.5", 350→"3.5"
                else:
                    continue
            if sp not in {"0.5", "1.5", "2.5", "3.5", "4.5", "5.5"}:
                continue
            SIDE_MAP = {"OVER": "Over", "OLTRE": "Over", "UNDER": "Under", "MENO": "Under"}
            odds_uo: dict[str, float] = {}
            for e in esiti:
                if not isinstance(e, dict):
                    continue
                lbl = str(e.get("descrizione") or e.get("descrizioneEsito") or e.get("esito") or "").strip().upper()
                side = SIDE_MAP.get(lbl)
                q_raw = e.get("quota")
                try:
                    q = float(q_raw) / 100 if q_raw is not None else None
                    if side and q and q > 1.0:
                        odds_uo[side] = q   # just "Over"/"Under"; spread is in market name
                except (TypeError, ValueError):
                    pass
            if len(odds_uo) >= 2:
                results.append(MatchOdds(
                    sport=sport_key, league=league_name,
                    home_team=home, away_team=away,
                    event_name=name, event_time=event_time,
                    match_url=match_url, market=f"Over/Under {sp}",
                    bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_uo}],
                ))

        # ── Goal / No Goal ───────────────────────────────────────────
        # Snai market name: " GOAL/NOGOAL". Exclude half-time and combo variants.
        elif "GOAL/NOGOAL" in _mname_up \
                and "TEMPO" not in _mname_up \
                and "COMBO" not in _mname_up \
                and "1T" not in _mname_up \
                and "2T" not in _mname_up:
            GG_MAP = {
                "GOAL": "Goal",   "GG": "Goal",  "SI": "Goal",
                "NOGOAL": "No Goal", "NG": "No Goal", "NO": "No Goal",
            }
            odds_gg: dict[str, float] = {}
            for e in esiti:
                if not isinstance(e, dict):
                    continue
                lbl = str(e.get("descrizione") or e.get("descrizioneEsito") or e.get("esito") or "").strip().upper()
                canonical = GG_MAP.get(lbl)
                q_raw = e.get("quota")
                try:
                    q = float(q_raw) / 100 if q_raw is not None else None
                    if canonical and q and q > 1.0:
                        odds_gg[canonical] = q
                except (TypeError, ValueError):
                    pass
            if len(odds_gg) >= 2:
                results.append(MatchOdds(
                    sport=sport_key, league=league_name,
                    home_team=home, away_team=away,
                    event_name=name, event_time=event_time,
                    match_url=match_url, market="BTTS",
                    bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_gg}],
                ))

    return results


class SnaiScraper:
    """Snai scraper — httpx only.

    Phase 1: alberaturaPrematch → competition IDs
    Phase 2: avvenimentiPrematch → event keys per league
    Phase 3: schedaAvvenimento/{key} per event → full odds in Sisal nested format
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
                competitions = self._find_competitions(alberatura_raw, sport)
                logger.info("[Snai] %d competitions found", len(competitions))
        except Exception as exc:
            logger.error("[Snai] alberaturaPrematch failed: %s", exc)
            return []

        if not competitions:
            return []

        # manif_id → (league_name, sport_key)
        manif_to_league: dict[int, tuple[str, str]] = {
            manif: (lg, sk) for lg, sk, _, manif in competitions
        }

        # ── Phase 2: Get all event keys from avvenimentiPrematch ─────────
        logger.info("[Snai] Fetching avvenimentiPrematch…")
        all_events: list[dict] = []
        try:
            async with httpx.AsyncClient(
                headers=_SNAI_HEADERS, timeout=30, follow_redirects=True, proxy=proxy_url,
            ) as client:
                resp = await client.get(AVVENIMENTI_URL)
                resp.raise_for_status()
                data = resp.json()
                avm = data.get("avvenimentoFeMap") or {}
                all_events = list(avm.values()) if isinstance(avm, dict) else []
                logger.info("[Snai] Got %d total events", len(all_events))
        except Exception as exc:
            logger.error("[Snai] avvenimentiPrematch failed: %s", exc)
            return []

        # Filter events for our leagues
        our_events: dict[int, list[dict]] = {}
        for ev in all_events:
            if not isinstance(ev, dict):
                continue
            mid = ev.get("codiceManifestazione")
            if mid and int(mid) in manif_to_league:
                our_events.setdefault(int(mid), []).append(ev)

        for mid, evs in our_events.items():
            lg, _ = manif_to_league[mid]
            logger.info("[Snai] %s: %d events", lg, len(evs))

        # ── Phase 3: Fetch odds per event via schedaAvvenimento ──────────
        logger.info("[Snai] Fetching odds per event via schedaAvvenimento…")
        all_results: list[MatchOdds] = []

        async with httpx.AsyncClient(
            headers=_SNAI_HEADERS, timeout=20, follow_redirects=True, proxy=proxy_url,
        ) as client:
            for mid, evs in our_events.items():
                lg, sk = manif_to_league[mid]
                league_rows: list[MatchOdds] = []
                league_diag_done = False

                for ev in evs[:40]:  # cap per league to avoid timeout
                    ev_key = ev.get("key") or (
                        f"{ev.get('codicePalinsesto')}-{ev.get('codiceAvvenimento')}"
                    )
                    url = SCHEDA_AVVENIMENTO.format(key=ev_key)
                    try:
                        resp = await client.get(url)
                        if resp.status_code != 200:
                            logger.debug("[Snai] %s event %s → %d", lg, ev_key, resp.status_code)
                            continue

                        odds_data = resp.json()

                        # Diagnostic: log structure of first event per league
                        if not league_diag_done and isinstance(odds_data, dict):
                            league_diag_done = True
                            s_map = odds_data.get("scommessaMap") or {}
                            ia_map = odds_data.get("infoAggiuntivaMap") or {}
                            # Log markets matching our target keywords (case-insensitive)
                            kw_markets = {}
                            for k, v in (s_map.items() if isinstance(s_map, dict) else []):
                                desc = str(v.get("descrizione") or "").upper()
                                if (("ESITO FINALE" in desc and "TEMPO" not in desc)
                                        or "TESTA A TESTA RISULTATO" in desc
                                        or ("DOPPIA CHANCE" in desc and "TEMPO" not in desc and "COMBO" not in desc)
                                        or ("OVER/UNDER" in desc and "COMBO" not in desc and "QUARTO" not in desc)
                                        or ("UNDER/OVER" in desc and "COMBO" not in desc and "TEMPO" not in desc and "SQUADRA" not in desc)
                                        or ("GOAL/NOGOAL" in desc and "TEMPO" not in desc and "COMBO" not in desc and "1T" not in desc)):
                                    kw_markets[k] = {"cod": v.get("codiceScommessa"), "desc": v.get("descrizione"), "stato": v.get("stato")}
                            ia_keys = list(ia_map.keys())[:2] if isinstance(ia_map, dict) else []
                            ia_first = {}
                            if ia_keys:
                                ia_v = ia_map[ia_keys[0]]
                                esiti = ia_v.get("esitoList") or []
                                ia_first = {"cod_s": ia_v.get("codiceScommessa"), "esitoList_len": len(esiti), "first_esito": esiti[0] if esiti else None}
                            logger.info("[Snai] DIAG %s event=%s cluster=%s kw_markets=%s ia_first=%s",
                                lg, ev_key,
                                odds_data.get("codiceClusterSelected"),
                                _json.dumps(kw_markets, ensure_ascii=False),
                                _json.dumps(ia_first, ensure_ascii=False),
                            )

                        rows = _parse_schedaAvvenimento(odds_data, lg, sk)
                        league_rows.extend(rows)
                    except Exception as exc:
                        logger.warning("[Snai] %s event %s error: %s", lg, ev_key, exc)

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
        """Parse manifestazioneMap to find competitions we want."""
        out: list[tuple[str, str, int, int]] = []
        if not isinstance(alberatura, dict):
            return out

        manif_map = alberatura.get("manifestazioneMap", {})
        if not isinstance(manif_map, dict):
            logger.warning("[Snai] manifestazioneMap missing or wrong type")
            return out

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
