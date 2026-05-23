"""odds-api.io scraper — Bet365 and Eurobet IT.

Uses https://api.odds-api.io/v3 to fetch pre-match and live odds.
Replaces the failing Playwright-based tennis/basket scraping for Eurobet
and the centroquote.it-based scraper for Bet365.

Bookmaker names in the API:  "Bet365"  /  "Eurobet IT"
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from oddsmatcher_backend.scraper.models import MatchOdds

logger = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────

_API_KEY  = os.environ.get(
    "ODDSAPI_KEY",
    "2e79cb122e3b02e9ed206cd8f94119bc383e7e772b3251b3bbe63184dad30d99",
)
_BASE     = "https://api.odds-api.io/v3"
_TIMEOUT  = httpx.Timeout(30.0)
_SEM      = 20          # max concurrent requests per run
_BATCH    = 20          # events per asyncio.gather batch
_LIMIT    = 200         # max events to fetch from /events
_HORIZON  = 48         # hours ahead — only fetch odds for events within this window

# internal sport key → API slug
_SPORT_SLUG = {
    "calcio":  "football",
    "tennis":  "tennis",
    "basket":  "basketball",
}

# API market name → internal market key (None = skip)
_MARKET_KEY: dict[str, str | None] = {
    "1X2":                  "1X2",
    "ML":                   "1X2",   # moneyline (2-way or 3-way)
    "Moneyline":            "1X2",
    "Double Chance":        "DC",
    "Both Teams To Score":  "BTTS",
    "BTTS":                 "BTTS",
    "Goal/No Goal":         "BTTS",
    "Totals":               "OU",    # resolved with hdp below
    "Totals (Games)":       "OU",
    "Total":                "OU",
    "Total (Games)":        "OU",
    # skip everything else
    "Spread":               None,
    "Spread (Games)":       None,
    "Set Betting":          None,
    "Asian Handicap":       None,
    "Draw No Bet":          None,
}

# Only these O/U spreads for football; tennis/basket accept all
_FOOTBALL_OU = {0.5, 1.5, 2.5, 3.5, 4.5, 5.5}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _safe_float(val: Any) -> float | None:
    try:
        v = float(val)
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def _parse_odds(mkt_name: str, entry: dict, sport: str) -> tuple[str, dict[str, float]] | None:
    """Return (market_key, odds_dict) or None if this entry should be skipped."""
    raw_key = _MARKET_KEY.get(mkt_name)

    # Also handle "Totals XXX" patterns not explicitly listed
    if raw_key is None and mkt_name.startswith("Totals"):
        raw_key = "OU"
    if raw_key is None and mkt_name.startswith("Total"):
        raw_key = "OU"

    if raw_key is None:
        return None

    try:
        if raw_key == "1X2":
            home = _safe_float(entry.get("home"))
            away = _safe_float(entry.get("away"))
            draw = _safe_float(entry.get("draw"))
            if home is None or away is None:
                return None
            odds: dict[str, float] = {"1": home, "2": away}
            if draw is not None:
                odds["X"] = draw
            return "1X2", odds

        if raw_key == "DC":
            h1x = _safe_float(entry.get("home") or entry.get("homeAway"))
            x2  = _safe_float(entry.get("draw") or entry.get("awayDraw"))
            h12 = _safe_float(entry.get("away") or entry.get("homeAway2"))
            odds = {}
            if h1x: odds["1X"] = h1x
            if x2:  odds["X2"] = x2
            if h12: odds["12"] = h12
            return ("DC", odds) if len(odds) >= 2 else None

        if raw_key == "BTTS":
            yes = _safe_float(entry.get("home") or entry.get("yes"))
            no  = _safe_float(entry.get("away") or entry.get("no"))
            if yes is None or no is None:
                return None
            return "BTTS", {"Goal": yes, "No Goal": no}

        if raw_key == "OU":
            hdp   = entry.get("hdp")
            over  = _safe_float(entry.get("over"))
            under = _safe_float(entry.get("under"))
            if hdp is None or over is None or under is None:
                return None
            spread = float(hdp)
            if sport == "calcio" and spread not in _FOOTBALL_OU:
                return None
            return f"Over/Under {spread}", {"Over": over, "Under": under}

    except Exception:
        return None

    return None


def _parse_event(data: dict, sport: str, bookmaker_api: str, bookmaker_display: str) -> list[MatchOdds]:
    """Turn one /odds API response into MatchOdds rows."""
    bk_markets: list[dict] = data.get("bookmakers", {}).get(bookmaker_api, [])
    if not bk_markets:
        return []

    home       = data.get("home", "")
    away       = data.get("away", "")
    ev_name    = f"{home} - {away}"
    ev_time    = data.get("date")
    league     = data.get("league", {}).get("name", "")
    match_url  = (data.get("urls") or {}).get(bookmaker_api, "")

    results: list[MatchOdds] = []
    for market in bk_markets:
        mkt_name = market.get("name", "")
        for entry in market.get("odds", []):
            parsed = _parse_odds(mkt_name, entry, sport)
            if parsed is None:
                continue
            mkt_key, odds_dict = parsed
            results.append(MatchOdds(
                sport=sport,
                league=league,
                home_team=home,
                away_team=away,
                event_name=ev_name,
                event_time=ev_time,
                match_url=match_url or "",
                market=mkt_key,
                bookmaker_odds=[{"bookmaker": bookmaker_display, "odds": odds_dict}],
            ))

    return results


# ─── Main scraper class ───────────────────────────────────────────────────────

class OddsApiScraper:
    """Fetch pre-match odds from odds-api.io for given bookmakers + sports."""

    def __init__(
        self,
        bookmaker_api: str,        # name used by the API  e.g. "Bet365"
        bookmaker_display: str,    # name stored in DB      e.g. "Bet365"
        sports: list[str],         # internal keys          e.g. ["calcio","tennis","basket"]
    ) -> None:
        self._bk_api     = bookmaker_api
        self._bk_display = bookmaker_display
        self._sports     = sports
        self._sem        = asyncio.Semaphore(_SEM)

    @property
    def bookmaker_name(self) -> str:
        return self._bk_display

    async def scrape_all(self) -> list[MatchOdds]:
        async with httpx.AsyncClient(timeout=_TIMEOUT, http2=True) as client:
            tasks = [self._scrape_sport(client, s) for s in self._sports]
            all_rows = await asyncio.gather(*tasks, return_exceptions=True)

        results: list[MatchOdds] = []
        for sport, rows in zip(self._sports, all_rows):
            if isinstance(rows, Exception):
                logger.error("[%s] %s: %s", self._bk_display, sport, rows)
            else:
                logger.info("[%s] %s: %d rows", self._bk_display, sport, len(rows))
                results.extend(rows)

        return results

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        async with httpx.AsyncClient(timeout=_TIMEOUT, http2=True) as client:
            return await self._scrape_sport(client, sport)

    # ── internals ────────────────────────────────────────────────────────────

    async def _scrape_sport(self, client: httpx.AsyncClient, sport: str) -> list[MatchOdds]:
        slug = _SPORT_SLUG.get(sport, sport)
        event_ids = await self._get_event_ids(client, slug)
        logger.info("[%s] %s: %d events to check", self._bk_display, sport, len(event_ids))
        if not event_ids:
            return []

        results: list[MatchOdds] = []
        for i in range(0, len(event_ids), _BATCH):
            batch = event_ids[i : i + _BATCH]
            tasks = [self._fetch_odds(client, eid, sport) for eid in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in batch_results:
                if isinstance(r, list):
                    results.extend(r)
        return results

    async def _get_event_ids(self, client: httpx.AsyncClient, slug: str) -> list[int]:
        """Fetch event IDs for this sport, limited to the next _HORIZON hours."""
        async with self._sem:
            resp = await client.get(
                f"{_BASE}/events",
                params={"apiKey": _API_KEY, "sport": slug, "limit": _LIMIT},
            )
        if resp.status_code != 200:
            logger.warning("[%s] /events %s → %d", self._bk_display, slug, resp.status_code)
            return []

        events   = resp.json()
        now      = datetime.now(timezone.utc)
        cutoff   = now + timedelta(hours=_HORIZON)
        result: list[int] = []

        for e in events:
            if e.get("status") in ("settled", "cancelled", "postponed"):
                continue
            # Filter to events that start within the next _HORIZON hours
            date_str = e.get("date") or e.get("startTime") or e.get("commence_time")
            if date_str:
                try:
                    ev_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    if ev_dt > cutoff or ev_dt < now - timedelta(hours=3):
                        continue   # too far in future, or already finished
                except Exception:
                    pass           # no valid date → include anyway (safe fallback)
            result.append(e["id"])

        logger.info("[%s] /events %s: %d/%d events within next %dh",
                    self._bk_display, slug, len(result), len(events), _HORIZON)
        return result

    async def _fetch_odds(self, client: httpx.AsyncClient, event_id: int, sport: str) -> list[MatchOdds]:
        async with self._sem:
            try:
                resp = await client.get(
                    f"{_BASE}/odds",
                    params={
                        "apiKey":      _API_KEY,
                        "eventId":     event_id,
                        "bookmakers":  self._bk_api,
                    },
                )
            except Exception as exc:
                logger.debug("[%s] event %d: %s", self._bk_display, event_id, exc)
                return []

        if resp.status_code != 200:
            return []
        try:
            data = resp.json()
        except Exception:
            return []
        return _parse_event(data, sport, self._bk_api, self._bk_display)


# ─── Pre-configured scrapers ─────────────────────────────────────────────────

class Bet365Scraper:
    """Bet365 via odds-api.io — football, tennis, basketball."""

    bookmaker_name = "Bet365"

    def __init__(self) -> None:
        self._inner = OddsApiScraper(
            bookmaker_api="Bet365",
            bookmaker_display="Bet365",
            sports=["calcio", "tennis", "basket"],
        )

    async def scrape_all(self) -> list[MatchOdds]:
        return await self._inner.scrape_all()

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        return await self._inner.scrape_sport(sport)


class EurobetApiScraper:
    """Eurobet tennis + basket via odds-api.io (football handled by webeb)."""

    bookmaker_name = "Eurobet"

    def __init__(self) -> None:
        self._inner = OddsApiScraper(
            bookmaker_api="Eurobet IT",
            bookmaker_display="Eurobet",
            sports=["tennis", "basket"],
        )

    async def scrape_all(self) -> list[MatchOdds]:
        return await self._inner.scrape_all()

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        return await self._inner.scrape_sport(sport)
