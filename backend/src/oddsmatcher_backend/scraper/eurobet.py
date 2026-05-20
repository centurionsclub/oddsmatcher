"""Eurobet Italy pregame odds scraper — httpx to web.eurobet.it.

www.eurobet.it is fully protected by Cloudflare Turnstile (blocks Playwright).
web.eurobet.it is the backend subdomain that is NOT behind Cloudflare.

Approach:
  1. Probe the detail-service API on web.eurobet.it with various URL patterns.
  2. Also probe /webeb/rest/... paths (the API observed in network traffic).
  3. Once a working pattern is found, fetch all leagues.

Known working:
  - web.eurobet.it/webeb/rest → {"result": "ok", "version": "1"}
  - The sport data API path is unknown — we probe multiple candidates.
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

BOOKMAKER = "Eurobet"
BASE_URL = "https://www.eurobet.it"
WEB_BASE = "https://web.eurobet.it"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "it-IT,it;q=0.9",
    "Referer": "https://www.eurobet.it/",
    "Origin": "https://www.eurobet.it",
}

# discipline → list of (league_name, meeting_alias)
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
        ("NBA",            "nba"),
        ("Eurolega",       "euroleague"),
        ("Serie A Basket", "serie-a"),
    ],
}


def _parse_date(s: str | None) -> str | None:
    if not s:
        return None
    FMTS = [
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
        "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S",
    ]
    for fmt in FMTS:
        try:
            dt = datetime.strptime(str(s).strip()[:19], fmt)
            off = 2 if 3 <= dt.month <= 10 else 1
            return dt.replace(tzinfo=timezone(timedelta(hours=off))).astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        return str(s)


def _extract_events(data: Any) -> list[dict]:
    """Recursively search for a list of event-like dicts."""
    if isinstance(data, list) and data:
        if isinstance(data[0], dict) and any(
            k in data[0] for k in ("description", "descrizione", "eventName",
                                    "startDate", "dataOra", "betGroupList",
                                    "betGroups", "markets", "scommesse")
        ):
            return data
        for item in data:
            result = _extract_events(item)
            if result:
                return result

    if isinstance(data, dict):
        for key in ("eventList", "events", "avvenimenti", "items", "data",
                     "meetings", "competitions", "fixtures", "matches", "result"):
            val = data.get(key)
            if val is not None:
                result = _extract_events(val)
                if result:
                    return result
        for val in data.values():
            if isinstance(val, (dict, list)):
                result = _extract_events(val)
                if result:
                    return result

    return []


def _parse_events(events: list, league_name: str, discipline: str) -> list[MatchOdds]:
    """Parse a list of event dicts into MatchOdds rows."""
    results: list[MatchOdds] = []

    OUTCOME_MAP = {
        "1": "1", "Casa": "1", "Home": "1",
        "X": "X", "Pareggio": "X", "Draw": "X",
        "2": "2", "Ospite": "2", "Away": "2",
        "1X": "1X", "X2": "X2", "12": "12",
        "Over": "Over", "Under": "Under",
        "Sì": "Goal", "Si": "Goal", "Yes": "Goal", "No": "No Goal",
    }

    for ev in events:
        if not isinstance(ev, dict):
            continue

        name_raw = (ev.get("description") or ev.get("descrizione") or
                    ev.get("name") or ev.get("eventName") or
                    ev.get("eventDescription") or "")
        name = re.sub(r"\s+[-–]\s+", " - ", str(name_raw)).strip()
        if not name:
            continue

        parts = name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else name
        away = parts[1].strip() if len(parts) == 2 else ""

        time_raw = (ev.get("startDate") or ev.get("dataOra") or ev.get("startTime") or
                    ev.get("data") or ev.get("eventDate") or "")
        event_time = _parse_date(str(time_raw)) if time_raw else None

        bet_groups = (ev.get("betGroupList") or ev.get("betGroups") or
                      ev.get("markets") or ev.get("mercati") or ev.get("scommesse") or [])
        if isinstance(bet_groups, dict):
            bet_groups = list(bet_groups.values())

        for bg in bet_groups:
            if not isinstance(bg, dict):
                continue
            bg_name = str(bg.get("description") or bg.get("descrizione") or
                          bg.get("name") or bg.get("marketType") or bg.get("tipo") or "").strip()

            bets = (bg.get("betList") or bg.get("bets") or bg.get("outcomes") or
                    bg.get("esiti") or bg.get("selections") or bg.get("quote") or [])
            if isinstance(bets, dict):
                bets = list(bets.values())

            # ── 1X2 ──
            if any(kw in bg_name for kw in ("Esito Finale", "1X2", "Match Result",
                                             "Testa a Testa", "Head to Head", "Risultato",
                                             "1 X 2")):
                odds_dict: dict[str, float] = {}
                for bet in bets:
                    if not isinstance(bet, dict):
                        continue
                    lbl = str(bet.get("description") or bet.get("descrizione") or
                              bet.get("name") or bet.get("outcome") or "").strip()
                    canonical = OUTCOME_MAP.get(lbl, lbl)
                    q_raw = bet.get("quota") or bet.get("odds") or bet.get("price") or bet.get("value")
                    try:
                        q = float(str(q_raw).replace(",", ".")) if q_raw is not None else None
                        if q and q > 1.0:
                            odds_dict[canonical] = round(q, 3)
                    except (TypeError, ValueError):
                        pass
                if odds_dict:
                    results.append(MatchOdds(
                        sport=discipline, league=league_name,
                        home_team=home, away_team=away,
                        event_name=name, event_time=event_time,
                        match_url=f"{BASE_URL}/scommesse-sportive/", market="1X2",
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
                    canonical = OUTCOME_MAP.get(lbl, lbl)
                    q_raw = bet.get("quota") or bet.get("odds") or bet.get("price") or bet.get("value")
                    try:
                        q = float(str(q_raw).replace(",", ".")) if q_raw is not None else None
                        if q and q > 1.0:
                            odds_dict[canonical] = round(q, 3)
                    except (TypeError, ValueError):
                        pass
                if odds_dict:
                    results.append(MatchOdds(
                        sport=discipline, league=league_name,
                        home_team=home, away_team=away,
                        event_name=name, event_time=event_time,
                        match_url=f"{BASE_URL}/scommesse-sportive/", market="DC",
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
                    q_raw = bet.get("quota") or bet.get("odds") or bet.get("price") or bet.get("value")
                    try:
                        q = float(str(q_raw).replace(",", ".")) if q_raw is not None else None
                        if q and q > 1.0:
                            odds_dict[f"{side} {sp}"] = round(q, 3)
                    except (TypeError, ValueError):
                        pass
                if odds_dict:
                    results.append(MatchOdds(
                        sport=discipline, league=league_name,
                        home_team=home, away_team=away,
                        event_name=name, event_time=event_time,
                        match_url=f"{BASE_URL}/scommesse-sportive/", market=f"Over/Under {sp}",
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                    ))

    return results


class EurobetScraper:
    """Eurobet scraper — httpx to web.eurobet.it backend API.

    www.eurobet.it is Cloudflare-protected (Turnstile challenge blocks Playwright).
    web.eurobet.it is the backend subdomain without Cloudflare protection.
    We probe multiple API paths to discover the working endpoint.
    """

    bookmaker_name = BOOKMAKER

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

        # Build (league_name, discipline, alias) list
        meetings: list[tuple[str, str, str]] = []
        for discipline, entries in MEETINGS.items():
            if sport_filter and discipline != sport_filter:
                continue
            for league_name, alias in entries:
                meetings.append((league_name, discipline, alias))

        # ── Phase 1: Discover working API on web.eurobet.it ──────────────
        first_disc, first_alias = meetings[0][1], meetings[0][2]
        working_url_template: str | None = None  # with {disc}/{alias} placeholders

        # Probe candidates on web.eurobet.it (not Cloudflare-protected)
        # integration-bridge is confirmed as a real Spring Boot API (returns JSON 404 on wrong paths)
        get_probe_candidates: list[tuple[str, str]] = [
            # ── integration-bridge: sport-schedule paths ──
            (f"{WEB_BASE}/integration-bridge/sport-schedule/services/meeting/{first_disc}/{first_alias}?prematch=1&live=0",
             f"{WEB_BASE}/integration-bridge/sport-schedule/services/meeting/{{disc}}/{{alias}}?prematch=1&live=0"),
            (f"{WEB_BASE}/integration-bridge/sport-schedule/services/meeting/{first_disc}/{first_alias}",
             f"{WEB_BASE}/integration-bridge/sport-schedule/services/meeting/{{disc}}/{{alias}}"),
            (f"{WEB_BASE}/integration-bridge/sport-schedule/services/sport/{first_disc}?prematch=1&live=0",
             f"{WEB_BASE}/integration-bridge/sport-schedule/services/sport/{{disc}}?prematch=1&live=0"),
            # ── integration-bridge: api/v* paths ──
            (f"{WEB_BASE}/integration-bridge/api/v1/sport/{first_disc}/meeting/{first_alias}",
             f"{WEB_BASE}/integration-bridge/api/v1/sport/{{disc}}/meeting/{{alias}}"),
            (f"{WEB_BASE}/integration-bridge/api/v1/events?sport={first_disc}&meeting={first_alias}&prematch=1",
             f"{WEB_BASE}/integration-bridge/api/v1/events?sport={{disc}}&meeting={{alias}}&prematch=1"),
            (f"{WEB_BASE}/integration-bridge/api/v2/sport/{first_disc}/meeting/{first_alias}",
             f"{WEB_BASE}/integration-bridge/api/v2/sport/{{disc}}/meeting/{{alias}}"),
            (f"{WEB_BASE}/integration-bridge/api/sports/{first_disc}/meetings/{first_alias}/events",
             f"{WEB_BASE}/integration-bridge/api/sports/{{disc}}/meetings/{{alias}}/events"),
            # ── integration-bridge: simplified paths ──
            (f"{WEB_BASE}/integration-bridge/meeting/{first_disc}/{first_alias}",
             f"{WEB_BASE}/integration-bridge/meeting/{{disc}}/{{alias}}"),
            (f"{WEB_BASE}/integration-bridge/events/{first_disc}/{first_alias}",
             f"{WEB_BASE}/integration-bridge/events/{{disc}}/{{alias}}"),
            (f"{WEB_BASE}/integration-bridge/sport/{first_disc}/meeting/{first_alias}",
             f"{WEB_BASE}/integration-bridge/sport/{{disc}}/meeting/{{alias}}"),
            (f"{WEB_BASE}/integration-bridge/v1/{first_disc}/{first_alias}",
             f"{WEB_BASE}/integration-bridge/v1/{{disc}}/{{alias}}"),
            (f"{WEB_BASE}/integration-bridge/prematch/sport-schedule/{first_disc}/{first_alias}",
             f"{WEB_BASE}/integration-bridge/prematch/sport-schedule/{{disc}}/{{alias}}"),
            (f"{WEB_BASE}/integration-bridge/prematch/{first_disc}/{first_alias}",
             f"{WEB_BASE}/integration-bridge/prematch/{{disc}}/{{alias}}"),
            (f"{WEB_BASE}/integration-bridge/prematch/events?sport={first_disc}&meeting={first_alias}",
             f"{WEB_BASE}/integration-bridge/prematch/events?sport={{disc}}&meeting={{alias}}"),
            # ── webeb/rest paths ──
            (f"{WEB_BASE}/webeb/rest/api/prematch/{first_disc}/{first_alias}",
             f"{WEB_BASE}/webeb/rest/api/prematch/{{disc}}/{{alias}}"),
            (f"{WEB_BASE}/webeb/rest/prematch/{first_disc}/{first_alias}",
             f"{WEB_BASE}/webeb/rest/prematch/{{disc}}/{{alias}}"),
            (f"{WEB_BASE}/webeb/rest/sport/{first_disc}/meeting/{first_alias}",
             f"{WEB_BASE}/webeb/rest/sport/{{disc}}/meeting/{{alias}}"),
            # ── www.eurobet.it detail-service (might bypass Cloudflare for API calls) ──
            (f"{BASE_URL}/detail-service/sport-schedule/services/meeting/{first_disc}/{first_alias}?prematch=1&live=0",
             f"{BASE_URL}/detail-service/sport-schedule/services/meeting/{{disc}}/{{alias}}?prematch=1&live=0"),
        ]

        # POST probe paths for webeb/rest
        post_probe_paths: list[str] = [
            f"{WEB_BASE}/webeb/rest",
            f"{WEB_BASE}/webeb/rest/meeting",
            f"{WEB_BASE}/webeb/rest/prematch",
            f"{WEB_BASE}/webeb/rest/sport/{first_disc}/meeting/{first_alias}",
            f"{WEB_BASE}/webeb/rest/api/events",
            f"{WEB_BASE}/integration-bridge/sport-schedule/services/meeting/{first_disc}/{first_alias}",
        ]
        post_bodies: list[dict] = [
            {},
            {"sport": first_disc, "meeting": first_alias, "prematch": True},
            {"discipline": first_disc, "alias": first_alias},
            {"codiceDisciplina": first_disc, "alias": first_alias},
        ]

        async with httpx.AsyncClient(
            headers=_HEADERS, timeout=15, follow_redirects=True, proxy=proxy_url,
        ) as client:
            # First verify web.eurobet.it is accessible
            try:
                ping = await client.get(f"{WEB_BASE}/webeb/rest")
                logger.info("[Eurobet] web.eurobet.it ping → %d | %s",
                            ping.status_code, ping.text[:150])
            except Exception as e:
                logger.warning("[Eurobet] web.eurobet.it not reachable: %s", e)

            # ── GET probes ──
            for probe_url, url_template in get_probe_candidates:
                if working_url_template:
                    break
                try:
                    resp = await client.get(probe_url)
                    text = resp.text[:300]
                    logger.info("[Eurobet] GET PROBE %s → %d | %s",
                                probe_url[:110], resp.status_code, text)

                    if resp.status_code == 200:
                        if any(kw in resp.text for kw in (
                            "eventList", "events", "betGroupList", "betGroups",
                            "description", "descrizione", "startDate", "dataOra",
                            "avveniment", "incontro", "partita",
                        )):
                            logger.info("[Eurobet] ✅ Working API (GET): %s", probe_url)
                            working_url_template = url_template
                        else:
                            logger.info("[Eurobet] 200 but no event keywords | full=%.600s",
                                        resp.text)
                    elif resp.status_code not in (404, 403, 520):
                        logger.info("[Eurobet] Unexpected %d for %s | body=%.300s",
                                    resp.status_code, probe_url[:100], resp.text)
                except Exception as exc:
                    logger.info("[Eurobet] GET PROBE error %s: %s", probe_url[:80], str(exc)[:100])

            # ── POST probes (webeb/rest accepts POST) ──
            if not working_url_template:
                for post_url in post_probe_paths:
                    if working_url_template:
                        break
                    for body in post_bodies[:2]:  # limit to first 2 bodies per path
                        try:
                            resp = await client.post(post_url, json=body)
                            text = resp.text[:300]
                            logger.info("[Eurobet] POST PROBE %s body=%s → %d | %s",
                                        post_url[:90], body, resp.status_code, text)
                            if resp.status_code == 200 and any(kw in resp.text for kw in (
                                "eventList", "events", "betGroupList", "description",
                                "descrizione", "startDate", "avveniment",
                            )):
                                logger.info("[Eurobet] ✅ Working API (POST): %s", post_url)
                                # POST not usable as a template — keep probing GET
                                logger.info("[Eurobet] POST full response: %.1000s", resp.text)
                                break
                        except Exception as exc:
                            logger.info("[Eurobet] POST PROBE error %s: %s",
                                        post_url[:80], str(exc)[:100])

        if working_url_template is None:
            logger.warning("[Eurobet] No working API found — all probes failed")
            logger.info("[Eurobet] Total: 0 events, 0 rows")
            return []

        # ── Phase 2: Fetch all leagues ────────────────────────────────────
        all_results: list[MatchOdds] = []

        async with httpx.AsyncClient(
            headers=_HEADERS, timeout=20, follow_redirects=True, proxy=proxy_url,
        ) as client:
            for league_name, discipline, alias in meetings:
                url = working_url_template.format(disc=discipline, alias=alias)
                logger.info("[Eurobet] Fetching %s…", league_name)
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        logger.info("[Eurobet] %s → %d", league_name, resp.status_code)
                        continue
                    data = resp.json()
                    if isinstance(data, dict):
                        logger.info("[Eurobet] %s top keys: %s | preview=%.300s",
                                    league_name, list(data.keys())[:10],
                                    _json.dumps(data, ensure_ascii=False)[:300])
                    events = _extract_events(data)
                    if events:
                        logger.info("[Eurobet] %s: %d events | first keys=%s",
                                    league_name, len(events),
                                    list(events[0].keys())[:10] if isinstance(events[0], dict) else "?")
                        rows = _parse_events(events, league_name, discipline)
                        logger.info("[Eurobet] %s: %d rows", league_name, len(rows))
                        all_results.extend(rows)
                    else:
                        logger.info("[Eurobet] %s: no events found in response", league_name)
                except Exception as exc:
                    logger.error("[Eurobet] %s error: %s", league_name, exc)

        # Deduplicate by (event_name, market)
        seen: dict[tuple[str, str], MatchOdds] = {}
        for r in all_results:
            seen[(r.event_name, r.market)] = r
        deduped = list(seen.values())
        n_events = len({r.event_name for r in deduped})
        logger.info("[Eurobet] Total: %d events, %d rows", n_events, len(deduped))
        return deduped
