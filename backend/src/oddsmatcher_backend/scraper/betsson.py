"""Betsson Italy pregame odds scraper — direct REST API (no browser needed).

Betsson's XSportDatastore API is accessible with standard HTTP headers.
Endpoint: /XSportDatastore/getWidgetCentrali

Response structure (current):
  - tms: list of "central widget" events (may be null outside match windows)
  - lms: dict of league buckets, each with 'avs' list of upcoming events

Both sources are parsed and merged.  Each avvenimento has a 'scs' array
with all available markets (1X2, DC, BTTS, Over/Under).

Odds format: q/100 → decimal (e.g. q=450 → 4.50)
"""

import logging
import os
import json as _json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from oddsmatcher_backend.scraper.models import MatchOdds

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

# Leagues we want to track.
# calcio/basket: explicit set — only these leagues are kept.
# tennis: None → accept ALL tournaments.
WANTED_LEAGUES: dict[str, set[str] | None] = {
    "calcio": {
        "Serie A", "Serie B", "Premier League", "La Liga", "LaLiga",
        "Bundesliga", "Ligue 1", "Champions League", "Europa League",
        "Conference League",
    },
    "tennis": None,
    "basket": {
        "NBA", "Serie A", "Serie A Basket", "Eurolega",
        "WNBA", "A2 Basket", "Legabasket A2", "Serie A2 Basket",
    },
}

# CE (outcome code) → canonical outcome name for 1X2
CE_TO_OUTCOME = {1: "1", 2: "X", 3: "2"}

# URL slug fragments → league name (for lms events that lack a dt field)
_SLUG_TO_LEAGUE: dict[str, str] = {
    "serie-a":          "Serie A",
    "serie-b":          "Serie B",
    "premier-league":   "Premier League",
    "la-liga":          "La Liga",
    "laliga":           "LaLiga",
    "bundesliga":       "Bundesliga",
    "ligue-1":          "Ligue 1",
    "champions-league": "Champions League",
    "europa-league":    "Europa League",
    "conference-league":"Conference League",
    "nba":              "NBA",
    "eurolega":         "Eurolega",
    "euroligue":        "Eurolega",
}


def _parse_date(ts: str) -> str | None:
    """Parse Betsson timestamp 'YYYYMMDD HH:MM:SS' → UTC ISO string."""
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
    """Convert Betsson integer quota (q*100) to decimal odds."""
    try:
        f = float(q) / 100.0
        return f if f > 1.0 else None
    except (TypeError, ValueError):
        return None


def _first_eq(eqs: list, ce: int) -> float | None:
    """Return decimal odds for a specific ce value from an eqs list."""
    for eq in eqs:
        if eq.get("ce") == ce:
            return _q_to_decimal(eq.get("q"))
    return None


def _extract_url_and_league(seo_raw: str | None) -> tuple[str, str]:
    """Extract (match_url, league_name) from the seo JSON field.

    seo looks like: '{"DEFAULT":{"IT":"evento/serie-a/juventus-vs-inter"}}'
    Returns (full URL, league name) or fallback values.
    """
    match_url = f"{BASE_URL}/scommesse"
    league_from_url = ""
    if not seo_raw:
        return match_url, league_from_url
    try:
        seo_data = _json.loads(seo_raw) if isinstance(seo_raw, str) else seo_raw
        url_path = (seo_data.get("DEFAULT") or {}).get("IT", "") if isinstance(seo_data, dict) else ""
        if url_path:
            match_url = f"{BASE_URL}/{url_path}"
            # extract league slug: path is "evento/<league-slug>/<match-slug>"
            parts = url_path.strip("/").split("/")
            if len(parts) >= 2:
                slug = parts[1]  # e.g. "serie-a", "premier-league"
                league_from_url = _SLUG_TO_LEAGUE.get(slug, "")
    except Exception:
        pass
    return match_url, league_from_url


def _parse_scs(scs: list, base: dict, sport_key: str) -> list[MatchOdds]:
    """Parse all markets from a Betsson scs array into MatchOdds entries."""
    results: list[MatchOdds] = []

    # ── 1X2 ──────────────────────────────────────────────────────────────────
    _TT_MARKETS = {"1X2", "T/T", "T/T (ESCL. RITIRO)", "TESTA A TESTA"}
    for sc_entry in scs:
        d = sc_entry.get("d", "")
        if d not in _TT_MARKETS:
            continue
        eqs = sc_entry.get("eqs", [])
        is_hh = d != "1X2"
        odds_dict: dict[str, float] = {}
        for eq in eqs:
            ce = eq.get("ce")
            if is_hh:
                outcome = "1" if ce == 1 else ("2" if ce in (2, 3) else None)
            else:
                outcome = CE_TO_OUTCOME.get(ce)
            val = _q_to_decimal(eq.get("q"))
            if outcome and val:
                odds_dict[outcome] = val
        if odds_dict:
            results.append(MatchOdds(
                **base, market="1X2",
                bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
            ))
        break  # only one 1X2 market per event

    # ── Only calcio extras below ──────────────────────────────────────────────
    if sport_key != "calcio":
        return results

    # ── Double Chance (1X / X2 / 12 entries — ce:2 = DC outcome odds) ───────
    dc_odds: dict[str, float] = {}
    for sc_entry in scs:
        d = sc_entry.get("d", "")
        if d in ("1X", "X2", "12"):
            val = _first_eq(sc_entry.get("eqs", []), ce=2)
            if val:
                dc_odds[d] = val
    if len(dc_odds) == 3:
        results.append(MatchOdds(
            **base, market="DC",
            bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": dc_odds}],
        ))

    # ── BTTS (GG/NG) — ce:1=Goal, ce:2=No Goal ───────────────────────────────
    for sc_entry in scs:
        if sc_entry.get("d") == "GG/NG":
            goal = _first_eq(sc_entry.get("eqs", []), ce=1)
            no_goal = _first_eq(sc_entry.get("eqs", []), ce=2)
            if goal and no_goal:
                results.append(MatchOdds(
                    **base, market="BTTS",
                    bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": {
                        "Goal": goal, "No Goal": no_goal,
                    }}],
                ))
            break

    # ── Over/Under (U/O) — h/100=spread, ce:1=Under, ce:2=Over ──────────────
    for sc_entry in scs:
        if sc_entry.get("d") != "U/O":
            continue
        h = sc_entry.get("h", 0)
        if not h:
            continue
        spread = h / 100  # 250 → 2.5
        if spread not in (0.5, 1.5, 2.5, 3.5, 4.5):
            continue
        under = _first_eq(sc_entry.get("eqs", []), ce=1)
        over = _first_eq(sc_entry.get("eqs", []), ce=2)
        if under and over:
            results.append(MatchOdds(
                **base, market=f"Over/Under {spread:g}",
                bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": {
                    "Under": under, "Over": over,
                }}],
            ))

    return results


def _parse_tms_item(item: dict, sport_key: str, league: str) -> list[MatchOdds]:
    """Parse a single event item (from tms or lms avs) into MatchOdds."""
    # Event name: tms items use 'da', lms items use dsl.IT
    event_name = (
        item.get("da")
        or (item.get("dsl") or {}).get("IT", "")
    ).strip()
    if not event_name:
        return []

    event_time = _parse_date(item.get("ts", ""))

    # URL: tms uses 'seot' (league page), lms uses 'seo' (event page)
    seot = item.get("seot") or item.get("seo") or ""
    match_url, league_from_url = _extract_url_and_league(seot)

    # League: prefer explicit league name, fallback to URL-extracted
    final_league = league or league_from_url

    # League filter
    wanted = WANTED_LEAGUES.get(sport_key)
    if wanted is not None and final_league not in wanted:
        return []

    parts = event_name.split(" - ", 1)
    home = parts[0].strip() if len(parts) == 2 else event_name
    away = parts[1].strip() if len(parts) == 2 else ""

    base = dict(
        sport=sport_key, league=final_league,
        home_team=home, away_team=away,
        event_name=event_name, event_time=event_time,
        match_url=match_url,
    )

    # scs: all markets (preferred); fallback to sc/sc2 for old tms structure
    scs: list = item.get("scs") or []
    if scs:
        return _parse_scs(scs, base, sport_key)

    # Legacy tms fallback: sc = main market, sc2 = DC (if 3 outcomes)
    results: list[MatchOdds] = []
    sc = item.get("sc")
    _TT_MARKETS = {"1X2", "T/T", "T/T (ESCL. RITIRO)", "TESTA A TESTA"}
    if isinstance(sc, dict) and sc.get("d") in _TT_MARKETS:
        eqs = sc.get("eqs", [])
        is_hh = sc.get("d") != "1X2"
        odds_dict: dict[str, float] = {}
        for eq in eqs:
            ce = eq.get("ce")
            outcome = "1" if (is_hh and ce == 1) else ("2" if (is_hh and ce in (2, 3)) else CE_TO_OUTCOME.get(ce))
            val = _q_to_decimal(eq.get("q"))
            if outcome and val:
                odds_dict[outcome] = val
        if odds_dict:
            results.append(MatchOdds(**base, market="1X2",
                bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}]))
    return results


def _parse_response(data: dict) -> list[MatchOdds]:
    """Parse full getWidgetCentrali response → list of MatchOdds."""
    results: list[MatchOdds] = []
    seen_bids: set[int] = set()  # deduplicate by event bid

    def _add(item: dict, sport_key: str, league: str = "") -> None:
        bid = item.get("bid", 0)
        if bid and bid in seen_bids:
            return
        rows = _parse_tms_item(item, sport_key, league)
        if rows:
            if bid:
                seen_bids.add(bid)
            results.extend(rows)

    # ── tms (central widget — may be null) ───────────────────────────────────
    for item in (data.get("tms") or []):
        if not isinstance(item, dict):
            continue
        sport_key = SPORT_MAP.get(item.get("ds", ""))
        if not sport_key:
            continue
        _add(item, sport_key, league=item.get("dt", ""))

    # ── lms (league-grouped upcoming matches) ────────────────────────────────
    for league_data in (data.get("lms") or {}).values():
        if not isinstance(league_data, dict):
            continue
        sport_key = SPORT_MAP.get(league_data.get("ds", ""))
        if not sport_key:
            continue
        league_name = (league_data.get("dts") or {}).get("IT", "")
        for item in (league_data.get("avs") or []):
            if isinstance(item, dict):
                _add(item, sport_key, league=league_name)

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

        tms_count = len(data.get("tms") or [])
        lms_count = sum(len(v.get("avs") or []) for v in (data.get("lms") or {}).values())
        logger.info("[Betsson] tms=%d items, lms=%d avs", tms_count, lms_count)

        results = _parse_response(data)
        logger.info("[Betsson] Parsed %d MatchOdds rows", len(results))
        return results
