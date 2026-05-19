"""Eurobet Italy pregame odds scraper — Kambi REST API (no browser needed).

Eurobet Italy is powered by Kambi. The Kambi offering API is publicly
accessible (CORS-enabled JSON) at:
  https://eu-offering-api.kambicdn.com/offering/v2018/eurobet/

No Cloudflare, no browser, no Playwright. Direct httpx calls.

Odds format: decimal (already decimal in Kambi responses).
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)

BOOKMAKER = "Eurobet"
BASE_URL = "https://www.eurobet.it"

# Kambi API base for Eurobet Italy
KAMBI_BASE = "https://eu-offering-api.kambicdn.com/offering/v2018/eurobet"
KAMBI_PARAMS = "lang=it_IT&market=IT&client_id=2&channel_id=1&ncid=1&useCombined=true"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "it-IT,it;q=0.9",
    "Origin": "https://www.eurobet.it",
    "Referer": "https://www.eurobet.it/",
}

# Kambi sport path → (our sport_key, our league_name, kambi group path)
# Kambi uses "football" for soccer, "basketball" for basket, "tennis" for tennis
LEAGUES: list[tuple[str, str, str]] = [
    # (league_name, sport_key, kambi_listView_path)
    ("Serie A",           "calcio", "football/italy/serie_a"),
    ("Serie B",           "calcio", "football/italy/serie_b"),
    ("Champions League",  "calcio", "football/europe/champions_league"),
    ("Europa League",     "calcio", "football/europe/europa_league"),
    ("Conference League", "calcio", "football/europe/conference_league"),
    ("Premier League",    "calcio", "football/england/premier_league"),
    ("La Liga",           "calcio", "football/spain/primera_division"),
    ("Bundesliga",        "calcio", "football/germany/bundesliga"),
    ("Ligue 1",           "calcio", "football/france/ligue_1"),
    ("Roland Garros",     "tennis", "tennis/france/roland_garros"),
    ("Wimbledon",         "tennis", "tennis/great_britain/wimbledon"),
    ("US Open",           "tennis", "tennis/usa/us_open"),
    ("Australian Open",   "tennis", "tennis/australia/australian_open"),
    ("NBA",               "basket", "basketball/usa/nba"),
    ("Eurolega",          "basket", "basketball/europe/euroleague"),
    ("Serie A Basket",    "basket", "basketball/italy/serie_a"),
]

OUTCOME_MAP: dict[str, str] = {
    "1": "1", "Home": "1", "Casa": "1",
    "X": "X", "Draw": "X", "Pareggio": "X",
    "2": "2", "Away": "2", "Ospite": "2",
    "1X": "1X", "X2": "X2", "12": "12",
    "Yes": "Goal", "No": "No Goal",
}


def _parse_date(ts_ms: int | None) -> str | None:
    """Convert Kambi millisecond timestamp to UTC ISO string."""
    if not ts_ms:
        return None
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        return dt.isoformat()
    except Exception:
        return None


def _parse_kambi_events(data: Any, league_name: str, sport_key: str) -> list[MatchOdds]:
    """Parse Kambi listView response into MatchOdds."""
    results: list[MatchOdds] = []
    if not isinstance(data, dict):
        return results

    events = data.get("events") or []

    for ev_wrapper in events:
        if not isinstance(ev_wrapper, dict):
            continue

        event = ev_wrapper.get("event") or ev_wrapper
        if not isinstance(event, dict):
            continue

        name = event.get("name") or event.get("englishName") or ""
        name = re.sub(r"\s+vs\.?\s+", " - ", name, flags=re.IGNORECASE).strip()
        if not name:
            continue

        ts = event.get("start")
        event_time = _parse_date(ts)
        match_url = f"{BASE_URL}/it/scommesse/"
        parts = name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else name
        away = parts[1].strip() if len(parts) == 2 else ""

        # betOffers come directly in the event wrapper from Kambi listView
        bet_offers = ev_wrapper.get("betOffers") or []

        for bo in bet_offers:
            if not isinstance(bo, dict):
                continue

            criterion = bo.get("criterion") or {}
            label = criterion.get("label") or bo.get("betOfferType", {}).get("name") or ""
            label = label.strip()

            outcomes = bo.get("outcomes") or []

            # ── 1X2 ──
            if label in ("Match", "Match Result", "1X2", "Esito Finale",
                         "Head to Head", "Testa a Testa"):
                odds_dict: dict[str, float] = {}
                for out in outcomes:
                    olabel = out.get("label") or out.get("type") or ""
                    odds_key = OUTCOME_MAP.get(olabel, olabel)
                    odds_val = out.get("odds")
                    if odds_val:
                        try:
                            f = float(odds_val) / 1000.0  # Kambi stores odds * 1000
                            if f > 1.0:
                                odds_dict[odds_key] = round(f, 3)
                        except (TypeError, ValueError):
                            pass
                if odds_dict:
                    results.append(MatchOdds(
                        sport=sport_key, league=league_name,
                        home_team=home, away_team=away,
                        event_name=name, event_time=event_time,
                        match_url=match_url, market="1X2",
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                    ))

            # ── Double Chance ──
            elif "Double Chance" in label or "Doppia Chance" in label:
                odds_dict = {}
                for out in outcomes:
                    olabel = out.get("label") or ""
                    key = OUTCOME_MAP.get(olabel, olabel)
                    odds_val = out.get("odds")
                    if odds_val:
                        try:
                            f = float(odds_val) / 1000.0
                            if f > 1.0:
                                odds_dict[key] = round(f, 3)
                        except (TypeError, ValueError):
                            pass
                if odds_dict:
                    results.append(MatchOdds(
                        sport=sport_key, league=league_name,
                        home_team=home, away_team=away,
                        event_name=name, event_time=event_time,
                        match_url=match_url, market="DC",
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                    ))

            # ── Over/Under ──
            elif any(kw in label for kw in ("Over/Under", "Goals", "Total")):
                sp_m = re.search(r"(\d+[.,]\d+)", label)
                if not sp_m:
                    continue
                sp = sp_m.group(1).replace(",", ".")
                if sp not in {"1.5", "2.5", "3.5"}:
                    continue
                odds_dict = {}
                for out in outcomes:
                    olabel = out.get("label") or ""
                    side = "Over" if "over" in olabel.lower() else ("Under" if "under" in olabel.lower() else None)
                    if not side:
                        continue
                    odds_val = out.get("odds")
                    if odds_val:
                        try:
                            f = float(odds_val) / 1000.0
                            if f > 1.0:
                                odds_dict[f"{side} {sp}"] = round(f, 3)
                        except (TypeError, ValueError):
                            pass
                if odds_dict:
                    results.append(MatchOdds(
                        sport=sport_key, league=league_name,
                        home_team=home, away_team=away,
                        event_name=name, event_time=event_time,
                        match_url=match_url, market=f"Over/Under {sp}",
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                    ))

    return results


class EurobetScraper:
    """Direct Kambi API scraper for Eurobet Italy — no browser, no Cloudflare."""

    bookmaker_name = BOOKMAKER

    async def scrape_all(self) -> list[MatchOdds]:
        return await self._run(sport_filter=None)

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        return await self._run(sport_filter=sport)

    async def _run(self, sport_filter: str | None) -> list[MatchOdds]:
        proxy_url = os.environ.get("PROXY_URL")
        if proxy_url:
            logger.info("[Eurobet] Using proxy: %s", proxy_url.split("@")[-1] if "@" in proxy_url else proxy_url)

        all_results: list[MatchOdds] = []

        async with httpx.AsyncClient(
            headers=_HEADERS,
            timeout=30,
            follow_redirects=True,
            proxy=proxy_url,
        ) as client:
            for league_name, sport_key, kambi_path in LEAGUES:
                if sport_filter and sport_key != sport_filter:
                    continue

                url = f"{KAMBI_BASE}/listView/{kambi_path}.json?{KAMBI_PARAMS}"
                logger.info("[Eurobet] Fetching %s — %s", league_name, url)

                try:
                    resp = await client.get(url)
                    if resp.status_code == 404:
                        logger.info("[Eurobet] %s: 404 (no events)", league_name)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    logger.error("[Eurobet] %s: request failed: %s", league_name, exc)
                    continue

                rows = _parse_kambi_events(data, league_name, sport_key)
                if not rows:
                    # Log a preview of the response to calibrate parsing
                    import json as _json
                    preview = _json.dumps(data, ensure_ascii=False)[:600]
                    logger.info("[Eurobet] %s: 0 rows — response preview: %s", league_name, preview)
                else:
                    n_events = len({r.event_name for r in rows})
                    logger.info("[Eurobet] %s: %d events, %d market rows", league_name, n_events, len(rows))

                all_results.extend(rows)

        logger.info("[Eurobet] Total rows: %d", len(all_results))
        return all_results
