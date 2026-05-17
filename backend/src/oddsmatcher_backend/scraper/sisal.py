"""Sisal pregame odds scraper.

Strategy: Playwright browser + network response interception.
We navigate to each Sisal league page and capture all JSON API responses
automatically — no hardcoded internal API URL needed.  Once Akamai cookies
are set by the first navigation, every subsequent JSON response from
sisal.it is intercepted, parsed for match/odds data, and stored.

The parser uses a flexible heuristic that works regardless of the exact
internal API path Sisal uses.
"""

import asyncio
import logging
import re
import unicodedata
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright, Response

from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)

BASE_URL = "https://www.sisal.it"
BOOKMAKER = "Sisal"

# fmt: off
# (league_name, sport_key, sisal_url_slug, country_slug)
LEAGUES: list[tuple[str, str, str, str]] = [
    ("Serie A",          "calcio", "calcio/serie-a",          "italia"),
    ("Serie B",          "calcio", "calcio/serie-b",          "italia"),
    ("Champions League", "calcio", "calcio/champions-league", "europa"),
    ("Europa League",    "calcio", "calcio/europa-league",    "europa"),
    ("Premier League",   "calcio", "calcio/premier-league",   "inghilterra"),
    ("La Liga",          "calcio", "calcio/la-liga",          "spagna"),
    ("Bundesliga",       "calcio", "calcio/bundesliga",       "germania"),
    ("Ligue 1",          "calcio", "calcio/ligue-1",          "francia"),
]
# fmt: on

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Minimum number of numeric odds values we expect in a valid API response
_MIN_ODDS_COUNT = 10


def _slugify(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_str.lower()).strip("-")


class SisalScraper:
    """Scrapes pregame odds from Sisal using Playwright network interception."""

    def __init__(self, browser=None):
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def _start(self) -> None:
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

        # Warm up Akamai session
        logger.info("[Sisal] Navigating to homepage for Akamai warm-up...")
        try:
            await self._page.goto(
                f"{BASE_URL}/scommesse-matchpoint",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            await self._page.wait_for_timeout(3000)
            logger.info("[Sisal] Homepage loaded")
        except Exception as e:
            logger.warning("[Sisal] Homepage warm-up failed: %s", e)

    async def _stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._page = self._context = self._browser = self._playwright = None

    async def scrape_all(self) -> list[MatchOdds]:
        await self._start()
        try:
            return await self._scrape_leagues(None)
        finally:
            await self._stop()

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        await self._start()
        try:
            return await self._scrape_leagues(sport)
        finally:
            await self._stop()

    # ── internals ─────────────────────────────────────────────────────

    async def _scrape_leagues(self, sport: str | None) -> list[MatchOdds]:
        all_results: list[MatchOdds] = []
        for league_name, sport_key, sisal_slug, country_slug in LEAGUES:
            if sport and sport_key != sport:
                continue
            try:
                results = await self._scrape_league(league_name, sport_key, sisal_slug, country_slug)
                all_results.extend(results)
                logger.info("[Sisal] %s — %d match+market rows", league_name, len(results))
            except Exception as exc:
                logger.error("[Sisal] %s failed: %s", league_name, exc, exc_info=True)
            await asyncio.sleep(1.0)

        logger.info("[Sisal] Total rows: %d", len(all_results))
        return all_results

    async def _scrape_league(
        self,
        league_name: str,
        sport_key: str,
        sisal_slug: str,
        country_slug: str,
    ) -> list[MatchOdds]:
        assert self._page is not None

        captured: list[dict[str, Any]] = []

        async def on_response(response: Response) -> None:
            if "sisal.it" not in response.url:
                return
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            try:
                body = await response.json()
                captured.append({"url": response.url, "body": body})
                logger.debug("[Sisal] Captured JSON from %s", response.url)
            except Exception:
                pass

        self._page.on("response", on_response)

        url = f"{BASE_URL}/scommesse-matchpoint/quote/{sisal_slug}"
        logger.info("[Sisal] Loading %s", url)
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await self._page.wait_for_timeout(4000)  # let lazy data load
        except Exception as e:
            logger.error("[Sisal] Failed to load %s: %s", url, e)
            self._page.remove_listener("response", on_response)
            return []

        self._page.remove_listener("response", on_response)

        logger.info("[Sisal] %s: captured %d JSON responses", league_name, len(captured))

        # Try to parse each captured response
        for item in captured:
            results = _parse_response(item["url"], item["body"], league_name, sport_key, country_slug)
            if results:
                logger.info(
                    "[Sisal] %s: found %d rows from %s",
                    league_name, len(results), item["url"],
                )
                return results

        logger.warning("[Sisal] %s: no parseable response found in %d captured", league_name, len(captured))
        return []


# ── response parser ────────────────────────────────────────────────────

def _parse_response(
    url: str,
    body: Any,
    league_name: str,
    sport_key: str,
    country_slug: str,
) -> list[MatchOdds]:
    """Try to extract MatchOdds from a captured Sisal JSON response.

    Sisal's internal API format is not publicly documented.  We use a
    heuristic: walk the JSON tree looking for structures that contain
    two team names and numeric odds values (>1.0).
    """
    try:
        # Flatten the body into a list of candidate "event" dicts
        events = _find_event_list(body)
        if not events:
            return []

        results: list[MatchOdds] = []
        for evt in events:
            row = _parse_event(evt, url, league_name, sport_key, country_slug)
            if row:
                results.extend(row)

        return results
    except Exception as e:
        logger.debug("[Sisal] parse_response error for %s: %s", url, e)
        return []


def _find_event_list(obj: Any, depth: int = 0) -> list[dict]:
    """Recursively walk JSON looking for a list of event-like dicts."""
    if depth > 8:
        return []

    if isinstance(obj, list) and len(obj) >= 2:
        # Check if items look like events (have team-name-like strings)
        sample = obj[0] if obj else {}
        if isinstance(sample, dict) and _looks_like_event(sample):
            return obj

    if isinstance(obj, dict):
        for v in obj.values():
            found = _find_event_list(v, depth + 1)
            if found:
                return found

    if isinstance(obj, list):
        for item in obj:
            found = _find_event_list(item, depth + 1)
            if found:
                return found

    return []


def _looks_like_event(d: dict) -> bool:
    """Heuristic: does this dict look like a betting event?"""
    text = " ".join(str(v) for v in d.values() if isinstance(v, str)).lower()
    # Must contain at least one typical event field
    return any(k in d for k in ("descrizione", "evento", "avvenimento", "home", "away", "squadraCasa", "nomeCasa"))


def _parse_event(
    evt: dict,
    source_url: str,
    league_name: str,
    sport_key: str,
    country_slug: str,
) -> list[MatchOdds]:
    """Extract MatchOdds from a single event dict."""
    # --- team names ---
    home = (
        evt.get("squadraCasa") or evt.get("nomeCasa") or evt.get("home") or
        evt.get("teamHome") or evt.get("descrizione", "").split(" - ")[0]
    )
    away = (
        evt.get("squadraOspite") or evt.get("nomeOspite") or evt.get("away") or
        evt.get("teamAway") or evt.get("descrizione", "").split(" - ")[-1]
    )
    if not home or not away or home == away:
        return []

    home = home.strip()
    away = away.strip()

    # --- event time ---
    event_time = evt.get("dataOra") or evt.get("dataEvento") or evt.get("startDate") or None

    # --- event URL ---
    event_id = evt.get("idAvvenimento") or evt.get("id") or evt.get("eventId") or ""
    home_slug = _slugify(home)
    away_slug = _slugify(away)
    match_url = f"{BASE_URL}/scommesse-matchpoint/quote/{sport_key}/{home_slug}-{away_slug}"
    if event_id:
        match_url += f"?id={event_id}"

    # --- odds ---
    results: list[MatchOdds] = []

    # Try common 1X2 fields
    odds_1x2 = _extract_1x2(evt)
    if odds_1x2:
        results.append(MatchOdds(
            sport=sport_key,
            league=league_name,
            home_team=home,
            away_team=away,
            event_name=f"{home} - {away}",
            event_time=event_time,
            match_url=match_url,
            market="1X2",
            bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_1x2}],
        ))

    return results


def _extract_1x2(evt: dict) -> dict[str, float] | None:
    """Try to extract 1X2 odds from various possible field structures."""
    # Pattern 1: explicit quota1, quotaX, quota2
    q1 = _to_float(evt.get("quota1") or evt.get("q1") or evt.get("odd1") or evt.get("esitoUno"))
    qx = _to_float(evt.get("quotaX") or evt.get("qX") or evt.get("oddX") or evt.get("esitoX"))
    q2 = _to_float(evt.get("quota2") or evt.get("q2") or evt.get("odd2") or evt.get("esitoDue"))

    if q1 and qx and q2:
        return {"1": q1, "X": qx, "2": q2}

    # Pattern 2: odds inside a nested list/dict
    for key in ("quote", "odds", "esitiList", "pronostici", "scommesse"):
        if key in evt and isinstance(evt[key], list) and len(evt[key]) >= 3:
            vals = [_to_float(x) for x in evt[key][:3]]
            if all(v and v > 1.0 for v in vals):
                return {"1": vals[0], "X": vals[1], "2": vals[2]}

    return None


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(str(val).replace(",", "."))
        return f if f > 1.0 else None
    except (ValueError, TypeError):
        return None
