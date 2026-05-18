"""Sisal pregame odds scraper.

Strategy: Playwright browser + DOM scraping.
Akamai Bot Manager blocks all API calls from CI runners, so we cannot
use network response interception.  Instead we navigate to each league
page and read the odds directly from the rendered DOM via page.evaluate().

Sisal renders event rows in the page HTML; each row contains team names
and 1X2 odds buttons.  We extract them with JS selectors after waiting
for the content to appear.
"""

import asyncio
import logging
import re
import unicodedata
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)

BASE_URL = "https://www.sisal.it"
BOOKMAKER = "Sisal"

# fmt: off
LEAGUES: list[tuple[str, str, str, str]] = [
    ("Serie A",          "calcio", "calcio/serie-a",               "italia"),
    ("Serie B",          "calcio", "calcio/serie-b",               "italia"),
    ("Champions League", "calcio", "calcio/calcio-champions-league","europa"),
    ("Europa League",    "calcio", "calcio/calcio-europa-league",   "europa"),
    ("Conference League","calcio", "calcio/calcio-conference-league","europa"),
    ("Premier League",   "calcio", "calcio/calcio-premier-league", "inghilterra"),
    ("La Liga",          "calcio", "calcio/calcio-la-liga",        "spagna"),
    ("Bundesliga",       "calcio", "calcio/calcio-bundesliga",     "germania"),
    ("Ligue 1",          "calcio", "calcio/calcio-ligue-1",        "francia"),
]
# fmt: on

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# JS che estrae le quote direttamente dal DOM di Sisal
_EXTRACT_JS = """
() => {
    const results = [];

    // Sisal usa elementi con data attributes o classi specifiche per gli eventi.
    // Proviamo diversi selettori comuni per i siti di scommesse italiani.

    // Selettore 1: righe evento con quote (struttura tipica Sisal)
    const eventSelectors = [
        '[data-testid*="event"]',
        '[class*="event-row"]',
        '[class*="EventRow"]',
        '[class*="avvenimento"]',
        '[class*="match-row"]',
        'article[class*="event"]',
    ];

    let eventRows = [];
    for (const sel of eventSelectors) {
        const found = document.querySelectorAll(sel);
        if (found.length > 0) {
            eventRows = Array.from(found);
            break;
        }
    }

    // Selettore 2: cerchiamo bottoni quota con valori numerici
    if (eventRows.length === 0) {
        // Cerca gruppi di 3 bottoni consecutivi con valori numerici (1X2)
        const allButtons = Array.from(document.querySelectorAll('button, [role="button"]'));
        const oddsButtons = allButtons.filter(b => {
            const txt = b.textContent.trim();
            return /^\\d+[.,]\\d+$/.test(txt) && parseFloat(txt.replace(',', '.')) > 1.0;
        });

        if (oddsButtons.length >= 3) {
            // Raggruppa in blocchi di 3 (1, X, 2)
            for (let i = 0; i <= oddsButtons.length - 3; i += 3) {
                const o1 = parseFloat(oddsButtons[i].textContent.replace(',', '.'));
                const ox = parseFloat(oddsButtons[i+1].textContent.replace(',', '.'));
                const o2 = parseFloat(oddsButtons[i+2].textContent.replace(',', '.'));
                if (o1 > 1 && ox > 1 && o2 > 1) {
                    results.push({
                        home: '', away: '', time: '',
                        odds1: o1, oddsX: ox, odds2: o2
                    });
                }
            }
        }
    }

    // Selettore 3: cerca testo con pattern "Squadra A - Squadra B" vicino a numeri quota
    if (results.length === 0) {
        const allText = document.body.innerText;
        const lines = allText.split('\\n').map(l => l.trim()).filter(l => l);
        let i = 0;
        while (i < lines.length) {
            const line = lines[i];
            // Pattern: "Team A - Team B" (almeno 5 caratteri per parte, separato da " - ")
            if (/ - /.test(line) && line.length > 6 && !/^\\d/.test(line)) {
                const parts = line.split(' - ');
                if (parts.length === 2 && parts[0].length > 2 && parts[1].length > 2) {
                    // Cerca le prossime righe con quote
                    let odds = [];
                    for (let j = i+1; j < Math.min(i+15, lines.length); j++) {
                        const m = lines[j].match(/^(\\d+[.,]\\d+)$/);
                        if (m) {
                            odds.push(parseFloat(m[1].replace(',', '.')));
                            if (odds.length === 3) break;
                        }
                    }
                    if (odds.length === 3 && odds.every(o => o > 1.0 && o < 50)) {
                        results.push({
                            home: parts[0].trim(),
                            away: parts[1].trim(),
                            time: '',
                            odds1: odds[0], oddsX: odds[1], odds2: odds[2]
                        });
                    }
                }
            }
            i++;
        }
    }

    // Log DOM snapshot per debug
    return {
        results: results,
        pageTitle: document.title,
        bodyLength: document.body.innerText.length,
        url: window.location.href,
        // Primi 800 chars del testo per debug
        bodyPreview: document.body.innerText.substring(0, 800),
    };
}
"""


def _slugify(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_str.lower()).strip("-")


class SisalScraper:
    """Scrapes pregame odds from Sisal via Playwright DOM scraping."""

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
            viewport={"width": 1280, "height": 900},
        )
        self._page = await self._context.new_page()

        logger.info("[Sisal] Navigating to homepage for Akamai warm-up...")
        try:
            await self._page.goto(
                f"{BASE_URL}/scommesse-matchpoint",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            await self._page.wait_for_timeout(4000)
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

        url = f"{BASE_URL}/scommesse-matchpoint/quote/{sisal_slug}"
        logger.info("[Sisal] Loading %s", url)

        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        except Exception as e:
            logger.warning("[Sisal] Page load issue for %s: %s", url, e)
            return []

        # Aspetta che gli elementi evento appaiano nel DOM (max 10s)
        try:
            await self._page.wait_for_timeout(6000)
        except Exception:
            pass

        # Estrae dati direttamente dal DOM
        try:
            dom_data = await self._page.evaluate(_EXTRACT_JS)
        except Exception as e:
            logger.warning("[Sisal] DOM extraction failed for %s: %s", league_name, e)
            return []

        logger.info(
            "[Sisal] %s: DOM title=%r bodyLen=%d url=%s",
            league_name,
            dom_data.get("pageTitle", "?"),
            dom_data.get("bodyLength", 0),
            dom_data.get("url", "?"),
        )
        logger.info("[Sisal] %s: BODY_PREVIEW=%s", league_name, dom_data.get("bodyPreview", "")[:400])

        raw_events = dom_data.get("results", [])
        logger.info("[Sisal] %s: extracted %d events from DOM", league_name, len(raw_events))

        return _build_match_odds(raw_events, league_name, sport_key, country_slug)


def _build_match_odds(
    raw_events: list[dict],
    league_name: str,
    sport_key: str,
    country_slug: str,
) -> list[MatchOdds]:
    results: list[MatchOdds] = []
    for evt in raw_events:
        home = (evt.get("home") or "").strip()
        away = (evt.get("away") or "").strip()
        if not home or not away or home == away:
            continue

        o1 = evt.get("odds1")
        ox = evt.get("oddsX")
        o2 = evt.get("odds2")
        if not (o1 and ox and o2 and o1 > 1.0 and ox > 1.0 and o2 > 1.0):
            continue

        event_name = f"{home} - {away}"
        event_time = evt.get("time") or None
        home_slug = _slugify(home)
        away_slug = _slugify(away)
        match_url = f"{BASE_URL}/scommesse-matchpoint/quote/{sport_key}/{home_slug}-{away_slug}"

        results.append(MatchOdds(
            sport=sport_key,
            league=league_name,
            home_team=home,
            away_team=away,
            event_name=event_name,
            event_time=event_time,
            match_url=match_url,
            market="1X2",
            bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": {"1": o1, "X": ox, "2": o2}}],
        ))

    return results
