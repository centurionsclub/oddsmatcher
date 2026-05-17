"""Lottomatica pregame odds scraper.

Strategy: Playwright browser + page.request.get() for API calls.
We navigate to the Lottomatica homepage once to get Akamai session cookies,
then use the browser's request context (which carries those cookies) to call
the internal pregame JSON API.  httpx alone gets 403 from Akamai-protected IPs.

Flow per tournament:
  1. Navigate to homepage once → Akamai sets cookies/fingerprint
  2. getOverviewEventsAams → list of events with IDs (tai, ti, pi, ei)
  3. getDetailsEventAams per event → full market/odds data
"""

import asyncio
import logging
import re
import unicodedata

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)

BASE_URL = "https://www.lottomatica.it"
API_BASE = f"{BASE_URL}/api/sport/pregame"

# fmt: off
# (id_sport, id_tournament, id_aams_tournament, league_name, sport_key, league_slug, country_slug)
TOURNAMENTS: list[tuple[int, int, int, str, str, str, str]] = [
    # Calcio — leghe nazionali
    (1,  93,      21,   "Serie A",           "calcio", "serie-a",               "italia"),
    (1,  97,      34,   "Serie B",           "calcio", "serie-b",               "italia"),
    (1,  26604,   86,   "Premier League",    "calcio", "premier-league",        "inghilterra"),
    (1,  95,      79,   "La Liga",           "calcio", "la-liga",               "spagna"),
    (1,  94,      20,   "Bundesliga",        "calcio", "bundesliga",            "germania"),
    (1,  96,      23,   "Ligue 1",           "calcio", "ligue-1",               "francia"),
    # Calcio — coppe europee
    (1,  26534,   18,   "Champions League",  "calcio", "champions-league-uefa", "europa"),
    (1,  247944,  153,  "Europa League",     "calcio", "europa-league-uefa",    "europa"),
    (1,  5675488, 2474, "Conference League", "calcio", "conference-league-uefa","europa"),
]
# fmt: on

SIMPLE_MARKET_MAP: dict[str, str] = {
    "1X2": "1X2",
    "DC": "Doppia Chance",
    "GG/NG": "Goal No Goal",
    "Esito Finale": "1X2",
}

UO_SPREADS_WANTED: set[str] = {"1.5", "2.5", "3.5"}

BOOKMAKER = "lottomatica"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_API_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "it-IT,it;q=0.9,en;q=0.8",
    "x-brand": "2",
    "x-idcanale": "13",
    "x-verticale": "1",
    "referer": f"{BASE_URL}/scommesse/sport/",
    "origin": BASE_URL,
}


def _slugify_team(name: str) -> str:
    """Convert a team name to a URL slug.

    Example: "Atlético Madrid" → "atletico-madrid"
    """
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_str.lower()).strip("-")
    return slug


class LottomaticaScraper:
    """Scrapes pregame odds from Lottomatica using Playwright browser context.

    Uses the browser's request context (which carries Akamai session cookies
    obtained by navigating to the homepage) to call the internal pregame API.
    """

    def __init__(self, browser=None):  # browser param kept for API compat but not used
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def _start(self) -> None:
        """Launch browser and warm up Akamai session."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = await self._browser.new_context(
            user_agent=_USER_AGENT,
            locale="it-IT",
            timezone_id="Europe/Rome",
            viewport={"width": 1280, "height": 800},
        )
        self._page = await self._context.new_page()

        logger.info("[Lottomatica] Navigating to homepage to get Akamai cookies...")
        try:
            await self._page.goto(
                f"{BASE_URL}/scommesse/sport/",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            await self._page.wait_for_timeout(3000)  # let Akamai set cookies
            logger.info("[Lottomatica] Homepage loaded — browser ready")
        except Exception as e:
            logger.warning("[Lottomatica] Homepage navigation failed: %s", e)

    async def _stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    async def scrape_all(self) -> list[MatchOdds]:
        """Scrape all configured tournaments."""
        await self._start()
        try:
            return await self._scrape_tournaments(None)
        finally:
            await self._stop()

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        """Scrape only tournaments for the given sport key."""
        await self._start()
        try:
            return await self._scrape_tournaments(sport)
        finally:
            await self._stop()

    # ── internals ────────────────────────────────────────────────────

    async def _scrape_tournaments(self, sport: str | None) -> list[MatchOdds]:
        all_results: list[MatchOdds] = []
        for id_sport, id_tournament, id_aams, league_name, sport_key, league_slug, country_slug in TOURNAMENTS:
            if sport is not None and sport_key != sport:
                continue
            try:
                results = await self._scrape_tournament(
                    id_sport, id_tournament, id_aams, league_name, sport_key, league_slug, country_slug
                )
                all_results.extend(results)
                n_events = self._count_unique_events(results)
                logger.info(
                    "[Lottomatica] %s — %d events, %d market rows",
                    league_name, n_events, len(results),
                )
            except Exception as exc:
                logger.error("[Lottomatica] %s failed: %s", league_name, exc, exc_info=True)
            await asyncio.sleep(0.4)

        logger.info("[Lottomatica] Total match+market rows: %d", len(all_results))
        return all_results

    async def _api_get(self, url: str) -> dict | None:
        """Make an API GET using the browser's request context (carries Akamai cookies)."""
        assert self._page is not None, "Browser not started"
        try:
            response = await self._page.request.get(url, headers=_API_HEADERS, timeout=15_000)
            logger.debug("[Lottomatica] GET %s → %s", url, response.status)
            if response.status != 200:
                body = await response.text()
                logger.warning(
                    "[Lottomatica] HTTP %s for %s — body: %.300s",
                    response.status, url, body,
                )
                return None
            return await response.json()
        except Exception as e:
            logger.error("[Lottomatica] Request failed for %s: %s", url, e)
            return None

    async def _scrape_tournament(
        self,
        id_sport: int,
        id_tournament: int,
        id_aams: int,
        league_name: str,
        sport_key: str,
        league_slug: str,
        country_slug: str,
    ) -> list[MatchOdds]:
        overview_url = (
            f"{API_BASE}/getOverviewEventsAams"
            f"/0/{id_sport}/{id_aams}/{id_tournament}/0/0/STANDARD"
        )
        overview = await self._api_get(overview_url)
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

            tai = event.get("tai", id_aams)
            ti = event.get("ti", id_tournament)
            pi = event.get("pi", "")
            ei = event.get("ei", "")

            if not pi or not ei:
                continue

            details_url = (
                f"{API_BASE}/getDetailsEventAams"
                f"/{tai}/{ti}/{pi}/{ei}/0/STANDARD"
            )
            details = await self._api_get(details_url)
            if not details or not details.get("leo"):
                continue

            # Build direct event URL:
            # e.g. /scommesse/sport/calcio/italia/serie-a/atalanta-bologna?tid=93&eid=15569840
            home_slug = _slugify_team(home)
            away_slug = _slugify_team(away)
            match_url = (
                f"{BASE_URL}/scommesse/sport/{sport_key}/{country_slug}/{league_slug}"
                f"/{home_slug}-{away_slug}?tid={id_tournament}&eid={ei}"
            )

            for detail_event in details["leo"]:
                market_rows = self._parse_markets(
                    detail_event, event_name, home, away, event_time,
                    league_name, sport_key, match_url,
                )
                results.extend(market_rows)

            await asyncio.sleep(0.2)

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
        match_url: str,
    ) -> list[MatchOdds]:
        results: list[MatchOdds] = []

        for mkt in event.get("mmkW", {}).values():
            market_raw = mkt.get("mn", "").strip()

            # ── simple markets ────────────────────────────────────────
            canonical = SIMPLE_MARKET_MAP.get(market_raw)
            if canonical:
                odds_dict: dict[str, float] = {}
                for spread_data in mkt.get("spd", {}).values():
                    for sel in spread_data.get("asl", []):
                        ov = sel.get("ov")
                        sn = sel.get("sn", "")
                        cls = sel.get("cls", 1)  # cls=0 → suspended
                        if ov and ov > 1.0 and cls == 1:
                            odds_dict[sn] = float(ov)
                if odds_dict:
                    results.append(self._make_match_odds(
                        sport_key, league_name, home, away,
                        event_name, event_time, canonical, odds_dict, match_url,
                    ))
                continue

            # ── Over/Under: one MatchOdds per spread level ────────────
            if market_raw == "U/O":
                for spread_data in mkt.get("spd", {}).values():
                    sl = spread_data.get("sl", "")
                    if sl not in UO_SPREADS_WANTED:
                        continue
                    odds_dict = {}
                    for sel in spread_data.get("asl", []):
                        ov = sel.get("ov")
                        sn = sel.get("sn", "")
                        cls = sel.get("cls", 1)
                        if ov and ov > 1.0 and cls == 1:
                            odds_dict[sn] = float(ov)
                    if odds_dict:
                        results.append(self._make_match_odds(
                            sport_key, league_name, home, away,
                            event_name, event_time, f"Over/Under {sl}", odds_dict, match_url,
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
        match_url: str,
    ) -> MatchOdds:
        return MatchOdds(
            sport=sport,
            league=league,
            home_team=home,
            away_team=away,
            event_name=event_name,
            event_time=event_time,
            match_url=match_url,
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
