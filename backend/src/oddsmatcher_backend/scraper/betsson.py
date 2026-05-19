"""Betsson pregame odds scraper — Playwright + network interception."""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from oddsmatcher_backend.scraper._base_playwright import BasePlaywrightScraper
from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)

BASE_URL = "https://www.betsson.it"
BOOKMAKER = "Betsson"

# fmt: off
LEAGUES: list[tuple[str, str, str]] = [
    ("Serie A",           "calcio", "/scommesse/sport/calcio/italia/serie-a/"),
    ("Serie B",           "calcio", "/scommesse/sport/calcio/italia/serie-b/"),
    ("Premier League",    "calcio", "/scommesse/sport/calcio/inghilterra/premier-league/"),
    ("La Liga",           "calcio", "/scommesse/sport/calcio/spagna/la-liga/"),
    ("Bundesliga",        "calcio", "/scommesse/sport/calcio/germania/bundesliga/"),
    ("Ligue 1",           "calcio", "/scommesse/sport/calcio/francia/ligue-1/"),
    ("Champions League",  "calcio", "/scommesse/sport/calcio/europa/champions-league/"),
    ("Europa League",     "calcio", "/scommesse/sport/calcio/europa/europa-league/"),
    ("Conference League", "calcio", "/scommesse/sport/calcio/europa/conference-league/"),
    ("NBA",               "basket", "/scommesse/sport/basket/usa/nba/"),
    ("Serie A Basket",    "basket", "/scommesse/sport/basket/italia/serie-a/"),
    ("ATP",               "tennis", "/scommesse/sport/tennis/"),
]
# fmt: on

SIMPLE_MARKET_MAP: dict[str, str] = {
    "1X2": "1X2", "Match Result": "1X2", "Esito Finale": "1X2",
    "Moneyline": "1X2", "Result": "1X2",
    "Double Chance": "DC", "Doppia Chance": "DC",
    "Both Teams to Score": "BTTS", "Goal/No Goal": "BTTS",
}
UO_SPREADS_WANTED: set[str] = {"1.5", "2.5", "3.5"}
OUTCOME_MAP: dict[str, str] = {
    "1": "1", "Home": "1", "Casa": "1",
    "X": "X", "Draw": "X", "Pareggio": "X",
    "2": "2", "Away": "2", "Ospite": "2",
    "1X": "1X", "X2": "X2", "12": "12",
    "Yes": "Goal", "Goal": "Goal", "GG": "Goal",
    "No": "No Goal", "No Goal": "No Goal", "NG": "No Goal",
}


def _parse_date(s: str) -> str | None:
    if not s:
        return None
    FMTS = ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
            "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"]
    for fmt in FMTS:
        try:
            dt = datetime.strptime(s.strip(), fmt)
            off = 2 if 3 <= dt.month <= 10 else 1
            return dt.replace(tzinfo=timezone(timedelta(hours=off))).astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        return s


def _v(d: dict, *keys: str) -> Any:
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def _odds_val(sel: dict) -> float | None:
    v = _v(sel, "price", "odds", "quota", "value", "odd")
    if v is None:
        return None
    try:
        f = float(v)
        return f if f > 1.0 else None
    except (TypeError, ValueError):
        return None


def _label(sel: dict) -> str:
    v = _v(sel, "name", "selectionDescription", "description", "outcome", "label")
    return str(v).strip() if v else ""


def _parse_events(events: list, league_name: str, sport_key: str) -> list[MatchOdds]:
    results: list[MatchOdds] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        name_raw = _v(ev, "name", "eventDescription", "description", "EventName", "eventName") or ""
        name = re.sub(r"\s+v\s+", " - ", str(name_raw)).strip()
        if not name:
            continue
        raw_time = _v(ev, "startDate", "eventDate", "date", "startTime") or ""
        etime = _parse_date(str(raw_time)) if raw_time else None
        murl = str(_v(ev, "url", "deepLink", "link") or f"{BASE_URL}/scommesse/")
        if not murl.startswith("http"):
            murl = BASE_URL + murl
        parts = name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else name
        away = parts[1].strip() if len(parts) == 2 else ""

        mkts_raw = _v(ev, "markets", "market", "Markets", "odds") or []
        if isinstance(mkts_raw, dict):
            mkts_raw = list(mkts_raw.values())

        for mkt in mkts_raw:
            if not isinstance(mkt, dict):
                continue
            mname = str(_v(mkt, "name", "marketDescription", "marketName", "description") or "").strip()
            canonical = SIMPLE_MARKET_MAP.get(mname)
            sels_raw = _v(mkt, "selections", "outcomes", "odds", "runners", "Selections") or []
            if isinstance(sels_raw, dict):
                sels_raw = list(sels_raw.values())

            if canonical:
                odds_dict = {OUTCOME_MAP.get(_label(s), _label(s)): v
                             for s in sels_raw if isinstance(s, dict) and (v := _odds_val(s)) and _label(s)}
                if odds_dict:
                    results.append(MatchOdds(sport=sport_key, league=league_name, home_team=home, away_team=away,
                                             event_name=name, event_time=etime, match_url=murl, market=canonical,
                                             bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}]))
                continue

            if any(kw in mname for kw in ("Over/Under", "Total Goals", "Goals", "Over Under")):
                sp_m = re.search(r"(\d+[.,]\d+)", mname)
                if sp_m:
                    sp = sp_m.group(1).replace(",", ".")
                    if sp in UO_SPREADS_WANTED:
                        SIDE = {"Over": "Over", "Under": "Under"}
                        odds_dict = {}
                        for s in sels_raw:
                            if not isinstance(s, dict):
                                continue
                            side = SIDE.get(_label(s))
                            v = _odds_val(s)
                            if side and v:
                                odds_dict[f"{side} {sp}"] = v
                        if odds_dict:
                            results.append(MatchOdds(sport=sport_key, league=league_name, home_team=home, away_team=away,
                                                     event_name=name, event_time=etime, match_url=murl,
                                                     market=f"Over/Under {sp}",
                                                     bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}]))
    return results


class BetssonScraper(BasePlaywrightScraper):
    bookmaker_name = BOOKMAKER
    base_url = BASE_URL
    warmup_path = "/scommesse/"
    leagues = LEAGUES

    def parse_response(self, url: str, body: Any, league_name: str, sport_key: str) -> list[MatchOdds]:
        try:
            if isinstance(body, dict):
                for key in ("events", "data", "fixtures", "matches", "results", "items",
                            "EventList", "eventList", "matchList"):
                    val = body.get(key)
                    if isinstance(val, list) and val:
                        rows = _parse_events(val, league_name, sport_key)
                        if rows:
                            return rows
                    if isinstance(val, dict):
                        for k2 in ("events", "fixtures", "matches"):
                            v2 = val.get(k2)
                            if isinstance(v2, list) and v2:
                                rows = _parse_events(v2, league_name, sport_key)
                                if rows:
                                    return rows
            if isinstance(body, list) and body and isinstance(body[0], dict):
                return _parse_events(body, league_name, sport_key)
        except Exception as e:
            logger.debug("[Betsson] parse error for %s: %s", url, e)
        return []
