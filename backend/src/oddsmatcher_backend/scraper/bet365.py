"""Bet365 pre-match odds scraper — CDP (Chrome DevTools Protocol).

Connects to a real Chrome instance via CDP so Akamai Bot Manager is bypassed.
Chrome must be running with remote debugging enabled, OR this module will
auto-launch it.

Auto-launch command (run once, or let the scraper start it automatically):
    google-chrome --remote-debugging-port=9222 \\
                  --user-data-dir="$HOME/.bet365-chrome-profile" \\
                  --no-first-run --no-default-browser-check

Configuration
-------------
BET365_CDP_PORT  – CDP port (default: 9222)
BET365_URL       – Base URL of the bet365 site (default: https://www.bet365.it)
BET365_CHROME    – Path to Chrome/Chromium binary for auto-launch
                   (default: tries google-chrome, chromium, chromium-browser)
"""

import asyncio
import logging
import os
import shutil
import subprocess
import time
from typing import Any

from playwright.async_api import async_playwright

from oddsmatcher_backend.scraper.models import MatchOdds

logger = logging.getLogger(__name__)

# ── configuration ─────────────────────────────────────────────────────────────

BOOKMAKER  = "Bet365"
CDP_PORT   = int(os.environ.get("BET365_CDP_PORT", "9222"))
BASE_URL   = os.environ.get("BET365_URL", "https://www.bet365.it")
CDP_URL    = f"http://localhost:{CDP_PORT}"

# Seconds to wait after navigation for bet365 JS to render odds
_WAIT_AFTER_NAV = float(os.environ.get("BET365_WAIT_S", "15"))

# ── league definitions ────────────────────────────────────────────────────────
# (display_name, sport_key, url_fragment)
# /#/AS/B1/  = All Sports → Calcio
# /#/AS/B18/ = All Sports → Basket
# /#/AS/B13/ = All Sports → Tennis

LEAGUES: list[tuple[str, str, str]] = [
    ("Calcio",  "calcio", "/#/AS/B1/"),
    ("Basket",  "basket", "/#/AS/B18/"),
    ("Tennis",  "tennis", "/#/AS/B13/"),
]

# ── Chrome auto-launch ────────────────────────────────────────────────────────

_CHROME_CANDIDATES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]
_CHROME_PROFILE    = os.path.expanduser("~/.bet365-chrome-profile")

_chrome_proc: subprocess.Popen | None = None


def _find_chrome() -> str | None:
    """Return the path to the first available Chrome binary."""
    custom = os.environ.get("BET365_CHROME")
    if custom:
        return custom
    for name in _CHROME_CANDIDATES:
        path = shutil.which(name)
        if path:
            return path
    return None


def _chrome_is_running() -> bool:
    """Quick check: can we reach the CDP endpoint?"""
    import urllib.request
    try:
        urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=2)
        return True
    except Exception:
        return False


def _launch_chrome() -> bool:
    """Launch Chrome in the background.  Returns True if started."""
    global _chrome_proc
    if _chrome_is_running():
        logger.info("[Bet365] CDP already reachable on port %d", CDP_PORT)
        return True

    binary = _find_chrome()
    if not binary:
        logger.error(
            "[Bet365] No Chrome binary found. Install Chrome or set BET365_CHROME. "
            "Cannot auto-launch."
        )
        return False

    cmd = [
        binary,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={_CHROME_PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--disable-background-networking",
    ]
    logger.info("[Bet365] Launching Chrome: %s", " ".join(cmd))
    try:
        _chrome_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        logger.error("[Bet365] Failed to launch Chrome: %s", e)
        return False

    # Wait up to 10s for CDP to become available
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if _chrome_is_running():
            logger.info("[Bet365] Chrome ready on port %d", CDP_PORT)
            return True
        time.sleep(0.5)

    logger.error("[Bet365] Chrome launched but CDP not reachable after 10s")
    return False


# ── DOM text parser ───────────────────────────────────────────────────────────

def _parse_page_text(text: str, league_name: str, sport_key: str) -> list[MatchOdds]:
    """Parse bet365 innerText for a single sport page into MatchOdds rows.

    bet365 renders event rows roughly as:
        <team1>\\n<team2>\\n<date/time>\\n<odd1>\\n<oddX>\\n<odd2>   (soccer)
        <team1>\\n<team2>\\n<date/time>\\n<odd1>\\n<odd2>             (basket/tennis)

    We use a line-by-line heuristic:
    1. Detect price lines (numeric, 1.01–100, one decimal minimum).
    2. Work backwards from each price group to find team names and time.
    """
    import re

    # ── helpers ──
    _price_re = re.compile(r"^\d{1,3}[.,]\d{1,3}$")
    _time_re  = re.compile(r"^\d{1,2}:\d{2}$")
    _date_re  = re.compile(r"^\d{1,2}/\d{1,2}$")

    def is_price(s: str) -> bool:
        s = s.strip()
        if not _price_re.match(s):
            return False
        try:
            v = float(s.replace(",", "."))
            return 1.01 <= v <= 200
        except ValueError:
            return False

    def norm_price(s: str) -> float:
        return round(float(s.strip().replace(",", ".")), 3)

    is_soccer  = sport_key == "calcio"
    n_prices   = 3 if is_soccer else 2

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    results: list[MatchOdds] = []
    i = 0
    while i <= len(lines) - n_prices:
        # Look for a window of n_prices consecutive price lines
        if all(is_price(lines[i + k]) for k in range(n_prices)):
            prices = [norm_price(lines[i + k]) for k in range(n_prices)]

            # Scan backwards for time + two team names
            j = i - 1
            event_time = None
            teams: list[str] = []

            while j >= 0 and len(teams) < 2:
                tok = lines[j]
                if _time_re.match(tok) or _date_re.match(tok):
                    if event_time is None:
                        event_time = tok
                elif not is_price(tok) and len(tok) > 1 and not tok.isdigit():
                    teams.insert(0, tok)
                j -= 1

            if len(teams) < 2:
                i += n_prices
                continue

            home, away = teams[-2], teams[-1]
            event_name = f"{home} - {away}"

            if is_soccer:
                odds_dict: dict[str, float] = {"1": prices[0], "X": prices[1], "2": prices[2]}
                market = "1X2"
            else:
                odds_dict = {"1": prices[0], "2": prices[1]}
                market = "Moneyline"

            results.append(MatchOdds(
                sport=sport_key,
                league=league_name,
                home_team=home,
                away_team=away,
                event_name=event_name,
                event_time=event_time,
                match_url=BASE_URL,
                market=market,
                bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
            ))
            i += n_prices
        else:
            i += 1

    return results


# ── scraper class ─────────────────────────────────────────────────────────────

class Bet365Scraper:
    """CDP-based Bet365 scraper.

    Connects to an existing real Chrome session via CDP so that Akamai
    Bot Manager does not block the requests.  Falls back to auto-launching
    Chrome if none is running.
    """

    bookmaker_name = BOOKMAKER

    def __init__(self):
        self._log = logging.getLogger(f"{__name__}.Bet365Scraper")

    # ── public interface ──────────────────────────────────────────────────────

    async def scrape_all(self) -> list[MatchOdds]:
        """Scrape all supported sports."""
        return await self._run(None)

    async def scrape_sport(self, sport_key: str) -> list[MatchOdds]:
        """Scrape a single sport (e.g. 'calcio', 'basket', 'tennis')."""
        return await self._run(sport_key)

    # ── internals ─────────────────────────────────────────────────────────────

    async def _run(self, sport_filter: str | None) -> list[MatchOdds]:
        leagues = [lg for lg in LEAGUES if sport_filter is None or lg[1] == sport_filter]
        if not leagues:
            self._log.warning("[Bet365] No leagues to scrape for sport_filter=%s", sport_filter)
            return []

        # Ensure Chrome is available
        if not _launch_chrome():
            self._log.error("[Bet365] Cannot proceed without Chrome CDP")
            return []

        all_rows: list[MatchOdds] = []

        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.connect_over_cdp(CDP_URL)
            except Exception as e:
                self._log.error("[Bet365] CDP connect failed: %s", e)
                return []

            try:
                # Re-use the first context (real user profile) — don't create a new one
                contexts = browser.contexts
                if contexts:
                    ctx = contexts[0]
                else:
                    ctx = await browser.new_context()

                for league_name, sport_key, fragment in leagues:
                    try:
                        rows = await self._scrape_league(ctx, league_name, sport_key, fragment)
                        all_rows.extend(rows)
                        self._log.info("[Bet365] %-8s %d rows", sport_key, len(rows))
                    except Exception:
                        self._log.exception("[Bet365] Error scraping %s", league_name)

            finally:
                # Disconnect only — do NOT close the browser (it's the user's Chrome)
                await browser.close()

        self._log.info("[Bet365] Total: %d rows", len(all_rows))
        return all_rows

    async def _scrape_league(
        self,
        ctx: Any,
        league_name: str,
        sport_key: str,
        fragment: str,
    ) -> list[MatchOdds]:
        url = BASE_URL + fragment

        # Open a new tab so we don't disturb the user's browsing
        page = await ctx.new_page()
        try:
            self._log.info("[Bet365] Navigating to %s", url)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            except Exception as e:
                self._log.warning("[Bet365] %s: goto timeout/error (will still try): %s",
                                  league_name, type(e).__name__)

            # Wait for JS rendering — bet365 is heavily dynamic
            self._log.info("[Bet365] %s: waiting %.0fs for JS render…",
                           league_name, _WAIT_AFTER_NAV)
            await asyncio.sleep(_WAIT_AFTER_NAV)

            # Grab visible text
            try:
                text = await page.evaluate("document.body.innerText")
            except Exception as e:
                self._log.error("[Bet365] %s: could not read page text: %s", league_name, e)
                return []

            self._log.debug("[Bet365] %s: text length=%d", league_name, len(text))

            rows = _parse_page_text(text, league_name, sport_key)
            self._log.info("[Bet365] %s: parsed %d events", league_name, len(rows))
            return rows

        finally:
            await page.close()
