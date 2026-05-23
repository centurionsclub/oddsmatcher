"""Eurobet Italy pregame odds scraper.

Two-tier approach:
  1. webeb legacy API (web.eurobet.it/webeb/sport) — httpx, no proxy needed.
     Provides: calcio 1X2 / DC / BTTS for the main leagues.
     Limitation: no O/U, no tennis, no basket (chooseSport 2/3 → retCode:-1).

  2. Playwright + mobile proxy — www.eurobet.it main site via BasePlaywrightScraper.
     Provides: calcio O/U + ALL tennis + ALL basket.
     Intercepts ALL JSON responses (no URL filter), same pattern as Sisal/Lottomatica.

Both sets of results are merged before returning.  Duplicates on the same
(event_name, market) key are resolved in favour of the webeb source (it is
faster and more reliable for 1X2/BTTS/DC).
"""

import asyncio
import logging
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from oddsmatcher_backend.scraper._base_playwright import BasePlaywrightScraper
from oddsmatcher_backend.scraper.models import MatchOdds

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

BOOKMAKER = "Eurobet"
BASE_URL  = "https://www.eurobet.it"
WEBEB_URL = "https://web.eurobet.it/webeb/sport"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9",
    "Referer": "https://web.eurobet.it/webeb/sport",
}

# ─── webeb league config ──────────────────────────────────────────────────────

# (league_name, chooseSport, meetingsParam)
WEBEB_MEETINGS: dict[str, list[tuple[str, int, int]]] = {
    # NOTE: the webeb legacy API (web.eurobet.it) only supports calcio (chooseSport=1).
    # chooseSport=2 (basket) and chooseSport=3 (tennis) always return retCode:-1.
    # Tennis and basket are only available on www.eurobet.it (Cloudflare-protected).
    "calcio": [
        ("Champions League",  1, 18),
        ("Conference League", 1, 2474),
        ("Premier League",    1, 86),
        ("La Liga",           1, 79),
        ("Bundesliga",        1, 4),
        ("Ligue 1",           1, 14),
        ("Serie A",           1, 21),
        ("Serie B",           1, 22),
    ],
}

BET_TYPES: list[tuple[int, str]] = [
    (3,      "1X2"),
    (200018, "DC"),
    (18,     "BTTS"),
]

# ─── Playwright league config (main site) ────────────────────────────────────

# (league_name, sport_key, page_path)
# These pages trigger JSON API calls that BasePlaywrightScraper intercepts.
PLAYWRIGHT_LEAGUES: list[tuple[str, str, str]] = [
    # Calcio — for O/U (1X2/DC/BTTS already covered by webeb)
    ("Serie A",           "calcio", "/it/scommesse/calcio/serie-a/"),
    ("Serie B",           "calcio", "/it/scommesse/calcio/serie-b/"),
    ("Premier League",    "calcio", "/it/scommesse/calcio/inghilterra/premier-league/"),
    ("La Liga",           "calcio", "/it/scommesse/calcio/spagna/primera-division/"),
    ("Bundesliga",        "calcio", "/it/scommesse/calcio/germania/bundesliga/"),
    ("Ligue 1",           "calcio", "/it/scommesse/calcio/francia/ligue-1/"),
    ("Champions League",  "calcio", "/it/scommesse/calcio/competizioni-europee/champions-league/"),
    ("Conference League", "calcio", "/it/scommesse/calcio/competizioni-europee/conference-league/"),
    # Tennis — overview loads all active tournaments
    ("Tennis",            "tennis", "/it/scommesse/tennis/"),
    # Basket
    ("NBA",               "basket", "/it/scommesse/basket/usa/nba/"),
    ("Eurolega",          "basket", "/it/scommesse/basket/competizioni-europee/eurolega/"),
    ("Serie A Basket",    "basket", "/it/scommesse/basket/italia/serie-a/"),
]

# ─── webeb parser ─────────────────────────────────────────────────────────────

def _webeb_url(choose_sport: int, meetings_param: int, bet_types_param: int) -> str:
    return (
        f"{WEBEB_URL}?action=scommesseV2_meeting_comm"
        f"&meetingsParam={meetings_param}"
        f"&chooseSport={choose_sport}"
        f"&betTypesParam={bet_types_param}"
        f"&betTypeGroupSel=1&showSplash=0"
    )


def _parse_italy_date(date_str: str, time_str: str = "") -> str | None:
    try:
        s = f"{date_str.strip()} {time_str.strip()}".strip()
        fmt = "%d/%m/%Y %H:%M" if time_str.strip() else "%d/%m/%Y"
        dt = datetime.strptime(s, fmt)
        off = 2 if 3 <= dt.month <= 10 else 1
        return dt.replace(tzinfo=timezone(timedelta(hours=off))).astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def _extract_event_times(html: str) -> dict[str, str]:
    date_times = re.findall(
        r'class="box_container_scommesse_info[^"]*"[^>]*>.*?'
        r'<h4>\s*(\d+/\d+)\s*</h4>\s*<p>\s*(\d+:\d+)',
        html, re.DOTALL,
    )
    event_codes = re.findall(r'loadSingleEventPage\s*\(\s*\d+\s*,\s*(\d+)\s*,', html)
    result: dict[str, str] = {}
    if len(date_times) == len(event_codes) and date_times:
        current_year = datetime.now().year
        for (date_part, time_part), code in zip(date_times, event_codes):
            full_date = f"{date_part}/{current_year}"
            parsed = _parse_italy_date(full_date, time_part)
            if parsed:
                result[code] = parsed
    return result


def _parse_webeb_html(html: str, league_name: str, sport_key: str, bet_label: str) -> list[MatchOdds]:
    bets = re.findall(r'onMouseUp="placeBet\(([^"]+)\)"', html)
    if not bets:
        logger.info("[Eurobet] %s / %s: 0 placeBet calls (len=%d)", league_name, bet_label, len(html))
        return []
    logger.info("[Eurobet] %s / %s: %d placeBet calls", league_name, bet_label, len(bets))

    event_times = _extract_event_times(html)
    market_data: dict[tuple[str, str], dict] = {}

    for bet_str in bets:
        args = re.findall(r"'([^']*)'", bet_str)
        if len(args) < 22:
            continue
        bet_code   = args[8]
        bet_name   = args[9]
        ev_code    = args[10]
        ev_name    = args[11]
        outcome    = args[14]
        odds_str   = args[15]
        date_str   = args[21]

        if not ev_name or not odds_str:
            continue
        try:
            odds_val = float(odds_str)
        except (ValueError, TypeError):
            continue
        if odds_val <= 1.0:
            continue

        bn_lower = bet_name.lower()
        if bet_code == "3" or "1x2" in bn_lower:
            market_key = "1X2"
            outcome_mapped = {"1": "1", "X": "X", "2": "2"}.get(outcome, outcome)
        elif bet_code == "200018" or "doppia" in bn_lower:
            market_key = "DC"
            outcome_mapped = {"1X": "1X", "X2": "X2", "12": "12"}.get(outcome, outcome)
        elif bet_code == "18" or "goal/no goal" in bn_lower:
            market_key = "BTTS"
            ol = outcome.lower()
            outcome_mapped = ("Goal" if ol in ("goal", "si", "sì", "yes", "gg")
                              else "No Goal" if ol in ("nogoal", "no goal", "no", "ng")
                              else outcome)
        else:
            continue

        parts = ev_name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else ev_name
        away = parts[1].strip() if len(parts) == 2 else ""
        ev_time = event_times.get(ev_code) or _parse_italy_date(date_str)

        key = (ev_name, market_key)
        if key not in market_data:
            market_data[key] = {"home": home, "away": away, "event_time": ev_time, "odds": {}}
        market_data[key]["odds"][outcome_mapped] = odds_val

    results: list[MatchOdds] = []
    for (ev_name, market_key), data in market_data.items():
        odds = data["odds"]
        if not odds:
            continue
        if market_key == "BTTS" and len(odds) < 2:
            continue
        results.append(MatchOdds(
            sport=sport_key, league=league_name,
            home_team=data["home"], away_team=data["away"],
            event_name=ev_name, event_time=data["event_time"],
            match_url=f"{BASE_URL}/it/scommesse/",
            market=market_key,
            bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds}],
        ))
    return results


# ─── Playwright / detail-service parser ──────────────────────────────────────

def _parse_date_eurobet(s: str) -> str | None:
    """Parse various Eurobet date formats to UTC ISO string."""
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            dt = datetime.strptime(s[:19], fmt)
            off = 2 if 3 <= dt.month <= 10 else 1
            return dt.replace(tzinfo=timezone(timedelta(hours=off))).astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        return s


_OU_SPREADS = {"0.5", "1.5", "2.5", "3.5", "4.5", "5.5"}

_OUTCOME_MAP: dict[str, str] = {
    "1": "1", "home": "1", "casa": "1",
    "x": "X", "draw": "X", "pareggio": "X",
    "2": "2", "away": "2", "ospite": "2",
    "1x": "1X", "x2": "X2", "12": "12",
    "goal": "Goal", "gg": "Goal", "sì": "Goal", "si": "Goal", "yes": "Goal",
    "no goal": "No Goal", "ng": "No Goal", "no": "No Goal",
    "over": "Over", "o": "Over",
    "under": "Under", "u": "Under",
}


def _map_outcome(raw: str) -> str:
    return _OUTCOME_MAP.get(raw.lower().strip(), raw)


def _parse_detail_response(data: Any, league_name: str, sport_key: str) -> list[MatchOdds]:
    """Parse Eurobet detail-service / SPA JSON response.

    Supports several known response shapes and falls back gracefully.
    Full debug logging so we can learn the real structure on first run.
    """
    if not data or not isinstance(data, dict):
        return []

    results: list[MatchOdds] = []

    # ── Shape 1: {"body": {"result": {"avvenimenti": [...]}}} ─────────────────
    body = data.get("body") or data
    result_node = body.get("result") or body if isinstance(body, dict) else {}

    # Try multiple known keys for the events list
    events: list = []
    for key in ("avvenimenti", "avvenimento", "events", "event", "matches", "match",
                "items", "data", "eventiList", "eventiFeList"):
        val = result_node.get(key) if isinstance(result_node, dict) else None
        if isinstance(val, list) and val:
            events = val
            break

    # ── Shape 2: body is itself a list ────────────────────────────────────────
    if not events and isinstance(body, list):
        events = body

    if not events:
        logger.debug("[Eurobet-PW] _parse_detail_response: no events list found, keys=%s",
                     list(result_node.keys())[:10] if isinstance(result_node, dict) else type(result_node))
        return []

    logger.info("[Eurobet-PW] _parse_detail_response: %d events for %s", len(events), league_name)

    for ev in events:
        if not isinstance(ev, dict):
            continue

        # Event name — try multiple field names
        ev_name_raw = (
            ev.get("descrizione") or ev.get("description") or ev.get("name") or
            ev.get("eventName") or ev.get("label") or ev.get("nome") or ""
        )
        ev_name = re.sub(r"\s+v\s+|\s+vs\s+", " - ", str(ev_name_raw)).strip()
        if not ev_name:
            continue

        # Event time
        raw_time = (ev.get("data") or ev.get("dataOra") or ev.get("startDate") or
                    ev.get("startTime") or ev.get("dateTime") or ev.get("date") or "")
        ev_time = _parse_date_eurobet(str(raw_time)) if raw_time else None

        parts = ev_name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else ev_name
        away = parts[1].strip() if len(parts) == 2 else ""

        # Determine league from event if possible (tennis tournaments)
        ev_league = (ev.get("campionato") or ev.get("competizione") or
                     ev.get("league") or ev.get("tournament") or league_name)
        league_name_ev = str(ev_league) if (sport_key == "tennis" and ev_league != league_name) else league_name

        # Markets — look for odds data in various locations
        market_data: dict[str, dict[str, float]] = {}  # market_key → {outcome → odds}

        # Collect bet/market objects
        bets_raw: list = []
        for mk in ("scommesse", "bets", "markets", "betOffers", "scommessa",
                   "mercati", "offerte", "quote"):
            val = ev.get(mk)
            if isinstance(val, list):
                bets_raw.extend(val)
            elif isinstance(val, dict):
                bets_raw.extend(val.values())

        for bet in bets_raw:
            if not isinstance(bet, dict):
                continue

            # Market name / type
            mkt_name = str(
                bet.get("descrizione") or bet.get("description") or
                bet.get("name") or bet.get("type") or bet.get("label") or ""
            ).strip()
            mkt_lower = mkt_name.lower()

            # Detect market type
            if any(k in mkt_lower for k in ("1x2", "esito finale", "risultato", "testa a testa",
                                             "vincitore", "t/t", "1 x 2", "moneyline")):
                market_key = "1X2"
            elif any(k in mkt_lower for k in ("doppia chance", "double chance", "dc")):
                market_key = "DC"
            elif any(k in mkt_lower for k in ("goal/no goal", "gol/no gol", "gg/ng", "btts")):
                market_key = "BTTS"
            elif any(k in mkt_lower for k in ("over", "under", "u/o", "totale", "total",
                                               "somma", "reti")):
                # Extract spread
                sp_m = re.search(r"(\d+[.,]\d+)", mkt_name)
                if not sp_m:
                    continue
                spread = sp_m.group(1).replace(",", ".")
                if spread not in _OU_SPREADS:
                    continue
                market_key = f"Over/Under {spread}"
            else:
                continue

            # Collect outcomes/odds
            outcomes_raw: list = []
            for ok in ("esiti", "outcomes", "selections", "options", "risultati",
                       "quote", "odds", "esito"):
                val = bet.get(ok)
                if isinstance(val, list):
                    outcomes_raw.extend(val)
                    break

            odds_dict: dict[str, float] = {}
            for oc in outcomes_raw:
                if not isinstance(oc, dict):
                    continue
                label_raw = str(
                    oc.get("descrizione") or oc.get("description") or
                    oc.get("label") or oc.get("name") or oc.get("outcome") or ""
                ).strip()
                label = _map_outcome(label_raw)

                # Extract quota value
                quota = None
                for qk in ("quota", "odds", "value", "price", "decimalOdds",
                           "quotaDecimale", "q"):
                    v = oc.get(qk)
                    if v is not None:
                        try:
                            quota = float(v)
                            if quota > 1.0:
                                break
                        except (TypeError, ValueError):
                            pass

                if quota and quota > 1.0 and label:
                    odds_dict[label] = quota

            if odds_dict:
                if market_key not in market_data:
                    market_data[market_key] = {}
                market_data[market_key].update(odds_dict)

        for mkt_key, odds in market_data.items():
            if not odds:
                continue
            if mkt_key == "BTTS" and len(odds) < 2:
                continue
            results.append(MatchOdds(
                sport=sport_key, league=league_name_ev,
                home_team=home, away_team=away,
                event_name=ev_name, event_time=ev_time,
                match_url=f"{BASE_URL}/it/scommesse/",
                market=mkt_key,
                bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds}],
            ))

    return results


# ─── Next.js __NEXT_DATA__ parser ────────────────────────────────────────────

def _parse_next_data(next_data: Any, league_name: str, sport_key: str) -> list[MatchOdds]:
    """Extract MatchOdds from Next.js __NEXT_DATA__ embedded in the page HTML.

    Eurobet's Next.js pages include all the page data in a <script id="__NEXT_DATA__">
    JSON tag.  The odds are somewhere in props.pageProps — we navigate the tree looking
    for event/market structures.
    """
    if not isinstance(next_data, dict):
        return []

    # Navigate into pageProps
    page_props = (
        next_data.get("props", {}).get("pageProps", {})
    )
    if not page_props:
        return []

    # Try several known locations where Eurobet might put odds data
    candidates: list[Any] = []

    # Common Next.js patterns
    for key in ("data", "initialData", "events", "avvenimenti", "fixtures",
                "scommesse", "meetings", "meeting", "palinsesto", "offerte",
                "betOffers", "odds", "content"):
        val = page_props.get(key)
        if val:
            candidates.append(val)

    # Also try the whole pageProps as-is
    candidates.append(page_props)

    for candidate in candidates:
        rows = _parse_detail_response(candidate, league_name, sport_key)
        if rows:
            return rows

    return []


# ─── httpx direct API probe ──────────────────────────────────────────────────
#
# Cloudflare challenges HTML pages but often lets REST API requests through
# when the request looks like AJAX (Accept: application/json, no cookie).
# We try this first — it's much faster than Playwright.
#
# Known detail-service path:
#   /detail-service/sport-schedule/services/meeting/{disc}/{alias}?prematch=1&live=0
#
# Discipline IDs (guessed from URL patterns — adjust if response confirms them):
#   4 = calcio,  5 = tennis,  7 = basket

# league_name → (endpoint_type, full_path) for detail-service API
# endpoint_type is "meeting" (league-level slug) or "event" (country/slug structure)
# Paths discovered from live browser network captures on www.eurobet.it
_LEAGUE_ALIASES: dict[str, tuple[str, str]] = {
    "Serie A":           ("meeting", "calcio/serie-a"),
    "Serie B":           ("meeting", "calcio/serie-b"),
    "Premier League":    ("event",   "calcio/inghilterra/premier-league"),
    "La Liga":           ("event",   "calcio/spagna/primera-division"),
    "Bundesliga":        ("event",   "calcio/germania/bundesliga"),
    "Ligue 1":           ("event",   "calcio/francia/ligue-1"),
    "Champions League":  ("event",   "calcio/competizioni-europee/champions-league"),
    "Conference League": ("event",   "calcio/competizioni-europee/conference-league"),
    "Tennis":            ("meeting", "tennis"),
    "NBA":               ("event",   "basket/usa/nba"),
    "Eurolega":          ("event",   "basket/competizioni-europee/eurolega"),
    "Serie A Basket":    ("event",   "basket/italia/serie-a"),
}

_API_LEAGUES: list[tuple[str, str, str, str]] = [
    # (league_name, sport_key, endpoint_type, full_path)
    ("Serie A",           "calcio", "meeting", "calcio/serie-a"),
    ("Serie B",           "calcio", "meeting", "calcio/serie-b"),
    ("Premier League",    "calcio", "event",   "calcio/inghilterra/premier-league"),
    ("La Liga",           "calcio", "event",   "calcio/spagna/primera-division"),
    ("Bundesliga",        "calcio", "event",   "calcio/germania/bundesliga"),
    ("Ligue 1",           "calcio", "event",   "calcio/francia/ligue-1"),
    ("Champions League",  "calcio", "event",   "calcio/competizioni-europee/champions-league"),
    ("Conference League", "calcio", "event",   "calcio/competizioni-europee/conference-league"),
    ("Tennis",            "tennis", "meeting", "tennis"),
    ("NBA",               "basket", "event",   "basket/usa/nba"),
    ("Eurolega",          "basket", "event",   "basket/competizioni-europee/eurolega"),
    ("Serie A Basket",    "basket", "event",   "basket/italia/serie-a"),
]

_API_HEADERS = {
    "User-Agent":      _UA,
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    "Origin":          BASE_URL,
    "Referer":         f"{BASE_URL}/it/scommesse/calcio/serie-a/",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Dest":  "empty",
    "Sec-Fetch-Mode":  "cors",
    "Sec-Fetch-Site":  "same-origin",
}


async def _probe_api_httpx(proxy_url: str | None) -> list[MatchOdds]:
    """Try detail-service API via httpx + mobile proxy, no browser needed."""
    all_results: list[MatchOdds] = []

    async with httpx.AsyncClient(
        headers=_API_HEADERS,
        timeout=15,
        follow_redirects=True,
        proxy=proxy_url,
    ) as client:
        for league_name, sport_key, endpoint_type, path in _API_LEAGUES:
            url = (f"{BASE_URL}/detail-service/sport-schedule/services/"
                   f"{endpoint_type}/{path}?prematch=1&live=0")
            try:
                resp = await client.get(url)
                ct = resp.headers.get("content-type", "")
                logger.info(
                    "[Eurobet-API] %s: status=%d ct=%s len=%d",
                    league_name, resp.status_code, ct[:60], len(resp.content),
                )
                if resp.status_code != 200:
                    continue
                if "json" not in ct and not resp.content.startswith(b"{") and not resp.content.startswith(b"["):
                    preview = resp.text[:300].replace("\n", " ")
                    logger.info("[Eurobet-API] %s: non-JSON body preview: %s", league_name, preview)
                    continue
                data = resp.json()
                rows = _parse_detail_response(data, league_name, sport_key)
                logger.info("[Eurobet-API] %s: parsed %d rows", league_name, len(rows))
                all_results.extend(rows)
            except Exception as exc:
                logger.error("[Eurobet-API] %s error: %s", league_name, exc)
            await asyncio.sleep(0.3)

    seen: dict[tuple[str, str], MatchOdds] = {}
    for r in all_results:
        seen[(r.event_name, r.market)] = r
    return list(seen.values())


# ─── Playwright scraper (extends BasePlaywrightScraper) ───────────────────────

class _EurobetPlaywrightScraper(BasePlaywrightScraper):
    """Playwright scraper for www.eurobet.it (Cloudflare, needs mobile proxy).

    Uses patchright (CF-bypass fork of Playwright) when available.
    Falls back to standard playwright + stealth if patchright not installed.
    Captures ALL JSON responses (no URL filter) like BasePlaywrightScraper.
    """

    bookmaker_name = BOOKMAKER
    base_url       = BASE_URL
    warmup_path    = "/it/scommesse/"
    leagues        = PLAYWRIGHT_LEAGUES

    async def _start(self) -> None:
        """Override to use patchright (Cloudflare bypass) instead of plain Playwright."""
        import urllib.parse as _up

        # Prefer patchright — it patches Chromium's JA3/JA4 TLS fingerprint and
        # navigator properties at the binary level, bypassing CF Turnstile.
        try:
            from patchright.async_api import async_playwright as _async_pw
            self._log.info("[%s] Using patchright for Cloudflare bypass", self.bookmaker_name)
            _using_patchright = True
        except ImportError:
            from playwright.async_api import async_playwright as _async_pw  # type: ignore[assignment]
            self._log.warning("[%s] patchright not found — falling back to playwright", self.bookmaker_name)
            _using_patchright = False

        self._playwright = await _async_pw().start()

        proxy_url = os.environ.get("PROXY_URL")
        proxy = None
        if proxy_url:
            p = _up.urlparse(proxy_url)
            proxy = {
                "server":   f"{p.scheme}://{p.hostname}:{p.port}",
                "username": p.username or "",
                "password": p.password or "",
            }
            self._log.info("[%s] Usando proxy: %s:%s", self.bookmaker_name, p.hostname, p.port)

        launch_args = ["--no-sandbox", "--disable-dev-shm-usage"]
        if not _using_patchright:
            launch_args.append("--disable-blink-features=AutomationControlled")

        self._browser = await self._playwright.chromium.launch(
            headless=False,
            args=launch_args,
            proxy=proxy,
        )
        self._context = await self._browser.new_context(
            user_agent=_UA,
            locale="it-IT",
            timezone_id="Europe/Rome",
            viewport={"width": 1280, "height": 900},
        )
        self._page = await self._context.new_page()

        if not _using_patchright:
            # Manual stealth only needed when patchright isn't patching natively
            await self._page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined, configurable: true});
                Object.defineProperty(navigator, 'plugins', {get: () => { const ps = [1,2,3,4,5]; ps.__proto__ = PluginArray.prototype; return ps; }, configurable: true});
                Object.defineProperty(navigator, 'languages', {get: () => ['it-IT','it','en-US','en'], configurable: true});
                if (!window.chrome) window.chrome = {runtime: {}};
            """)

        warmup_url = self.base_url + self.warmup_path
        self._log.info("[%s] Warmup: %s", self.bookmaker_name, warmup_url)
        try:
            await self._page.goto(warmup_url, wait_until="domcontentloaded", timeout=40_000)
            await self._page.wait_for_timeout(5000)
            title = await self._page.title()
            self._log.info("[%s] Warmup done — title: %s", self.bookmaker_name, title)
        except Exception as e:
            self._log.warning("[%s] Warmup failed: %s", self.bookmaker_name, e)

    async def _scrape_league(
        self,
        league_name: str,
        sport_key: str,
        page_path: str,
    ) -> list[MatchOdds]:
        """Override: navigate the page (CF bypass via patchright), then call
        detail-service API via page.evaluate() using the browser's session cookies."""
        import json as _j

        # Navigate to league page to ensure session cookies are valid
        url = self.base_url + page_path
        self._log.info("[%s] Loading %s", self.bookmaker_name, url)
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await self._page.wait_for_timeout(2000)
            title = await self._page.title()
            self._log.info("[%s] %s: title=%s", self.bookmaker_name, league_name, title)
        except Exception as exc:
            self._log.warning("[%s] %s: navigation error: %s", self.bookmaker_name, league_name, exc)

        # Call detail-service API from within the browser (same-origin, cookies included)
        alias_entry = _LEAGUE_ALIASES.get(league_name)
        if not alias_entry:
            self._log.warning("[%s] %s: no alias configured", self.bookmaker_name, league_name)
            return []

        endpoint_type, path = alias_entry
        api_path = f"/detail-service/sport-schedule/services/{endpoint_type}/{path}?prematch=1&live=0"
        self._log.info("[%s] %s: page.evaluate fetch %s", self.bookmaker_name, league_name, api_path)
        try:
            result = await self._page.evaluate(f"""
                async () => {{
                    try {{
                        const r = await fetch('{api_path}', {{
                            credentials: 'include',
                            headers: {{
                                'Accept': 'application/json, text/plain, */*',
                                'X-Requested-With': 'XMLHttpRequest',
                            }}
                        }});
                        const text = await r.text();
                        return {{status: r.status, body: text.substring(0, 8000)}};
                    }} catch(e) {{
                        return {{status: 0, error: String(e)}};
                    }}
                }}
            """)
        except Exception as exc:
            self._log.warning("[%s] %s: page.evaluate failed: %s", self.bookmaker_name, league_name, exc)
            return []

        status = result.get("status", 0)
        body_text = result.get("body", "")
        self._log.info("[%s] %s: fetch status=%d body_len=%d preview=%s",
                       self.bookmaker_name, league_name, status, len(body_text), body_text[:300])

        if status != 200 or not body_text:
            return []

        try:
            data = _j.loads(body_text)
        except Exception:
            self._log.warning("[%s] %s: response is not JSON", self.bookmaker_name, league_name)
            return []

        rows = _parse_detail_response(data, league_name, sport_key)
        self._log.info("[%s] %s: %d rows from detail-service", self.bookmaker_name, league_name, len(rows))
        return rows

    def parse_response(
        self,
        url: str,
        body: Any,
        league_name: str,
        sport_key: str,
    ) -> list[MatchOdds]:
        return _parse_detail_response(body, league_name, sport_key)


# ─── Main Scraper class ───────────────────────────────────────────────────────

class EurobetScraper:
    """Combined Eurobet scraper.

    - webeb httpx  → calcio 1X2 / DC / BTTS  (no proxy, no browser)
    - Playwright   → calcio O/U + tennis + basket  (proxy mobile, main site)
    """

    bookmaker_name = BOOKMAKER

    async def scrape_all(self) -> list[MatchOdds]:
        return await self._run(sport_filter=None)

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        return await self._run(sport_filter=sport)

    async def _run(self, sport_filter: str | None) -> list[MatchOdds]:
        # Run webeb (httpx) and Playwright in parallel
        webeb_task = asyncio.create_task(self._run_webeb(sport_filter))
        pw_task    = asyncio.create_task(self._run_playwright(sport_filter))
        webeb_rows, pw_rows = await asyncio.gather(webeb_task, pw_task,
                                                   return_exceptions=True)

        if isinstance(webeb_rows, Exception):
            logger.error("[Eurobet] webeb failed: %s", webeb_rows)
            webeb_rows = []
        if isinstance(pw_rows, Exception):
            logger.error("[Eurobet] Playwright failed: %s", pw_rows)
            pw_rows = []

        # Merge: webeb wins on duplicate (event_name, market) — it's more reliable
        seen: dict[tuple[str, str], MatchOdds] = {}
        for r in pw_rows:       # PW first (lower priority)
            seen[(r.event_name, r.market)] = r
        for r in webeb_rows:    # webeb overwrites (higher priority)
            seen[(r.event_name, r.market)] = r

        merged = list(seen.values())
        n_ev = len({r.event_name for r in merged})
        mc = Counter(r.market for r in merged)
        sc = Counter(r.sport  for r in merged)
        logger.info("[Eurobet] Total: %d events, %d rows | markets=%s sports=%s",
                    n_ev, len(merged), dict(mc), dict(sc))
        return merged

    # ── webeb ────────────────────────────────────────────────────────────────

    async def _run_webeb(self, sport_filter: str | None) -> list[MatchOdds]:
        proxy_url = os.environ.get("PROXY_URL")
        all_results: list[MatchOdds] = []

        async with httpx.AsyncClient(
            headers=_HEADERS, timeout=20, follow_redirects=True,
            proxy=proxy_url,
        ) as client:
            for sport_key, meetings in WEBEB_MEETINGS.items():
                if sport_filter and sport_key != sport_filter:
                    continue
                for league_name, choose_sport, meetings_param in meetings:
                    league_rows: list[MatchOdds] = []
                    for bet_param, bet_label in BET_TYPES:
                        url = _webeb_url(choose_sport, meetings_param, bet_param)
                        try:
                            resp = await client.get(url)
                            if resp.status_code != 200:
                                continue
                            rows = _parse_webeb_html(resp.text, league_name, sport_key, bet_label)
                            logger.info("[Eurobet] webeb %s/%s: %d rows", league_name, bet_label, len(rows))
                            league_rows.extend(rows)
                        except Exception as exc:
                            logger.error("[Eurobet] webeb %s/%s error: %s", league_name, bet_label, exc)
                    all_results.extend(league_rows)

        seen: dict[tuple[str, str], MatchOdds] = {}
        for r in all_results:
            seen[(r.event_name, r.market)] = r
        return list(seen.values())

    # ── API / Playwright (main site) ─────────────────────────────────────────

    async def _run_playwright(self, sport_filter: str | None) -> list[MatchOdds]:
        proxy_url = os.environ.get("PROXY_URL")
        if not proxy_url:
            logger.info("[Eurobet-PW] No PROXY_URL — skipping API+Playwright scrape")
            return []

        # ── Step 1: try httpx direct API call (faster, no browser) ──────────
        logger.info("[Eurobet-API] Trying direct httpx API probe via mobile proxy...")
        api_rows = await _probe_api_httpx(proxy_url)
        logger.info("[Eurobet-API] httpx probe: %d rows", len(api_rows))

        if api_rows:
            return api_rows

        # ── Step 2: fall back to Playwright if API returned nothing ──────────
        logger.info("[Eurobet-PW] httpx API returned 0 rows — falling back to Playwright")
        pw_scraper = _EurobetPlaywrightScraper()

        if sport_filter:
            return await pw_scraper.scrape_sport(sport_filter)
        else:
            return await pw_scraper.scrape_all()
