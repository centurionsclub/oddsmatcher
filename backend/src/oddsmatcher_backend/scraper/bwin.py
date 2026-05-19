"""Bwin pregame odds scraper — Playwright + network interception.

Bwin (Entain group) uses sports.bwin.it — same platform as Eurobet in some areas.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from oddsmatcher_backend.scraper._base_playwright import BasePlaywrightScraper
from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)

BASE_URL = "https://sports.bwin.it"
BOOKMAKER = "Bwin"

# fmt: off
LEAGUES: list[tuple[str, str, str]] = [
    ("Serie A",           "calcio", "/it/sports/calcio-4/italia/serie-a-67"),
    ("Serie B",           "calcio", "/it/sports/calcio-4/italia/serie-b-72"),
    ("Premier League",    "calcio", "/it/sports/calcio-4/inghilterra/premier-league-46"),
    ("La Liga",           "calcio", "/it/sports/calcio-4/spagna/primera-division-2687"),
    ("Bundesliga",        "calcio", "/it/sports/calcio-4/germania/bundesliga-65"),
    ("Ligue 1",           "calcio", "/it/sports/calcio-4/francia/ligue-1-55"),
    ("Champions League",  "calcio", "/it/sports/calcio-4/europa/champions-league-7"),
    ("Europa League",     "calcio", "/it/sports/calcio-4/europa/europa-league-379"),
    ("Conference League", "calcio", "/it/sports/calcio-4/europa/conference-league-18340"),
    ("NBA",               "basket", "/it/sports/basket-7/usa/nba-6004"),
    ("Serie A Basket",    "basket", "/it/sports/basket-7/italia/serie-a-lba-596"),
    ("ATP",               "tennis", "/it/sports/tennis-5/"),
]
# fmt: on

SIMPLE_MARKET_MAP: dict[str, str] = {
    "1X2": "1X2", "Match Result": "1X2", "Esito Finale": "1X2",
    "To Win (incl. Extra Time)": "1X2", "Result": "1X2",
    "Moneyline": "1X2",
    "Double Chance": "DC", "Doppia Chance": "DC",
    "Both Teams to Score": "BTTS", "Goal/No Goal": "BTTS",
}
UO_SPREADS_WANTED: set[str] = {"1.5", "2.5", "3.5"}

OUTCOME_MAP: dict[str, str] = {
    "1": "1", "Home": "1", "Team 1": "1",
    "X": "X", "Draw": "X", "Tie": "X",
    "2": "2", "Away": "2", "Team 2": "2",
    "1X": "1X", "X2": "X2", "12": "12",
    "Yes": "Goal", "Goal": "Goal",
    "No": "No Goal", "No Goal": "No Goal",
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


def _odds(sel: dict) -> float | None:
    v = _v(sel, "price", "odds", "quota", "value", "odd", "Price")
    if v is None:
        return None
    try:
        f = float(v)
        return f if f > 1.0 else None
    except (TypeError, ValueError):
        return None


def _label(sel: dict) -> str:
    v = _v(sel, "name", "Name", "selectionDescription", "description", "outcome", "Result")
    return str(v).strip() if v else ""


def _parse_events(events: list, league_name: str, sport_key: str) -> list[MatchOdds]:
    results: list[MatchOdds] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        name_raw = _v(ev, "name", "Name", "eventDescription", "description", "EventName") or ""
        name = re.sub(r"\s+v\s+", " - ", str(name_raw)).strip()
        if not name:
            continue

        raw_time = _v(ev, "startDate", "StartDate", "eventDate", "date", "startTime", "StartTime") or ""
        etime = _parse_date(str(raw_time)) if raw_time else None
        murl = _v(ev, "url", "deepLink", "link") or f"{BASE_URL}/it/sports/"
        if murl and not str(murl).startswith("http"):
            murl = BASE_URL + murl

        parts = name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else name
        away = parts[1].strip() if len(parts) == 2 else ""

        mkts_raw = _v(ev, "markets", "Markets", "market", "odds") or []
        if isinstance(mkts_raw, dict):
            mkts_raw = list(mkts_raw.values())

        for mkt in mkts_raw:
            if not isinstance(mkt, dict):
                continue
            mname = str(_v(mkt, "name", "Name", "marketDescription", "marketName", "description") or "").strip()
            canonical = SIMPLE_MARKET_MAP.get(mname)
            sels_raw = _v(mkt, "selections", "Selections", "outcomes", "odds", "runners") or []
            if isinstance(sels_raw, dict):
                sels_raw = list(sels_raw.values())

            if canonical:
                odds_dict = {}
                for s in sels_raw:
                    if not isinstance(s, dict):
                        continue
                    lbl = OUTCOME_MAP.get(_label(s), _label(s))
                    v = _odds(s)
                    if lbl and v:
                        odds_dict[lbl] = v
                if odds_dict:
                    results.append(MatchOdds(sport=sport_key, league=league_name, home_team=home, away_team=away,
                                             event_name=name, event_time=etime, match_url=str(murl),
                                             market=canonical, bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}]))
                continue

            if any(kw in mname for kw in ("Over/Under", "Total Goals", "Goals Over", "Over Under")):
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
                            v = _odds(s)
                            if side and v:
                                odds_dict[f"{side} {sp}"] = v
                        if odds_dict:
                            results.append(MatchOdds(sport=sport_key, league=league_name, home_team=home, away_team=away,
                                                     event_name=name, event_time=etime, match_url=str(murl),
                                                     market=f"Over/Under {sp}",
                                                     bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}]))
    return results


class BwinScraper(BasePlaywrightScraper):
    bookmaker_name = BOOKMAKER
    base_url = BASE_URL
    warmup_path = "/it/sports/"
    leagues = LEAGUES

    def parse_response(self, url: str, body: Any, league_name: str, sport_key: str) -> list[MatchOdds]:
        try:
            if isinstance(body, dict):
                for key in ("events", "Events", "data", "fixtures", "Fixtures", "matches", "results",
                            "items", "competitions", "leagues"):
                    val = body.get(key)
                    if isinstance(val, list) and val:
                        rows = _parse_events(val, league_name, sport_key)
                        if rows:
                            return rows
                    if isinstance(val, dict):
                        for k2 in ("events", "Events", "fixtures", "Fixtures", "matches"):
                            v2 = val.get(k2)
                            if isinstance(v2, list) and v2:
                                rows = _parse_events(v2, league_name, sport_key)
                                if rows:
                                    return rows
            if isinstance(body, list) and body and isinstance(body[0], dict):
                return _parse_events(body, league_name, sport_key)
        except Exception as e:
            logger.debug("[Bwin] parse error for %s: %s", url, e)
        return []
