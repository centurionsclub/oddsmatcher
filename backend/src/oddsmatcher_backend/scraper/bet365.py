"""Bet365 pre-match odds scraper — OddspAPI.io (smart tournament filter).

Uses the OddspAPI.io REST API (v4) to fetch Bet365 odds for soccer, basketball
and tennis.  Only the top leagues are fetched, keeping the total number of API
calls to ~4–6 per full scrape (vs 100+ with the naive all-tournaments approach).

Configuration
-------------
ODDSPAPI_KEY   – API key (default: bundled key)
ODDSPAPI_DAYS  – look-ahead window in days (default: 7, max: 9)
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from oddsmatcher_backend.scraper.models import MatchOdds

logger = logging.getLogger(__name__)

# ── configuration ─────────────────────────────────────────────────────────────

BOOKMAKER = "Bet365"
API_KEY   = os.environ.get("ODDSPAPI_KEY", "9decc47d-a843-485d-9706-0ab370da052d")
API_BASE  = "https://api.oddspapi.io/v4"

_LOOKAHEAD_DAYS = min(int(os.environ.get("ODDSPAPI_DAYS", "7")), 9)

# ── market definitions ─────────────────────────────────────────────────────────

_SOCCER_1X2 = {101: {101: "1", 102: "X", 103: "2"}}
_BASKET_ML  = {111: {111: "1", 112: "2"}}
_TENNIS_ML  = {121: {121: "1", 122: "2"}}

# ── tournament name filter ─────────────────────────────────────────────────────
# Only fetch odds for tournaments whose name contains at least one of these
# keywords (case-insensitive substring match).
# Empty list = accept ALL tournaments for that sport (used for tennis).

_WANTED_NAMES: dict[str, list[str]] = {
    "calcio": [
        "serie a", "serie b",
        "premier league",
        "la liga", "primera division",
        "bundesliga",
        "ligue 1",
        "champions league",
        "europa league",
        "conference league",
        "fa cup", "coppa italia",
    ],
    "basket": [
        "nba", "euroleague", "eurolega", "serie a",
    ],
    "tennis": [],   # ← empty: accept all ATP/WTA/Challenger tournaments
}

# ── sport descriptors ──────────────────────────────────────────────────────────

@dataclass
class _Sport:
    key: str
    sport_id: int
    markets: dict
    market_label: str

_SPORTS = [
    _Sport("calcio", 10, _SOCCER_1X2, "1X2"),
    _Sport("basket", 11, _BASKET_ML,  "Moneyline"),
    _Sport("tennis", 12, _TENNIS_ML,  "Moneyline"),
]
_SPORT_BY_KEY = {s.key: s for s in _SPORTS}

# ── helpers ────────────────────────────────────────────────────────────────────

async def _get_json(client: httpx.AsyncClient, url: str, params: dict) -> Any:
    """GET + parse JSON, with automatic retry on 429."""
    for attempt in range(3):
        resp = await client.get(url, params=params)
        if resp.status_code == 429:
            retry_sec = 2.0
            try:
                data = resp.json()
                retry_sec = float(data.get("error", {}).get("retryMs", 2000)) / 1000 + 0.1
            except Exception:
                pass
            logger.debug("Rate-limited, waiting %.1fs (attempt %d)", retry_sec, attempt + 1)
            await asyncio.sleep(retry_sec)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"Failed after retries: GET {url}")


def _date_range():
    today = datetime.now(timezone.utc).date()
    end   = today + timedelta(days=_LOOKAHEAD_DAYS)
    return today.isoformat(), end.isoformat()


def _extract_odds(odds_fixture: dict, sport: _Sport) -> list[MatchOdds] | None:
    b365 = odds_fixture.get("bookmakerOdds", {}).get("bet365")
    if not b365 or not b365.get("bookmakerIsActive"):
        return None
    if b365.get("suspended"):
        return None

    markets_data = b365.get("markets", {})
    results: list[MatchOdds] = []

    for market_id, outcome_map in sport.markets.items():
        mdata = markets_data.get(str(market_id))
        if not mdata or not mdata.get("marketActive"):
            continue

        outcomes_data = mdata.get("outcomes", {})
        odds_dict: dict[str, float] = {}

        for oid, label in outcome_map.items():
            o = outcomes_data.get(str(oid), {})
            player = o.get("players", {}).get("0", {})
            price = player.get("price")
            if price and price > 1.0 and player.get("active"):
                odds_dict[label] = round(float(price), 3)

        min_outcomes = 2 if sport.market_label == "Moneyline" else 3
        if len(odds_dict) < min_outcomes:
            continue

        results.append(MatchOdds(
            sport=sport.key,
            league="",
            home_team="",
            away_team="",
            event_name="",
            event_time=odds_fixture.get("startTime"),
            match_url=b365.get("fixturePath", "https://www.bet365.it"),
            market=sport.market_label,
            bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
        ))

    return results if results else None


# ── scraper class ──────────────────────────────────────────────────────────────

class Bet365Scraper:
    """OddspAPI-based Bet365 scraper with smart tournament name filtering.

    Fetches only the top leagues (Serie A, Premier League, NBA, etc.) instead
    of all tournaments, reducing API calls from 100+ to ~4–6 per full scrape.
    """

    bookmaker_name = BOOKMAKER

    def __init__(self):
        self._log = logging.getLogger(f"{__name__}.Bet365Scraper")

    async def scrape_all(self) -> list[MatchOdds]:
        rows: list[MatchOdds] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for sport in _SPORTS:
                try:
                    sport_rows = await self._scrape_sport_obj(client, sport)
                    rows.extend(sport_rows)
                    self._log.info("[Bet365] %-8s %d rows", sport.key, len(sport_rows))
                except Exception:
                    self._log.exception("[Bet365] Error scraping %s", sport.key)
        self._log.info("[Bet365] Total: %d rows", len(rows))
        return rows

    async def scrape_sport(self, sport_key: str) -> list[MatchOdds]:
        sport = _SPORT_BY_KEY.get(sport_key)
        if not sport:
            self._log.warning("[Bet365] Unknown sport key: %s", sport_key)
            return []
        async with httpx.AsyncClient(timeout=30) as client:
            return await self._scrape_sport_obj(client, sport)

    async def _scrape_sport_obj(self, client: httpx.AsyncClient, sport: _Sport) -> list[MatchOdds]:
        date_from, date_to = _date_range()

        # ── Step 1: fetch fixtures (1 API call) ───────────────────────────────
        self._log.info("[Bet365] %s: fetching fixtures %s → %s", sport.key, date_from, date_to)
        try:
            fixtures_raw = await _get_json(client, f"{API_BASE}/fixtures", {
                "sportId": sport.sport_id,
                "from":    date_from,
                "to":      date_to,
                "apiKey":  API_KEY,
            })
        except Exception:
            self._log.exception("[Bet365] %s: fixtures fetch failed", sport.key)
            return []

        if not isinstance(fixtures_raw, list):
            self._log.warning("[Bet365] %s: unexpected fixtures response: %s", sport.key, fixtures_raw)
            return []

        self._log.info("[Bet365] %s: %d total fixtures", sport.key, len(fixtures_raw))

        # ── Step 2: build tournament ID → name map, apply name filter ─────────
        fixture_map: dict[str, dict] = {f["fixtureId"]: f for f in fixtures_raw}

        tid_to_name: dict[int, str] = {}
        for f in fixtures_raw:
            tid   = f.get("tournamentId")
            tname = (f.get("tournamentName") or "").strip()
            if tid is not None and tid not in tid_to_name:
                tid_to_name[int(tid)] = tname

        wanted_kws = _WANTED_NAMES.get(sport.key, [])
        if wanted_kws:
            tournament_ids = [
                tid for tid, tname in tid_to_name.items()
                if any(kw in tname.lower() for kw in wanted_kws)
            ]
        else:
            # No filter (e.g. tennis) — sort by fixture count, hard-cap at 50 tournaments
            from collections import Counter
            tid_counts = Counter(int(f["tournamentId"]) for f in fixtures_raw)
            tournament_ids = [tid for tid, _ in tid_counts.most_common(50)]

        self._log.info(
            "[Bet365] %s: %d/%d tournaments selected (filter=%s)",
            sport.key, len(tournament_ids), len(tid_to_name),
            bool(wanted_kws),
        )

        if not tournament_ids:
            self._log.warning("[Bet365] %s: no matching tournaments — check _WANTED_NAMES", sport.key)
            return []

        # ── Step 3: fetch odds in batches of 5 (few calls with name filter) ───
        rows: list[MatchOdds] = []

        for i in range(0, len(tournament_ids), 5):
            batch = tournament_ids[i : i + 5]
            if i > 0:
                await asyncio.sleep(1.1)   # respect 1000ms rate-limit

            try:
                odds_raw = await _get_json(client, f"{API_BASE}/odds-by-tournaments", {
                    "bookmaker":     "bet365",
                    "tournamentIds": ",".join(str(x) for x in batch),
                    "apiKey":        API_KEY,
                })
            except Exception:
                self._log.debug("[Bet365] %s: batch %d failed, skipping", sport.key, i // 5)
                continue

            if not isinstance(odds_raw, list):
                continue

            for odds_fixture in odds_raw:
                partial = _extract_odds(odds_fixture, sport)
                if not partial:
                    continue

                fixture_id = odds_fixture.get("fixtureId", "")
                fdata = fixture_map.get(fixture_id, {})
                p1_id = odds_fixture.get("participant1Id")
                p2_id = odds_fixture.get("participant2Id")

                home = (fdata.get("participant1Name") or fdata.get("participant1ShortName")
                        or f"Team {p1_id}")
                away = (fdata.get("participant2Name") or fdata.get("participant2ShortName")
                        or f"Team {p2_id}")
                league = fdata.get("tournamentName", "")

                for mo in partial:
                    mo.home_team  = home
                    mo.away_team  = away
                    mo.event_name = f"{home} - {away}"
                    mo.league     = league

                rows.extend(partial)

        self._log.info("[Bet365] %s: %d rows extracted", sport.key, len(rows))
        return rows
