"""Multi-bookmaker odds scraper via The Odds API (the-odds-api.com).

Fetches Pinnacle, Codere IT and MarathonBet pre-match odds with a single HTTP
request per sport.  One call returns ALL bookmakers × ALL events, so it is
extremely credit-efficient.

Included bookmakers (all available in EU region):
  pinnacle    – the sharpest reference book; ideal for value-bet calculations
  codere_it   – Italian bookmaker (not otherwise in our system)
  marathonbet – European bookmaker

Configuration
-------------
THEODDSAPI_KEY  – API key (default: bundled key, 500 free requests/month)
THEODDSAPI_BKS  – comma-separated bookmaker keys to include
                  (default: pinnacle,codere_it,marathonbet)

Credit usage: 1 request per sport key (regardless of bookmaker count).
With ~12 sports per full scrape, use sparingly — ideally max 2×/day on the
free plan, or upgrade to the $10/month Starter (10 000 req/month).
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from oddsmatcher_backend.scraper.models import MatchOdds

logger = logging.getLogger(__name__)

# ── configuration ──────────────────────────────────────────────────────────────

API_KEY  = os.environ.get("THEODDSAPI_KEY") or "c0c9bae9b0ea1a2e877038b76610ae94"
API_BASE = "https://api.the-odds-api.com/v4"

_DEFAULT_BKS = "pinnacle,codere_it,marathonbet"
_BOOKMAKERS  = [b.strip() for b in os.environ.get("THEODDSAPI_BKS", _DEFAULT_BKS).split(",") if b.strip()]

# Human-readable names for the DB / logging
_BK_DISPLAY: dict[str, str] = {
    "pinnacle":    "Pinnacle",
    "codere_it":   "Codere",
    "marathonbet": "MarathonBet",
    "betsson":     "Betsson",
    "williamhill": "William Hill",
    "nordicbet":   "NordicBet",
    "matchbook":   "Matchbook",
    "betfair_ex_eu": "Betfair Exchange",
    "onexbet":     "1xBet",
    "pinnacle_eu": "Pinnacle",
}

# ── sport / league map ─────────────────────────────────────────────────────────
# (the-odds-api sport_key,  our sport_key,  league display name)
# Sports with no active events are skipped automatically (empty response).

_SPORTS: list[tuple[str, str, str]] = [
    ("soccer_italy_serie_a",                  "calcio", "Serie A"),
    ("soccer_italy_serie_b",                  "calcio", "Serie B"),
    ("soccer_england_premier_league",         "calcio", "Premier League"),
    ("soccer_spain_la_liga",                  "calcio", "La Liga"),
    ("soccer_germany_bundesliga",             "calcio", "Bundesliga"),
    ("soccer_france_ligue_one",               "calcio", "Ligue 1"),
    ("soccer_uefa_champs_league",             "calcio", "Champions League"),
    ("soccer_uefa_europa_league",             "calcio", "Europa League"),
    ("soccer_uefa_europa_conference_league",  "calcio", "Conference League"),
    ("basketball_nba",                        "basket", "NBA"),
    ("tennis_atp_french_open",                "tennis", "Roland Garros"),
    ("tennis_wta_french_open",                "tennis", "Roland Garros"),
    ("tennis_atp_wimbledon",                  "tennis", "Wimbledon"),
    ("tennis_wta_wimbledon",                  "tennis", "Wimbledon"),
    ("tennis_atp_us_open",                    "tennis", "US Open"),
    ("tennis_wta_us_open",                    "tennis", "US Open"),
    ("tennis_atp_australian_open",            "tennis", "Australian Open"),
    ("tennis_wta_australian_open",            "tennis", "Australian Open"),
    ("tennis_atp_hamburg_open",               "tennis", "ATP Hamburg"),
]

_SPORT_BY_KEY = {api_key: (sport, league) for api_key, sport, league in _SPORTS}

# ── Over/Under spreads we care about ──────────────────────────────────────────
_WANTED_TOTALS = {1.5, 2.5, 3.5, 4.5}

# ── helpers ────────────────────────────────────────────────────────────────────

def _parse_date(s: str) -> str | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        return s


def _parse_event(event: dict, sport_key: str, league_name: str) -> list[MatchOdds]:
    """Parse one The Odds API event into MatchOdds rows (one per matched bookmaker)."""
    home_team = event.get("home_team", "")
    away_team = event.get("away_team", "")
    if not home_team or not away_team:
        return []

    event_name = f"{home_team} - {away_team}"
    event_time = _parse_date(event.get("commence_time", ""))

    bookmakers: list[dict] = event.get("bookmakers", [])

    # Collect odds per bookmaker
    # {bk_key: {market_label: {outcome: price}}}
    bk_markets: dict[str, dict[str, dict[str, float]]] = {}

    for bk in bookmakers:
        bk_key = bk.get("key", "")
        if bk_key not in _BOOKMAKERS:
            continue

        for market in bk.get("markets", []):
            mkey = market.get("key", "")

            if mkey == "h2h":
                # Map to 1/X/2
                odds_dict: dict[str, float] = {}
                for o in market.get("outcomes", []):
                    name  = o.get("name", "")
                    price = o.get("price")
                    if not price or price <= 1.0:
                        continue
                    if name == home_team:
                        odds_dict["1"] = round(float(price), 3)
                    elif name == away_team:
                        odds_dict["2"] = round(float(price), 3)
                    elif name.lower() in ("draw", "pareggio", "x"):
                        odds_dict["X"] = round(float(price), 3)
                if len(odds_dict) >= 2:
                    bk_markets.setdefault(bk_key, {})["1X2"] = odds_dict

            elif mkey == "totals":
                # Group by point value
                by_point: dict[float, dict[str, float]] = {}
                for o in market.get("outcomes", []):
                    point = o.get("point")
                    price = o.get("price")
                    name  = o.get("name", "").lower()
                    if point is None or not price or price <= 1.0:
                        continue
                    try:
                        pt = float(point)
                    except (TypeError, ValueError):
                        continue
                    if pt not in _WANTED_TOTALS:
                        continue
                    side = "Over" if "over" in name else ("Under" if "under" in name else None)
                    if side:
                        by_point.setdefault(pt, {})[side] = round(float(price), 3)

                for pt, odds_uo in by_point.items():
                    if len(odds_uo) >= 2:
                        mname = f"Over/Under {pt:g}"
                        bk_markets.setdefault(bk_key, {})[mname] = odds_uo

    if not bk_markets:
        return []

    # Group bookmakers by market, produce one MatchOdds per market
    # (one bookmaker_odds entry per bookmaker that has that market)
    market_to_bks: dict[str, list[dict[str, Any]]] = {}
    for bk_key, markets in bk_markets.items():
        display = _BK_DISPLAY.get(bk_key, bk_key.title())
        for mname, odds in markets.items():
            market_to_bks.setdefault(mname, []).append({
                "bookmaker": display,
                "odds": odds,
            })

    results: list[MatchOdds] = []
    for mname, bk_odds_list in market_to_bks.items():
        # Use the first bookmaker's URL pattern as match_url placeholder
        bk_key = next(iter(bk_markets))
        results.append(MatchOdds(
            sport=sport_key,
            league=league_name,
            home_team=home_team,
            away_team=away_team,
            event_name=event_name,
            event_time=event_time,
            match_url=f"https://www.{bk_key.replace('_it','').replace('_eu','')}.com/",
            market=mname,
            bookmaker_odds=bk_odds_list,
        ))

    return results


# ── scraper class ──────────────────────────────────────────────────────────────

class TheOddsAPIScraper:
    """Fetches Pinnacle + Codere IT + MarathonBet via The Odds API.

    1 HTTP request per sport → ALL events × ALL bookmakers.
    Credit cost: ~12 requests per full scrape (one per active sport).
    """

    bookmaker_name = "TheOddsAPI"   # internal; each MatchOdds carries its own bookmaker name

    def __init__(self):
        self._log = logging.getLogger(f"{__name__}.TheOddsAPIScraper")

    async def scrape_all(self) -> list[MatchOdds]:
        return await self._run(sport_filter=None)

    async def scrape_sport(self, sport_key: str) -> list[MatchOdds]:
        return await self._run(sport_filter=sport_key)

    async def _run(self, sport_filter: str | None) -> list[MatchOdds]:
        sports_to_fetch = [
            (api_key, sport_key, league)
            for api_key, sport_key, league in _SPORTS
            if sport_filter is None or sport_key == sport_filter
        ]

        if not sports_to_fetch:
            self._log.warning("[TheOddsAPI] No sports match filter=%s", sport_filter)
            return []

        self._log.info("[TheOddsAPI] Fetching %d sport endpoints in parallel (bookmakers=%s)",
                       len(sports_to_fetch), _BOOKMAKERS)

        async with httpx.AsyncClient(timeout=20) as client:
            tasks = [self._fetch_sport(client, api_key, sport_key, league)
                     for api_key, sport_key, league in sports_to_fetch]
            results_per_sport = await asyncio.gather(*tasks)

        all_rows: list[MatchOdds] = []
        for rows in results_per_sport:
            all_rows.extend(rows)

        # Deduplicate by (event_name, market, bookmaker)
        seen: set[tuple] = set()
        deduped: list[MatchOdds] = []
        for mo in all_rows:
            for bk in mo.bookmaker_odds:
                key = (mo.event_name, mo.market, bk["bookmaker"])
                if key not in seen:
                    seen.add(key)
        # Keep all (dedup happens in the DB writer via upsert)
        deduped = all_rows

        n_events = len({r.event_name for r in deduped})
        self._log.info("[TheOddsAPI] Total: %d events, %d market rows", n_events, len(deduped))
        return deduped

    async def _fetch_sport(
        self,
        client: httpx.AsyncClient,
        api_sport_key: str,
        sport_key: str,
        league_name: str,
    ) -> list[MatchOdds]:
        params = {
            "apiKey":      API_KEY,
            "regions":     "eu",
            "markets":     "h2h,totals",
            "oddsFormat":  "decimal",
            "bookmakers":  ",".join(_BOOKMAKERS),
        }
        try:
            resp = await client.get(
                f"{API_BASE}/sports/{api_sport_key}/odds/",
                params=params,
            )
        except Exception as exc:
            self._log.warning("[TheOddsAPI] %s: request failed: %s", api_sport_key, exc)
            return []

        remaining = resp.headers.get("x-requests-remaining", "?")

        if resp.status_code == 404:
            # Sport key not active this season — silently skip
            return []
        if resp.status_code == 401:
            self._log.error("[TheOddsAPI] 401 Unauthorized — check THEODDSAPI_KEY")
            return []
        if resp.status_code == 429:
            self._log.error("[TheOddsAPI] 429 Monthly quota exceeded — upgrade plan at the-odds-api.com")
            return []
        if resp.status_code != 200:
            self._log.warning("[TheOddsAPI] %s: HTTP %d", api_sport_key, resp.status_code)
            return []

        data = resp.json()
        if not isinstance(data, list):
            self._log.warning("[TheOddsAPI] %s: unexpected response type %s", api_sport_key, type(data))
            return []

        rows: list[MatchOdds] = []
        for event in data:
            rows.extend(_parse_event(event, sport_key, league_name))

        n_events = len(data)
        self._log.info("[TheOddsAPI] %-45s %2d events → %3d rows  [remaining: %s]",
                       api_sport_key, n_events, len(rows), remaining)
        return rows
