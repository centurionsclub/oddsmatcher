"""Main CentroQuote scraper — orchestrates the full scraping pipeline.

Flow:
  1. Navigate to each league listing page
  2. Scroll to load all lazy-loaded event rows
  3. Collect match detail URLs
  4. Navigate to each match detail page
  5. Parse bookmaker odds from the HTML
  6. Click market tabs to scrape additional markets (Over/Under, etc.)
  7. Return structured data for DB insertion
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import Page

from oddsmatcher_backend.config.leagues import League, get_leagues
from oddsmatcher_backend.config.markets import MARKETS_BY_SPORT, DEFAULT_MARKET, Market
from oddsmatcher_backend.config.settings import settings
from oddsmatcher_backend.scraper.browser import BrowserManager
from oddsmatcher_backend.scraper.page_helpers import prepare_page, scroll_to_load_all
from oddsmatcher_backend.scraper.parsers import extract_match_links, parse_bookmaker_odds
from oddsmatcher_backend.scraper.selectors import Selectors

logger = logging.getLogger(__name__)

BASE_URL = "https://www.centroquote.it"


@dataclass
class MatchOdds:
    """Structured result for a single match."""
    sport: str
    league: str
    home_team: str
    away_team: str
    event_name: str
    event_time: str | None
    match_url: str
    market: str
    bookmaker_odds: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ScrapeStats:
    leagues_scraped: int = 0
    matches_found: int = 0
    matches_scraped: int = 0
    matches_failed: int = 0
    total_odds_rows: int = 0


class CentroQuoteScraper:
    """Scrapes upcoming match odds from centroquote.it."""

    def __init__(self, browser: BrowserManager):
        self.browser = browser
        self.cfg = settings.scraper
        self.stats = ScrapeStats()

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        """Scrape all leagues for a given sport."""
        leagues = get_leagues(sport)
        if not leagues:
            logger.warning("No leagues configured for sport: %s", sport)
            return []

        logger.info("Scraping %d leagues for %s", len(leagues), sport)
        all_results: list[MatchOdds] = []

        for league in leagues:
            results = await self.scrape_league(league)
            all_results.extend(results)
            self.stats.leagues_scraped += 1

        logger.info(
            "Sport %s complete: %d leagues, %d matches scraped, %d failed",
            sport, self.stats.leagues_scraped, self.stats.matches_scraped, self.stats.matches_failed,
        )
        return all_results

    async def scrape_all(self) -> list[MatchOdds]:
        """Scrape all configured sports and leagues."""
        all_results: list[MatchOdds] = []
        for sport in MARKETS_BY_SPORT:
            results = await self.scrape_sport(sport)
            all_results.extend(results)
        return all_results

    async def scrape_league(self, league: League) -> list[MatchOdds]:
        """Scrape a single league: list matches then scrape each one."""
        page = self.browser.page
        url = BASE_URL + league.path
        logger.info("Scraping league: %s (%s)", league.name, url)

        try:
            await page.goto(url, timeout=self.cfg.page_load_timeout_ms, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            await prepare_page(page)
            await scroll_to_load_all(
                page,
                timeout_s=self.cfg.scroll_timeout_s,
                pause_s=self.cfg.scroll_pause_s,
                max_attempts=self.cfg.max_scroll_attempts,
            )
        except Exception as e:
            logger.error("Failed to load league page %s: %s", league.name, e)
            return []

        # Extract match links from the league listing
        html = await page.content()
        match_links = extract_match_links(html)

        if not match_links:
            # Fallback: try to get links directly via Playwright locators
            match_links = await self._extract_links_via_locator(page)

        self.stats.matches_found += len(match_links)
        logger.info("Found %d matches in %s", len(match_links), league.name)

        # Scrape each match detail page
        results: list[MatchOdds] = []
        markets = MARKETS_BY_SPORT.get(league.sport, [DEFAULT_MARKET.get(league.sport)])

        for i, link in enumerate(match_links):
            logger.info("[%d/%d] Scraping: %s", i + 1, len(match_links), link)
            try:
                match_results = await self._scrape_match(
                    match_url=link,
                    league=league,
                    markets=markets,
                )
                results.extend(match_results)
                self.stats.matches_scraped += 1
            except Exception as e:
                logger.error("Failed to scrape match %s: %s", link, e)
                self.stats.matches_failed += 1

            # Random delay between requests
            delay = self.cfg.request_delay_s + random.uniform(0, 1.0)  # noqa: S311
            await asyncio.sleep(delay)

        return results

    async def _extract_links_via_locator(self, page: Page) -> list[str]:
        """Fallback: extract match links using Playwright locators."""
        links = set()
        event_rows = page.locator(Selectors.EVENT_ROW)
        count = await event_rows.count()

        for i in range(count):
            row = event_rows.nth(i)
            anchors = row.locator("a[href]")
            a_count = await anchors.count()
            for j in range(a_count):
                href = await anchors.nth(j).get_attribute("href")
                if href and "/" in href and href.count("/") >= 3:
                    links.add(href)

        logger.info("Locator fallback found %d links", len(links))
        return sorted(links)

    async def _scrape_match(
        self,
        match_url: str,
        league: League,
        markets: list[Market],
    ) -> list[MatchOdds]:
        """Scrape a single match detail page for all configured markets."""
        full_url = match_url if match_url.startswith("http") else BASE_URL + match_url
        tab = await self.browser.new_tab()

        try:
            await tab.goto(full_url, timeout=self.cfg.page_load_timeout_ms, wait_until="domcontentloaded")
            await tab.wait_for_timeout(1500)

            # Extract match info (teams, time) from the page
            match_info = await self._extract_match_info(tab)
            home = match_info.get("home", "")
            away = match_info.get("away", "")
            event_time = match_info.get("time")
            event_name = f"{home} v {away}" if home and away else match_url.split("/")[-2].replace("-", " ")

            results: list[MatchOdds] = []

            for market in markets:
                # Click market tab if not the default
                if market != markets[0]:
                    clicked = await self._click_market_tab(tab, market.tab_label)
                    if not clicked:
                        logger.debug("Could not switch to market tab: %s", market.tab_label)
                        continue
                    await tab.wait_for_timeout(1000)

                html = await tab.content()
                bookmaker_odds = parse_bookmaker_odds(html, market.outcomes)

                if bookmaker_odds:
                    self.stats.total_odds_rows += len(bookmaker_odds)
                    results.append(MatchOdds(
                        sport=league.sport,
                        league=league.name,
                        home_team=home,
                        away_team=away,
                        event_name=event_name,
                        event_time=event_time,
                        match_url=match_url,
                        market=market.name,
                        bookmaker_odds=bookmaker_odds,
                    ))

            return results

        finally:
            await tab.close()

    async def _extract_match_info(self, page: Page) -> dict[str, str | None]:
        """Extract team names and kick-off time from a match detail page."""
        try:
            info = await page.evaluate("""() => {
                // Team names are usually in h1 or prominent heading
                const heading = document.querySelector('h1, [class*="teamHeader"]');
                let home = '', away = '';

                if (heading) {
                    const text = heading.textContent.trim();
                    const parts = text.split(/\\s*[-–]\\s*/);
                    if (parts.length >= 2) {
                        home = parts[0].trim();
                        away = parts[1].trim();
                    }
                }

                // If no heading, try participant-name elements
                if (!home) {
                    const participants = document.querySelectorAll('[class*="participant"], .truncate');
                    const names = Array.from(participants).map(el => el.textContent.trim()).filter(n => n.length > 1);
                    if (names.length >= 2) {
                        home = names[0];
                        away = names[1];
                    }
                }

                // Event time
                const timeEl = document.querySelector('[class*="startTime"], time, [class*="date-time"]');
                const time = timeEl ? timeEl.getAttribute('datetime') || timeEl.textContent.trim() : null;

                return { home, away, time };
            }""")
            return info
        except Exception as e:
            logger.debug("Could not extract match info: %s", e)
            return {}

    async def _click_market_tab(self, page: Page, tab_label: str) -> bool:
        """Click a market tab by its label text."""
        try:
            # Try the primary tab selector
            tabs = page.locator(Selectors.MARKET_TABS)
            count = await tabs.count()

            for i in range(count):
                tab = tabs.nth(i)
                text = (await tab.inner_text()).strip()
                if text.lower() == tab_label.lower():
                    await tab.click()
                    return True

            # Fallback: check "More" dropdown
            more_btn = page.locator(Selectors.MORE_BUTTON)
            if await more_btn.count() > 0:
                await more_btn.first.click()
                await page.wait_for_timeout(500)

                # Look for the market in the dropdown
                dropdown_item = page.locator(f"li:has-text('{tab_label}'), a:has-text('{tab_label}')")
                if await dropdown_item.count() > 0:
                    await dropdown_item.first.click()
                    return True

            logger.debug("Market tab '%s' not found", tab_label)
            return False

        except Exception as e:
            logger.debug("Failed to click market tab '%s': %s", tab_label, e)
            return False
