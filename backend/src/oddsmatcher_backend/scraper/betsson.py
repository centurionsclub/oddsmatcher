"""Betsson Italy pregame odds scraper — direct REST API (no browser needed).

Betsson's XSportDatastore API is accessible with standard HTTP headers.
Key endpoint: /XSportDatastore/getWidgetCentrali
Returns 'tms' list — all upcoming matches across all sports with 1X2 odds.

Odds format: q/100 → decimal (e.g. q=450 → 4.50)
Market key: sc.d='1X2', sc.eqs[{ce:1→home, ce:2→draw, ce:3→away}]
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)

BASE_URL = "https://www.betsson.it"
BOOKMAKER = "Betsson"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "it-IT,it;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.betsson.it/scommesse",
    "Origin": "https://www.betsson.it",
}

# Sport mapping: Betsson name → our sport key
SPORT_MAP = {
    "CALCIO": "calcio",
    "TENNIS": "tennis",
    "BASKET": "basket",
}

# Leagues we want to track (subset — Betsson returns all, we filter)
WANTED_LEAGUES = {
    "calcio": {
        "Serie A", "Serie B", "Premier League", "La Liga", "LaLiga",
        "Bundesliga", "Ligue 1", "Champions League", "Europa League",
        "Conference League",
    },
    "tennis": {
        "Roland Garros", "Wimbledon", "US Open", "Australian Open",
        "Ginevra", "Amburgo", "Rabat", "Strasburgo",
        "Roland Garros Femminile", "Wimbledon Femminile",
        "US Open Femminile", "Australian Open Femminile",
    },
    "basket": {
        "NBA", "Serie A", "Serie A Basket", "Eurolega",
    },
}

# CE (outcome code) → canonical outcome name for 1X2
CE_TO_OUTCOME = {1: "1", 2: "X", 3: "2"}

# CE → canonical outcome name for Double Chance (sc2)
CE_TO_DC = {1: "1X", 2: "X2", 3: "12"}


def _parse_date(ts: str) -> str | None:
    """Parse Betsson timestamp 'YYYYMMDD HH:MM:SS' → UTC ISO string."""
    if not ts:
        return None
    FMTS = ["%Y%m%d %H:%M:%S", "%Y%m%d %H:%M", "%Y-%m-%dT%H:%M:%S"]
    for fmt in FMTS:
        try:
            dt = datetime.strptime(ts.strip(), fmt)
            # Betsson times are in Italian timezone (CEST/CET)
            off = 2 if 3 <= dt.month <= 10 else 1
            return dt.replace(tzinfo=timezone(timedelta(hours=off))).astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        return ts


def _q_to_decimal(q: Any) -> float | None:
    """Convert Betsson integer quota (q*100) to decimal odds."""
    try:
        f = float(q) / 100.0
        return f if f > 1.0 else None
    except (TypeError, ValueError):
        return None


def _parse_tms(tms: list) -> list[MatchOdds]:
    """Parse 'tms' array from getWidgetCentrali into MatchOdds list."""
    results: list[MatchOdds] = []

    for item in tms:
        if not isinstance(item, dict):
            continue

        # Sport filter
        ds = item.get("ds", "")
        sport_key = SPORT_MAP.get(ds)
        if not sport_key:
            continue

        # League name
        league = item.get("dt", "")

        # Check if we want this league
        wanted = WANTED_LEAGUES.get(sport_key, set())
        if league not in wanted:
            continue

        # Event info
        event_name = item.get("da", "").strip()
        if not event_name:
            continue

        ts = item.get("ts", "")
        event_time = _parse_date(ts)

        # Build match URL from seom if available
        seot = item.get("seot") or ""
        try:
            import json as _json
            seot_data = _json.loads(seot) if isinstance(seot, str) and seot else {}
            url_path = (
                seot_data.get("DEFAULT", {}).get("IT", "")
                if isinstance(seot_data, dict) else ""
            )
            match_url = f"{BASE_URL}/{url_path}" if url_path else f"{BASE_URL}/scommesse"
        except Exception:
            match_url = f"{BASE_URL}/scommesse"

        parts = event_name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else event_name
        away = parts[1].strip() if len(parts) == 2 else ""

        # ── 1X2 from sc ──────────────────────────────────────────────
        sc = item.get("sc")
        if isinstance(sc, dict) and sc.get("d") == "1X2":
            eqs = sc.get("eqs", [])
            odds_dict: dict[str, float] = {}
            for eq in eqs:
                ce = eq.get("ce")
                q = eq.get("q")
                outcome = CE_TO_OUTCOME.get(ce)
                val = _q_to_decimal(q)
                if outcome and val:
                    odds_dict[outcome] = val
            if odds_dict:
                results.append(MatchOdds(
                    sport=sport_key, league=league,
                    home_team=home, away_team=away,
                    event_name=event_name, event_time=event_time,
                    match_url=match_url, market="1X2",
                    bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                ))

        # ── Double Chance from sc2 (if present and has 3 outcomes) ───
        sc2 = item.get("sc2")
        if isinstance(sc2, dict):
            eqs2 = sc2.get("eqs", [])
            if len(eqs2) >= 3:  # Full DC has 3 outcomes
                odds_dc: dict[str, float] = {}
                for eq in eqs2:
                    ce = eq.get("ce")
                    q = eq.get("q")
                    outcome = CE_TO_DC.get(ce)
                    val = _q_to_decimal(q)
                    if outcome and val:
                        odds_dc[outcome] = val
                if odds_dc:
                    results.append(MatchOdds(
                        sport=sport_key, league=league,
                        home_team=home, away_team=away,
                        event_name=event_name, event_time=event_time,
                        match_url=match_url, market="DC",
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dc}],
                    ))

    return results


class BetssonScraper:
    """Direct REST API scraper for Betsson — no browser needed."""

    bookmaker_name = BOOKMAKER

    async def scrape_all(self) -> list[MatchOdds]:
        return await self._fetch_and_parse()

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        all_results = await self._fetch_and_parse()
        return [r for r in all_results if r.sport == sport]

    async def _fetch_and_parse(self) -> list[MatchOdds]:
        url = f"{BASE_URL}/XSportDatastore/getWidgetCentrali?systemCode=BETSSON&lingua=IT&hash="
        proxy_url = os.environ.get("PROXY_URL")
        client_kwargs: dict = {"headers": _HEADERS, "timeout": 30, "follow_redirects": True}
        if proxy_url:
            client_kwargs["proxy"] = proxy_url
            logger.debug("[Betsson] Using proxy: %s", proxy_url)
        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.error("[Betsson] API request failed: %s", exc)
            return []

        tms = data.get("tms", [])
        logger.info("[Betsson] getWidgetCentrali: %d tms items", len(tms))

        results = _parse_tms(tms)
        logger.info("[Betsson] Parsed %d MatchOdds rows", len(results))
        return results
