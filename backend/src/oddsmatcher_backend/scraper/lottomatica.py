"""Lottomatica pregame odds scraper.

Strategy: Playwright browser + on_response interception of Angular XHR.

Lottomatica is an Angular SPA.  When a tournament page loads, Angular fires
an XHR to:
    GET /api/sport/pregame/getOverviewEventsAams/0/{did}/0/{eid}/0/0/0

where `did` = discipline (1=calcio, 2=basket, 5=tennis) and `eid` = the
tournament ID already known from the TOURNAMENTS list.

Akamai blocks any *scripted* re-fetch (403), but Angular's natural XHR
returns the real JSON (200, ~14–50 KB).  We intercept that response via
Playwright's on_response handler and parse it — no re-fetch needed.

Flow per tournament:
  1. Register on_response listener for the specific endpoint URL.
  2. Navigate to the Lottomatica tournament page.
  3. Angular fires the XHR → Playwright captures the response body.
  4. Parse and return MatchOdds rows.
"""

import asyncio
import logging
import os
import re
import unicodedata
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, Response, async_playwright

from oddsmatcher_backend.scraper.models import MatchOdds

logger = logging.getLogger(__name__)

BASE_URL = "https://www.lottomatica.it"
BOOKMAKER = "lottomatica"

# Discipline IDs used by Lottomatica's internal API
_DID = {"calcio": 1, "basket": 2, "tennis": 5}

# fmt: off
# (eid, league_name, sport_key, league_slug, country_slug, page_url)
# eid   = tournament ID → used in the getOverviewEventsAams path
# page_url = the Lottomatica SPA URL to navigate to (triggers the XHR)
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
    (54529,   "NBA",            "basket", "nba",      "usa",    "/scommesse/sport/basket/usa/nba?did=2&nid=8455&eid=54529"),
    (890160,  "Serie A Basket", "basket", "serie-a",  "italia", "/scommesse/sport/basket/italia/serie-a?did=2&nid=7606&eid=890160"),
    (26064,   "A2 Basket",      "basket", "a2",       "italia", "/scommesse/sport/basket/italia/a2?did=2&nid=7606&eid=26064"),
    (155272,  "WNBA",           "basket", "wnba",     "usa",    "/scommesse/sport/basket/usa/wnba?did=2&nid=8455&eid=155272"),
    # Tennis — navigate to the primo-piano overview, which triggers XHR for each
    # active Grand Slam / ATP / WTA tournament.  We capture ALL getOverviewEventsAams
    # responses on that page.  eid=0 means "catch-all from overview page".
    (0,       "ATP/WTA",        "tennis", "tennis",   "internazionale", "/scommesse/sport/tennis/primo-piano/eventi-oggi-domani"),
]
# fmt: on

SIMPLE_MARKET_MAP: dict[str, str] = {
    "1X2": "1X2",
    "DC": "Doppia Chance",
    "GG/NG": "Goal No Goal",
    "Esito Finale": "1X2",
    # Basket 2-way
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

# Timeout (ms) to wait for the Angular XHR after page navigation
_XHR_WAIT_MS = 12_000


def _slugify_team(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_str.lower()).strip("-")


class LottomaticaScraper:
    """Scrapes pregame odds from Lottomatica via Playwright on_response interception."""

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
        for eid, league_name, sport_key, league_slug, country_slug, page_path in TOURNAMENTS:
            if sport and sport_key != sport:
                continue
            try:
                results = await self._scrape_tournament(
                    eid, league_name, sport_key, league_slug, country_slug, page_path
                )
                all_results.extend(results)
                n_events = len({r.event_name for r in results})
                logger.info("[Lottomatica] %s — %d events, %d market rows",
                            league_name, n_events, len(results))
            except Exception as exc:
                logger.error("[Lottomatica] %s failed: %s", league_name, exc, exc_info=True)
            await asyncio.sleep(0.5)

        logger.info("[Lottomatica] Total match+market rows: %d", len(all_results))
        return all_results

    async def _scrape_tournament(
        self,
        eid: int,
        league_name: str,
        sport_key: str,
        league_slug: str,
        country_slug: str,
        page_path: str,
    ) -> list[MatchOdds]:
        assert self._page is not None
        import json as _json

        did = _DID.get(sport_key, 1)

        # ── Intercept the Angular XHR response via on_response ──────────────
        # Angular fires GET /api/sport/pregame/getOverviewEventsAams/0/{did}/0/{eid}/0/0/0
        # naturally when the tournament page loads.  We capture that response body
        # directly — no scripted re-fetch needed (Akamai would block it).
        #
        # For the tennis overview page (eid=0) we capture ANY getOverviewEventsAams
        # response, since the page loads multiple tournaments dynamically.

        captured_bodies: list[tuple[str, Any]] = []  # [(url, parsed_json)]

        def _is_target(url: str) -> bool:
            if "getOverviewEventsAams" not in url:
                return False
            if eid == 0:
                # Tennis overview: capture all tournament responses
                return True
            # Specific tournament: match the eid in the path
            return f"/{eid}/" in url or url.endswith(f"/{eid}/0/0/0") or f"0/{eid}/0" in url

        async def on_response(response: Response) -> None:
            try:
                url = response.url
                if not _is_target(url):
                    return
                if response.status != 200:
                    logger.warning("[Lottomatica] %s: XHR %d for %s",
                                   league_name, response.status, url[50:120])
                    return
                body = await response.body()
                try:
                    data = _json.loads(body)
                except Exception:
                    logger.warning("[Lottomatica] %s: non-JSON response from %s (len=%d, preview=%s)",
                                   league_name, url[50:120], len(body), body[:100])
                    return
                logger.info("[Lottomatica] %s: captured XHR → %s (len=%d)",
                            league_name, url[50:120], len(body))
                captured_bodies.append((url, data))
            except Exception as exc:
                logger.warning("[Lottomatica] %s: on_response error: %s", league_name, exc)

        self._page.on("response", on_response)

        url = BASE_URL + page_path
        logger.info("[Lottomatica] Loading %s", url)
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            logger.info("[Lottomatica] %s: goto exception: %s", league_name, type(e).__name__)

        # Wait for Angular to boot and fire its XHR calls
        # For tennis (eid=0) wait a bit longer since multiple tournaments load
        wait_ms = _XHR_WAIT_MS if eid == 0 else _XHR_WAIT_MS
        await self._page.wait_for_timeout(wait_ms)
        self._page.remove_listener("response", on_response)

        logger.info("[Lottomatica] %s: %d XHR responses captured", league_name, len(captured_bodies))

        if not captured_bodies:
            logger.warning("[Lottomatica] %s: no getOverviewEventsAams response intercepted "
                           "(Angular may not have fired the XHR yet)", league_name)
            return []

        # Parse all captured responses
        all_rows: list[MatchOdds] = []
        for resp_url, data in captured_bodies:
            rows = _parse_lottomatica_response(
                resp_url, data, eid, league_name, sport_key, league_slug, country_slug,
            )
            if rows:
                logger.info("[Lottomatica] %s: parsed %d rows from %s",
                            league_name, len(rows), resp_url[50:120])
                all_rows.extend(rows)

        if not all_rows:
            # Log structure to help adapt the parser
            for resp_url, data in captured_bodies[:1]:
                if isinstance(data, dict):
                    keys = list(data.keys())[:10]
                elif isinstance(data, list):
                    keys = f"list[{len(data)}]"
                    if data and isinstance(data[0], dict):
                        keys = f"list[{len(data)}] keys={list(data[0].keys())[:8]}"
                else:
                    keys = type(data).__name__
                logger.warning("[Lottomatica] %s: parser got 0 rows. Response structure: %s | sample: %s",
                               league_name, keys,
                               _json.dumps(data, ensure_ascii=False)[:400])

        return all_rows


# ── response parser ────────────────────────────────────────────────────

def _parse_lottomatica_response(
    url: str,
    body: Any,
    eid: int,
    league_name: str,
    sport_key: str,
    league_slug: str,
    country_slug: str,
) -> list[MatchOdds]:
    """Parse a getOverviewEventsAams JSON response into MatchOdds rows."""
    try:
        # Known structure: {"leo": [...events...]}
        if isinstance(body, dict) and "leo" in body:
            return _parse_leo_list(
                body["leo"], eid, league_name, sport_key, league_slug, country_slug
            )

        # Sometimes nested one level deeper
        if isinstance(body, dict):
            for v in body.values():
                if isinstance(v, dict) and "leo" in v:
                    return _parse_leo_list(
                        v["leo"], eid, league_name, sport_key, league_slug, country_slug
                    )
                if isinstance(v, list) and v and isinstance(v[0], dict) and "leo" in v[0]:
                    rows = []
                    for item in v:
                        rows.extend(_parse_leo_list(
                            item.get("leo", []), eid, league_name, sport_key, league_slug, country_slug
                        ))
                    return rows

        return []
    except Exception as e:
        logger.info("[Lottomatica] parse error for %s: %s", url, e, exc_info=True)
        return []


def _parse_leo_list(
    events: list,
    eid: int,
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
        if eid == 0:
            match_url = f"{BASE_URL}/scommesse/sport/{sport_key}/"
        else:
            match_url = (
                f"{BASE_URL}/scommesse/sport/{sport_key}/{country_slug}/{league_slug}"
                f"/{home_slug}-{away_slug}?tid={eid}&eid={ei}"
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
    try:
        from datetime import datetime, timezone, timedelta
        dt_naive = datetime.strptime(date_str, "%d-%m-%Y %H:%M")
        italy_offset = 2 if 3 <= dt_naive.month <= 10 else 1
        dt_local = dt_naive.replace(tzinfo=timezone(timedelta(hours=italy_offset)))
        return dt_local.astimezone(timezone.utc).isoformat()
    except Exception:
        return date_str
