"""Lottomatica pregame odds scraper.

Strategy: direct async HTTP calls to Lottomatica's internal JSON API using
httpx (no browser needed). The pregame API endpoints don't require Akamai
session cookies — only the main SPA does.

Flow per tournament:
  1. getOverviewEventsAams → list of events with IDs (tai, ti, pi, ei)
  2. getDetailsEventAams per event → full market/odds data
"""

import asyncio
import logging

import httpx

from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)

BASE_URL = "https://www.lottomatica.it"
API_BASE = f"{BASE_URL}/api/sport/pregame"

# fmt: off
# (id_sport, id_tournament, id_aams_tournament, league_name, sport_key)
TOURNAMENTS: list[tuple[int, int, int, str, str]] = [
    # Calcio
    (1,  93,      21,   "Serie A",           "calcio"),
    (1,  97,      34,   "Serie B",           "calcio"),
    (1,  26534,   18,   "Champions League",  "calcio"),
    (1,  247944,  153,  "Europa League",     "calcio"),
    (1,  5675488, 2474, "Conference League", "calcio"),
    (1,  26604,   86,   "Premier League",    "calcio"),
    (1,  95,      79,   "La Liga",           "calcio"),
    (1,  94,      20,   "Bundesliga",        "calcio"),
    (1,  96,      23,   "Ligue 1",           "calcio"),
]
# fmt: on

SIMPLE_MARKET_MAP: dict[str, str] = {
    "1X2": "1X2",
    "DC": "Doppia Chance",
    "GG/NG": "Goal No Goal",
    "Esito Finale": "1X2",
}

UO_SPREADS_WANTED: set[str] = {"1.5", "2.5", "3.5"}

BOOKMAKER = "lottomatica"

_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "it-IT,it;q=0.9,en;q=0.8",
    "x-brand": "2",
    "x-idcanale": "13",
    "x-verticale": "1",
    "referer": "https://www.lottomatica.it/scommesse/sport/",
    "origin": "https://www.lottomatica.it",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


class LottomaticaScraper:
    """Scrapes pregame odds from Lottomatica via its internal JSON API."""

    def __init__(self, browser=None):  # browser kept for API compat but not used
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=_HEADERS,
                timeout=20.0,
                follow_redirects=True,
            )
        return self._client

    async def _close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def scrape_all(self) -> list[MatchOdds]:
        """Scrape all configured tournaments."""
        try:
            return await self._scrape_tournaments(None)
        finally:
            await self._close()

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        """Scrape only tournaments for the given sport key."""
        try:
            return await self._scrape_tournaments(sport)
        finally:
            await self._close()

    # ── internals ────────────────────────────────────────────────────

    async def _scrape_tournaments(self, sport: str | None) -> list[MatchOdds]:
        all_results: list[MatchOdds] = []
        for id_sport, id_tournament, id_aams, league_name, sport_key in TOURNAMENTS:
            if sport is not None and sport_key != sport:
                continue
            try:
                results = await self._scrape_tournament(
                    id_sport, id_tournament, id_aams, league_name, sport_key
                )
                all_results.extend(results)
                n_events = self._count_unique_events(results)
                logger.info(
                    "[Lottomatica] %s — %d events, %d market rows",
                    league_name, n_events, len(results),
                )
            except Exception as exc:
                logger.error("[Lottomatica] %s failed: %s", league_name, exc, exc_info=True)
            await asyncio.sleep(0.4)

        logger.info("[Lottomatica] Total match+market rows: %d", len(all_results))
        return all_results

    async def _api_get(self, url: str) -> dict | None:
        client = await self._get_client()
        try:
            resp = await client.get(url)
            logger.debug("[Lottomatica] GET %s → %s", url, resp.status_code)
            if resp.status_code != 200:
                logger.warning(
                    "[Lottomatica] HTTP %s for %s — body: %s",
                    resp.status_code, url, resp.text[:300],
                )
                return None
            return resp.json()
        except Exception as e:
            logger.error("[Lottomatica] Request failed for %s: %s", url, e)
            return None

    async def _scrape_tournament(
        self,
        id_sport: int,
        id_tournament: int,
        id_aams: int,
        league_name: str,
        sport_key: str,
    ) -> list[MatchOdds]:
        overview_url = (
            f"{API_BASE}/getOverviewEventsAams"
            f"/0/{id_sport}/{id_aams}/{id_tournament}/0/0/STANDARD"
        )
        overview = await self._api_get(overview_url)
        if not overview or not overview.get("leo"):
            logger.warning("[Lottomatica] No events for %s", league_name)
            return []

        results: list[MatchOdds] = []
        for event in overview["leo"]:
            event_name = event.get("en", "")
            event_date = event.get("ed", "")
            event_time = _parse_date(event_date)

            parts = event_name.split(" - ", 1)
            home = parts[0].strip() if len(parts) == 2 else event_name
            away = parts[1].strip() if len(parts) == 2 else ""

            tai = event.get("tai", id_aams)
            ti = event.get("ti", id_tournament)
            pi = event.get("pi", "")
            ei = event.get("ei", "")

            if not pi or not ei:
                continue

            details_url = (
                f"{API_BASE}/getDetailsEventAams"
                f"/{tai}/{ti}/{pi}/{ei}/0/STANDARD"
            )
            details = await self._api_get(details_url)
            if not details or not details.get("leo"):
                continue

            for detail_event in details["leo"]:
                market_rows = self._parse_markets(
                    detail_event, event_name, home, away, event_time, league_name, sport_key
                )
                results.extend(market_rows)

            await asyncio.sleep(0.2)

        return results

    def _parse_markets(
        self,
        event: dict,
        event_name: str,
        home: str,
        away: str,
        event_time: str,
        league_name: str,
        sport_key: str,
    ) -> list[MatchOdds]:
        results: list[MatchOdds] = []

        for mkt in event.get("mmkW", {}).values():
            market_raw = mkt.get("mn", "").strip()

            # ── simple markets ────────────────────────────────────────
            canonical = SIMPLE_MARKET_MAP.get(market_raw)
            if canonical:
                odds_dict: dict[str, float] = {}
                for spread_data in mkt.get("spd", {}).values():
                    for sel in spread_data.get("asl", []):
                        ov = sel.get("ov")
                        sn = sel.get("sn", "")
                        cls = sel.get("cls", 1)  # cls=0 → suspended
                        if ov and ov > 1.0 and cls == 1:
                            odds_dict[sn] = float(ov)
                if odds_dict:
                    results.append(self._make_match_odds(
                        sport_key, league_name, home, away,
                        event_name, event_time, canonical, odds_dict,
                    ))
                continue

            # ── Over/Under: one MatchOdds per spread level ────────────
            if market_raw == "U/O":
                for spread_data in mkt.get("spd", {}).values():
                    sl = spread_data.get("sl", "")
                    if sl not in UO_SPREADS_WANTED:
                        continue
                    odds_dict = {}
                    for sel in spread_data.get("asl", []):
                        ov = sel.get("ov")
                        sn = sel.get("sn", "")
                        cls = sel.get("cls", 1)
                        if ov and ov > 1.0 and cls == 1:
                            odds_dict[sn] = float(ov)
                    if odds_dict:
                        results.append(self._make_match_odds(
                            sport_key, league_name, home, away,
                            event_name, event_time, f"Over/Under {sl}", odds_dict,
                        ))

        return results

    def _make_match_odds(
        self,
        sport: str,
        league: str,
        home: str,
        away: str,
        event_name: str,
        event_time: str,
        market: str,
        odds_dict: dict[str, float],
    ) -> MatchOdds:
        return MatchOdds(
            sport=sport,
            league=league,
            home_team=home,
            away_team=away,
            event_name=event_name,
            event_time=event_time,
            match_url=f"{BASE_URL}/scommesse/sport/",
            market=market,
            bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
        )

    @staticmethod
    def _count_unique_events(results: list[MatchOdds]) -> int:
        return len({r.event_name for r in results})


def _parse_date(date_str: str) -> str:
    """Convert Lottomatica date 'DD-MM-YYYY HH:MM' to ISO 8601."""
    try:
        from datetime import datetime
        dt = datetime.strptime(date_str, "%d-%m-%Y %H:%M")
        return dt.isoformat()
    except Exception:
        return date_str
