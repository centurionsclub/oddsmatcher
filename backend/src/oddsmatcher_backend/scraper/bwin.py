"""Bwin Italy pregame odds scraper — Playwright + Entain CDS API.

Bwin Italy (Entain group) uses www.bwin.it.
The Entain CDS API requires a runtime-injected x-bwin-accessid token.
Strategy:
  1. Warmup page loads, browser receives x-bwin-accessid in API URLs.
  2. We capture that token from intercepted CDS API calls.
  3. For each league we call the CDS fixtures endpoint via page.evaluate()
     so requests carry the browser's session cookies automatically.

CDS fixtures endpoint:
  /cds-api/bettingoffer/fixtures?x-bwin-accessid={id}&lang=it&country=IT
  &usercountry=IT&fixtureTypes=Standard&state=Active&offer=Main
  &sportIds={sportId}&competitionIds={compId}

League URL structure: /it/sports/{sport}-{sportId}/{country}/{name}-{compId}
"""

import json as _json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from oddsmatcher_backend.scraper._base_playwright import BasePlaywrightScraper
from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)

BASE_URL = "https://www.bwin.it"
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

# Market name → canonical key
SIMPLE_MARKET_MAP: dict[str, str] = {
    "1X2": "1X2", "Risultato 1 X 2": "1X2", "Match Result": "1X2",
    "Esito Finale": "1X2", "Result": "1X2", "Moneyline": "1X2",
    "Scommessa 1 2 - Chi vincerà?": "1X2",
    "Double Chance": "DC", "Doppia Chance": "DC",
    "Both Teams to Score": "BTTS", "Goal/No Goal": "BTTS",
}
UO_SPREADS_WANTED: set[str] = {"1.5", "2.5", "3.5"}
OUTCOME_MAP: dict[str, str] = {
    "1": "1", "Home": "1", "Team 1": "1",
    "X": "X", "Draw": "X", "Tie": "X", "Pareggio": "X",
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
            dt = datetime.strptime(s.strip()[:19], fmt)
            off = 2 if 3 <= dt.month <= 10 else 1
            return dt.replace(tzinfo=timezone(timedelta(hours=off))).astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        return s


def _parse_cds_fixtures(data: Any, league_name: str, sport_key: str) -> list[MatchOdds]:
    """Parse Entain CDS bettingoffer/fixtures response into MatchOdds."""
    results: list[MatchOdds] = []
    if not data:
        return results

    # CDS fixtures endpoint returns a list of fixture objects
    fixtures: list = data if isinstance(data, list) else data.get("fixtures", [])
    if not fixtures:
        return results

    for fix in fixtures:
        if not isinstance(fix, dict):
            continue

        # The fixture info is either at top level or under 'fixture' key
        fobj = fix.get("fixture", fix)
        if not isinstance(fobj, dict):
            continue

        name_raw = fobj.get("name", "") or ""
        # Parse home/away from participants
        participants = fobj.get("participants", [])
        home, away = "", ""
        for p in participants:
            if not isinstance(p, dict):
                continue
            if p.get("homeAway", "").lower() in ("home", "1"):
                home = p.get("name", "")
            elif p.get("homeAway", "").lower() in ("away", "2"):
                away = p.get("name", "")
        if not home:
            parts = re.split(r"\s+v[s]?\s+|\s+-\s+", str(name_raw))
            home = parts[0].strip() if len(parts) >= 2 else str(name_raw).strip()
            away = parts[1].strip() if len(parts) >= 2 else ""
        if not home:
            continue

        event_name = f"{home} - {away}" if away else home
        raw_time = fobj.get("startDate", fobj.get("startTime", ""))
        event_time = _parse_date(str(raw_time)) if raw_time else None
        murl = f"{BASE_URL}/it/sports/"

        # Collect markets: mainEventMarket + markets list
        all_markets: list[dict] = []
        main_mkt = fix.get("mainEventMarket")
        if isinstance(main_mkt, dict):
            all_markets.append(main_mkt)
        for m in (fix.get("markets") or []):
            if isinstance(m, dict):
                all_markets.append(m)

        for mkt in all_markets:
            mname = str(mkt.get("name", mkt.get("typeName", mkt.get("marketType", "")))).strip()
            canonical = SIMPLE_MARKET_MAP.get(mname)
            results_list = mkt.get("results", mkt.get("selections", mkt.get("outcomes", [])))
            if not isinstance(results_list, list):
                continue

            if canonical:
                odds_dict: dict[str, float] = {}
                for r in results_list:
                    if not isinstance(r, dict):
                        continue
                    lbl_raw = str(r.get("name", r.get("originId", r.get("outcome", "")))).strip()
                    lbl = OUTCOME_MAP.get(lbl_raw, lbl_raw)
                    price = r.get("odds", r.get("price", r.get("value", 0)))
                    try:
                        f = float(price)
                        if f > 1.0 and lbl:
                            odds_dict[lbl] = f
                    except (TypeError, ValueError):
                        pass
                if odds_dict:
                    results.append(MatchOdds(
                        sport=sport_key, league=league_name,
                        home_team=home, away_team=away,
                        event_name=event_name, event_time=event_time,
                        match_url=murl, market=canonical,
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                    ))
                continue

            # Over/Under detection
            if any(kw in mname for kw in ("Over/Under", "Total Goals", "Over Under", "Totale Reti")):
                sp_m = re.search(r"(\d+[.,]\d+)", mname)
                if sp_m:
                    sp = sp_m.group(1).replace(",", ".")
                    if sp in UO_SPREADS_WANTED:
                        odds_uo: dict[str, float] = {}
                        for r in results_list:
                            lbl = str(r.get("name", r.get("originId", ""))).strip()
                            if lbl in ("Over", "Under"):
                                price = r.get("odds", r.get("price", 0))
                                try:
                                    f = float(price)
                                    if f > 1.0:
                                        odds_uo[f"{lbl} {sp}"] = f
                                except (TypeError, ValueError):
                                    pass
                        if odds_uo:
                            results.append(MatchOdds(
                                sport=sport_key, league=league_name,
                                home_team=home, away_team=away,
                                event_name=event_name, event_time=event_time,
                                match_url=murl, market=f"Over/Under {sp}",
                                bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_uo}],
                            ))

    return results


def _parse_events(events: list, league_name: str, sport_key: str) -> list[MatchOdds]:
    """Fallback parser for intercepted JSON (non-CDS format)."""
    results: list[MatchOdds] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        name_raw = (ev.get("name") or ev.get("Name") or ev.get("eventDescription") or
                    ev.get("description") or ev.get("EventName") or "")
        name = re.sub(r"\s+v\s+", " - ", str(name_raw)).strip()
        if not name:
            continue
        raw_time = (ev.get("startDate") or ev.get("StartDate") or ev.get("eventDate") or
                    ev.get("date") or ev.get("startTime") or "")
        etime = _parse_date(str(raw_time)) if raw_time else None
        murl = f"{BASE_URL}/it/sports/"
        parts = name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else name
        away = parts[1].strip() if len(parts) == 2 else ""
        mkts_raw = (ev.get("markets") or ev.get("Markets") or ev.get("market") or ev.get("odds") or [])
        if isinstance(mkts_raw, dict):
            mkts_raw = list(mkts_raw.values())
        for mkt in mkts_raw:
            if not isinstance(mkt, dict):
                continue
            mname = str(mkt.get("name") or mkt.get("Name") or mkt.get("marketName") or "").strip()
            canonical = SIMPLE_MARKET_MAP.get(mname)
            sels = (mkt.get("selections") or mkt.get("Selections") or mkt.get("outcomes") or [])
            if isinstance(sels, dict):
                sels = list(sels.values())
            if canonical:
                odds_dict: dict[str, float] = {}
                for s in sels:
                    if not isinstance(s, dict):
                        continue
                    lbl = OUTCOME_MAP.get(
                        str(s.get("name") or s.get("Name") or s.get("selectionDescription") or "").strip(),
                        str(s.get("name") or "").strip()
                    )
                    v = s.get("price") or s.get("odds") or s.get("quota") or s.get("value")
                    try:
                        f = float(v) if v is not None else None
                        if f and f > 1.0 and lbl:
                            odds_dict[lbl] = f
                    except (TypeError, ValueError):
                        pass
                if odds_dict:
                    results.append(MatchOdds(
                        sport=sport_key, league=league_name,
                        home_team=home, away_team=away,
                        event_name=name, event_time=etime,
                        match_url=murl, market=canonical,
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                    ))
    return results


class BwinScraper(BasePlaywrightScraper):
    bookmaker_name = BOOKMAKER
    base_url = BASE_URL
    warmup_path = "/it/sports/calcio-4/"
    leagues = LEAGUES

    def __init__(self):
        super().__init__()
        self._access_id: str = ""  # x-bwin-accessid extracted from intercepted URLs

    def parse_response(self, url: str, body: Any, league_name: str, sport_key: str) -> list[MatchOdds]:
        """Try to parse intercepted responses — logs CDS URLs, tries CDS format."""
        # Log any CDS-related URL for discovery
        if "cds-api" in url:
            logger.info("[Bwin] CDS URL: %s keys=%s",
                        url,
                        list(body.keys())[:6] if isinstance(body, dict)
                        else f"list[{len(body)}]→{list(body[0].keys())[:5]}" if isinstance(body, list) and body and isinstance(body[0], dict)
                        else type(body).__name__)
            # Extract x-bwin-accessid from URL
            m = re.search(r"x-bwin-accessid=([A-Za-z0-9+/=_-]+)", url)
            if m and not self._access_id:
                self._access_id = m.group(1)
                logger.info("[Bwin] Extracted x-bwin-accessid: %s", self._access_id)

        # Try CDS fixtures format (list of fixture objects)
        if isinstance(body, list) and body and isinstance(body[0], dict):
            first = body[0]
            if any(k in first for k in ("fixture", "fixtureId", "mainEventMarket", "startDate")):
                rows = _parse_cds_fixtures(body, league_name, sport_key)
                if rows:
                    return rows

        # Try generic event list format
        try:
            if isinstance(body, dict):
                for key in ("events", "Events", "data", "fixtures", "Fixtures",
                            "matches", "results", "items"):
                    val = body.get(key)
                    if isinstance(val, list) and val:
                        rows = _parse_events(val, league_name, sport_key)
                        if rows:
                            return rows
                        rows = _parse_cds_fixtures(val, league_name, sport_key)
                        if rows:
                            return rows
            if isinstance(body, list) and body and isinstance(body[0], dict):
                rows = _parse_events(body, league_name, sport_key)
                if rows:
                    return rows
        except Exception as e:
            logger.debug("[Bwin] parse error for %s: %s", url, e)
        return []

    async def _scrape_league(
        self,
        league_name: str,
        sport_key: str,
        page_path: str,
    ) -> list[MatchOdds]:
        """Override: try JSON interception first, then CDS API via page.evaluate()."""
        # Phase 1: base class navigation + response interception
        results = await super()._scrape_league(league_name, sport_key, page_path)
        if results:
            return results

        # Phase 2: direct CDS API call from page JS context
        assert self._page is not None

        if not self._access_id:
            logger.warning("[Bwin] %s: no x-bwin-accessid captured yet", league_name)
            return []

        # Extract sportId and competitionId from page_path
        # e.g. "/it/sports/calcio-4/italia/serie-a-67" → sportId=4, compId=67
        ids = re.findall(r"-(\d+)", page_path)
        if len(ids) < 1:
            logger.warning("[Bwin] %s: cannot parse IDs from %s", league_name, page_path)
            return []

        sport_id = ids[0]  # first number after dash = sport ID
        comp_id = ids[-1] if len(ids) >= 2 else None  # last number = competition ID

        params = (
            f"x-bwin-accessid={self._access_id}"
            f"&lang=it&country=IT&usercountry=IT"
            f"&fixtureTypes=Standard&state=Active&offer=Main"
            f"&sportIds={sport_id}"
        )
        if comp_id and comp_id != sport_id:
            params += f"&competitionIds={comp_id}"

        cds_url = f"{BASE_URL}/cds-api/bettingoffer/fixtures?{params}"
        logger.info("[Bwin] %s: calling CDS fixtures API…", league_name)
        logger.info("[Bwin] URL: %s", cds_url)

        try:
            body = await self._page.evaluate(f"""
                async () => {{
                    try {{
                        const resp = await fetch({_json.dumps(cds_url)}, {{
                            headers: {{
                                'Accept': 'application/json',
                                'Accept-Language': 'it-IT,it;q=0.9',
                                'x-bwin-accessid': {_json.dumps(self._access_id)}
                            }},
                            credentials: 'include'
                        }});
                        if (!resp.ok) return {{'_error': resp.status, '_url': '{cds_url}'}};
                        return resp.json();
                    }} catch(e) {{
                        return {{'_error': String(e)}};
                    }}
                }}
            """)
        except Exception as exc:
            logger.error("[Bwin] %s: page.evaluate failed: %s", league_name, exc)
            return []

        if isinstance(body, dict) and "_error" in body:
            logger.warning("[Bwin] %s CDS API error: %s", league_name, body)
            # Log preview to understand response
            return []

        preview = _json.dumps(body, ensure_ascii=False)[:600] if body else "empty"
        logger.info("[Bwin] %s CDS response preview: %s", league_name, preview)

        rows = _parse_cds_fixtures(body, league_name, sport_key)
        logger.info("[Bwin] %s: %d rows from CDS API", league_name, len(rows))
        return rows
