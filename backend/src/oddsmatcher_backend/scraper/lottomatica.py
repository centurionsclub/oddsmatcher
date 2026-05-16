"""Lottomatica pregame odds scraper.

Strategy: navigate to lottomatica.it to get valid Akamai session cookies
(requires headless=False — Akamai blocks headless browsers), then use
page.evaluate(fetch(...)) so the browser context (with its cookies) makes
the API calls — no manual cookie management needed.

Flow per tournament:
  1. getOverviewEventsAams → list of events with IDs (tai, ti, pi, ei)
  2. getDetailsEventAams per event → full market/odds data
"""

import asyncio
import logging

from playwright.async_api import Page

from oddsmatcher_backend.scraper.browser import BrowserManager
from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)

BASE_URL = "https://www.lottomatica.it"
API_BASE = f"{BASE_URL}/api/sport/pregame"

# fmt: off
# (id_sport, id_tournament, id_aams_tournament, league_name, sport_key)
# id_aams comes from the "tai" field in getProgram/ response
TOURNAMENTS: list[tuple[int, int, int, str, str]] = [
    # Calcio
    (1,  93,      21,   "Serie A",           "calcio"),
    (1,  97,      34,   "Serie B",           "calcio"),
    (1,  26534,   18,   "Champions League",  "calcio"),
    (1,  247944,  153,  "Europa League",     "calcio"),
    (1,  5675488, 2474, "Conference League", "calcio"),
    (1,  26604,   86,   "Premier League",    "calcio"),
    (1,  95,      79,   "La Liga",           "calcio"),
    (1,  94,      20,   "Bundesliga",        "calcio"),
    (1,  96,      23,   "Ligue 1",           "calcio"),
    # Tennis / Basket — populated dynamically from getProgram (future)
    # (4, None, None, None, "tennis"),
    # (5, None, None, None, "basket"),
]
# fmt: on

# Markets from getDetailsEventAams → canonical name
# " U/O" markets are handled specially: spread_label (1.5/2.5/3.5) →
# "Over/Under 1.5" / "Over/Under 2.5" / "Over/Under 3.5"
SIMPLE_MARKET_MAP: dict[str, str] = {
    "1X2": "1X2",
    "DC": "Doppia Chance",
    "GG/NG": "Goal No Goal",
    "Esito Finale": "1X2",   # alias used in some sports
}

# Spread labels we want for U/O markets
UO_SPREADS_WANTED: set[str] = {"1.5", "2.5", "3.5"}

BOOKMAKER = "lottomatica"

# JS snippet reused for all API fetches
_FETCH_JS = """
async (url) => {
    try {
        const r = await fetch(url, {
            headers: {
                'accept': 'application/json, text/plain, */*',
                'x-brand': '2',
                'x-idcanale': '13',
                'x-verticale': '1',
                'referer': 'https://www.lottomatica.it/scommesse/sport/'
            }
        });
        if (!r.ok) return null;
        return await r.json();
    } catch(e) {
        return null;
    }
}
"""


class LottomaticaScraper:
    """Scrapes pregame odds from Lottomatica via its internal JSON API."""

    def __init__(self, browser: BrowserManager):
        self.browser = browser

    async def scrape_all(self) -> list[MatchOdds]:
        """Navigate to Lottomatica, acquire Akamai cookies, then scrape all tournaments."""
        page = self.browser.page
        await self._warm_up_session(page)

        all_results: list[MatchOdds] = []
        for id_sport, id_tournament, id_aams, league_name, sport_key in TOURNAMENTS:
            try:
                results = await self._scrape_tournament(
                    page, id_sport, id_tournament, id_aams, league_name, sport_key
                )
                all_results.extend(results)
                n_events = self._count_unique_events(results)
                logger.info("[Lottomatica] %s — %d events, %d market rows", league_name, n_events, len(results))
            except Exception as exc:
                logger.error("[Lottomatica] %s failed: %s", league_name, exc, exc_info=True)
            await asyncio.sleep(0.5)

        logger.info("[Lottomatica] Total match+market rows: %d", len(all_results))
        return all_results

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        """Scrape only tournaments for the given sport key."""
        page = self.browser.page
        await self._warm_up_session(page)

        all_results: list[MatchOdds] = []
        for id_sport, id_tournament, id_aams, league_name, sport_key in TOURNAMENTS:
            if sport_key != sport:
                continue
            try:
                results = await self._scrape_tournament(
                    page, id_sport, id_tournament, id_aams, league_name, sport_key
                )
                all_results.extend(results)
            except Exception as exc:
                logger.error("[Lottomatica] %s failed: %s", league_name, exc, exc_info=True)
            await asyncio.sleep(0.5)

        return all_results

    # ── internals ────────────────────────────────────────────────────

    async def _warm_up_session(self, page: Page) -> None:
        """Navigate to Lottomatica so Akamai sets valid session cookies."""
        logger.info("[Lottomatica] Warming up session...")
        await page.goto(
            f"{BASE_URL}/scommesse/sport/",
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        # Give Akamai JS fingerprinting time to run and set bm_sv / ak_bmsc
        await page.wait_for_timeout(4_000)
        logger.info("[Lottomatica] Session ready")

    async def _api_fetch(self, page: Page, url: str) -> dict | None:
        """Make an authenticated API call from within the browser context."""
        return await page.evaluate(_FETCH_JS, url)

    async def _scrape_tournament(
        self,
        page: Page,
        id_sport: int,
        id_tournament: int,
        id_aams: int,
        league_name: str,
        sport_key: str,
    ) -> list[MatchOdds]:
        # Step 1: get event list for the tournament
        overview_url = (
            f"{API_BASE}/getOverviewEventsAams"
            f"/0/{id_sport}/{id_aams}/{id_tournament}/0/0/STANDARD"
        )
        overview = await self._api_fetch(page, overview_url)
        if not overview or not overview.get("leo"):
            logger.warning("[Lottomatica] No events for %s", league_name)
            return []

        results: list[MatchOdds] = []
        for event in overview["leo"]:
            event_name = event.get("en", "")
            event_date = event.get("ed", "")
            event_time = _parse_date(event_date)

            parts = event_name.split(" - ", 1)
            home = parts[0].strip() if len(parts) == 2 else event_name
            away = parts[1].strip() if len(parts) == 2 else ""

            # IDs needed for the details endpoint
            tai = event.get("tai", id_aams)   # AAMS tournament ID
            ti = event.get("ti", id_tournament)
            pi = event.get("pi", "")          # AAMS event ID
            ei = event.get("ei", "")          # event ID

            if not pi or not ei:
                continue

            # Step 2: get full market details for this event
            details_url = (
                f"{API_BASE}/getDetailsEventAams"
                f"/{tai}/{ti}/{pi}/{ei}/0/STANDARD"
            )
            details = await self._api_fetch(page, details_url)
            if not details or not details.get("leo"):
                continue

            for detail_event in details["leo"]:
                market_rows = self._parse_markets(
                    detail_event, event_name, home, away, event_time, league_name, sport_key
                )
                results.extend(market_rows)

            await asyncio.sleep(0.3)

        return results

    def _parse_markets(
        self,
        event: dict,
        event_name: str,
        home: str,
        away: str,
        event_time: str,
        league_name: str,
        sport_key: str,
    ) -> list[MatchOdds]:
        """Parse all wanted markets from an event detail dict."""
        results: list[MatchOdds] = []

        for mkt in event.get("mmkW", {}).values():
            market_raw = mkt.get("mn", "").strip()

            # ── simple markets (flat odds, no spread) ────────────────
            canonical = SIMPLE_MARKET_MAP.get(market_raw)
            if canonical:
                odds_dict: dict[str, float] = {}
                for spread_data in mkt.get("spd", {}).values():
                    for sel in spread_data.get("asl", []):
                        ov = sel.get("ov")
                        sn = sel.get("sn", "")
                        if ov and ov > 1.0:
                            odds_dict[sn] = float(ov)
                if odds_dict:
                    results.append(self._make_match_odds(
                        sport_key, league_name, home, away, event_name, event_time, canonical, odds_dict
                    ))
                continue

            # ── U/O market: one MatchOdds per wanted spread level ────
            if market_raw == "U/O":
                for spread_data in mkt.get("spd", {}).values():
                    sl = spread_data.get("sl", "")
                    if sl not in UO_SPREADS_WANTED:
                        continue
                    odds_dict = {}
                    for sel in spread_data.get("asl", []):
                        ov = sel.get("ov")
                        sn = sel.get("sn", "")
                        if ov and ov > 1.0:
                            odds_dict[sn] = float(ov)
                    if odds_dict:
                        results.append(self._make_match_odds(
                            sport_key, league_name, home, away, event_name, event_time,
                            f"Over/Under {sl}", odds_dict
                        ))

        return results

    def _make_match_odds(
        self,
        sport: str,
        league: str,
        home: str,
        away: str,
        event_name: str,
        event_time: str,
        market: str,
        odds_dict: dict[str, float],
    ) -> MatchOdds:
        return MatchOdds(
            sport=sport,
            league=league,
            home_team=home,
            away_team=away,
            event_name=event_name,
            event_time=event_time,
            match_url=f"{BASE_URL}/scommesse/sport/",
            market=market,
            bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
        )

    @staticmethod
    def _count_unique_events(results: list[MatchOdds]) -> int:
        return len({r.event_name for r in results})


def _parse_date(date_str: str) -> str:
    """Convert Lottomatica date 'DD-MM-YYYY HH:MM' to ISO 8601."""
    try:
        from datetime import datetime
        dt = datetime.strptime(date_str, "%d-%m-%Y %H:%M")
        return dt.isoformat()
    except Exception:
        return date_str
