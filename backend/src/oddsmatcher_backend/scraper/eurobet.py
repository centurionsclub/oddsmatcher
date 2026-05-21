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

from oddsmatcher_backend.scraper.models import MatchOdds

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
# Aliases are the CORRECT Eurobet aliasUrl values (from prematch-menu-service).
# These are used to navigate to the page and intercept the detail-service call.
MEETINGS: dict[str, list[tuple[str, str]]] = {
    "calcio": [
        ("Champions League",  "eu-champions-league"),
        ("Europa League",     "eu-europa-league"),
        ("Conference League", "eu-conference-league"),
        ("Premier League",    "ing-premier-league"),
        ("La Liga",           "es-liga"),
        ("Bundesliga",        "ger-bundesliga"),
        ("Ligue 1",           "fr-ligue-1"),
        ("Serie A",           "it-serie-a"),
        ("Serie B",           "ita-serie-b"),
    ],
    "tennis": [
        ("Roland Garros",   "fr-roland-garros-m"),
        ("Wimbledon",       "ing-wimbledon"),
        ("US Open",         "us-open-m"),
        ("Australian Open", "au-australian-open-m"),
    ],
    "basket": [
        ("NBA",            "us-nba"),
        ("Eurolega",       "eu-eurolega"),
        ("Serie A Basket", "it-serie-a"),
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
    """Parse Eurobet detail-service event list into MatchOdds rows.

    Eurobet structure:
      event.eventInfo.eventDescription  → match name
      event.eventInfo.eventData         → Unix ms timestamp
      event.betGroupList[i]             → bet group (e.g. "SCOMMESSE TOP")
        .oddGroupList[j]                → market (e.g. oddGroupDescription="1X2")
          .oddList[k]                   → individual odd
            .oddDescription             → outcome label ("1", "X", "2", "Over", …)
            .oddValue                   → decimal odds (float)
    """
    from datetime import timezone as _tz

    results: list[MatchOdds] = []

    OUTCOME_MAP = {
        "1": "1", "Casa": "1", "Home": "1",
        "X": "X", "Pareggio": "X", "Draw": "X",
        "2": "2", "Ospite": "2", "Away": "2",
        "1X": "1X", "X2": "X2", "12": "12",
        "Over": "Over", "Under": "Under",
        "Sì": "Goal", "Si": "Goal", "Yes": "Goal", "No": "No Goal",
    }

    logged_first = False

    for ev in events:
        if not isinstance(ev, dict):
            continue

        ei = ev.get("eventInfo") or {}
        name_raw = (ev.get("description") or ev.get("descrizione") or
                    ev.get("name") or ev.get("eventName") or
                    ev.get("eventDescription") or
                    ei.get("eventDescription") or ei.get("description") or "")
        name = re.sub(r"\s+[-–]\s+", " - ", str(name_raw)).strip()
        if not name:
            continue

        parts = name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else name
        away = parts[1].strip() if len(parts) == 2 else ""

        time_raw = (ev.get("startDate") or ev.get("dataOra") or ev.get("startTime") or
                    ev.get("data") or ev.get("eventDate") or ei.get("eventData") or "")
        if isinstance(time_raw, (int, float)) and time_raw > 1e9:
            ts = time_raw / 1000 if time_raw > 1e12 else time_raw
            event_time = datetime.fromtimestamp(ts, tz=_tz.utc).isoformat()
        else:
            event_time = _parse_date(str(time_raw)) if time_raw else None

        bet_groups = ev.get("betGroupList") or []
        if isinstance(bet_groups, dict):
            bet_groups = list(bet_groups.values())

        for bg in bet_groups:
            if not isinstance(bg, dict):
                continue
            # Eurobet: markets are in oddGroupList inside each betGroup
            odd_groups = bg.get("oddGroupList") or []
            if isinstance(odd_groups, dict):
                odd_groups = list(odd_groups.values())

            for og in odd_groups:
                if not isinstance(og, dict):
                    continue
                og_name = str(og.get("oddGroupDescription") or og.get("description") or
                               og.get("name") or "").strip()

                # Odds items: try oddList first, then fallback names
                odds_items = (og.get("oddList") or og.get("betList") or
                              og.get("bets") or og.get("outcomes") or [])
                if isinstance(odds_items, dict):
                    odds_items = list(odds_items.values())

                # Log first oddGroup to discover full structure
                if not logged_first and odds_items:
                    logger.info("[Eurobet] %s oddGroup sample: name=%r odd0_keys=%s odd0=%.300s",
                                league_name, og_name,
                                list(odds_items[0].keys())[:10] if isinstance(odds_items[0], dict) else "?",
                                _json.dumps(odds_items[0], ensure_ascii=False)[:300])
                    logged_first = True

                def _get_q(odd: dict) -> float | None:
                    q_raw = (odd.get("oddValue") or odd.get("quota") or odd.get("value") or
                             odd.get("price") or odd.get("odds"))
                    if q_raw is None:
                        return None
                    try:
                        q = float(str(q_raw).replace(",", "."))
                        # Eurobet stores oddValue as integer ×100 (e.g. 225 = 2.25)
                        if q > 100:
                            q = q / 100
                        return round(q, 3) if q > 1.0 else None
                    except (TypeError, ValueError):
                        return None

                def _get_lbl(odd: dict) -> str:
                    return str(odd.get("oddDescription") or odd.get("description") or
                               odd.get("name") or odd.get("outcome") or "").strip()

                # ── 1X2 / Head-to-Head ──
                if og_name in ("1X2", "1 X 2", "T/T") or any(kw in og_name for kw in (
                        "Esito Finale", "Match Result", "Testa a Testa", "Head to Head",
                        "T/T (", "RISULTATO FINALE")):
                    odds_dict: dict[str, float] = {}
                    for odd in odds_items:
                        if not isinstance(odd, dict):
                            continue
                        lbl = _get_lbl(odd)
                        q = _get_q(odd)
                        if q:
                            odds_dict[OUTCOME_MAP.get(lbl, lbl)] = q
                    if odds_dict:
                        results.append(MatchOdds(
                            sport=discipline, league=league_name,
                            home_team=home, away_team=away,
                            event_name=name, event_time=event_time,
                            match_url=f"{BASE_URL}/scommesse-sportive/", market="1X2",
                            bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                        ))

                # ── Double Chance ──
                elif any(kw in og_name for kw in ("Doppia Chance", "Double Chance")):
                    odds_dict = {}
                    for odd in odds_items:
                        if not isinstance(odd, dict):
                            continue
                        lbl = _get_lbl(odd)
                        q = _get_q(odd)
                        if q:
                            odds_dict[OUTCOME_MAP.get(lbl, lbl)] = q
                    if odds_dict:
                        results.append(MatchOdds(
                            sport=discipline, league=league_name,
                            home_team=home, away_team=away,
                            event_name=name, event_time=event_time,
                            match_url=f"{BASE_URL}/scommesse-sportive/", market="DC",
                            bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                        ))

                # ── Over/Under ──
                elif any(kw in og_name for kw in ("Over/Under", "O/U", "Totale Gol", "Over Under",
                                                    "Gol: O/U", "GOL O/U", "TOTALE GOL")):
                    sp_m = re.search(r"(\d+[.,]\d+)", og_name)
                    if not sp_m:
                        continue
                    sp = sp_m.group(1).replace(",", ".")
                    if sp not in {"0.5", "1.5", "2.5", "3.5", "4.5", "5.5"}:
                        continue
                    odds_dict = {}
                    for odd in odds_items:
                        if not isinstance(odd, dict):
                            continue
                        lbl = _get_lbl(odd)
                        side = "Over" if "over" in lbl.lower() else ("Under" if "under" in lbl.lower() else None)
                        if not side:
                            continue
                        q = _get_q(odd)
                        if q:
                            odds_dict[side] = q   # "Over"/"Under" — spread is in market name
                    if odds_dict:
                        results.append(MatchOdds(
                            sport=discipline, league=league_name,
                            home_team=home, away_team=away,
                            event_name=name, event_time=event_time,
                            match_url=f"{BASE_URL}/scommesse-sportive/", market=f"Over/Under {sp}",
                            bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                        ))

                # ── Goal / No Goal (BTTS) ──
                elif any(kw in og_name for kw in ("Goal/No Goal", "Goal No Goal",
                                                    "GOAL/NO GOAL", "GG/NG",
                                                    "Entrambe le squadre segnano",
                                                    "ENTRAMBE LE SQUADRE")):
                    odds_dict = {}
                    for odd in odds_items:
                        if not isinstance(odd, dict):
                            continue
                        lbl = _get_lbl(odd)
                        q = _get_q(odd)
                        if not q:
                            continue
                        lbl_up = lbl.upper()
                        if lbl_up in ("SI", "SÌ", "YES", "GOAL", "GG"):
                            odds_dict["Goal"] = q
                        elif lbl_up in ("NO", "NO GOAL", "NG"):
                            odds_dict["No Goal"] = q
                    if len(odds_dict) >= 2:
                        results.append(MatchOdds(
                            sport=discipline, league=league_name,
                            home_team=home, away_team=away,
                            event_name=name, event_time=event_time,
                            match_url=f"{BASE_URL}/scommesse-sportive/", market="BTTS",
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
        # NOTE: integration-bridge Swagger confirmed it only has Opta/Perform/IMG (stats), NOT odds.
        # detail-service on www.eurobet.it is Cloudflare-protected (403).
        # Priority: try web.eurobet.it/detail-service (same service, CF-free backend).
        get_probe_candidates: list[tuple[str, str]] = [
            # ── web.eurobet.it detail-service (CF-free backend — same service as www.eurobet.it) ──
            (f"{WEB_BASE}/detail-service/sport-schedule/services/meeting/{first_disc}/{first_alias}?prematch=1&live=0",
             f"{WEB_BASE}/detail-service/sport-schedule/services/meeting/{{disc}}/{{alias}}?prematch=1&live=0"),
            (f"{WEB_BASE}/detail-service/sport-schedule/services/meeting/{first_disc}/{first_alias}",
             f"{WEB_BASE}/detail-service/sport-schedule/services/meeting/{{disc}}/{{alias}}"),
            (f"{WEB_BASE}/detail-service/sport-schedule/services/sport/{first_disc}?prematch=1&live=0",
             f"{WEB_BASE}/detail-service/sport-schedule/services/sport/{{disc}}?prematch=1&live=0"),
            # ── Alternative service names on web.eurobet.it ──
            (f"{WEB_BASE}/sport-schedule/services/meeting/{first_disc}/{first_alias}?prematch=1&live=0",
             f"{WEB_BASE}/sport-schedule/services/meeting/{{disc}}/{{alias}}?prematch=1&live=0"),
            (f"{WEB_BASE}/sport-schedule/services/meeting/{first_disc}/{first_alias}",
             f"{WEB_BASE}/sport-schedule/services/meeting/{{disc}}/{{alias}}"),
            (f"{WEB_BASE}/api/sport-schedule/services/meeting/{first_disc}/{first_alias}?prematch=1&live=0",
             f"{WEB_BASE}/api/sport-schedule/services/meeting/{{disc}}/{{alias}}?prematch=1&live=0"),
            (f"{WEB_BASE}/api/detail-service/sport-schedule/services/meeting/{first_disc}/{first_alias}?prematch=1&live=0",
             f"{WEB_BASE}/api/detail-service/sport-schedule/services/meeting/{{disc}}/{{alias}}?prematch=1&live=0"),
            # ── webeb/rest paths ──
            (f"{WEB_BASE}/webeb/rest/api/prematch/{first_disc}/{first_alias}",
             f"{WEB_BASE}/webeb/rest/api/prematch/{{disc}}/{{alias}}"),
            (f"{WEB_BASE}/webeb/rest/prematch/{first_disc}/{first_alias}",
             f"{WEB_BASE}/webeb/rest/prematch/{{disc}}/{{alias}}"),
            (f"{WEB_BASE}/webeb/rest/sport/{first_disc}/meeting/{first_alias}",
             f"{WEB_BASE}/webeb/rest/sport/{{disc}}/meeting/{{alias}}"),
            # ── www.eurobet.it detail-service (Cloudflare, might bypass for API) ──
            (f"{BASE_URL}/detail-service/sport-schedule/services/meeting/{first_disc}/{first_alias}?prematch=1&live=0",
             f"{BASE_URL}/detail-service/sport-schedule/services/meeting/{{disc}}/{{alias}}?prematch=1&live=0"),
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

            # webeb/rest action probes: 60+ names tried across multiple runs, all "invalid action"
            # Skipping — webeb/rest is likely a bet-booking API, not the odds feed.

            # ── Probe other services on web.eurobet.it ──────────────────────────────
            if not working_url_template:
                other_services = [
                    f"{WEB_BASE}/odds-service/sport-schedule/services/meeting/{first_disc}/{first_alias}?prematch=1&live=0",
                    f"{WEB_BASE}/betting-service/sport-schedule/services/meeting/{first_disc}/{first_alias}?prematch=1&live=0",
                    f"{WEB_BASE}/schedule-service/sport-schedule/services/meeting/{first_disc}/{first_alias}?prematch=1&live=0",
                    f"{WEB_BASE}/bet-service/sport-schedule/services/meeting/{first_disc}/{first_alias}?prematch=1&live=0",
                ]
                for svc_url in other_services:
                    try:
                        r = await client.get(svc_url)
                        logger.info("[Eurobet] SVC %s → %d | %.300s",
                                    svc_url[:100], r.status_code, r.text)
                        if r.status_code == 200 and any(kw in r.text for kw in
                                                        ("description", "betGroupList", "events", "avveniment")):
                            logger.info("[Eurobet] ✅ SVC works: %s", svc_url)
                            working_url_template = svc_url.replace(
                                f"/{first_disc}/{first_alias}",
                                "/{disc}/{alias}")
                            break
                    except Exception as e:
                        logger.info("[Eurobet] SVC %s error: %s", svc_url[:80], str(e)[:60])

            # ── Fetch www.eurobet.it HTML page for __NEXT_DATA__ (ISR = odds embedded) ──
            if not working_url_template:
                import re as _re
                # Eurobet is Next.js ISR — betting data is embedded in page HTML as __NEXT_DATA__
                html_url_candidates = [
                    (f"https://www.eurobet.it/it/scommesse/calcio/champions-league",
                     f"https://www.eurobet.it/it/scommesse/{{disc}}/{{alias}}"),
                    (f"https://www.eurobet.it/scommesse/calcio/champions-league",
                     f"https://www.eurobet.it/scommesse/{{disc}}/{{alias}}"),
                    (f"https://www.eurobet.it/it/scommesse-sportive/calcio/champions-league",
                     f"https://www.eurobet.it/it/scommesse-sportive/{{disc}}/{{alias}}"),
                ]
                for html_url, html_template in html_url_candidates:
                    try:
                        r = await client.get(html_url, follow_redirects=True)
                        logger.info("[Eurobet] HTML %s → %d | type=%s | len=%d",
                                    html_url, r.status_code,
                                    r.headers.get("content-type", "?"), len(r.text))
                        if r.status_code == 200:
                            nd = _re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                                            r.text, _re.DOTALL)
                            if nd:
                                logger.info("[Eurobet] NEXT_DATA found len=%d | preview=%.3000s",
                                            len(nd.group(1)), nd.group(1))
                                # Try to find events in NEXT_DATA
                                nd_text = nd.group(1)
                                if any(kw in nd_text for kw in ("betGroupList", "betGroups",
                                                                  "description", "startDate")):
                                    logger.info("[Eurobet] ✅ NEXT_DATA has event data!")
                                    working_url_template = "HTML:" + html_template
                                    break
                            else:
                                # Look for API patterns in HTML
                                api_hits = _re.findall(
                                    r'["\']([^"\']*detail-service[^"\']*)["\']', r.text)
                                logger.info("[Eurobet] detail-service URLs in HTML: %s", api_hits[:10])
                                api_hits2 = _re.findall(
                                    r'["\']([^"\']*web\.eurobet[^"\']*)["\']', r.text)
                                logger.info("[Eurobet] web.eurobet URLs in HTML: %s", api_hits2[:10])
                    except Exception as e:
                        logger.info("[Eurobet] HTML %s error: %s", html_url, str(e)[:80])

        # ── Phase 2: Playwright — intercept /_next/data/ + detail-service ──
        # www.eurobet.it is Next.js ISR with isFallback:true — the initial HTML has
        # empty pageProps. The Next.js client auto-fetches /_next/data/{buildId}/{path}.json
        # after page mount to populate actual betting data.
        # Strategy: intercept all responses while page loads with networkidle; capture
        # /_next/data/ JSON (contains pageProps with events) or detail-service API calls.
        if working_url_template is None:
            logger.info("[Eurobet] httpx probes failed — trying Playwright + response interception")
            try:
                import asyncio
                from playwright.async_api import async_playwright
                try:
                    from playwright_stealth import stealth_async as _stealth_async
                    _STEALTH = True
                except ImportError:
                    _STEALTH = False

                proxy_cfg = None
                if proxy_url:
                    import urllib.parse as _up
                    p = _up.urlparse(proxy_url)
                    proxy_cfg = {
                        "server": f"{p.scheme}://{p.hostname}:{p.port}",
                        "username": p.username or "",
                        "password": p.password or "",
                    }

                all_results: list[MatchOdds] = []

                # CF clearance is ONE-USE per browser context — each navigation to a
                # betting page issues a fresh Turnstile token that allows exactly one
                # same-origin detail-service call. Use a fresh context per league.
                _FETCH_JS = """
                async (url) => {
                    try {
                        const r = await fetch(url, {
                            credentials: 'include',
                            headers: {'Accept': 'application/json, */*'}
                        });
                        if (!r.ok) return {_status: r.status, _error: 'http_error'};
                        const ct = r.headers.get('content-type') || '';
                        if (!ct.includes('json')) return {_status: r.status, _error: 'not_json', _ct: ct};
                        return await r.json();
                    } catch(e) {
                        return {_error: String(e)};
                    }
                }
                """

                def _parse_result(result: Any, league_name: str, discipline: str) -> list[MatchOdds]:
                    if not isinstance(result, dict):
                        logger.info("[Eurobet] %s: bad type %s", league_name, type(result).__name__)
                        return []
                    if "_error" in result:
                        logger.info("[Eurobet] %s: HTTP %s – %s",
                                    league_name, result.get("_status", "?"), result.get("_error"))
                        return []
                    code = result.get("code")
                    desc = str(result.get("description") or "")[:80]
                    logger.info("[Eurobet] %s: code=%s desc=%s", league_name, code, desc)
                    if code not in (1, "1"):
                        return []
                    events = _extract_events(result)
                    if not events:
                        logger.info("[Eurobet] %s: code=1 but no events | preview=%.500s",
                                    league_name, _json.dumps(result, ensure_ascii=False)[:500])
                        return []
                    # Log first event + first betGroup for structure discovery
                    ev0 = events[0] if isinstance(events[0], dict) else {}
                    bgl = ev0.get("betGroupList") or []
                    bg0 = bgl[0] if bgl else {}
                    logger.info("[Eurobet] %s: ev0 keys=%s betGroup0=%.400s",
                                league_name, list(ev0.keys())[:10],
                                _json.dumps(bg0, ensure_ascii=False)[:400])
                    rows = _parse_events(events, league_name, discipline)
                    logger.info("[Eurobet] %s: %d events → %d rows", league_name, len(events), len(rows))
                    return rows

                async with async_playwright() as pw:
                    browser = await pw.chromium.launch(
                        headless=True,
                        args=["--no-sandbox", "--disable-dev-shm-usage"],
                        proxy=proxy_cfg,
                    )

                    for league_name, discipline, alias in meetings:
                        bet_url = f"https://www.eurobet.it/it/scommesse/{discipline}/{alias}"
                        meeting_api = (f"/detail-service/sport-schedule/services/meeting"
                                       f"/{discipline}/{alias}?prematch=1&live=0")

                        # Fresh context per league → fresh CF clearance token.
                        # Retry up to 3 times if CF blocks.
                        meeting_result: Any = {"_error": "not_tried"}
                        ctx = None
                        pg = None
                        for attempt in range(3):
                            if ctx:
                                await ctx.close()
                            ctx = await browser.new_context(
                                user_agent=_UA,
                                locale="it-IT",
                                timezone_id="Europe/Rome",
                                viewport={"width": 1280, "height": 800},
                            )
                            pg = await ctx.new_page()
                            if _STEALTH:
                                await _stealth_async(pg)
                            try:
                                await pg.goto(bet_url, wait_until="domcontentloaded", timeout=30_000)
                                await pg.wait_for_timeout(2000)
                                meeting_result = await pg.evaluate(_FETCH_JS, meeting_api)
                            except Exception as e:
                                logger.warning("[Eurobet] %s attempt %d error: %s",
                                               league_name, attempt + 1, e)
                                meeting_result = {"_error": str(e)}

                            if isinstance(meeting_result, dict) and meeting_result.get("_status") == 403:
                                logger.info("[Eurobet] %s attempt %d → 403, retrying…",
                                            league_name, attempt + 1)
                                continue
                            break

                        # ── Parse meeting response → extract event list ──
                        league_rows: list[MatchOdds] = []
                        if (isinstance(meeting_result, dict)
                                and meeting_result.get("code") in (1, "1")):

                            meeting_events = _extract_events(meeting_result)
                            logger.info("[Eurobet] %s: meeting returned %d events",
                                        league_name, len(meeting_events))

                            # Log all market names in first event for diagnostics
                            if meeting_events and isinstance(meeting_events[0], dict):
                                ev0 = meeting_events[0]
                                all_og_names = [
                                    og.get("oddGroupDescription", "?")
                                    for bg in (ev0.get("betGroupList") or [])
                                    if isinstance(bg, dict)
                                    for og in (bg.get("oddGroupList") or [])
                                    if isinstance(og, dict)
                                ]
                                logger.info("[Eurobet] %s: ev0 market names: %s",
                                            league_name, all_og_names[:20])

                            # ── For each event, fetch the full event-detail endpoint ──
                            # The meeting response only has "SCOMMESSE TOP" (1X2 only).
                            # The event-detail endpoint returns all markets (O/U, BTTS, DC…).
                            for ev in meeting_events:
                                if not isinstance(ev, dict):
                                    continue
                                ei = ev.get("eventInfo") or {}
                                event_code = ei.get("eventCode")

                                # Fallback: try to find eventCode inside the betGroupList odds
                                if not event_code:
                                    for bg in (ev.get("betGroupList") or []):
                                        if not isinstance(bg, dict):
                                            continue
                                        for og in (bg.get("oddGroupList") or []):
                                            if not isinstance(og, dict):
                                                continue
                                            for odd in (og.get("oddList") or []):
                                                if isinstance(odd, dict) and odd.get("eventCode"):
                                                    event_code = odd["eventCode"]
                                                    break
                                            if event_code:
                                                break
                                        if event_code:
                                            break

                                if not event_code:
                                    logger.info("[Eurobet] %s: no eventCode in event, parsing meeting data only",
                                                league_name)
                                    # Still parse whatever we got from the meeting
                                    league_rows.extend(_parse_events([ev], league_name, discipline))
                                    continue

                                # Fetch full event detail (all markets)
                                detail_api = (f"/detail-service/sport-schedule/services/event"
                                              f"/{discipline}/{event_code}?prematch=1&live=0")
                                try:
                                    detail_result = await pg.evaluate(_FETCH_JS, detail_api)
                                except Exception as e:
                                    logger.warning("[Eurobet] %s event %s detail fetch error: %s",
                                                   league_name, event_code, e)
                                    detail_result = {"_error": str(e)}

                                if (isinstance(detail_result, dict)
                                        and detail_result.get("code") in (1, "1")):
                                    detail_events = _extract_events(detail_result)
                                    if detail_events:
                                        # Log market names for first event detail (once per league)
                                        if not league_rows:
                                            det_ev0 = detail_events[0] if isinstance(detail_events[0], dict) else {}
                                            det_og_names = [
                                                og.get("oddGroupDescription", "?")
                                                for bg in (det_ev0.get("betGroupList") or [])
                                                if isinstance(bg, dict)
                                                for og in (bg.get("oddGroupList") or [])
                                                if isinstance(og, dict)
                                            ]
                                            logger.info("[Eurobet] %s: event %s detail markets: %s",
                                                        league_name, event_code, det_og_names[:20])
                                        league_rows.extend(
                                            _parse_events(detail_events, league_name, discipline)
                                        )
                                    else:
                                        logger.info("[Eurobet] %s event %s: detail code=1 but no events",
                                                    league_name, event_code)
                                        # Fallback to meeting event data
                                        league_rows.extend(_parse_events([ev], league_name, discipline))
                                elif isinstance(detail_result, dict) and "_error" in detail_result:
                                    logger.info("[Eurobet] %s event %s: detail error %s %s — fallback to meeting",
                                                league_name, event_code,
                                                detail_result.get("_status", "?"),
                                                detail_result.get("_error"))
                                    league_rows.extend(_parse_events([ev], league_name, discipline))
                                else:
                                    logger.info("[Eurobet] %s event %s: detail unexpected response",
                                                league_name, event_code)
                                    league_rows.extend(_parse_events([ev], league_name, discipline))

                        else:
                            rows_fb = _parse_result(meeting_result, league_name, discipline)
                            league_rows.extend(rows_fb)

                        logger.info("[Eurobet] %s: %d rows total", league_name, len(league_rows))
                        all_results.extend(league_rows)
                        if league_rows:
                            working_url_template = "PLAYWRIGHT_PER_CTX"

                        if ctx:
                            await ctx.close()

                    await browser.close()

            except Exception as pw_err:
                logger.error("[Eurobet] Playwright phase failed: %s", pw_err)

            if not all_results:
                logger.warning("[Eurobet] All approaches failed — 0 rows")
                logger.info("[Eurobet] Total: 0 events, 0 rows")
                return []

            # Dedup and return Playwright results
            seen: dict[tuple[str, str], MatchOdds] = {}
            for r in all_results:
                seen[(r.event_name, r.market)] = r
            deduped = list(seen.values())
            n_events = len({r.event_name for r in deduped})
            logger.info("[Eurobet] Total: %d events, %d rows", n_events, len(deduped))
            return deduped

        # ── Phase 2: Fetch all leagues via httpx ──────────────────────────
        all_results: list[MatchOdds] = []

        async with httpx.AsyncClient(
            headers=_HEADERS, timeout=20, follow_redirects=True, proxy=proxy_url,
        ) as client:
            for league_name, discipline, alias in meetings:
                url = working_url_template.format(disc=discipline, alias=alias)
                logger.info("[Eurobet] Fetching %s…", league_name)
                try:
                    resp = await client.get(url, follow_redirects=True)
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
