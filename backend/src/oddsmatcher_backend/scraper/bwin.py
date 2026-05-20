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

# Competition ID → (league_name, sport_key).
# Bwin uses internal CDS competition IDs that differ from URL path IDs.
# Discovered by running the scraper with diagnostic logging.
# NOTE: Calcio league IDs (Serie A, Premier League, etc.) may change between seasons —
#       add them here once discovered from diagnostic logs when those leagues are active.
_COMP_ID_TO_LEAGUE: dict[int, tuple[str, str]] = {
    # ── Calcio (current) ─────────────────────────────────────────────
    102855: ("Champions League",  "calcio"),
    102919: ("Conference League", "calcio"),
    # Season IDs to be discovered when active (use diagnostic logs):
    # ???: ("Serie A",           "calcio"),
    # ???: ("Serie B",           "calcio"),
    # ???: ("Premier League",    "calcio"),
    # ???: ("La Liga",           "calcio"),
    # ???: ("Bundesliga",        "calcio"),
    # ???: ("Ligue 1",           "calcio"),
    # ???: ("Europa League",     "calcio"),

    # ── Basket ───────────────────────────────────────────────────────
    8548: ("NBA",            "basket"),
    8545: ("Eurolega",       "basket"),
    8533: ("Serie A Basket", "basket"),
}

# For tennis we accept ALL competition IDs and label them "ATP"
# (tournament-specific IDs change every week — no fixed mapping possible)
_TENNIS_CATCHALL_LEAGUE = "ATP"

# Market name → canonical key
SIMPLE_MARKET_MAP: dict[str, str] = {
    "1X2": "1X2", "Risultato 1 X 2": "1X2", "Match Result": "1X2",
    "Esito Finale": "1X2", "Result": "1X2", "Moneyline": "1X2",
    "Scommessa 1 2 - Chi vincerà?": "1X2",
    # Basket/tennis head-to-head (no draw, 2 outcomes)
    "Testa a testa (vincitore)": "1X2", "Vincitore partita": "1X2",
    "Head to Head": "1X2", "Testa a Testa": "1X2",
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


def _get_name_str(obj: Any) -> str:
    """Extract name string from a Bwin CDS name field (may be str or {"value": "..."})."""
    if isinstance(obj, dict):
        return str(obj.get("value", obj.get("name", ""))).strip()
    return str(obj).strip() if obj else ""


def _get_odds_float(r: dict) -> float | None:
    """Extract decimal odds from a Bwin CDS result/option."""
    # Direct odds field
    v = r.get("odds")
    if v is not None:
        try:
            f = float(v)
            return f if f > 1.0 else None
        except (TypeError, ValueError):
            pass
    # price sub-object
    price = r.get("price")
    if isinstance(price, dict):
        v = price.get("odds", price.get("decimalOdds"))
        if v is not None:
            try:
                f = float(v)
                return f if f > 1.0 else None
            except (TypeError, ValueError):
                pass
    return None


def _parse_cds_fixtures(data: Any, league_name: str, sport_key: str) -> list[MatchOdds]:
    """Parse Entain CDS bettingoffer/fixtures response into MatchOdds.

    Bwin CDS responses come in two forms:
    A) List of fixture objects (old format)
    B) {"fixtures": [...]} with each fixture having:
       - optionMarkets: [{"name": {"value": "1X2"}, "options": [...], ...}]  (soccer)
       - games: [{"name": {"value": "Vincitore"}, "results": [...], ...}]   (tennis/basket)
       Each fixture has "name" (match name) and "startDate".
    """
    results: list[MatchOdds] = []
    if not data:
        return results

    # Normalise to a list of fixture dicts
    fixtures: list = data if isinstance(data, list) else (data.get("fixtures") or [])
    if not fixtures:
        return results

    _unknown_logged: set = set()
    for fix in fixtures:
        if not isinstance(fix, dict):
            continue

        # ── Determine real league from competition inside fixture ───────
        fix_league = league_name
        fix_sport = sport_key
        comp_obj = (fix.get("competition") or
                    fix.get("fixture", {}).get("competition") or {})
        if isinstance(comp_obj, dict):
            comp_id = comp_obj.get("id")
            if comp_id is not None:
                try:
                    cid = int(comp_id)
                    mapping = _COMP_ID_TO_LEAGUE.get(cid)
                    if mapping:
                        fix_league, fix_sport = mapping
                    elif sport_key == "tennis":
                        # Tennis: accept all tournaments, label as ATP
                        fix_league = _TENNIS_CATCHALL_LEAGUE
                        fix_sport = "tennis"
                    else:
                        # Calcio/basket: unknown competition — log once, skip
                        if cid not in _unknown_logged:
                            _unknown_logged.add(cid)
                            comp_name = _get_name_str(comp_obj.get("name", ""))
                            logger.info("[Bwin] Unknown comp_id=%s name=%r sport=%s — add to _COMP_ID_TO_LEAGUE",
                                        cid, comp_name, sport_key)
                        continue
                except (TypeError, ValueError):
                    pass

        # ── Extract event name and time ────────────────────────────────
        name_obj = fix.get("name") or fix.get("fixture", {}).get("name", "")
        name_raw = _get_name_str(name_obj)
        if not name_raw:
            name_raw = str(fix.get("fixture", {}).get("name", ""))

        raw_time = fix.get("startDate") or fix.get("startTime") or fix.get("fixture", {}).get("startDate", "")
        event_time = _parse_date(str(raw_time)) if raw_time else None
        murl = f"{BASE_URL}/it/sports/"

        # ── Extract home/away from participants ────────────────────────
        participants = fix.get("participants") or fix.get("fixture", {}).get("participants", [])
        home, away = "", ""
        for p in (participants or []):
            if not isinstance(p, dict):
                continue
            ha = str(p.get("homeAway", p.get("type", ""))).lower()
            pname = _get_name_str(p.get("name", ""))
            if ha in ("home", "1") and not home:
                home = pname
            elif ha in ("away", "2") and not away:
                away = pname
        if not home:
            parts = re.split(r"\s+v[s]?\s+|\s+-\s+", name_raw)
            home = parts[0].strip() if len(parts) >= 2 else name_raw.strip()
            away = parts[1].strip() if len(parts) >= 2 else ""
        if not home:
            continue

        event_name = f"{home} - {away}" if away else home

        # ── Collect all market objects ─────────────────────────────────
        # optionMarkets = soccer markets (with "options" as selections)
        # games = tennis/basket markets (with "results" as selections)
        # mainEventMarket, markets = legacy/alternative keys
        all_markets: list[tuple[str, list]] = []  # (market_name, selections_list)

        for mkt in (fix.get("optionMarkets") or []):
            if not isinstance(mkt, dict):
                continue
            mname = _get_name_str(mkt.get("name", ""))
            sels = mkt.get("options") or []
            all_markets.append((mname, sels))

        for mkt in (fix.get("games") or []):
            if not isinstance(mkt, dict):
                continue
            mname = _get_name_str(mkt.get("name", ""))
            sels = mkt.get("results") or []
            all_markets.append((mname, sels))

        # Legacy keys
        for key in ("mainEventMarket", "markets", "market"):
            val = fix.get(key)
            if isinstance(val, dict):
                mname = _get_name_str(val.get("name", ""))
                sels = val.get("results", val.get("selections", val.get("outcomes", [])))
                if isinstance(sels, list):
                    all_markets.append((mname, sels))
            elif isinstance(val, list):
                for m in val:
                    if isinstance(m, dict):
                        mname = _get_name_str(m.get("name", ""))
                        sels = m.get("results", m.get("selections", m.get("outcomes", m.get("options", []))))
                        if isinstance(sels, list):
                            all_markets.append((mname, sels))

        # ── Parse markets ──────────────────────────────────────────────
        for mname, sels_raw in all_markets:
            canonical = SIMPLE_MARKET_MAP.get(mname)

            if canonical:
                odds_dict: dict[str, float] = {}
                for r in sels_raw:
                    if not isinstance(r, dict):
                        continue
                    # Prefer sourceName ("1"/"X"/"2") over display name (player name)
                    lbl_raw = _get_name_str(r.get("sourceName") or r.get("name", ""))
                    lbl = OUTCOME_MAP.get(lbl_raw, lbl_raw)
                    f = _get_odds_float(r)
                    if f and lbl:
                        odds_dict[lbl] = f
                if odds_dict:
                    results.append(MatchOdds(
                        sport=fix_sport, league=fix_league,
                        home_team=home, away_team=away,
                        event_name=event_name, event_time=event_time,
                        match_url=murl, market=canonical,
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                    ))
                continue

            # Over/Under detection
            if any(kw in mname for kw in ("Over/Under", "Total Goals", "Over Under", "Totale Reti", "Totale gol")):
                sp_m = re.search(r"(\d+[.,]\d+)", mname)
                if sp_m:
                    sp = sp_m.group(1).replace(",", ".")
                    if sp in UO_SPREADS_WANTED:
                        odds_uo: dict[str, float] = {}
                        for r in sels_raw:
                            if not isinstance(r, dict):
                                continue
                            lbl = _get_name_str(r.get("name") or r.get("sourceName", ""))
                            side = "Over" if "over" in lbl.lower() else ("Under" if "under" in lbl.lower() else None)
                            if not side:
                                continue
                            f = _get_odds_float(r)
                            if f:
                                odds_uo[f"{side} {sp}"] = f
                        if odds_uo:
                            results.append(MatchOdds(
                                sport=fix_sport, league=fix_league,
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
        self._captured_rows: list[MatchOdds] = []  # responses captured during navigation

    async def _start(self) -> None:
        """Override: navigate to sport pages, intercept CDS response bodies."""
        from playwright.async_api import Response as _Response
        import os, urllib.parse

        self._playwright = await __import__(
            "playwright.async_api", fromlist=["async_playwright"]
        ).async_playwright().start()
        proxy_url = os.environ.get("PROXY_URL")
        proxy = None
        if proxy_url:
            p = urllib.parse.urlparse(proxy_url)
            proxy = {
                "server": f"{p.scheme}://{p.hostname}:{p.port}",
                "username": p.username or "",
                "password": p.password or "",
            }
            self._log.info("[Bwin] Usando proxy: %s:%s", p.hostname, p.port)

        self._browser = await self._playwright.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            proxy=proxy,
        )
        _UA = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        self._context = await self._browser.new_context(
            user_agent=_UA,
            locale="it-IT",
            timezone_id="Europe/Rome",
            viewport={"width": 1280, "height": 800},
        )
        self._page = await self._context.new_page()

        try:
            from playwright_stealth import stealth_async as _stealth_async
            await _stealth_async(self._page)
            self._log.info("[Bwin] playwright-stealth applied")
        except ImportError:
            self._log.warning("[Bwin] playwright-stealth not installed")

        # Navigate to each sport overview page.
        # CDS fixture objects contain competition.id — _parse_cds_fixtures
        # uses _COMP_ID_TO_LEAGUE to determine the real league per fixture.
        SPORT_PAGES: list[tuple[str, str]] = [
            ("calcio",  "/it/sports/calcio-4/"),
            ("basket",  "/it/sports/basket-7/"),
            ("tennis",  "/it/sports/tennis-5/"),
        ]
        for sport_key, sport_path in SPORT_PAGES:
            rows = await self._navigate_and_capture(sport_key, sport_path)
            self._captured_rows.extend(rows)
            self._log.info("[Bwin] %s: %d rows captured during navigation",
                           sport_key, len(rows))

    async def _navigate_and_capture(
        self, sport_key: str, sport_path: str
    ) -> list[MatchOdds]:
        """Navigate to a sport overview page and capture all CDS fixture responses.

        League names are extracted from competition.id inside each fixture via
        _COMP_ID_TO_LEAGUE — no need to infer league from the URL.
        """
        from playwright.async_api import Response as _Response

        assert self._page is not None
        captured: list[MatchOdds] = []

        async def _on_response(resp: _Response) -> None:
            if "cds-api/bettingoffer/fixtures" not in resp.url:
                return
            try:
                body = await resp.json()
                rows = _parse_cds_fixtures(body, sport_key, sport_key)
                if rows:
                    # Count rows per league for diagnostics
                    from collections import Counter
                    leagues = Counter(r.league for r in rows)
                    logger.info("[Bwin] Intercepted %s: %d rows %s",
                                sport_key, len(rows), dict(leagues))
                    captured.extend(rows)
            except Exception as exc:
                logger.info("[Bwin] CDS resp parse error: %s", exc)

        self._page.on("response", _on_response)
        url = self.base_url + sport_path
        self._log.info("[Bwin] Navigating to %s", url)
        try:
            await self._page.goto(url, wait_until="networkidle", timeout=45_000)
            self._log.info("[Bwin] %s: networkidle", sport_key)
        except Exception as e:
            self._log.info("[Bwin] %s: %s — continuing", sport_key, type(e).__name__)
        await self._page.wait_for_timeout(3000)
        self._page.remove_listener("response", _on_response)
        return captured

    def parse_response(self, url: str, body: Any, league_name: str, sport_key: str) -> list[MatchOdds]:
        """Fallback for any JSON intercepted during base navigation (rarely fires)."""
        if "cds-api" in url:
            logger.info("[Bwin] CDS URL intercepted via base: %s", url[:120])
        if isinstance(body, list) and body and isinstance(body[0], dict):
            rows = _parse_cds_fixtures(body, league_name, sport_key)
            if rows:
                return rows
        try:
            if isinstance(body, dict):
                for key in ("events", "Events", "data", "fixtures", "Fixtures", "matches", "results"):
                    val = body.get(key)
                    if isinstance(val, list) and val:
                        rows = _parse_events(val, league_name, sport_key)
                        if rows:
                            return rows
        except Exception as e:
            logger.debug("[Bwin] parse error for %s: %s", url, e)
        return []

    async def _scrape_leagues(self, sport: str | None) -> list[MatchOdds]:
        """Return rows already captured during _start() navigation.

        All CDS fixture responses were captured during sport-page navigations.
        No additional navigation or fetch() calls needed.
        """
        if not self._captured_rows:
            logger.warning("[Bwin] No CDS fixture data captured during navigation")
        else:
            n_events = len({r.event_name for r in self._captured_rows})
            logger.info("[Bwin] Total from navigation: %d events, %d rows",
                        n_events, len(self._captured_rows))

        # Filter by sport if requested
        rows = [r for r in self._captured_rows if r.sport == sport] if sport else list(self._captured_rows)

        # Deduplicate: same event may appear in multiple CDS responses during navigation.
        # Keep the last captured entry per (event_name, market) to avoid DB unique-key conflicts.
        seen: dict[tuple[str, str], MatchOdds] = {}
        for r in rows:
            seen[(r.event_name, r.market)] = r
        filtered = list(seen.values())

        n_before = len(rows)
        n_after = len(filtered)
        if n_before != n_after:
            logger.info("[Bwin] Deduplicated %d → %d rows", n_before, n_after)

        self._log.info("[Bwin] Total match+market rows: %d", len(filtered))
        return filtered
