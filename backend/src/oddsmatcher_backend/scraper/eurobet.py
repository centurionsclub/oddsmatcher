"""Eurobet pregame odds scraper.

Strategy: Playwright browser + network response interception.
Uses BasePlaywrightScraper — see _base_playwright.py for the shared logic.

NOTE: Parser is best-effort until the first GitHub Actions run reveals
the actual Eurobet API structure via the CAPTURE log lines.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from oddsmatcher_backend.scraper._base_playwright import BasePlaywrightScraper
from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)

BASE_URL = "https://www.eurobet.it"
BOOKMAKER = "Eurobet"

# fmt: off
LEAGUES: list[tuple[str, str, str]] = [
    # Calcio
    ("Serie A",           "calcio", "/it/scommesse/calcio/it-serie-a"),
    ("Serie B",           "calcio", "/it/scommesse/calcio/ita-serie-b"),
    ("Champions League",  "calcio", "/it/scommesse/calcio/eu-champions-league"),
    ("Europa League",     "calcio", "/it/scommesse/calcio/eu-europa-league"),
    ("Conference League", "calcio", "/it/scommesse/calcio/eu-conference-league"),
    ("Premier League",    "calcio", "/it/scommesse/calcio/ing-premier-league"),
    ("La Liga",           "calcio", "/it/scommesse/calcio/es-liga"),
    ("Bundesliga",        "calcio", "/it/scommesse/calcio/de-bundesliga"),
    # Tennis
    ("ATP Amburgo",       "tennis", "/it/scommesse/tennis/de-amburgo"),
    ("ATP Ginevra",       "tennis", "/it/scommesse/tennis/ch-ginevra"),
    ("WTA Rabat",         "tennis", "/it/scommesse/tennis/ma-rabat"),
    ("WTA Strasburgo",    "tennis", "/it/scommesse/tennis/fr-strasburgo"),
    ("Roland Garros",     "tennis", "/it/scommesse/tennis/fr-roland-garros-m"),
    ("Wimbledon",         "tennis", "/it/scommesse/tennis/ing-wimbledon"),
    ("US Open",           "tennis", "/it/scommesse/tennis/us-open-m"),
    ("Australian Open",   "tennis", "/it/scommesse/tennis/au-australian-open-m"),
    # Basket
    ("NBA",               "basket", "/it/scommesse/basket/us-nba"),
    ("Serie A Basket",    "basket", "/it/scommesse/basket/it-serie-a12"),
]
# fmt: on

SIMPLE_MARKET_MAP: dict[str, str] = {
    "1X2": "1X2", "Esito Finale": "1X2", "Match Result": "1X2",
    "Testa A Testa": "1X2", "Testa a Testa": "1X2", "Risultato Finale": "1X2",
    "Doppia Chance": "DC", "Double Chance": "DC",
    "Goal/No Goal": "BTTS", "Gol/No Gol": "BTTS", "Both Teams to Score": "BTTS",
}
UO_SPREADS_WANTED: set[str] = {"1.5", "2.5", "3.5"}

OUTCOME_MAP: dict[str, str] = {
    "1": "1", "Home": "1", "Casa": "1",
    "X": "X", "Draw": "X", "Pareggio": "X",
    "2": "2", "Away": "2", "Ospite": "2",
    "1X": "1X", "X2": "X2", "12": "12",
    "Goal": "Goal", "GG": "Goal", "Si": "Goal", "Yes": "Goal",
    "No Goal": "No Goal", "NG": "No Goal", "No": "No Goal",
}


def _parse_date(date_str: str) -> str | None:
    if not date_str:
        return None
    FORMATS = [
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M",
    ]
    for fmt in FORMATS:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            off = 2 if 3 <= dt.month <= 10 else 1
            return dt.replace(tzinfo=timezone(timedelta(hours=off))).astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        return date_str


def _get_odds_value(sel: dict) -> float | None:
    for key in ("price", "odds", "quota", "value", "odd"):
        v = sel.get(key)
        if v is not None:
            try:
                f = float(v)
                return f if f > 1.0 else None
            except (TypeError, ValueError):
                pass
    return None


def _get_label(sel: dict) -> str:
    for key in ("selectionDescription", "description", "name", "outcome", "esito", "label"):
        v = sel.get(key)
        if v:
            return str(v).strip()
    return ""


def _get_event_name(event: dict) -> str:
    for key in ("eventDescription", "description", "name", "eventName", "descrizione", "event"):
        v = event.get(key)
        if v:
            return re.sub(r"\s+v\s+", " - ", str(v)).strip()
    return ""


def _get_event_time(event: dict) -> str | None:
    for key in ("eventDate", "date", "startTime", "matchDate", "data", "startDate", "eventTime"):
        v = event.get(key)
        if v:
            return _parse_date(str(v))
    return None


def _get_match_url(event: dict) -> str:
    for key in ("deepLink", "url", "link", "matchUrl"):
        v = event.get(key)
        if v:
            u = str(v)
            return u if u.startswith("http") else BASE_URL + u
    return f"{BASE_URL}/it/scommesse/"


def _extract_selections(mkt: dict) -> list:
    for key in ("selections", "outcomes", "odds", "esiti", "runners"):
        v = mkt.get(key)
        if v:
            return list(v.values()) if isinstance(v, dict) else v
    return []


def _parse_events(events: list, league_name: str, sport_key: str) -> list[MatchOdds]:
    results: list[MatchOdds] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_name = _get_event_name(event)
        if not event_name:
            continue
        event_time = _get_event_time(event)
        match_url = _get_match_url(event)
        parts = event_name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else event_name
        away = parts[1].strip() if len(parts) == 2 else ""

        markets_raw = event.get("markets") or event.get("market") or event.get("odds") or event.get("quote") or event.get("scommesse") or []
        if isinstance(markets_raw, dict):
            markets_raw = list(markets_raw.values())

        for mkt in markets_raw:
            if not isinstance(mkt, dict):
                continue
            market_name = (mkt.get("marketDescription") or mkt.get("description") or mkt.get("name") or mkt.get("marketName") or mkt.get("tipo") or "").strip()
            canonical = SIMPLE_MARKET_MAP.get(market_name)
            sels = _extract_selections(mkt)

            if canonical:
                odds_dict = {OUTCOME_MAP.get(_get_label(s), _get_label(s)): v
                             for s in sels if (v := _get_odds_value(s)) and _get_label(s)}
                if odds_dict:
                    results.append(MatchOdds(sport=sport_key, league=league_name, home_team=home, away_team=away,
                                             event_name=event_name, event_time=event_time, match_url=match_url,
                                             market=canonical, bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}]))
                continue

            if any(kw in market_name for kw in ("Over/Under", "Over Under", "U/O", "Totale Gol", "Goals")):
                spread_m = re.search(r"(\d+[.,]\d+)", market_name)
                if spread_m:
                    sp = spread_m.group(1).replace(",", ".")
                    if sp in UO_SPREADS_WANTED:
                        SIDE = {"Over": "Over", "Oltre": "Over", "O": "Over", "Under": "Under", "Meno": "Under", "U": "Under"}
                        odds_dict = {}
                        for s in sels:
                            side = SIDE.get(_get_label(s))
                            if side and (v := _get_odds_value(s)):
                                odds_dict[f"{side} {sp}"] = v
                        if odds_dict:
                            results.append(MatchOdds(sport=sport_key, league=league_name, home_team=home, away_team=away,
                                                     event_name=event_name, event_time=event_time, match_url=match_url,
                                                     market=f"Over/Under {sp}", bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}]))
    return results


class EurobetScraper(BasePlaywrightScraper):
    bookmaker_name = BOOKMAKER
    base_url = BASE_URL
    warmup_path = "/it/scommesse/"
    leagues = LEAGUES

    def parse_response(self, url: str, body: Any, league_name: str, sport_key: str) -> list[MatchOdds]:
        try:
            if isinstance(body, dict):
                for key in ("events", "data", "result", "competitionEvents", "matchList", "matches", "fixtures", "avvenimenti"):
                    val = body.get(key)
                    if isinstance(val, list) and val:
                        rows = _parse_events(val, league_name, sport_key)
                        if rows:
                            return rows
                    if isinstance(val, dict):
                        for k2 in ("events", "matches", "fixtures"):
                            v2 = val.get(k2)
                            if isinstance(v2, list) and v2:
                                rows = _parse_events(v2, league_name, sport_key)
                                if rows:
                                    return rows
            if isinstance(body, list) and body and isinstance(body[0], dict):
                return _parse_events(body, league_name, sport_key)
        except Exception as e:
            logger.debug("[Eurobet] parse error for %s: %s", url, e)
        return []
