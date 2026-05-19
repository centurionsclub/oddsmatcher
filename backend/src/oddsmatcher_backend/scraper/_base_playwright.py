"""Base class for Playwright-based bookmaker scrapers.

All scrapers that use network interception share this logic:
- Browser lifecycle (_start / _stop)
- Per-league navigation with response capture
- Full debug logging (for API discovery on first run)
- Abstract parse_response() to be implemented per bookmaker
"""

import asyncio
import json as _json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, Response, async_playwright

from oddsmatcher_backend.scraper.centroquote import MatchOdds

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Static resource extensions to ignore in on_response
_SKIP_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".woff", ".woff2", ".css", ".ico", ".svg", ".webp", ".mp4")


class BasePlaywrightScraper(ABC):
    """Playwright + network-interception base scraper.

    Subclasses must define:
      bookmaker_name  – str, e.g. "Snai"
      base_url        – str, e.g. "https://www.snai.it"
      warmup_path     – str, homepage path for Akamai warm-up
      leagues         – list of (league_name, sport_key, page_path) tuples

    And implement:
      parse_response(url, body, league_name, sport_key) -> list[MatchOdds]
    """

    bookmaker_name: str = ""
    base_url: str = ""
    warmup_path: str = "/"
    leagues: list[tuple[str, str, str]] = []

    def __init__(self):
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._log = logging.getLogger(self.__class__.__module__ + "." + self.__class__.__name__)

    # ── browser lifecycle ──────────────────────────────────────────────

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
            self._log.info("[%s] Usando proxy: %s:%s", self.bookmaker_name, p.hostname, p.port)

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

        warmup_url = self.base_url + self.warmup_path
        self._log.info("[%s] Navigating to homepage for Akamai warm-up...", self.bookmaker_name)
        try:
            await self._page.goto(warmup_url, wait_until="domcontentloaded", timeout=30_000)
            await self._page.wait_for_timeout(4000)
            self._log.info("[%s] Homepage loaded — browser ready", self.bookmaker_name)
        except Exception as e:
            self._log.warning("[%s] Homepage warm-up failed: %s", self.bookmaker_name, e)

    async def _stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._page = self._context = self._browser = self._playwright = None

    # ── public API ────────────────────────────────────────────────────

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
        for league_name, sport_key, page_path in self.leagues:
            if sport and sport_key != sport:
                continue
            try:
                results = await self._scrape_league(league_name, sport_key, page_path)
                all_results.extend(results)
                n_events = len({r.event_name for r in results})
                self._log.info("[%s] %s — %d events, %d market rows",
                               self.bookmaker_name, league_name, n_events, len(results))
            except Exception as exc:
                self._log.error("[%s] %s failed: %s", self.bookmaker_name, league_name, exc, exc_info=True)
            await asyncio.sleep(0.5)

        self._log.info("[%s] Total match+market rows: %d", self.bookmaker_name, len(all_results))
        return all_results

    async def _scrape_league(
        self,
        league_name: str,
        sport_key: str,
        page_path: str,
    ) -> list[MatchOdds]:
        assert self._page is not None
        captured: list[dict[str, Any]] = []

        async def on_response(response: Response) -> None:
            url_lower = response.url.lower()
            if any(url_lower.endswith(ext) for ext in _SKIP_EXTS):
                return
            try:
                body = await response.json()
                captured.append({"url": response.url, "body": body})
            except Exception:
                pass

        self._page.on("response", on_response)

        url = self.base_url + page_path
        self._log.info("[%s] Loading %s", self.bookmaker_name, url)
        try:
            await self._page.goto(url, wait_until="networkidle", timeout=65_000)
            self._log.info("[%s] %s: networkidle raggiunto", self.bookmaker_name, league_name)
        except Exception as e:
            self._log.info("[%s] %s: networkidle timeout (atteso): %s",
                           self.bookmaker_name, league_name, type(e).__name__)

        await self._page.wait_for_timeout(3000)
        self._page.remove_listener("response", on_response)

        # ── debug logging ──
        final_url = self._page.url
        self._log.info("[%s] %s: final_url=%s", self.bookmaker_name, league_name, final_url)
        try:
            title = await self._page.title()
            self._log.info("[%s] %s: page title=%s", self.bookmaker_name, league_name, title)
        except Exception:
            pass
        try:
            html = await self._page.evaluate("document.documentElement.innerHTML")
            self._log.info("[%s] %s: HTML snippet=%.2000s", self.bookmaker_name, league_name, html)
        except Exception as ex:
            self._log.warning("[%s] %s: could not read HTML: %s", self.bookmaker_name, league_name, ex)

        self._log.info("[%s] %s: captured %d JSON responses",
                       self.bookmaker_name, league_name, len(captured))
        for item in captured:
            body = item["body"]
            if isinstance(body, dict):
                keys = list(body.keys())[:8]
            elif isinstance(body, list):
                keys = f"list[{len(body)}]"
                if body and isinstance(body[0], dict):
                    keys = f"list[{len(body)}] → {list(body[0].keys())[:6]}"
            else:
                keys = type(body).__name__
            preview = _json.dumps(body, ensure_ascii=False)[:500]
            self._log.info("[%s] CAPTURE url=%s keys=%s BODY=%s",
                           self.bookmaker_name, item["url"], keys, preview)

        # ── parse ──
        for item in captured:
            results = self.parse_response(item["url"], item["body"], league_name, sport_key)
            if results:
                self._log.info("[%s] %s: parsed %d rows from %s",
                               self.bookmaker_name, league_name, len(results), item["url"])
                return results

        self._log.warning("[%s] %s: no parseable response in %d captured",
                          self.bookmaker_name, league_name, len(captured))
        return []

    @abstractmethod
    def parse_response(
        self,
        url: str,
        body: Any,
        league_name: str,
        sport_key: str,
    ) -> list[MatchOdds]:
        """Try to extract MatchOdds from a captured JSON response."""
        ...
