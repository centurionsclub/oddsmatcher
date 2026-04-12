"""Playwright browser lifecycle management."""

import logging
from dataclasses import dataclass, field

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from oddsmatcher_backend.config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class BrowserManager:
    """Manages a single Playwright browser instance and context."""

    _playwright: Playwright | None = field(default=None, repr=False)
    _browser: Browser | None = field(default=None, repr=False)
    _context: BrowserContext | None = field(default=None, repr=False)
    _page: Page | None = field(default=None, repr=False)

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not initialized. Call start() first.")
        return self._page

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("Browser not initialized. Call start() first.")
        return self._context

    async def start(self) -> Page:
        """Launch browser and return the main page."""
        cfg = settings.scraper
        logger.info("Launching Playwright (headless=%s)", cfg.headless)

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=cfg.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": cfg.viewport_width, "height": cfg.viewport_height},
            locale=cfg.locale,
            timezone_id=cfg.timezone_id,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        self._page = await self._context.new_page()
        logger.info("Browser started successfully")
        return self._page

    async def new_tab(self) -> Page:
        """Open a new tab in the existing context."""
        return await self.context.new_page()

    async def stop(self):
        """Close browser and clean up."""
        if self._browser:
            await self._browser.close()
            logger.info("Browser closed")
        if self._playwright:
            await self._playwright.stop()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *exc):
        await self.stop()
