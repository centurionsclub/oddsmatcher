"""Lottomatica pregame odds scraper.

Strategy: Playwright browser + network response interception.
Navigate to each Lottomatica tournament page; the SPA fires internal
API calls automatically.  We capture those JSON responses and parse them —
no direct API calls from Python (which Akamai blocks with 403).

Flow per tournament:
  1. Navigate to the Lottomatica tournament page
  2. Intercept JSON responses from lottomatica.it
  3. Find the response with event/odds data
  4. Parse and return MatchOdds
"""

import asyncio
import logging
import os
import re
import unicodedata
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, Request, async_playwright

from oddsmatcher_backend.scraper.models import MatchOdds

logger = logging.getLogger(__name__)

BASE_URL = "https://www.lottomatica.it"
BOOKMAKER = "lottomatica"

# fmt: off
# (id_tournament, league_name, sport_key, league_slug, country_slug, page_url)
TOURNAMENTS: list[tuple[int, str, str, str, str, str]] = [
    (93,      "Serie A",           "calcio", "serie-a",            "italia",                  "/scommesse/sport/calcio/italia/serie-a/"),
    (1626630, "Serie B",           "calcio", "serie-b",            "italia",                  "/scommesse/sport/calcio/italia/serie-b/"),
    (26604,   "Premier League",    "calcio", "premier-league",     "inghilterra",             "/scommesse/sport/calcio/inghilterra/premier-league/"),
    (95,      "La Liga",           "calcio", "liga",               "spagna",                  "/scommesse/sport/calcio/spagna/liga/"),
    (84,      "Bundesliga",        "calcio", "bundesliga",         "germania",                "/scommesse/sport/calcio/germania/bundesliga/"),
    (86,      "Ligue 1",           "calcio", "ligue-1",            "francia",                 "/scommesse/sport/calcio/francia/ligue-1/"),
    (26534,   "Champions League",  "calcio", "champions-league",   "internazionali-di-club",  "/scommesse/sport/calcio/internazionali-di-club/champions-league/"),
    (247944,  "Europa League",     "calcio", "europa-league",      "internazionali-di-club",  "/scommesse/sport/calcio/internazionali-di-club/europa-league/"),
    (5675488, "Conference League", "calcio", "conference-league",  "internazionali-di-club",  "/scommesse/sport/calcio/internazionali-di-club/conference-league/"),
    # Basket
    (54529,   "NBA",               "basket", "nba",                   "usa",          "/scommesse/sport/basket/usa/nba?did=2&nid=8455&eid=54529"),
    (890160,  "Serie A Basket",    "basket", "serie-a",               "italia",       "/scommesse/sport/basket/italia/serie-a?did=2&nid=7606&eid=890160"),
    (26064,   "A2 Basket",         "basket", "a2",                    "italia",       "/scommesse/sport/basket/italia/a2?did=2&nid=7606&eid=26064"),
    (155272,  "WNBA",              "basket", "wnba",                  "usa",          "/scommesse/sport/basket/usa/wnba?did=2&nid=8455&eid=155272"),
    # Tennis — overview page loads all active tournaments dynamically (id=0 = catch-all)
    (0,       "ATP",               "tennis", "tennis",                "internazionale", "/scommesse/sport/tennis/"),
]
# fmt: on

SIMPLE_MARKET_MAP: dict[str, str] = {
    "1X2": "1X2",
    "DC": "Doppia Chance",
    "GG/NG": "Goal No Goal",
    "Esito Finale": "1X2",
    # Basket 2-way (NBA, WNBA, Serie A Basket ecc.)
    "T/T Risultato": "1X2",
    "Testa a Testa Risultato": "1X2",
    # Tennis
    "Vincente Incontro (escl. ritiro)": "1X2",
    "Vincente Incontro": "1X2",
}

UO_SPREADS_WANTED: set[str] = {"1.5", "2.5", "3.5"}

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _slugify_team(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_str.lower()).strip("-")


class LottomaticaScraper:
    """Scrapes pregame odds from Lottomatica via Playwright network interception."""

    def __init__(self, browser=None):
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def _start(self) -> None:
        self._playwright = await async_playwright().start()

        proxy_url = os.environ.get("PROXY_URL")
        proxy = None
        if proxy_url:
            import urllib.parse
            p = urllib.parse.urlparse(proxy_url)
            proxy = {
                "server": f"{p.scheme}://{p.hostname}:{p.port}",
                "username": p.username or "",
                "password": p.password or "",
            }
            logger.info("[Lottomatica] Usando proxy: %s:%s", p.hostname, p.port)

        self._browser = await self._playwright.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            proxy=proxy,
        )
        self._context = await self._browser.new_context(
            user_agent=_USER_AGENT,
            locale="it-IT",
            timezone_id="Europe/Rome",
            viewport={"width": 1280, "height": 800},
        )
        self._page = await self._context.new_page()

        logger.info("[Lottomatica] Navigating to homepage for Akamai warm-up...")
        try:
            await self._page.goto(
                f"{BASE_URL}/scommesse/sport/",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            await self._page.wait_for_timeout(3000)
            logger.info("[Lottomatica] Homepage loaded — browser ready")
        except Exception as e:
            logger.warning("[Lottomatica] Homepage warm-up failed: %s", e)

    async def _stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._page = self._context = self._browser = self._playwright = None

    async def scrape_all(self) -> list[MatchOdds]:
        await self._start()
        try:
            return await self._scrape_tournaments(None)
        finally:
            await self._stop()

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        await self._start()
        try:
            return await self._scrape_tournaments(sport)
        finally:
            await self._stop()

    # ── internals ─────────────────────────────────────────────────────

    async def _scrape_tournaments(self, sport: str | None) -> list[MatchOdds]:
        all_results: list[MatchOdds] = []
        for id_tournament, league_name, sport_key, league_slug, country_slug, page_path in TOURNAMENTS:
            if sport and sport_key != sport:
                continue
            try:
                results = await self._scrape_tournament(
                    id_tournament, league_name, sport_key, league_slug, country_slug, page_path
                )
                all_results.extend(results)
                n_events = len({r.event_name for r in results})
                logger.info("[Lottomatica] %s — %d events, %d market rows", league_name, n_events, len(results))
            except Exception as exc:
                logger.error("[Lottomatica] %s failed: %s", league_name, exc, exc_info=True)
            await asyncio.sleep(0.5)

        logger.info("[Lottomatica] Total match+market rows: %d", len(all_results))
        return all_results

    async def _scrape_tournament(
        self,
        id_tournament: int,
        league_name: str,
        sport_key: str,
        league_slug: str,
        country_slug: str,
        page_path: str,
    ) -> list[MatchOdds]:
        assert self._page is not None

        # Capture XHR/fetch REQUEST URLs (not response bodies — Akamai may replace
        # the response body seen by Playwright with an HTML challenge even though the
        # real browser receives the actual JSON).  We then re-fetch each URL from
        # inside the browser via page.evaluate(fetch()) which uses the real session.
        captured_api_urls: list[str] = []
        _SKIP_EXTS = (".js", ".css", ".png", ".jpg", ".woff", ".woff2", ".svg",
                      ".ico", ".gif", ".webp", ".ttf", ".map")

        def on_request(request: Request) -> None:
            if request.resource_type not in ("xhr", "fetch"):
                return
            ru = request.url
            if "lottomatica.it" not in ru:
                return
            if any(ru.endswith(ext) for ext in _SKIP_EXTS):
                return
            if ru not in captured_api_urls:
                captured_api_urls.append(ru)
                logger.debug("[Lottomatica] %s: API request captured: %s", league_name, ru[:120])

        self._page.on("request", on_request)

        url = BASE_URL + page_path
        logger.info("[Lottomatica] Loading %s", url)
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            logger.info("[Lottomatica] %s: goto: %s", league_name, type(e).__name__)

        # Wait for SPA data requests to fire
        await self._page.wait_for_timeout(5_000)
        self._page.remove_listener("request", on_request)

        logger.info("[Lottomatica] %s: %d API URLs captured", league_name, len(captured_api_urls))

        if not captured_api_urls:
            logger.warning("[Lottomatica] %s: no API URLs captured (SPA may not have loaded)", league_name)
            return []

        # Re-fetch each URL from inside the browser — uses real session cookies,
        # bypasses Akamai's network-layer inspection of Python requests.
        import json as _json
        for api_url in captured_api_urls:
            try:
                safe_url = api_url.replace("'", "%27")
                result = await self._page.evaluate(f"""
                    async () => {{
                        try {{
                            const r = await fetch('{safe_url}', {{
                                credentials: 'include',
                                headers: {{'Accept': 'application/json, */*'}}
                            }});
                            if (!r.ok) return {{error: r.status}};
                            return await r.json();
                        }} catch(e) {{ return {{error: String(e)}}; }}
                    }}
                """)
            except Exception as exc:
                logger.warning("[Lottomatica] %s: evaluate failed: %s", league_name, exc)
                continue

            if isinstance(result, dict) and "error" in result:
                logger.debug("[Lottomatica] %s: fetch error %s from %s",
                             league_name, result["error"], api_url[:80])
                continue

            # Log structure for debugging
            if isinstance(result, dict):
                keys = list(result.keys())[:8]
            elif isinstance(result, list):
                keys = f"list[{len(result)}]"
                if result and isinstance(result[0], dict):
                    keys = f"list[{len(result)}] → {list(result[0].keys())[:6]}"
            else:
                keys = type(result).__name__
            logger.info("[Lottomatica] CAPTURE url=%s keys=%s BODY=%s",
                        api_url[:100], keys, _json.dumps(result, ensure_ascii=False)[:500])

            rows = _parse_lottomatica_response(
                api_url, result,
                id_tournament, league_name, sport_key, league_slug, country_slug,
            )
            if rows:
                logger.info("[Lottomatica] %s: parsed %d rows from %s",
                            league_name, len(rows), api_url[:80])
                return rows

        logger.warning("[Lottomatica] %s: no parseable data in %d captured URLs",
                       league_name, len(captured_api_urls))
        return []

    @staticmethod
    def _count_unique_events(results: list[MatchOdds]) -> int:
        return len({r.event_name for r in results})


# ── response parser ────────────────────────────────────────────────────

def _parse_lottomatica_response(
    url: str,
    body: Any,
    id_tournament: int,
    league_name: str,
    sport_key: str,
    league_slug: str,
    country_slug: str,
) -> list[MatchOdds]:
    """Try to extract MatchOdds from a captured Lottomatica JSON response.

    Lottomatica's internal API (via the SPA) returns events in a `leo` list.
    Each event has market data in `mmkW` dict, with spreads in `spd` and
    selections in `asl`.  This mirrors the old httpx-based parser.
    """
    try:
        # Known structure: {"leo": [...events...]}
        if isinstance(body, dict) and "leo" in body:
            return _parse_leo_list(
                body["leo"], id_tournament, league_name, sport_key, league_slug, country_slug
            )

        # Sometimes nested one level deeper
        if isinstance(body, dict):
            for v in body.values():
                if isinstance(v, dict) and "leo" in v:
                    return _parse_leo_list(
                        v["leo"], id_tournament, league_name, sport_key, league_slug, country_slug
                    )

        return []
    except Exception as e:
        logger.info("[Lottomatica] parse error for %s: %s", url, e, exc_info=True)
        return []


def _parse_leo_list(
    events: list,
    id_tournament: int,
    league_name: str,
    sport_key: str,
    league_slug: str,
    country_slug: str,
) -> list[MatchOdds]:
    results: list[MatchOdds] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_name = event.get("en", "")
        event_date = event.get("ed", "")
        event_time = _parse_date(event_date)
        ei = event.get("ei", "")

        parts = event_name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else event_name
        away = parts[1].strip() if len(parts) == 2 else ""

        home_slug = _slugify_team(home)
        away_slug = _slugify_team(away)
        if id_tournament == 0:
            # catch-all overview page (e.g. tennis) — use sport-level URL
            match_url = f"{BASE_URL}/scommesse/sport/{sport_key}/"
        else:
            match_url = (
                f"{BASE_URL}/scommesse/sport/{sport_key}/{country_slug}/{league_slug}"
                f"/{home_slug}-{away_slug}?tid={id_tournament}&eid={ei}"
            )

        market_rows = _parse_markets(event, event_name, home, away, event_time, league_name, sport_key, match_url)
        results.extend(market_rows)

    return results


def _parse_markets(
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

        canonical = SIMPLE_MARKET_MAP.get(market_raw)
        if canonical:
            odds_dict: dict[str, float] = {}
            for spread_data in mkt.get("spd", {}).values():
                for sel in spread_data.get("asl", []):
                    ov = sel.get("ov")
                    sn = sel.get("sn", "")
                    # cls=1 means "active" for football; basket may use cls=0 or other
                    # values.  Accept any cls when ov is a valid playable price.
                    if ov and ov > 1.0:
                        odds_dict[sn] = float(ov)
            if odds_dict:
                results.append(MatchOdds(
                    sport=sport_key, league=league_name,
                    home_team=home, away_team=away,
                    event_name=event_name, event_time=event_time,
                    match_url=match_url, market=canonical,
                    bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                ))
            continue

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
                    results.append(MatchOdds(
                        sport=sport_key, league=league_name,
                        home_team=home, away_team=away,
                        event_name=event_name, event_time=event_time,
                        match_url=match_url, market=f"Over/Under {sl}",
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                    ))

    return results


def _parse_date(date_str: str) -> str:
    """Parse Lottomatica date string (Italian local time) → UTC ISO string.

    Lottomatica returns dates in Italian time (CET = UTC+1 in winter,
    CEST = UTC+2 in summer). We use the ``dateutil`` / stdlib ``zoneinfo``
    to convert properly so that all scrapers store UTC in the DB.
    """
    try:
        from datetime import datetime, timezone, timedelta
        dt_naive = datetime.strptime(date_str, "%d-%m-%Y %H:%M")
        # Determine Italy offset: CEST (UTC+2) Mar–Oct, CET (UTC+1) Nov–Feb
        # Use a simple heuristic: month 3-10 → UTC+2, else UTC+1
        italy_offset = 2 if 3 <= dt_naive.month <= 10 else 1
        dt_local = dt_naive.replace(tzinfo=timezone(timedelta(hours=italy_offset)))
        return dt_local.astimezone(timezone.utc).isoformat()
    except Exception:
        return date_str
