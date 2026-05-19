"""Snai pregame odds scraper — Playwright + network interception."""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from oddsmatcher_backend.scraper._base_playwright import BasePlaywrightScraper
from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)

BASE_URL = "https://www.snai.it"
BOOKMAKER = "Snai"

# fmt: off
LEAGUES: list[tuple[str, str, str]] = [
    ("Serie A",           "calcio", "/scommesse/calcio/italia/serie-a/"),
    ("Serie B",           "calcio", "/scommesse/calcio/italia/serie-b/"),
    ("Premier League",    "calcio", "/scommesse/calcio/inghilterra/premier-league/"),
    ("La Liga",           "calcio", "/scommesse/calcio/spagna/primera-division/"),
    ("Bundesliga",        "calcio", "/scommesse/calcio/germania/bundesliga/"),
    ("Ligue 1",           "calcio", "/scommesse/calcio/francia/ligue-1/"),
    ("Champions League",  "calcio", "/scommesse/calcio/champions-league/"),
    ("Europa League",     "calcio", "/scommesse/calcio/europa-league/"),
    ("Conference League", "calcio", "/scommesse/calcio/conference-league/"),
    ("NBA",               "basket", "/scommesse/basket/usa/nba/"),
    ("Serie A Basket",    "basket", "/scommesse/basket/italia/serie-a/"),
    ("ATP",               "tennis", "/scommesse/tennis/"),
]
# fmt: on

SIMPLE_MARKET_MAP: dict[str, str] = {
    "1X2": "1X2", "Esito Finale": "1X2", "Finale": "1X2", "Match Result": "1X2",
    "Testa a Testa": "1X2", "Vincente": "1X2",
    "Doppia Chance": "DC", "Double Chance": "DC",
    "Goal/No Goal": "BTTS", "Gol/No Gol": "BTTS",
}
UO_SPREADS_WANTED: set[str] = {"1.5", "2.5", "3.5"}

OUTCOME_MAP: dict[str, str] = {
    "1": "1", "Casa": "1", "Home": "1",
    "X": "X", "Pareggio": "X", "Draw": "X",
    "2": "2", "Ospite": "2", "Away": "2",
    "1X": "1X", "X2": "X2", "12": "12",
    "Gol": "Goal", "Goal": "Goal", "GG": "Goal", "Si": "Goal",
    "No Gol": "No Goal", "No Goal": "No Goal", "NG": "No Goal", "No": "No Goal",
}


def _parse_date(s: str) -> str | None:
    if not s:
        return None
    FMTS = ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
            "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M"]
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


def _val(d: dict, *keys: str) -> Any:
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def _odds(sel: dict) -> float | None:
    v = _val(sel, "price", "odds", "quota", "value", "odd", "ov")
    if v is None:
        return None
    try:
        f = float(v)
        return f if f > 1.0 else None
    except (TypeError, ValueError):
        return None


def _label(sel: dict) -> str:
    v = _val(sel, "selectionDescription", "description", "name", "outcome", "esito", "label", "sn")
    return str(v).strip() if v else ""


def _event_name(ev: dict) -> str:
    v = _val(ev, "eventDescription", "description", "name", "eventName", "descrizione", "en")
    return re.sub(r"\s+v\s+", " - ", str(v)).strip() if v else ""


def _event_time(ev: dict) -> str | None:
    v = _val(ev, "eventDate", "date", "startTime", "matchDate", "data", "startDate", "ed")
    return _parse_date(str(v)) if v else None


def _match_url(ev: dict) -> str:
    v = _val(ev, "deepLink", "url", "link", "matchUrl")
    if v:
        u = str(v)
        return u if u.startswith("http") else BASE_URL + u
    return f"{BASE_URL}/scommesse/"


def _selections(mkt: dict) -> list:
    v = _val(mkt, "selections", "outcomes", "odds", "esiti", "runners", "asl")
    if v is None:
        return []
    return list(v.values()) if isinstance(v, dict) else list(v)


def _parse_events(events: list, league_name: str, sport_key: str) -> list[MatchOdds]:
    results: list[MatchOdds] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        name = _event_name(ev)
        if not name:
            continue
        etime = _event_time(ev)
        murl = _match_url(ev)
        parts = name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else name
        away = parts[1].strip() if len(parts) == 2 else ""

        mkts_raw = _val(ev, "markets", "market", "odds", "quote", "scommesse", "mmkW") or []
        if isinstance(mkts_raw, dict):
            mkts_raw = list(mkts_raw.values())

        for mkt in mkts_raw:
            if not isinstance(mkt, dict):
                continue
            mname = (_val(mkt, "marketDescription", "description", "name", "marketName", "tipo", "mn") or "").strip()
            canonical = SIMPLE_MARKET_MAP.get(mname)
            sels = _selections(mkt)

            if canonical:
                odds_dict = {}
                for s in sels:
                    lbl = OUTCOME_MAP.get(_label(s), _label(s))
                    v = _odds(s)
                    if lbl and v:
                        odds_dict[lbl] = v
                if odds_dict:
                    results.append(MatchOdds(sport=sport_key, league=league_name, home_team=home, away_team=away,
                                             event_name=name, event_time=etime, match_url=murl, market=canonical,
                                             bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}]))
                continue

            if any(kw in mname for kw in ("Over/Under", "U/O", "Totale Gol", "Over Under", "Goals")):
                sp_m = re.search(r"(\d+[.,]\d+)", mname)
                if sp_m:
                    sp = sp_m.group(1).replace(",", ".")
                    if sp in UO_SPREADS_WANTED:
                        SIDE = {"Over": "Over", "Oltre": "Over", "O": "Over",
                                "Under": "Under", "Meno": "Under", "U": "Under"}
                        odds_dict = {}
                        for s in sels:
                            side = SIDE.get(_label(s))
                            v = _odds(s)
                            if side and v:
                                odds_dict[f"{side} {sp}"] = v
                        if odds_dict:
                            results.append(MatchOdds(sport=sport_key, league=league_name, home_team=home, away_team=away,
                                                     event_name=name, event_time=etime, match_url=murl,
                                                     market=f"Over/Under {sp}",
                                                     bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}]))
    return results


class SnaiScraper(BasePlaywrightScraper):
    bookmaker_name = BOOKMAKER
    base_url = BASE_URL
    warmup_path = "/scommesse/"
    leagues = LEAGUES

    def parse_response(self, url: str, body: Any, league_name: str, sport_key: str) -> list[MatchOdds]:
        try:
            if isinstance(body, dict):
                for key in ("events", "data", "result", "avvenimenti", "matches", "matchList", "competitionEvents", "fixtures", "leo"):
                    val = body.get(key)
                    if isinstance(val, list) and val:
                        rows = _parse_events(val, league_name, sport_key)
                        if rows:
                            return rows
                    if isinstance(val, dict):
                        for k2 in ("events", "matches", "fixtures", "avvenimenti"):
                            v2 = val.get(k2)
                            if isinstance(v2, list) and v2:
                                rows = _parse_events(v2, league_name, sport_key)
                                if rows:
                                    return rows
            if isinstance(body, list) and body and isinstance(body[0], dict):
                return _parse_events(body, league_name, sport_key)
        except Exception as e:
            logger.debug("[Snai] parse error for %s: %s", url, e)
        return []
