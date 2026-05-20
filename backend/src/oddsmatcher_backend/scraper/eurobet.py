"""Eurobet Italy pregame odds scraper — Kambi REST API (no browser needed).

Eurobet Italy is powered by Kambi. The Kambi offering API is publicly
accessible (CORS-enabled JSON) at:
  https://eu-offering-api.kambicdn.com/offering/v2018/eurobet/

No Cloudflare, no browser, no Playwright. Direct httpx calls.

Odds format: decimal (already decimal in Kambi responses).
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)

BOOKMAKER = "Eurobet"
BASE_URL = "https://www.eurobet.it"

# Kambi API base for Eurobet Italy
KAMBI_BASE = "https://eu-offering-api.kambicdn.com/offering/v2018/eurobet"
KAMBI_PARAMS = "lang=it_IT&market=IT&client_id=2&channel_id=1&ncid=1&useCombined=true"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "it-IT,it;q=0.9",
    "Origin": "https://www.eurobet.it",
    "Referer": "https://www.eurobet.it/",
}

# Sport-level Kambi paths — one request per sport gets all competitions.
# This avoids per-league rate limiting (16 requests → 3 requests).
SPORT_PATHS: list[tuple[str, str]] = [
    ("calcio",  "football"),
    ("tennis",  "tennis"),
    ("basket",  "basketball"),
]

# Competition group name → canonical league name (from Kambi group data)
# Kambi returns group names like "Italy - Serie A", "England - Premier League" etc.
LEAGUE_FROM_GROUP: dict[str, str] = {
    "Italy - Serie A": "Serie A",
    "Italy - Serie B": "Serie B",
    "Europe - Champions League": "Champions League",
    "Europe - Europa League": "Europa League",
    "Europe - Conference League": "Conference League",
    "England - Premier League": "Premier League",
    "Spain - Primera División": "La Liga",
    "Spain - Primera Division": "La Liga",
    "Germany - Bundesliga": "Bundesliga",
    "France - Ligue 1": "Ligue 1",
    "France - Roland Garros": "Roland Garros",
    "Great Britain - Wimbledon": "Wimbledon",
    "USA - US Open": "US Open",
    "Australia - Australian Open": "Australian Open",
    "USA - NBA": "NBA",
    "Europe - Euroleague": "Eurolega",
    "Italy - Serie A (Basket)": "Serie A Basket",
    "Italy - Lega Basket Serie A": "Serie A Basket",
}

# Keep the old per-league list for fallback filtering
LEAGUES: list[tuple[str, str, str]] = [
    ("Serie A",           "calcio", "football/italy/serie_a"),
    ("Serie B",           "calcio", "football/italy/serie_b"),
    ("Champions League",  "calcio", "football/europe/champions_league"),
    ("Europa League",     "calcio", "football/europe/europa_league"),
    ("Conference League", "calcio", "football/europe/conference_league"),
    ("Premier League",    "calcio", "football/england/premier_league"),
    ("La Liga",           "calcio", "football/spain/primera_division"),
    ("Bundesliga",        "calcio", "football/germany/bundesliga"),
    ("Ligue 1",           "calcio", "football/france/ligue_1"),
    ("Roland Garros",     "tennis", "tennis/france/roland_garros"),
    ("Wimbledon",         "tennis", "tennis/great_britain/wimbledon"),
    ("US Open",           "tennis", "tennis/usa/us_open"),
    ("Australian Open",   "tennis", "tennis/australia/australian_open"),
    ("NBA",               "basket", "basketball/usa/nba"),
    ("Eurolega",          "basket", "basketball/europe/euroleague"),
    ("Serie A Basket",    "basket", "basketball/italy/serie_a"),
]

OUTCOME_MAP: dict[str, str] = {
    "1": "1", "Home": "1", "Casa": "1",
    "X": "X", "Draw": "X", "Pareggio": "X",
    "2": "2", "Away": "2", "Ospite": "2",
    "1X": "1X", "X2": "X2", "12": "12",
    "Yes": "Goal", "No": "No Goal",
}

import json as _std_json


def import_json_dumps(obj: Any) -> str:
    """Safe JSON serialization helper."""
    try:
        return _std_json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)[:200]


def _parse_eurobet_date(s: str | None) -> str | None:
    """Parse Eurobet date strings to UTC ISO."""
    if not s:
        return None
    from datetime import timezone as _tz, timedelta as _td
    FMTS = [
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
        "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S",
    ]
    for fmt in FMTS:
        try:
            dt = datetime.strptime(str(s).strip()[:19], fmt)
            # Assume Europe/Rome (UTC+1 or +2 in summer)
            off = 2 if 3 <= dt.month <= 10 else 1
            return dt.replace(tzinfo=_tz(timedelta(hours=off))).astimezone(_tz.utc).isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(
            datetime.now().astimezone().tzinfo
        ).isoformat()
    except Exception:
        return str(s)


def _parse_eurobet_detail(result: Any, league_name: str, sport_key: str) -> list[MatchOdds]:
    """Parse Eurobet detail-service API response into MatchOdds.

    The result structure (discovered from live API):
    {
      "eventList": [
        {
          "eventId": ...,
          "description": "Team A - Team B",
          "startDate": "2026-05-21T18:00:00",
          "betGroupList": [
            {
              "description": "Esito Finale",
              "betList": [
                {"description": "1", "quota": "1.85"},
                {"description": "X", "quota": "3.50"},
                {"description": "2", "quota": "4.20"},
              ]
            }
          ]
        }
      ]
    }
    """
    results: list[MatchOdds] = []
    if not result:
        return results

    # Handle both dict with eventList and direct list
    events: list = []
    if isinstance(result, list):
        events = result
    elif isinstance(result, dict):
        for key in ("eventList", "events", "avvenimenti", "data", "result"):
            v = result.get(key)
            if isinstance(v, list):
                events = v
                break
        if not events:
            # Log structure for debugging
            logger.info("[Eurobet] _parse_eurobet_detail: unexpected result keys=%s preview=%s",
                        list(result.keys())[:10], import_json_dumps(result)[:300])
            return results

    if not events:
        logger.info("[Eurobet] _parse_eurobet_detail: empty event list for %s", league_name)
        return results

    # Log first event structure for diagnostic
    if events:
        logger.info("[Eurobet] First event keys: %s, preview: %s",
                    list(events[0].keys())[:15] if isinstance(events[0], dict) else "?",
                    import_json_dumps(events[0])[:400])

    OUTCOME_MAP_LOCAL = {
        "1": "1", "Casa": "1", "Home": "1",
        "X": "X", "Pareggio": "X", "Draw": "X",
        "2": "2", "Ospite": "2", "Away": "2",
        "1X": "1X", "X2": "X2", "12": "12",
        "Over": "Over", "Under": "Under",
        "Sì": "Goal", "Si": "Goal", "Yes": "Goal",
        "No": "No Goal",
    }

    match_url = f"{BASE_URL}/it/scommesse/"

    for ev in events:
        if not isinstance(ev, dict):
            continue

        # Event name
        name_raw = (ev.get("description") or ev.get("descrizione") or
                    ev.get("name") or ev.get("eventName") or "")
        name = re.sub(r"\s+[-–vs\.]+\s+", " - ", str(name_raw)).strip()
        if not name:
            continue

        parts = name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else name
        away = parts[1].strip() if len(parts) == 2 else ""

        # Event time
        time_raw = (ev.get("startDate") or ev.get("dataOra") or ev.get("startTime") or
                    ev.get("data") or "")
        event_time = _parse_eurobet_date(str(time_raw)) if time_raw else None

        # Bet groups
        bet_groups = (ev.get("betGroupList") or ev.get("betGroups") or
                      ev.get("markets") or ev.get("mercati") or
                      ev.get("scommesse") or [])
        if isinstance(bet_groups, dict):
            bet_groups = list(bet_groups.values())

        for bg in bet_groups:
            if not isinstance(bg, dict):
                continue

            bg_name = str(bg.get("description") or bg.get("descrizione") or
                          bg.get("name") or bg.get("marketType") or "").strip()

            bets = (bg.get("betList") or bg.get("bets") or bg.get("outcomes") or
                    bg.get("esiti") or bg.get("quote") or [])
            if isinstance(bets, dict):
                bets = list(bets.values())

            # ── 1X2 ──
            if any(kw in bg_name for kw in ("Esito Finale", "1X2", "Risultato", "Match Result",
                                             "Testa a Testa", "Head to Head")):
                odds_dict: dict[str, float] = {}
                for bet in bets:
                    if not isinstance(bet, dict):
                        continue
                    lbl = str(bet.get("description") or bet.get("descrizione") or
                              bet.get("name") or bet.get("label") or "").strip()
                    canonical = OUTCOME_MAP_LOCAL.get(lbl, lbl)
                    q_raw = bet.get("quota") or bet.get("odds") or bet.get("price")
                    try:
                        q = float(str(q_raw).replace(",", ".")) if q_raw is not None else None
                        if q and q > 1.0:
                            odds_dict[canonical] = round(q, 3)
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

            # ── Double Chance ──
            elif any(kw in bg_name for kw in ("Doppia Chance", "Double Chance")):
                odds_dict = {}
                for bet in bets:
                    if not isinstance(bet, dict):
                        continue
                    lbl = str(bet.get("description") or bet.get("descrizione") or
                              bet.get("name") or "").strip()
                    canonical = OUTCOME_MAP_LOCAL.get(lbl, lbl)
                    q_raw = bet.get("quota") or bet.get("odds") or bet.get("price")
                    try:
                        q = float(str(q_raw).replace(",", ".")) if q_raw is not None else None
                        if q and q > 1.0:
                            odds_dict[canonical] = round(q, 3)
                    except (TypeError, ValueError):
                        pass
                if odds_dict:
                    results.append(MatchOdds(
                        sport=sport_key, league=league_name,
                        home_team=home, away_team=away,
                        event_name=name, event_time=event_time,
                        match_url=match_url, market="DC",
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                    ))

            # ── Over/Under ──
            elif any(kw in bg_name for kw in ("Over/Under", "O/U", "Totale Gol", "Over Under")):
                sp_m = re.search(r"(\d+[.,]\d+)", bg_name)
                if not sp_m:
                    continue
                sp = sp_m.group(1).replace(",", ".")
                if sp not in {"1.5", "2.5", "3.5"}:
                    continue
                odds_dict = {}
                for bet in bets:
                    if not isinstance(bet, dict):
                        continue
                    lbl = str(bet.get("description") or bet.get("descrizione") or
                              bet.get("name") or "").strip()
                    side = "Over" if "over" in lbl.lower() else ("Under" if "under" in lbl.lower() else None)
                    if not side:
                        continue
                    q_raw = bet.get("quota") or bet.get("odds") or bet.get("price")
                    try:
                        q = float(str(q_raw).replace(",", ".")) if q_raw is not None else None
                        if q and q > 1.0:
                            odds_dict[f"{side} {sp}"] = round(q, 3)
                    except (TypeError, ValueError):
                        pass
                if odds_dict:
                    results.append(MatchOdds(
                        sport=sport_key, league=league_name,
                        home_team=home, away_team=away,
                        event_name=name, event_time=event_time,
                        match_url=match_url, market=f"Over/Under {sp}",
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                    ))

    return results


def _parse_date(ts_ms: int | None) -> str | None:
    """Convert Kambi millisecond timestamp to UTC ISO string."""
    if not ts_ms:
        return None
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        return dt.isoformat()
    except Exception:
        return None


def _parse_kambi_events_sport(data: Any, sport_key: str, wanted_leagues: set[str]) -> list[MatchOdds]:
    """Parse a sport-level Kambi listView response (contains multiple competitions).

    The sport-level response groups events by path — the event's path contains
    country and competition info. We use the group name from the event to assign
    a league name.
    """
    results: list[MatchOdds] = []
    if not isinstance(data, dict):
        return results

    events = data.get("events") or []
    for ev_wrapper in events:
        if not isinstance(ev_wrapper, dict):
            continue

        event = ev_wrapper.get("event") or ev_wrapper
        if not isinstance(event, dict):
            continue

        # Determine league from event group/path
        group = event.get("group") or ""
        path = event.get("path") or []
        # Try to find league name from LEAGUE_FROM_GROUP
        league_name: str | None = None

        # Try direct group match
        league_name = LEAGUE_FROM_GROUP.get(group)

        # Try from path elements
        if not league_name and isinstance(path, list):
            # path is usually [{id, name, termKey}, ...] for country, competition
            if len(path) >= 2:
                country = path[0].get("name", "")
                comp = path[-1].get("name", "")
                combo = f"{country} - {comp}"
                league_name = LEAGUE_FROM_GROUP.get(combo)
            if not league_name and path:
                # Try competition name alone
                for seg in path:
                    seg_name = seg.get("name", "")
                    league_name = LEAGUE_FROM_GROUP.get(seg_name)
                    if league_name:
                        break

        # If still not found, try fuzzy matching against wanted_leagues
        if not league_name:
            group_lower = group.lower()
            for lg in wanted_leagues:
                if lg.lower() in group_lower or group_lower in lg.lower():
                    league_name = lg
                    break

        if not league_name:
            continue  # Not a league we track

        # Parse the event using the existing per-event parser
        rows = _parse_kambi_events({"events": [ev_wrapper]}, league_name, sport_key)
        results.extend(rows)

    return results


def _parse_kambi_events(data: Any, league_name: str, sport_key: str) -> list[MatchOdds]:
    """Parse Kambi listView response into MatchOdds."""
    results: list[MatchOdds] = []
    if not isinstance(data, dict):
        return results

    events = data.get("events") or []

    for ev_wrapper in events:
        if not isinstance(ev_wrapper, dict):
            continue

        event = ev_wrapper.get("event") or ev_wrapper
        if not isinstance(event, dict):
            continue

        name = event.get("name") or event.get("englishName") or ""
        name = re.sub(r"\s+vs\.?\s+", " - ", name, flags=re.IGNORECASE).strip()
        if not name:
            continue

        ts = event.get("start")
        event_time = _parse_date(ts)
        match_url = f"{BASE_URL}/it/scommesse/"
        parts = name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else name
        away = parts[1].strip() if len(parts) == 2 else ""

        # betOffers come directly in the event wrapper from Kambi listView
        bet_offers = ev_wrapper.get("betOffers") or []

        for bo in bet_offers:
            if not isinstance(bo, dict):
                continue

            criterion = bo.get("criterion") or {}
            label = criterion.get("label") or bo.get("betOfferType", {}).get("name") or ""
            label = label.strip()

            outcomes = bo.get("outcomes") or []

            # ── 1X2 ──
            if label in ("Match", "Match Result", "1X2", "Esito Finale",
                         "Head to Head", "Testa a Testa"):
                odds_dict: dict[str, float] = {}
                for out in outcomes:
                    olabel = out.get("label") or out.get("type") or ""
                    odds_key = OUTCOME_MAP.get(olabel, olabel)
                    odds_val = out.get("odds")
                    if odds_val:
                        try:
                            f = float(odds_val) / 1000.0  # Kambi stores odds * 1000
                            if f > 1.0:
                                odds_dict[odds_key] = round(f, 3)
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

            # ── Double Chance ──
            elif "Double Chance" in label or "Doppia Chance" in label:
                odds_dict = {}
                for out in outcomes:
                    olabel = out.get("label") or ""
                    key = OUTCOME_MAP.get(olabel, olabel)
                    odds_val = out.get("odds")
                    if odds_val:
                        try:
                            f = float(odds_val) / 1000.0
                            if f > 1.0:
                                odds_dict[key] = round(f, 3)
                        except (TypeError, ValueError):
                            pass
                if odds_dict:
                    results.append(MatchOdds(
                        sport=sport_key, league=league_name,
                        home_team=home, away_team=away,
                        event_name=name, event_time=event_time,
                        match_url=match_url, market="DC",
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                    ))

            # ── Over/Under ──
            elif any(kw in label for kw in ("Over/Under", "Goals", "Total")):
                sp_m = re.search(r"(\d+[.,]\d+)", label)
                if not sp_m:
                    continue
                sp = sp_m.group(1).replace(",", ".")
                if sp not in {"1.5", "2.5", "3.5"}:
                    continue
                odds_dict = {}
                for out in outcomes:
                    olabel = out.get("label") or ""
                    side = "Over" if "over" in olabel.lower() else ("Under" if "under" in olabel.lower() else None)
                    if not side:
                        continue
                    odds_val = out.get("odds")
                    if odds_val:
                        try:
                            f = float(odds_val) / 1000.0
                            if f > 1.0:
                                odds_dict[f"{side} {sp}"] = round(f, 3)
                        except (TypeError, ValueError):
                            pass
                if odds_dict:
                    results.append(MatchOdds(
                        sport=sport_key, league=league_name,
                        home_team=home, away_team=away,
                        event_name=name, event_time=event_time,
                        match_url=match_url, market=f"Over/Under {sp}",
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                    ))

    return results


class EurobetScraper:
    """Eurobet scraper — direct httpx to Eurobet's internal REST API.

    Eurobet's web app (Next.js) does NOT call Kambi CDN client-side for the
    main events listing. Instead it uses:
      - prematch-menu-service → competition discovery / foreground menus
      - detail-service        → events + odds per competition

    Both endpoints live on www.eurobet.it, no rate limiting.
    No browser/Playwright needed.
    """

    bookmaker_name = BOOKMAKER

    # Eurobet internal REST API base paths
    DETAIL_BASE = "https://www.eurobet.it/detail-service/sport-schedule/services"
    MENU_BASE   = "https://www.eurobet.it/prematch-menu-service/api/v2/sport-schedule/services"

    # discipline → list of (league_name, meeting_alias)
    # meeting_alias is the slug used in detail-service URLs
    MEETINGS: dict[str, list[tuple[str, str]]] = {
        "calcio": [
            ("Champions League",  "champions-league"),
            ("Europa League",     "europa-league"),
            ("Conference League", "conference-league"),
            ("Premier League",    "premier-league"),
            ("La Liga",           "prima-divisione"),
            ("Bundesliga",        "bundesliga"),
            ("Ligue 1",           "ligue-1"),
            ("Serie A",           "serie-a"),
            ("Serie B",           "serie-b"),
        ],
        "tennis": [
            ("Roland Garros",   "roland-garros"),
            ("Wimbledon",       "wimbledon"),
            ("US Open",         "us-open"),
            ("Australian Open", "australian-open"),
        ],
        "basket": [
            ("NBA",           "nba"),
            ("Eurolega",      "euroleague"),
            ("Serie A Basket","serie-a"),
        ],
    }

    async def scrape_all(self) -> list[MatchOdds]:
        return await self._run(sport_filter=None)

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        return await self._run(sport_filter=sport)

    async def _run(self, sport_filter: str | None) -> list[MatchOdds]:
        proxy_url = os.environ.get("PROXY_URL")
        if proxy_url:
            import urllib.parse as _up
            p = _up.urlparse(proxy_url)
            logger.info("[Eurobet] Using proxy: %s:%s", p.hostname, p.port)

        all_results: list[MatchOdds] = []

        async with httpx.AsyncClient(
            headers=_HEADERS,
            timeout=20,
            follow_redirects=True,
            proxy=proxy_url,
        ) as client:
            for discipline, meetings in self.MEETINGS.items():
                if sport_filter and discipline != sport_filter:
                    continue

                for league_name, meeting_alias in meetings:
                    url = (
                        f"{self.DETAIL_BASE}/meeting/{discipline}/{meeting_alias}"
                        f"?prematch=1&live=0"
                    )
                    logger.info("[Eurobet] Fetching %s (%s/%s)…", league_name, discipline, meeting_alias)
                    try:
                        resp = await client.get(url)
                        logger.info("[Eurobet] %s → %d", meeting_alias, resp.status_code)
                        if resp.status_code != 200:
                            continue
                        data = resp.json()
                    except Exception as exc:
                        logger.info("[Eurobet] %s request error: %s", meeting_alias, exc)
                        continue

                    code = data.get("code") if isinstance(data, dict) else None
                    if code != 1:
                        desc = data.get("description", "") if isinstance(data, dict) else ""
                        logger.info("[Eurobet] %s: code=%s desc=%s", meeting_alias, code, desc)
                        continue

                    result = data.get("result")
                    preview = import_json_dumps(result)[:400]
                    logger.info("[Eurobet] %s result preview: %s", meeting_alias, preview)

                    rows = _parse_eurobet_detail(result, league_name, discipline)
                    logger.info("[Eurobet] %s: %d rows", league_name, len(rows))
                    all_results.extend(rows)

        # Deduplicate by (event_name, market)
        seen: dict[tuple[str, str], MatchOdds] = {}
        for r in all_results:
            seen[(r.event_name, r.market)] = r
        deduped = list(seen.values())
        n_events = len({r.event_name for r in deduped})
        logger.info("[Eurobet] Total: %d events, %d rows", n_events, len(deduped))
        return deduped
