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
    """Eurobet scraper — Playwright browser intercepts Kambi API calls.

    Direct httpx to Kambi CDN gets 429 (rate-limited by proxy IP).
    Using a browser session: the JS on eurobet.it makes Kambi API calls
    that carry browser fingerprint + cookies, bypassing the CDN rate limit.
    """

    bookmaker_name = BOOKMAKER

    # Eurobet sport pages that trigger Kambi API calls
    SPORT_PAGES: list[tuple[str, str]] = [
        ("calcio",  "https://www.eurobet.it/it/scommesse/sport/calcio/"),
        ("tennis",  "https://www.eurobet.it/it/scommesse/sport/tennis/"),
        ("basket",  "https://www.eurobet.it/it/scommesse/sport/basket/"),
    ]

    async def scrape_all(self) -> list[MatchOdds]:
        return await self._run(sport_filter=None)

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        return await self._run(sport_filter=sport)

    async def _run(self, sport_filter: str | None) -> list[MatchOdds]:
        import json as _json
        import os, urllib.parse
        from playwright.async_api import async_playwright, Response as _Response

        proxy_url = os.environ.get("PROXY_URL")

        # Wanted league names per sport (for filtering intercepted Kambi events)
        wanted_leagues: dict[str, set[str]] = {}
        for lg_name, sp_key, _ in LEAGUES:
            wanted_leagues.setdefault(sp_key, set()).add(lg_name)

        all_results: list[MatchOdds] = []

        async with async_playwright() as pw:
            proxy = None
            if proxy_url:
                p = urllib.parse.urlparse(proxy_url)
                proxy = {
                    "server": f"{p.scheme}://{p.hostname}:{p.port}",
                    "username": p.username or "",
                    "password": p.password or "",
                }
                logger.info("[Eurobet] Using proxy: %s:%s", p.hostname, p.port)

            browser = await pw.chromium.launch(
                headless=False,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
                proxy=proxy,
            )
            try:
                context = await browser.new_context(
                    user_agent=_HEADERS["User-Agent"],
                    locale="it-IT",
                    timezone_id="Europe/Rome",
                    viewport={"width": 1280, "height": 800},
                )
                try:
                    from playwright_stealth import stealth_async as _stealth_async
                    page = await context.new_page()
                    await _stealth_async(page)
                    logger.info("[Eurobet] playwright-stealth applied")
                except ImportError:
                    page = await context.new_page()
                    logger.warning("[Eurobet] playwright-stealth not installed")

                # Navigate to calcio page and extract SSR data via window.__NEXT_DATA__
                # The page uses Next.js SSR — odds are embedded in the initial page data,
                # not loaded client-side via Kambi CDN (which rate-limits the proxy IP).
                logger.info("[Eurobet] Navigating to calcio page to read __NEXT_DATA__…")
                try:
                    await page.goto(
                        "https://www.eurobet.it/it/scommesse/sport/calcio/",
                        wait_until="domcontentloaded",
                        timeout=45_000,
                    )
                    logger.info("[Eurobet] Calcio page loaded")
                except Exception as e:
                    logger.info("[Eurobet] Calcio page load error: %s — continuing", type(e).__name__)

                # Read window.__NEXT_DATA__ which contains all SSR props
                try:
                    next_data = await page.evaluate("() => window.__NEXT_DATA__")
                    preview = _json.dumps(next_data, ensure_ascii=False)[:500] if next_data else "null"
                    logger.info("[Eurobet] __NEXT_DATA__ preview: %s", preview)
                    if next_data:
                        # Log all top-level keys recursively to find odds structure
                        def _log_keys(obj, prefix="", depth=0):
                            if depth > 3:
                                return
                            if isinstance(obj, dict):
                                logger.info("[Eurobet] __NEXT_DATA__ keys at %s: %s", prefix or "root", list(obj.keys())[:20])
                                for k, v in obj.items():
                                    if isinstance(v, (dict, list)) and depth < 2:
                                        _log_keys(v, f"{prefix}.{k}", depth + 1)
                            elif isinstance(obj, list) and obj:
                                logger.info("[Eurobet] __NEXT_DATA__ list at %s len=%d first=%s",
                                            prefix, len(obj),
                                            _json.dumps(obj[0], ensure_ascii=False)[:200] if obj else "")
                        _log_keys(next_data)
                except Exception as exc:
                    logger.info("[Eurobet] __NEXT_DATA__ read error: %s", exc)

                # Also try reading from the _next/data URL directly via httpx
                # using cookies from the browser session
                cookies = await context.cookies()
                cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
                logger.info("[Eurobet] Browser cookies count: %d", len(cookies))

                # Get current page URL to extract buildId
                current_url = page.url
                logger.info("[Eurobet] Current page URL: %s", current_url)

                import httpx as _httpx
                import re as _re
                # Try to extract buildId from _next/data URL pattern seen in previous logs
                # Pattern: /_next/data/{buildId}/it/...
                try:
                    page_html = await page.content()
                    build_match = _re.search(r'"buildId"\s*:\s*"([^"]+)"', page_html)
                    if build_match:
                        build_id = build_match.group(1)
                        logger.info("[Eurobet] buildId: %s", build_id)
                        # Fetch the _next/data endpoint for each sport via httpx
                        async with _httpx.AsyncClient(
                            headers={**_HEADERS, "Cookie": cookie_header},
                            timeout=20,
                            follow_redirects=True,
                        ) as hclient:
                            for sport_key, _ in self.SPORT_PAGES:
                                if sport_filter and sport_key != sport_filter:
                                    continue
                                next_url = (
                                    f"https://www.eurobet.it/_next/data/{build_id}"
                                    f"/it/scommesse/sport/{sport_key}.json"
                                    f"?language=it&discipline=sport&meeting={sport_key}"
                                )
                                logger.info("[Eurobet] Fetching _next/data for %s: %s", sport_key, next_url[:120])
                                try:
                                    r = await hclient.get(next_url)
                                    logger.info("[Eurobet] _next/data %s → %d", sport_key, r.status_code)
                                    if r.status_code == 200:
                                        data = r.json()
                                        preview = _json.dumps(data, ensure_ascii=False)[:600]
                                        logger.info("[Eurobet] _next/data %s preview: %s", sport_key, preview)
                                        # Try to find Kambi events in the page props
                                        rows = _parse_kambi_events_sport(
                                            data, sport_key, wanted_leagues.get(sport_key, set())
                                        )
                                        if rows:
                                            logger.info("[Eurobet] %s: %d rows from _next/data", sport_key, len(rows))
                                            seen: dict[tuple[str, str], MatchOdds] = {}
                                            for r2 in rows:
                                                seen[(r2.event_name, r2.market)] = r2
                                            all_results.extend(seen.values())
                                except Exception as exc:
                                    logger.info("[Eurobet] _next/data error for %s: %s", sport_key, exc)
                    else:
                        logger.info("[Eurobet] buildId not found in page HTML")
                except Exception as exc:
                    logger.info("[Eurobet] buildId extraction error: %s", exc)

            finally:
                await browser.close()

        logger.info("[Eurobet] Total rows: %d", len(all_results))
        return all_results
