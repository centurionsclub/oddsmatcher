"""Eurobet pregame odds scraper.

Strategy: Playwright browser + network response interception on eurobet.it.

Eurobet is a SPA that fires internal API calls when you navigate to a sport/league
page. We capture those JSON responses via Playwright's response event and parse them.
No direct HTTP calls from Python (Akamai blocks 403).

Flow per tournament:
  1. Navigate to the Eurobet tournament page
  2. Intercept ALL JSON responses from eurobet.it
  3. Log every response (URL + keys + 500-char body preview) for debugging
  4. Try to parse odds from known response shapes
  5. Return MatchOdds list

NOTE: The first GitHub Actions run will dump the full API structure in the logs.
      Update _parse_eurobet_response() once the actual format is known.
"""

import asyncio
import json as _json
import logging
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, Response, async_playwright

from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)

BASE_URL = "https://www.eurobet.it"
BOOKMAKER = "Eurobet"

# fmt: off
# (league_name, sport_key, page_path)
LEAGUES: list[tuple[str, str, str]] = [
    # Calcio
    ("Serie A",           "calcio", "/it/scommesse/sport/calcio/italy/serie-a/"),
    ("Serie B",           "calcio", "/it/scommesse/sport/calcio/italy/serie-b/"),
    ("Premier League",    "calcio", "/it/scommesse/sport/calcio/england/premier-league/"),
    ("La Liga",           "calcio", "/it/scommesse/sport/calcio/spain/la-liga/"),
    ("Bundesliga",        "calcio", "/it/scommesse/sport/calcio/germany/bundesliga/"),
    ("Ligue 1",           "calcio", "/it/scommesse/sport/calcio/france/ligue-1/"),
    ("Champions League",  "calcio", "/it/scommesse/sport/calcio/europe/champions-league/"),
    ("Europa League",     "calcio", "/it/scommesse/sport/calcio/europe/europa-league/"),
    ("Conference League", "calcio", "/it/scommesse/sport/calcio/europe/conference-league/"),
    # Basket
    ("NBA",               "basket", "/it/scommesse/sport/basket/usa/nba/"),
    ("Serie A Basket",    "basket", "/it/scommesse/sport/basket/italy/serie-a/"),
    # Tennis
    ("ATP",               "tennis", "/it/scommesse/sport/tennis/"),
]
# fmt: on

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Market name normalisation (Eurobet API name → canonical)
# Populated once we know the actual Eurobet API field names from logs.
SIMPLE_MARKET_MAP: dict[str, str] = {
    # 1X2 variants
    "1X2": "1X2",
    "Esito Finale": "1X2",
    "Testa A Testa": "1X2",
    "Testa a Testa": "1X2",
    "Match Result": "1X2",
    "Risultato Finale": "1X2",
    # Double Chance
    "Doppia Chance": "DC",
    "Double Chance": "DC",
    # BTTS
    "Goal/No Goal": "BTTS",
    "Gol/No Gol": "BTTS",
    "Both Teams to Score": "BTTS",
}

# Over/Under spreads we care about
UO_SPREADS_WANTED: set[str] = {"1.5", "2.5", "3.5"}


def _slugify(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_str.lower()).strip("-")


def _parse_eurobet_date(date_str: str) -> str | None:
    """Normalise a Eurobet date string to a UTC ISO-8601 string.

    Eurobet likely returns dates in Italian local time (CEST/CET).
    We try multiple formats and convert to UTC.
    """
    if not date_str:
        return None

    FORMATS = [
        "%Y-%m-%dT%H:%M:%S",   # "2026-05-20T20:30:00"
        "%Y-%m-%d %H:%M:%S",   # "2026-05-20 20:30:00"
        "%Y-%m-%d %H:%M",      # "2026-05-20 20:30"
        "%d/%m/%Y %H:%M:%S",   # "20/05/2026 20:30:00"
        "%d/%m/%Y %H:%M",      # "20/05/2026 20:30"
        "%d-%m-%Y %H:%M",      # "20-05-2026 20:30"
    ]
    for fmt in FORMATS:
        try:
            dt_naive = datetime.strptime(date_str.strip(), fmt)
            # Treat as Italian local time → UTC
            italy_offset = 2 if 3 <= dt_naive.month <= 10 else 1
            dt_local = dt_naive.replace(tzinfo=timezone(timedelta(hours=italy_offset)))
            return dt_local.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue

    # Try ISO with explicit timezone
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        pass

    return date_str  # unknown format — return unchanged


# ─── Scraper class ────────────────────────────────────────────────────────────

class EurobetScraper:
    """Scrapes pregame odds from Eurobet via Playwright network interception."""

    def __init__(self):
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
            logger.info("[Eurobet] Usando proxy: %s:%s", p.hostname, p.port)

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

        logger.info("[Eurobet] Navigating to homepage for Akamai warm-up...")
        try:
            await self._page.goto(
                f"{BASE_URL}/it/scommesse/",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            await self._page.wait_for_timeout(4000)
            logger.info("[Eurobet] Homepage loaded — browser ready")
        except Exception as e:
            logger.warning("[Eurobet] Homepage warm-up failed: %s", e)

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
        for league_name, sport_key, page_path in LEAGUES:
            if sport and sport_key != sport:
                continue
            try:
                results = await self._scrape_league(league_name, sport_key, page_path)
                all_results.extend(results)
                n_events = len({r.event_name for r in results})
                logger.info("[Eurobet] %s — %d events, %d market rows", league_name, n_events, len(results))
            except Exception as exc:
                logger.error("[Eurobet] %s failed: %s", league_name, exc, exc_info=True)
            await asyncio.sleep(0.5)

        logger.info("[Eurobet] Total match+market rows: %d", len(all_results))
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
            if "eurobet.it" not in response.url:
                return
            try:
                body = await response.json()
                captured.append({"url": response.url, "body": body})
            except Exception:
                pass

        self._page.on("response", on_response)

        url = BASE_URL + page_path
        logger.info("[Eurobet] Loading %s", url)
        try:
            await self._page.goto(url, wait_until="networkidle", timeout=65_000)
            logger.info("[Eurobet] %s: networkidle raggiunto", league_name)
        except Exception as e:
            logger.info("[Eurobet] %s: networkidle timeout (atteso): %s", league_name, type(e).__name__)

        await self._page.wait_for_timeout(500)
        self._page.remove_listener("response", on_response)

        logger.info("[Eurobet] %s: captured %d JSON responses", league_name, len(captured))

        # Log every captured response for first-run API discovery
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
            body_preview = _json.dumps(body, ensure_ascii=False)[:500]
            logger.info("[Eurobet] CAPTURE url=%s keys=%s BODY=%s", item["url"], keys, body_preview)

        # Try to parse a known structure from each captured response
        for item in captured:
            results = _parse_eurobet_response(
                item["url"], item["body"],
                league_name, sport_key,
            )
            if results:
                logger.info("[Eurobet] %s: parsed %d rows from %s", league_name, len(results), item["url"])
                return results

        logger.warning("[Eurobet] %s: no parseable response in %d captured", league_name, len(captured))
        return []


# ─── Response parsers ─────────────────────────────────────────────────────────

def _parse_eurobet_response(
    url: str,
    body: Any,
    league_name: str,
    sport_key: str,
) -> list[MatchOdds]:
    """Try multiple known Eurobet API shapes to extract MatchOdds.

    Eurobet's internal API has been observed to return data in several shapes.
    We try each in order and return the first non-empty result.
    """
    try:
        # Shape A: {"result": {"events": [...]}} or {"events": [...]}
        if isinstance(body, dict):
            events = (
                body.get("events")
                or body.get("result", {}).get("events")
                or body.get("data", {}).get("events") if isinstance(body.get("data"), dict) else None
                or body.get("data") if isinstance(body.get("data"), list) else None
            )
            if isinstance(events, list) and events:
                rows = _parse_events_list(events, league_name, sport_key)
                if rows:
                    return rows

        # Shape B: flat list of events at top level
        if isinstance(body, list) and body and isinstance(body[0], dict):
            rows = _parse_events_list(body, league_name, sport_key)
            if rows:
                return rows

        # Shape C: {"competitionEvents": [...]} or {"matchList": [...]}
        if isinstance(body, dict):
            for key in ("competitionEvents", "matchList", "matches", "fixtures", "avvenimenti"):
                val = body.get(key)
                if isinstance(val, list) and val:
                    rows = _parse_events_list(val, league_name, sport_key)
                    if rows:
                        return rows

        return []
    except Exception as e:
        logger.debug("[Eurobet] parse error for %s: %s", url, e)
        return []


def _parse_events_list(events: list, league_name: str, sport_key: str) -> list[MatchOdds]:
    """Parse a list of event dicts into MatchOdds.

    Tries common field name patterns used by Italian bookmaker APIs.
    """
    results: list[MatchOdds] = []
    for event in events:
        if not isinstance(event, dict):
            continue

        # ── Event name ──
        event_name = (
            event.get("eventDescription")
            or event.get("description")
            or event.get("name")
            or event.get("eventName")
            or event.get("descrizione")
            or ""
        )
        if not event_name:
            continue

        # Normalise "Team A - Team B" or "Team A v Team B"
        event_name = re.sub(r"\s+v\s+", " - ", event_name).strip()

        # ── Event time ──
        raw_time = (
            event.get("eventDate")
            or event.get("date")
            or event.get("startTime")
            or event.get("matchDate")
            or event.get("data")
            or ""
        )
        event_time = _parse_eurobet_date(str(raw_time)) if raw_time else None

        # ── Match URL (best-effort) ──
        match_url = (
            event.get("deepLink")
            or event.get("url")
            or event.get("link")
            or f"{BASE_URL}/it/scommesse/"
        )
        if match_url and not match_url.startswith("http"):
            match_url = BASE_URL + match_url

        # ── Markets / odds ──
        markets_raw = (
            event.get("markets")
            or event.get("market")
            or event.get("odds")
            or event.get("quote")
            or event.get("scommesse")
            or []
        )
        if isinstance(markets_raw, dict):
            markets_raw = list(markets_raw.values())

        market_rows = _parse_markets_list(markets_raw, event_name, event_time, league_name, sport_key, match_url)
        results.extend(market_rows)

    return results


def _parse_markets_list(
    markets: list,
    event_name: str,
    event_time: str | None,
    league_name: str,
    sport_key: str,
    match_url: str,
) -> list[MatchOdds]:
    results: list[MatchOdds] = []

    parts = event_name.split(" - ", 1)
    home = parts[0].strip() if len(parts) == 2 else event_name
    away = parts[1].strip() if len(parts) == 2 else ""

    for mkt in markets:
        if not isinstance(mkt, dict):
            continue

        # Market name
        market_name = (
            mkt.get("marketDescription")
            or mkt.get("description")
            or mkt.get("name")
            or mkt.get("marketName")
            or mkt.get("tipo")
            or ""
        ).strip()

        # ── 1X2 / DC / BTTS ──
        canonical = SIMPLE_MARKET_MAP.get(market_name)
        if canonical:
            selections = (
                mkt.get("selections")
                or mkt.get("outcomes")
                or mkt.get("odds")
                or mkt.get("esiti")
                or []
            )
            if isinstance(selections, dict):
                selections = list(selections.values())

            odds_dict = _extract_odds(selections, canonical)
            if odds_dict:
                mo = MatchOdds(
                    sport=sport_key, league=league_name,
                    home_team=home, away_team=away,
                    event_name=event_name, event_time=event_time,
                    match_url=match_url, market=canonical,
                    bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                )
                results.append(mo)
            continue

        # ── Over/Under ──
        if any(kw in market_name for kw in ("Over/Under", "Over Under", "U/O", "Totale Gol")):
            # Spread value may be in market name ("Over/Under 2.5") or in selections
            spread_match = re.search(r"(\d+[.,]\d+)", market_name)
            if spread_match:
                spread = spread_match.group(1).replace(",", ".")
                if spread in UO_SPREADS_WANTED:
                    selections = (
                        mkt.get("selections") or mkt.get("outcomes")
                        or mkt.get("odds") or mkt.get("esiti") or []
                    )
                    if isinstance(selections, dict):
                        selections = list(selections.values())
                    odds_dict = _extract_ou_odds(selections, spread)
                    if odds_dict:
                        results.append(MatchOdds(
                            sport=sport_key, league=league_name,
                            home_team=home, away_team=away,
                            event_name=event_name, event_time=event_time,
                            match_url=match_url, market=f"Over/Under {spread}",
                            bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                        ))
            else:
                # Spread might be per-selection
                selections = (
                    mkt.get("selections") or mkt.get("outcomes")
                    or mkt.get("odds") or mkt.get("esiti") or []
                )
                if isinstance(selections, dict):
                    selections = list(selections.values())
                _extract_ou_from_selections(
                    selections, event_name, event_time, league_name, sport_key, match_url,
                    home, away, results,
                )

    return results


def _extract_odds(selections: list, canonical_market: str) -> dict[str, float]:
    """Extract a {outcome: odds} dict from a selections list."""
    OUTCOME_MAP: dict[str, str] = {
        # 1X2
        "1": "1", "Home": "1", "Casa": "1",
        "X": "X", "Draw": "X", "Pareggio": "X",
        "2": "2", "Away": "2", "Ospite": "2",
        # DC
        "1X": "1X", "X2": "X2", "12": "12",
        # BTTS
        "Goal": "Goal", "GG": "Goal", "Si": "Goal", "Yes": "Goal",
        "No Goal": "No Goal", "NG": "No Goal", "No": "No Goal",
    }

    odds_dict: dict[str, float] = {}
    for sel in selections:
        if not isinstance(sel, dict):
            continue
        label = (
            sel.get("selectionDescription")
            or sel.get("description")
            or sel.get("name")
            or sel.get("outcome")
            or sel.get("esito")
            or ""
        ).strip()
        raw_odds = (
            sel.get("price")
            or sel.get("odds")
            or sel.get("quota")
            or sel.get("value")
        )
        if raw_odds is None:
            continue
        try:
            ov = float(raw_odds)
        except (TypeError, ValueError):
            continue
        if ov <= 1.0:
            continue

        outcome = OUTCOME_MAP.get(label, label)
        odds_dict[outcome] = ov

    return odds_dict


def _extract_ou_odds(selections: list, spread: str) -> dict[str, float]:
    """Extract Over/Under odds for a specific spread."""
    SIDE_MAP = {
        "Over": "Over", "Oltre": "Over", "O": "Over",
        "Under": "Under", "Meno": "Under", "U": "Under",
    }
    odds_dict: dict[str, float] = {}
    for sel in selections:
        if not isinstance(sel, dict):
            continue
        label = (
            sel.get("selectionDescription")
            or sel.get("description")
            or sel.get("name")
            or sel.get("outcome")
            or ""
        ).strip()
        raw_odds = sel.get("price") or sel.get("odds") or sel.get("quota") or sel.get("value")
        if raw_odds is None:
            continue
        try:
            ov = float(raw_odds)
        except (TypeError, ValueError):
            continue
        if ov <= 1.0:
            continue

        side = SIDE_MAP.get(label)
        if side:
            odds_dict[f"{side} {spread}"] = ov

    return odds_dict


def _extract_ou_from_selections(
    selections: list,
    event_name: str,
    event_time: str | None,
    league_name: str,
    sport_key: str,
    match_url: str,
    home: str,
    away: str,
    results: list[MatchOdds],
) -> None:
    """Handle Over/Under when the spread is embedded in each selection label."""
    # Group selections by spread (e.g. "Over 2.5" and "Under 2.5" → spread "2.5")
    import re as _re
    grouped: dict[str, dict[str, float]] = {}
    for sel in selections:
        if not isinstance(sel, dict):
            continue
        label = (
            sel.get("selectionDescription") or sel.get("description")
            or sel.get("name") or sel.get("outcome") or ""
        ).strip()
        raw_odds = sel.get("price") or sel.get("odds") or sel.get("quota") or sel.get("value")
        if raw_odds is None:
            continue
        try:
            ov = float(raw_odds)
        except (TypeError, ValueError):
            continue
        if ov <= 1.0:
            continue

        m = _re.match(r"^(Over|Under|Oltre|Meno)\s+(\d+[.,]\d+)$", label, re.IGNORECASE)
        if not m:
            continue
        side_raw, spread_raw = m.group(1), m.group(2).replace(",", ".")
        side = "Over" if side_raw.lower() in ("over", "oltre") else "Under"
        if spread_raw not in UO_SPREADS_WANTED:
            continue
        grouped.setdefault(spread_raw, {})[f"{side} {spread_raw}"] = ov

    for spread, odds_dict in grouped.items():
        if odds_dict:
            results.append(MatchOdds(
                sport=sport_key, league=league_name,
                home_team=home, away_team=away,
                event_name=event_name, event_time=event_time,
                match_url=match_url, market=f"Over/Under {spread}",
                bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
            ))
