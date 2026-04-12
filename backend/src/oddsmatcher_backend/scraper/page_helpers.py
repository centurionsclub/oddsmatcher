"""Reusable page-level helpers: cookie dismissal, scrolling, odds format."""

import logging

from playwright.async_api import Page

from oddsmatcher_backend.scraper.selectors import Selectors

logger = logging.getLogger(__name__)


async def dismiss_cookie_banner(page: Page) -> None:
    """Click the cookie consent button if present."""
    try:
        btn = page.locator(Selectors.COOKIE_ACCEPT)
        if await btn.count() > 0:
            await btn.click(timeout=3_000)
            logger.debug("Cookie banner dismissed")
    except Exception:
        pass  # Banner not present or already dismissed


async def set_odds_format_eu(page: Page) -> None:
    """Ensure decimal (EU) odds format is selected.

    CentroQuote shows EU by default for Italian locale, but we click it
    explicitly to be safe.
    """
    try:
        btn = page.locator(Selectors.ODDS_FORMAT_EU)
        if await btn.count() > 0:
            await btn.first.click(timeout=3_000)
            await page.wait_for_timeout(500)
            logger.debug("Odds format set to EU (decimal)")
    except Exception:
        logger.debug("Could not set odds format — likely already EU")


async def scroll_to_load_all(
    page: Page,
    timeout_s: int = 30,
    pause_s: float = 2.0,
    max_attempts: int = 5,
) -> bool:
    """Scroll down repeatedly until no new content loads (lazy-loading).

    Returns True if scrolling completed normally.
    """
    previous_height = 0
    attempts = 0

    while attempts < max_attempts:
        current_height = await page.evaluate("document.body.scrollHeight")
        if current_height == previous_height:
            break
        previous_height = current_height
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(int(pause_s * 1000))
        attempts += 1

    loaded = await page.locator(Selectors.CONTENT_CHECK).count()
    logger.debug("Scroll complete after %d attempts, %d event rows visible", attempts, loaded)
    return loaded > 0


async def prepare_page(page: Page) -> None:
    """One-shot page preparation: dismiss cookies + set odds format."""
    await dismiss_cookie_banner(page)
    await set_odds_format_eu(page)
