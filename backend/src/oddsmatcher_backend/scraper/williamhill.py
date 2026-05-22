"""William Hill Italy pregame odds scraper — direct REST API (no browser needed).

William Hill Italy uses the same XSportDatastore API as Betsson.it.
Key endpoint: /XSportDatastore/getWidgetCentrali
Returns 'tms' list — upcoming matches with odds across all sports.

Odds format: q/100 → decimal (e.g. q=183 → 1.83)
1X2 market: sc.d='1X2', sc.eqs[{ce:1→home, ce:2→draw, ce:3→away}]
DC markets:  in scs[], d∈{'1X','X2','12'}, take eqs[ce:1].q for each
Over/Under:  in scs[], d='U/O', h=spread*100 (250→2.5), ce:1=Under/ce:2=Over
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from oddsmatcher_backend.scraper.models import MatchOdds

logger = logging.getLogger(__name__)

BASE_URL = "https://www.williamhill.it"
BOOKMAKER = "William Hill"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "it-IT,it;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.williamhill.it/xsportapp/xsport_desktop/",
    "Origin": "https://www.williamhill.it",
}

# Sport mapping: WH 'ds' field → our sport key
SPORT_MAP = {
    "Calcio": "calcio",
    "CALCIO": "calcio",
    "calcio": "calcio",
    "Pallacanestro": "basket",
    "PALLACANESTRO": "basket",
    "Basket": "basket",
    "BASKET": "basket",
    "Tennis": "tennis",
    "TENNIS": "tennis",
}

# Keywords to look for in the WH 'dt' (tournament name) field.
# We use substring matching because WH often adds country info:
# e.g. "ATP Amburgo, Germania Uomini Singolare", "UEFA Europa League"
WANTED_KEYWORDS: dict[str, list[str]] = {
    "calcio": [
        "Serie A", "Serie B", "Premier League", "La Liga", "Primera",
        "Bundesliga", "Ligue 1", "Champions League", "Europa League",
        "Conference League",
    ],
    "tennis": [
        "Roland Garros", "Wimbledon", "US Open", "Australian Open",
        "Amburgo", "Ginevra", "Rabat", "Strasburgo",
    ],
    "basket": [
        "NBA", "Eurolega", "Serie A",
    ],
}

# Canonical league name from matching keyword
KEYWORD_TO_LEAGUE: dict[str, str] = {
    "Serie A": "Serie A",
    "Serie B": "Serie B",
    "Premier League": "Premier League",
    "La Liga": "La Liga",
    "Primera": "La Liga",
    "Bundesliga": "Bundesliga",
    "Ligue 1": "Ligue 1",
    "Champions League": "Champions League",
    "Europa League": "Europa League",
    "Conference League": "Conference League",
    "Roland Garros": "Roland Garros",
    "Wimbledon": "Wimbledon",
    "US Open": "US Open",
    "Australian Open": "Australian Open",
    "Amburgo": "Amburgo",
    "Ginevra": "Ginevra",
    "Rabat": "Rabat",
    "Strasburgo": "Strasburgo",
    "NBA": "NBA",
    "Eurolega": "Eurolega",
}

# CE (outcome code) → canonical 1X2 outcome name
CE_TO_OUTCOME = {1: "1", 2: "X", 3: "2"}


def _match_league(dt: str, sport_key: str) -> str | None:
    """Return canonical league name if dt contains a wanted keyword."""
    keywords = WANTED_KEYWORDS.get(sport_key, [])
    for kw in keywords:
        if kw.lower() in dt.lower():
            # Disambiguate "Serie A" for basket vs calcio
            if kw == "Serie A" and sport_key == "basket":
                return "Serie A Basket"
            return KEYWORD_TO_LEAGUE.get(kw, kw)
    return None


def _parse_date(ts: str) -> str | None:
    """Parse WH timestamp 'YYYYMMDD HH:MM:SS' → UTC ISO string."""
    if not ts:
        return None
    FMTS = ["%Y%m%d %H:%M:%S", "%Y%m%d %H:%M", "%Y-%m-%dT%H:%M:%S"]
    for fmt in FMTS:
        try:
            dt = datetime.strptime(ts.strip(), fmt)
            off = 2 if 3 <= dt.month <= 10 else 1
            return dt.replace(tzinfo=timezone(timedelta(hours=off))).astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        return ts


def _q_to_decimal(q: Any) -> float | None:
    """Convert WH integer quota (q*100) to decimal odds."""
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

        # League
        dt = item.get("dt", "")
        league_name = _match_league(dt, sport_key)
        if not league_name:
            continue

        # Event info
        event_name = item.get("da", "").strip()
        if not event_name:
            continue

        ts = item.get("ts", "")
        event_time = _parse_date(ts)

        # Build match URL from seot
        try:
            import json as _json
            seot_raw = item.get("seot") or ""
            seot_data = _json.loads(seot_raw) if isinstance(seot_raw, str) and seot_raw else {}
            # Try WH-specific path first, then DEFAULT
            url_path = (
                seot_data.get("WILLIAMHILL", {}).get("IT", "")
                or seot_data.get("DEFAULT", {}).get("IT", "")
                if isinstance(seot_data, dict) else ""
            )
            match_url = f"{BASE_URL}{url_path}" if url_path else f"{BASE_URL}/xsportapp/xsport_desktop/"
        except Exception:
            match_url = f"{BASE_URL}/xsportapp/xsport_desktop/"

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
                    sport=sport_key, league=league_name,
                    home_team=home, away_team=away,
                    event_name=event_name, event_time=event_time,
                    match_url=match_url, market="1X2",
                    bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                ))

        # ── Double Chance from scs (d∈{"1X","X2","12"}) ─────────────
        scs = item.get("scs", [])
        if isinstance(scs, list):
            dc_map = {"1X": None, "X2": None, "12": None}
            for mkt in scs:
                if not isinstance(mkt, dict):
                    continue
                d = mkt.get("d", "")
                if d in dc_map:
                    eqs = mkt.get("eqs", [])
                    # ce:1 is the "this combination wins" selection
                    for eq in eqs:
                        if eq.get("ce") == 1:
                            val = _q_to_decimal(eq.get("q"))
                            if val:
                                dc_map[d] = val
                            break

            odds_dc = {k: v for k, v in dc_map.items() if v is not None}
            if len(odds_dc) >= 2:
                results.append(MatchOdds(
                    sport=sport_key, league=league_name,
                    home_team=home, away_team=away,
                    event_name=event_name, event_time=event_time,
                    match_url=match_url, market="DC",
                    bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dc}],
                ))

            # ── Over/Under from scs (d="U/O") ────────────────────────
            uo_markets: dict[str, dict[str, float]] = {}  # "2.5" → {"Over":..., "Under":...}
            for mkt in scs:
                if not isinstance(mkt, dict):
                    continue
                if mkt.get("d") != "U/O":
                    continue
                h = mkt.get("h", 0)
                spread_val = h / 100.0
                if spread_val not in {1.5, 2.5, 3.5}:
                    continue
                sp = str(spread_val)
                if sp not in uo_markets:
                    uo_markets[sp] = {}
                eqs = mkt.get("eqs", [])
                for eq in eqs:
                    ce = eq.get("ce")
                    val = _q_to_decimal(eq.get("q"))
                    if val:
                        if ce == 1:
                            uo_markets[sp]["Under"] = val  # d='U/O' → ce:1=Under, ce:2=Over
                        elif ce == 2:
                            uo_markets[sp]["Over"] = val

            for sp, odds_uo in uo_markets.items():
                if odds_uo:
                    results.append(MatchOdds(
                        sport=sport_key, league=league_name,
                        home_team=home, away_team=away,
                        event_name=event_name, event_time=event_time,
                        match_url=match_url, market=f"Over/Under {sp}",
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_uo}],
                    ))

    return results


class WilliamHillScraper:
    """Direct REST API scraper for William Hill Italy — no browser needed."""

    bookmaker_name = BOOKMAKER

    async def scrape_all(self) -> list[MatchOdds]:
        return await self._fetch_and_parse()

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        all_results = await self._fetch_and_parse()
        return [r for r in all_results if r.sport == sport]

    async def _fetch_and_parse(self) -> list[MatchOdds]:
        import os
        url = f"{BASE_URL}/XSportDatastore/getWidgetCentrali?systemCode=WILLIAMHILL&lingua=IT&hash="
        proxy_url = os.environ.get("PROXY_URL")
        if proxy_url:
            logger.info("[WilliamHill] Using proxy")
        try:
            async with httpx.AsyncClient(headers=_HEADERS, timeout=30, follow_redirects=True,
                                         proxy=proxy_url) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.error("[WilliamHill] API request failed: %s", exc)
            return []

        tms = data.get("tms", [])
        logger.info("[WilliamHill] getWidgetCentrali: %d tms items", len(tms))

        results = _parse_tms(tms)
        logger.info("[WilliamHill] Parsed %d MatchOdds rows", len(results))
        return results
