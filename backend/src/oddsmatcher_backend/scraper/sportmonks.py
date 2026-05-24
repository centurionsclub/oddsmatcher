"""Bet365 pre-match odds via SportMonks API v3.

SportMonks API provides Bet365 (bookmaker_id=2) pre-match odds for football
fixtures. This scraper:
  1. Fetches upcoming fixtures (next 7 days) with participant and league info.
  2. For each fixture with odds available, fetches Bet365 odds for the key
     markets: 1X2, BTTS, and Over/Under.
  3. Returns MatchOdds objects compatible with write_direct_live_odds().

API docs: https://docs.sportmonks.com/football
Rate limit: 3000 req/hour (free plan) — well within limits.

NOTE: The free plan only provides odds for a limited set of leagues.
A paid plan subscription unlocks all major European leagues (Serie A,
Premier League, Bundesliga, etc.).
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from oddsmatcher_backend.scraper.models import MatchOdds

logger = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

_API_KEY = (
    os.environ.get("SPORTMONKS_KEY")
    or "8aeFToFxZZFoDeZUhOKwAYmxaq2JvSPFc7ifQqQYrHuW3UpudxC5BumKTFxI"
)
_BASE    = "https://api.sportmonks.com/v3/football"
_TIMEOUT = httpx.Timeout(30.0)
_SEM     = 5          # max concurrent fixture-odds API calls
_DAYS    = 7          # look-ahead window for upcoming fixtures

# Bet365 bookmaker_id in SportMonks
_BET365_ID = 2

# SportMonks market_id → internal key (None = skip)
_MARKET_ID_KEY: dict[int, str] = {
    1:  "1X2",       # Full Time Result  (labels: Home / Draw / Away)
    14: "BTTS",      # Both Teams to Score (labels: Yes / No)
    80: "OU",        # Goals Over/Under    (labels: Over / Under; total in 'total' field)
}

# Only fetch these markets from the API (comma-separated list for filter param)
_MARKET_FILTER = ",".join(str(m) for m in _MARKET_ID_KEY)

# For Over/Under: only these spreads matter for football
_FOOTBALL_OU_SPREADS = {0.5, 1.5, 2.5, 3.5, 4.5}

# market_id=1 label → MatchOdds outcome key
_FTR_LABEL: dict[str, str] = {
    "Home": "1",
    "Draw": "X",
    "Away": "2",
}

# market_id=14 label → MatchOdds outcome key
_BTTS_LABEL: dict[str, str] = {
    "Yes": "Goal",
    "No":  "No Goal",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe_float(val: Any) -> float | None:
    try:
        v = float(val)
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def _parse_event_time(starting_at: str | None) -> str | None:
    """Convert SportMonks 'YYYY-MM-DD HH:MM:SS' UTC to ISO-8601 string."""
    if not starting_at:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(starting_at, fmt).replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            pass
    return starting_at


def _parse_participants(participants: list[dict]) -> tuple[str, str]:
    """Return (home_name, away_name) from the participants include."""
    home = away = ""
    for p in participants:
        loc = (p.get("meta") or {}).get("location", "")
        if loc == "home":
            home = p.get("name", "")
        elif loc == "away":
            away = p.get("name", "")
    return home, away


def _build_match_odds(
    fixture: dict,
    raw_odds: list[dict],
) -> list[MatchOdds]:
    """Turn SportMonks fixture + raw Bet365 odds into MatchOdds rows."""
    participants = fixture.get("participants") or []
    home_team, away_team = _parse_participants(participants)
    league_obj  = fixture.get("league") or {}
    league_name = league_obj.get("name", "Unknown")
    fixture_name = fixture.get("name", f"{home_team} - {away_team}")
    event_time   = _parse_event_time(fixture.get("starting_at"))
    match_url    = "https://www.bet365.com"

    # Group by (market_id, total) to build one entry per spread
    from collections import defaultdict
    groups: dict[tuple[int, str | None], dict[str, float]] = defaultdict(dict)

    for odd in raw_odds:
        mid   = odd.get("market_id")
        label = odd.get("label", "")
        value = _safe_float(odd.get("value"))
        total = odd.get("total")  # e.g. "2.5" for Over/Under, None otherwise

        if mid not in _MARKET_ID_KEY or value is None:
            continue

        key = (mid, str(total) if total is not None else None)

        if mid == 1:  # 1X2
            outcome = _FTR_LABEL.get(label)
            if outcome:
                groups[key][outcome] = value

        elif mid == 14:  # BTTS
            outcome = _BTTS_LABEL.get(label)
            if outcome:
                groups[key][outcome] = value

        elif mid == 80:  # Over/Under
            if label in ("Over", "Under") and total is not None:
                groups[key][label] = value

    results: list[MatchOdds] = []
    for (mid, total_str), odds_dict in groups.items():
        if not odds_dict:
            continue

        if mid == 1:
            # 1X2 must have at least home+away
            if "1" not in odds_dict or "2" not in odds_dict:
                continue
            market_key = "1X2"

        elif mid == 14:
            if len(odds_dict) < 2:
                continue
            market_key = "BTTS"

        elif mid == 80:
            if len(odds_dict) < 2 or total_str is None:
                continue
            try:
                spread = float(total_str)
            except ValueError:
                continue
            if spread not in _FOOTBALL_OU_SPREADS:
                continue
            market_key = f"Over/Under {spread}"

        else:
            continue

        results.append(MatchOdds(
            sport="calcio",
            league=league_name,
            home_team=home_team,
            away_team=away_team,
            event_name=fixture_name,
            event_time=event_time,
            match_url=match_url,
            market=market_key,
            bookmaker_odds=[{
                "bookmaker": "Bet365",
                "url": match_url,
                "odds": odds_dict,
            }],
        ))

    return results


# ─── API client ───────────────────────────────────────────────────────────────

async def _fetch_json(client: httpx.AsyncClient, url: str, params: dict) -> dict:
    params["api_token"] = _API_KEY
    resp = await client.get(url, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


async def _fetch_fixture_odds(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    fixture: dict,
) -> list[MatchOdds]:
    """Fetch Bet365 odds for a single fixture and return MatchOdds rows."""
    fid = fixture["id"]
    async with sem:
        try:
            data = await _fetch_json(
                client,
                f"{_BASE}/odds/pre-match/fixtures/{fid}",
                {
                    "filters": f"bookmakers:{_BET365_ID};markets:{_MARKET_FILTER}",
                    "per_page": 100,
                },
            )
        except httpx.HTTPStatusError as exc:
            logger.warning("[SportMonks] Fixture %s odds error: %s", fid, exc.response.status_code)
            return []
        except Exception as exc:
            logger.warning("[SportMonks] Fixture %s odds failed: %s", fid, exc)
            return []

    raw_odds = data.get("data") or []
    if not raw_odds:
        return []

    rows = _build_match_odds(fixture, raw_odds)
    if rows:
        logger.debug(
            "[SportMonks] Fixture %s (%s): %d MatchOdds rows",
            fid, fixture.get("name", "?"), len(rows),
        )
    return rows


# ─── Scraper class ────────────────────────────────────────────────────────────

class SportmonksScraper:
    """Fetches Bet365 pre-match football odds from the SportMonks API."""

    async def scrape_all(self) -> list[MatchOdds]:
        """Scrape all available sports. SportMonks covers football only."""
        return await self._scrape()

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        """Scrape a single sport. Only 'calcio' is supported."""
        if sport and sport != "calcio":
            logger.info("[SportMonks] sport=%s not supported (calcio only)", sport)
            return []
        return await self._scrape()

    async def _scrape(self) -> list[MatchOdds]:
        now      = datetime.now(timezone.utc)
        date_from = now.strftime("%Y-%m-%d")
        date_to   = (now + timedelta(days=_DAYS)).strftime("%Y-%m-%d")

        async with httpx.AsyncClient() as client:
            # ── 1. Fetch upcoming fixtures ─────────────────────────────────────
            fixtures = await self._fetch_all_fixtures(client, date_from, date_to)
            logger.info(
                "[SportMonks] %d upcoming fixtures (%s → %s), %d with odds",
                len(fixtures),
                date_from,
                date_to,
                sum(1 for f in fixtures if f.get("has_odds")),
            )

            # ── 2. Fetch Bet365 odds for each fixture ─────────────────────────
            sem = asyncio.Semaphore(_SEM)
            tasks = [
                _fetch_fixture_odds(client, sem, f)
                for f in fixtures
                if f.get("has_odds")
            ]
            results_nested = await asyncio.gather(*tasks, return_exceptions=True)

        results: list[MatchOdds] = []
        for r in results_nested:
            if isinstance(r, Exception):
                logger.error("[SportMonks] Task error: %s", r)
            else:
                results.extend(r)

        logger.info(
            "[SportMonks] Total: %d MatchOdds rows from %d fixtures",
            len(results),
            len(tasks),
        )
        return results

    async def _fetch_all_fixtures(
        self,
        client: httpx.AsyncClient,
        date_from: str,
        date_to: str,
    ) -> list[dict]:
        """Paginate through all fixtures in the date range."""
        fixtures: list[dict] = []
        page = 1
        while True:
            try:
                data = await _fetch_json(
                    client,
                    f"{_BASE}/fixtures/between/{date_from}/{date_to}",
                    {
                        "include": "participants;league",
                        "per_page": 100,
                        "page": page,
                    },
                )
            except Exception as exc:
                logger.error("[SportMonks] Fixtures fetch error (page %d): %s", page, exc)
                break

            batch = data.get("data") or []
            fixtures.extend(batch)

            pagination = data.get("pagination") or {}
            if not pagination.get("has_more"):
                break
            page += 1

        return fixtures
