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

                for sport_key, sport_url in self.SPORT_PAGES:
                    if sport_filter and sport_key != sport_filter:
                        continue

                    captured: list[MatchOdds] = []

                    async def _on_response(resp: _Response, _sk: str = sport_key, _cap: list = captured) -> None:
                        url = resp.url
                        # Log all non-trivial API-looking responses for diagnostics
                        if any(kw in url for kw in ("api", "kambi", "offering", "json", "sport", "scommesse", "calcio", "tennis", "basket")):
                            ct = resp.headers.get("content-type", "")
                            if "json" in ct or "javascript" in ct or not ct:
                                logger.info("[Eurobet] API resp (sport=%s): %s [%s]", _sk, url[:120], resp.status)
                        if "kambicdn.com" not in url and "kambi" not in url:
                            return
                        try:
                            data = await resp.json()
                            rows = _parse_kambi_events_sport(data, _sk, wanted_leagues.get(_sk, set()))
                            if rows:
                                logger.info("[Eurobet] Intercepted Kambi resp for %s: %d rows", _sk, len(rows))
                                _cap.extend(rows)
                            else:
                                preview = _json.dumps(data, ensure_ascii=False)[:200] if data else "empty"
                                logger.info("[Eurobet] Kambi resp 0 rows (sport=%s) — %s", _sk, preview)
                        except Exception as exc:
                            logger.info("[Eurobet] Kambi parse error (sport=%s): %s", _sk, exc)

                    page.on("response", _on_response)
                    logger.info("[Eurobet] Navigating to %s", sport_url)
                    try:
                        await page.goto(sport_url, wait_until="networkidle", timeout=45_000)
                        logger.info("[Eurobet] %s: networkidle", sport_key)
                    except Exception as e:
                        logger.info("[Eurobet] %s: %s — continuing", sport_key, type(e).__name__)
                    await page.wait_for_timeout(3000)
                    page.remove_listener("response", _on_response)

                    # Deduplicate by (event_name, market)
                    seen: dict[tuple[str, str], MatchOdds] = {}
                    for r in captured:
                        seen[(r.event_name, r.market)] = r
                    deduped = list(seen.values())
                    n_events = len({r.event_name for r in deduped})
                    logger.info("[Eurobet] %s: %d events, %d market rows (after dedup)",
                                sport_key, n_events, len(deduped))
                    all_results.extend(deduped)

                    await asyncio.sleep(2.0)

            finally:
                await browser.close()

        logger.info("[Eurobet] Total rows: %d", len(all_results))
        return all_results
