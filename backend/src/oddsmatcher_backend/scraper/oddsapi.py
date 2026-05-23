"""odds-api.io scraper — Bet365 and Eurobet IT.

Uses https://api.odds-api.io/v3 to fetch pre-match odds.

QUOTA MANAGEMENT
----------------
The API allows 100 requests/hour.  This module uses a single combined run:
  - /events  : 1 call per sport (3 total: football, tennis, basketball)
  - /odds    : 1 call per event, requesting BOTH bookmakers at once
                (bookmakers=Bet365,Eurobet IT)

Total per run  ≈  3 + N_events  (typically 50-90 for major leagues)
With a separate hourly workflow → well under 100 req/hour.

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

_API_KEY  = (
    os.environ.get("ODDSAPI_KEY")
    or "2e79cb122e3b02e9ed206cd8f94119bc383e7e772b3251b3bbe63184dad30d99"
)
_BASE     = "https://api.odds-api.io/v3"
_TIMEOUT  = httpx.Timeout(30.0)
_SEM        = 5         # max concurrent requests (throttle to avoid burst 429)
_BATCH      = 5         # events per asyncio.gather batch
_LIMIT      = 200       # max events to fetch from /events per sport

# Per-sport cap on /odds calls — ensures every sport is covered even when
# one sport (e.g. basket) has 150+ events that would crowd out the others.
# Sum must stay ≤ 94 so total calls (94 odds + 3 /events) < 100/hour quota.
_SPORT_CAP: dict[str, int] = {
    "calcio": 25,
    "tennis": 50,   # higher cap since league filter dramatically reduces candidates
    "basket": 44,
}

# League name substrings to SKIP — these are minor/amateur events that
# Bet365 and Eurobet IT almost never quote (wasted API calls).
# Matching is case-insensitive on the league name.
_LEAGUE_SKIP: dict[str, list[str]] = {
    "tennis": [
        "itf",          # ITF Futures/Challengers (e.g. "ITF Men - Hurghada")
        "challenger",   # ATP/WTA Challenger series
        "doubles",      # Doubles events (only singles are quoted)
        "mixed",        # Mixed doubles
        "juniors",
        "junior",
        "exhibition",
        "qualifying",
    ],
    "basket": [
        "wnba",
        "g league",
        "g-league",
        "nba 2k",
        "summer league",
    ],
    "calcio": [
        # Keep all football for now — 22 events is already small
    ],
}

# internal sport key → API slug
_SPORT_SLUG = {
    "calcio":  "football",
    "tennis":  "tennis",
    "basket":  "basketball",
}

# bookmakers to fetch: api_name → display_name
_BOOKMAKERS: dict[str, str] = {
    "Bet365":    "Bet365",
    "Eurobet IT": "Eurobet",
}

# sports per bookmaker (Eurobet has no calcio via this API — covered by webeb)
_BK_SPORTS: dict[str, list[str]] = {
    "Bet365":     ["calcio", "tennis", "basket"],
    "Eurobet IT": ["tennis", "basket"],
}

# API market name → internal market key (None = skip)
_MARKET_KEY: dict[str, str | None] = {
    "1X2":                  "1X2",
    "ML":                   "1X2",
    "Moneyline":            "1X2",
    "Double Chance":        "DC",
    "Both Teams To Score":  "BTTS",
    "BTTS":                 "BTTS",
    "Goal/No Goal":         "BTTS",
    "Totals":               "OU",
    "Totals (Games)":       "OU",
    "Total":                "OU",
    "Total (Games)":        "OU",
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


def _parse_event(
    data: dict,
    sport: str,
    bookmaker_api: str,
    bookmaker_display: str,
) -> list[MatchOdds]:
    """Turn one /odds API response into MatchOdds rows for a given bookmaker."""
    bk_markets: list[dict] = data.get("bookmakers", {}).get(bookmaker_api, [])
    if not bk_markets:
        return []

    home      = data.get("home", "")
    away      = data.get("away", "")
    ev_name   = f"{home} - {away}"
    ev_time   = data.get("date")
    league    = data.get("league", {}).get("name", "")
    match_url = (data.get("urls") or {}).get(bookmaker_api, "")

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


# ─── Combined scraper (minimises API requests) ───────────────────────────────

class CombinedOddsApiScraper:
    """Fetch Bet365 + Eurobet odds in a single pass.

    Strategy:
    - /events  called ONCE per sport  (3 total)
    - /odds    called ONCE per event, requesting both bookmakers together
               (bookmakers=Bet365,Eurobet IT)

    This keeps total requests ≈ 3 + N_events per run, vs the naive approach
    of 6 + 2N that exceeded the 100 req/hour quota.
    """

    def __init__(self) -> None:
        self._sem = asyncio.Semaphore(_SEM)

    async def scrape_all(self) -> dict[str, list[MatchOdds]]:
        """Return {"Bet365": [...], "Eurobet": [...]}."""
        all_sports = list(_SPORT_SLUG.keys())   # calcio, tennis, basket

        async with httpx.AsyncClient(timeout=_TIMEOUT, http2=True) as client:
            # ── 1. fetch event lists for each sport in parallel ──────────────
            # Returns list of (event_id, date_str, sport) tuples
            event_tasks = [self._get_events(client, sport) for sport in all_sports]
            all_events: list[tuple[int, str, str]] = []
            for res in await asyncio.gather(*event_tasks, return_exceptions=True):
                if isinstance(res, list):
                    all_events.extend(res)

            # Apply per-sport cap (nearest events first) so every sport gets
            # fair representation regardless of how many events each has.
            # e.g. basket might have 154 events but only takes its capped share,
            # leaving room for tennis and calcio.
            by_sport: dict[str, list[tuple[int, str, str]]] = {}
            for ev in all_events:
                by_sport.setdefault(ev[2], []).append(ev)

            all_events = []
            for sport_name, evs in by_sport.items():
                evs.sort(key=lambda x: x[1] or "9999-99-99")  # nearest first
                cap = _SPORT_CAP.get(sport_name, 30)
                taken = evs[:cap]
                logger.info("[OddsAPI] %s: using %d/%d events (cap=%d)",
                            sport_name, len(taken), len(evs), cap)
                all_events.extend(taken)

            logger.info("[OddsAPI] fetching odds for %d total events", len(all_events))

            # ── 2. fetch odds for all capped events in batches ───────────────
            results: dict[str, list[MatchOdds]] = {"Bet365": [], "Eurobet": []}

            for i in range(0, len(all_events), _BATCH):
                batch = all_events[i : i + _BATCH]
                tasks = []
                for ev_id, _date, sport in batch:
                    bks = [bk for bk, sports in _BK_SPORTS.items() if sport in sports]
                    bk_param = ",".join(bks)
                    tasks.append(self._fetch_odds(client, ev_id, sport, bk_param))

                for outcome in await asyncio.gather(*tasks, return_exceptions=True):
                    if not isinstance(outcome, dict):
                        continue
                    for bk_api, rows in outcome.items():
                        display = _BOOKMAKERS[bk_api]
                        results[display].extend(rows)

        # log summary per bookmaker and per sport
        for display, rows in results.items():
            n_ev = len({r.event_name for r in rows})
            by_sport_count: dict[str, int] = {}
            for r in rows:
                by_sport_count[r.sport] = by_sport_count.get(r.sport, 0) + 1
            logger.info("[OddsAPI] %s: %d events, %d rows | by sport: %s",
                        display, n_ev, len(rows), by_sport_count)
        return results

    # ── internals ────────────────────────────────────────────────────────────

    async def _get_events(
        self, client: httpx.AsyncClient, sport: str
    ) -> list[tuple[int, str, str]]:
        """Return list of (event_id, date_str, sport) for active events."""
        slug = _SPORT_SLUG[sport]
        async with self._sem:
            resp = await client.get(
                f"{_BASE}/events",
                params={"apiKey": _API_KEY, "sport": slug, "limit": _LIMIT},
            )
        if resp.status_code == 429:
            logger.error("[OddsAPI] /events %s → 429 rate limited (quota exhausted)", slug)
            return []
        if resp.status_code != 200:
            logger.warning("[OddsAPI] /events %s → %d", slug, resp.status_code)
            return []

        try:
            data = resp.json()
            if not isinstance(data, list):
                logger.warning("[OddsAPI] /events %s unexpected response: %s", slug, str(data)[:200])
                return []
        except Exception:
            return []

        skip_terms = [s.lower() for s in _LEAGUE_SKIP.get(sport, [])]
        result = []
        skipped = 0
        for e in data:
            if not isinstance(e, dict):
                continue
            if e.get("status") in ("settled", "cancelled", "postponed"):
                continue
            # Filter out minor leagues that bookmakers don't cover
            league_name = (e.get("league") or {}).get("name", "").lower()
            if skip_terms and any(t in league_name for t in skip_terms):
                skipped += 1
                continue
            date_str = e.get("date") or ""
            result.append((e["id"], date_str, sport))

        logger.info("[OddsAPI] /events %s: %d active events (%d skipped as minor leagues)",
                    slug, len(result), skipped)
        return result

    async def _fetch_odds(
        self,
        client: httpx.AsyncClient,
        event_id: int,
        sport: str,
        bk_param: str,          # e.g. "Bet365,Eurobet IT"
    ) -> dict[str, list[MatchOdds]]:
        """Fetch odds for one event and all bookmakers in one API call."""
        async with self._sem:
            try:
                resp = await client.get(
                    f"{_BASE}/odds",
                    params={
                        "apiKey":     _API_KEY,
                        "eventId":    event_id,
                        "bookmakers": bk_param,
                    },
                )
            except Exception as exc:
                logger.debug("[OddsAPI] event %d: %s", event_id, exc)
                return {}

        if resp.status_code == 429:
            logger.warning("[OddsAPI] event %d → 429 rate limited", event_id)
            return {}
        if resp.status_code != 200:
            return {}
        try:
            data = resp.json()
            if not isinstance(data, dict):
                return {}
        except Exception:
            return {}

        out: dict[str, list[MatchOdds]] = {}
        for bk_api in bk_param.split(","):
            bk_api = bk_api.strip()
            rows = _parse_event(data, sport, bk_api, _BOOKMAKERS[bk_api])
            if rows:
                out[bk_api] = rows
        return out


# ─── Legacy single-bookmaker scraper (kept for scrape_sport() compatibility) ─

class OddsApiScraper:
    """Single-bookmaker scraper — used by EurobetScraper.scrape_sport()."""

    def __init__(
        self,
        bookmaker_api: str,
        bookmaker_display: str,
        sports: list[str],
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
                results.extend(rows)
        return results

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        async with httpx.AsyncClient(timeout=_TIMEOUT, http2=True) as client:
            return await self._scrape_sport(client, sport)

    async def _scrape_sport(self, client: httpx.AsyncClient, sport: str) -> list[MatchOdds]:
        slug = _SPORT_SLUG.get(sport, sport)
        event_ids = await self._get_event_ids(client, slug)
        if not event_ids:
            return []
        results: list[MatchOdds] = []
        for i in range(0, len(event_ids), _BATCH):
            batch = event_ids[i : i + _BATCH]
            tasks = [self._fetch_odds(client, eid, sport) for eid in batch]
            for r in await asyncio.gather(*tasks, return_exceptions=True):
                if isinstance(r, list):
                    results.extend(r)
        return results

    async def _get_event_ids(self, client: httpx.AsyncClient, slug: str) -> list[int]:
        async with self._sem:
            resp = await client.get(
                f"{_BASE}/events",
                params={"apiKey": _API_KEY, "sport": slug, "limit": _LIMIT},
            )
        if resp.status_code != 200:
            return []
        return [
            e["id"] for e in resp.json()
            if e.get("status") not in ("settled", "cancelled", "postponed")
        ]

    async def _fetch_odds(self, client: httpx.AsyncClient, event_id: int, sport: str) -> list[MatchOdds]:
        async with self._sem:
            try:
                resp = await client.get(
                    f"{_BASE}/odds",
                    params={
                        "apiKey":     _API_KEY,
                        "eventId":    event_id,
                        "bookmakers": self._bk_api,
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


# ─── Pre-configured single-bookmaker scrapers (legacy, used by eurobet.py) ───

class Bet365Scraper:
    """Bet365 via odds-api.io — kept for backwards compatibility."""
    bookmaker_name = "Bet365"

    def __init__(self) -> None:
        self._inner = OddsApiScraper("Bet365", "Bet365", ["calcio", "tennis", "basket"])

    async def scrape_all(self) -> list[MatchOdds]:
        return await self._inner.scrape_all()

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        return await self._inner.scrape_sport(sport)


class EurobetApiScraper:
    """Eurobet tennis + basket via odds-api.io."""
    bookmaker_name = "Eurobet"

    def __init__(self) -> None:
        self._inner = OddsApiScraper("Eurobet IT", "Eurobet", ["tennis", "basket"])

    async def scrape_all(self) -> list[MatchOdds]:
        return await self._inner.scrape_all()

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        return await self._inner.scrape_sport(sport)
