"""Snai Italy pregame odds scraper.

Strategy: Playwright browser navigates Snai pages and we intercept the
JSON responses that the Snai JavaScript automatically fetches from
betting-snai.flutterseatech.it.

We do NOT call flutterseatech.it directly via page.request.get() because
that endpoint requires session cookies that are only set by flutterseatech's
own JS (cross-domain from snai.it). Instead we listen for the browser's own
XHR/fetch calls and capture their responses.

Pages we navigate:
  /scommesse        → triggers alberaturaPrematch + some featured events
  /scommesse/calcio → triggers events for top calcio competitions
  /scommesse/tennis → triggers events for top tennis competitions
  /scommesse/basket → triggers events for top basket competitions

API base: https://betting-snai.flutterseatech.it/api/lettura-palinsesto-sport
"""

import json as _json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from playwright.async_api import async_playwright

from oddsmatcher_backend.scraper.centroquote import MatchOdds

try:
    from playwright_stealth import stealth_async as _stealth_async
    _STEALTH_AVAILABLE = True
except ImportError:
    _STEALTH_AVAILABLE = False

logger = logging.getLogger(__name__)

BASE_URL = "https://www.snai.it"
API_HOST = "betting-snai.flutterseatech.it"
BOOKMAKER = "Snai"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# codiceDisciplina (int) → our sport key
SPORT_CODE_MAP: dict[int, str] = {
    1: "calcio",
    2: "basket",
    3: "tennis",
}

# Each entry: (our_league_name, [keywords_ALL_must_appear_in_descrizione])
LEAGUE_PATTERNS: dict[str, list[tuple[str, list[str]]]] = {
    "calcio": [
        ("Serie A",           ["ITA", "Serie A"]),
        ("Serie B",           ["ITA", "Serie B"]),
        ("Premier League",    ["ENG", "Premier"]),
        ("La Liga",           ["ESP", "Primera"]),
        ("Bundesliga",        ["GER", "Bundesliga"]),
        ("Ligue 1",           ["FRA", "Ligue 1"]),
        ("Champions League",  ["Champions League"]),
        ("Europa League",     ["Europa League"]),
        ("Conference League", ["Conference"]),
    ],
    "tennis": [
        ("Roland Garros",    ["Roland Garros"]),
        ("Wimbledon",        ["Wimbledon"]),
        ("US Open",          ["US Open"]),
        ("Australian Open",  ["Australian Open"]),
        ("Amburgo",          ["Amburgo"]),
        ("Ginevra",          ["Ginevra"]),
        ("Rabat",            ["Rabat"]),
        ("Strasburgo",       ["Strasburgo"]),
    ],
    "basket": [
        ("NBA",            ["NBA"]),
        ("Serie A Basket", ["ITA", "Serie A"]),
        ("Eurolega",       ["Eurolega"]),
    ],
}


def _match_league(descrizione: str, sport_key: str) -> str | None:
    for league_name, keywords in LEAGUE_PATTERNS.get(sport_key, []):
        if all(kw in descrizione for kw in keywords):
            return league_name
    return None


def _parse_date(s: str) -> str | None:
    if not s:
        return None
    FMTS = [
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y%m%d %H:%M:%S",
    ]
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


def _parse_snai_events(data: Any, league_name: str, sport_key: str) -> list[MatchOdds]:
    """Parse Snai API event response."""
    results: list[MatchOdds] = []
    if not data:
        return results

    events: list = []
    if isinstance(data, list):
        events = data
    elif isinstance(data, dict):
        for key in ("avvenimenti", "eventi", "events", "data", "result",
                    "matches", "fixtures", "palinsesto", "avv"):
            val = data.get(key)
            if isinstance(val, list) and val:
                events = val
                break
            if isinstance(val, dict):
                for k2 in ("avvenimenti", "eventi", "events", "avv"):
                    v2 = val.get(k2)
                    if isinstance(v2, list) and v2:
                        events = v2
                        break
                if events:
                    break

    for ev in events:
        if not isinstance(ev, dict):
            continue

        name_raw = (
            ev.get("descrizione") or ev.get("description") or
            ev.get("eventDescription") or ev.get("name") or
            ev.get("da") or ev.get("en") or ""
        )
        name = re.sub(r"\s+[-–v]\s+", " - ", str(name_raw)).strip()
        if not name:
            continue

        time_raw = (
            ev.get("dataOra") or ev.get("data") or ev.get("startTime") or
            ev.get("startDate") or ev.get("eventDate") or ev.get("ts") or ""
        )
        event_time = _parse_date(str(time_raw)) if time_raw else None
        match_url = f"{BASE_URL}/scommesse/"

        parts = name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else name
        away = parts[1].strip() if len(parts) == 2 else ""

        mkts_raw = (
            ev.get("scommesse") or ev.get("mercati") or ev.get("markets") or
            ev.get("quote") or ev.get("odds") or []
        )
        if isinstance(mkts_raw, dict):
            mkts_raw = list(mkts_raw.values())

        for mkt in mkts_raw:
            if not isinstance(mkt, dict):
                continue

            mname = str(
                mkt.get("descrizione") or mkt.get("description") or
                mkt.get("name") or mkt.get("tipo") or mkt.get("marketName") or ""
            ).strip()

            if any(kw in mname for kw in ("1X2", "Esito Finale", "Finale", "Risultato Finale",
                                           "1 X 2", "Match Result", "Testa a Testa")):
                sels_raw = (
                    mkt.get("esiti") or mkt.get("selections") or
                    mkt.get("outcomes") or mkt.get("quote") or []
                )
                if isinstance(sels_raw, dict):
                    sels_raw = list(sels_raw.values())
                odds_dict: dict[str, float] = {}
                OUTCOME_MAP = {
                    "1": "1", "Casa": "1", "Home": "1",
                    "X": "X", "Pareggio": "X", "Draw": "X",
                    "2": "2", "Ospite": "2", "Away": "2",
                }
                for sel in sels_raw:
                    if not isinstance(sel, dict):
                        continue
                    lbl = str(
                        sel.get("descrizione") or sel.get("esito") or
                        sel.get("name") or sel.get("outcome") or sel.get("label") or ""
                    ).strip()
                    canonical = OUTCOME_MAP.get(lbl, lbl)
                    q_raw = sel.get("quota") or sel.get("odds") or sel.get("price") or sel.get("q")
                    try:
                        q = float(q_raw) if q_raw is not None else None
                        if q and q > 1.0:
                            odds_dict[canonical] = q
                    except (TypeError, ValueError):
                        pass
                if odds_dict:
                    results.append(MatchOdds(
                        sport=sport_key, league=league_name,
                        home_team=home, away_team=away,
                        event_name=name, event_time=event_time,
                        match_url=match_url, market="1X2",
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                    ))

            elif any(kw in mname for kw in ("Doppia Chance", "Double Chance")):
                sels_raw = (
                    mkt.get("esiti") or mkt.get("selections") or
                    mkt.get("outcomes") or []
                )
                if isinstance(sels_raw, dict):
                    sels_raw = list(sels_raw.values())
                DC_MAP = {"1X": "1X", "X2": "X2", "12": "12"}
                odds_dc: dict[str, float] = {}
                for sel in sels_raw:
                    lbl = str(sel.get("descrizione") or sel.get("esito") or sel.get("name") or "").strip()
                    canonical = DC_MAP.get(lbl, lbl)
                    q_raw = sel.get("quota") or sel.get("odds") or sel.get("price")
                    try:
                        q = float(q_raw) if q_raw is not None else None
                        if q and q > 1.0:
                            odds_dc[canonical] = q
                    except (TypeError, ValueError):
                        pass
                if odds_dc:
                    results.append(MatchOdds(
                        sport=sport_key, league=league_name,
                        home_team=home, away_team=away,
                        event_name=name, event_time=event_time,
                        match_url=match_url, market="DC",
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dc}],
                    ))

            elif any(kw in mname for kw in ("Over/Under", "U/O", "Totale Gol", "Over Under")):
                sp_m = re.search(r"(\d+[.,]\d+)", mname)
                if not sp_m:
                    continue
                sp = sp_m.group(1).replace(",", ".")
                if sp not in {"1.5", "2.5", "3.5"}:
                    continue
                sels_raw = mkt.get("esiti") or mkt.get("selections") or mkt.get("outcomes") or []
                if isinstance(sels_raw, dict):
                    sels_raw = list(sels_raw.values())
                SIDE_MAP = {"Over": "Over", "Oltre": "Over", "Under": "Under", "Meno": "Under"}
                odds_uo: dict[str, float] = {}
                for sel in sels_raw:
                    lbl = str(sel.get("descrizione") or sel.get("esito") or sel.get("name") or "").strip()
                    side = SIDE_MAP.get(lbl)
                    q_raw = sel.get("quota") or sel.get("odds") or sel.get("price")
                    try:
                        q = float(q_raw) if q_raw is not None else None
                        if side and q and q > 1.0:
                            odds_uo[f"{side} {sp}"] = q
                    except (TypeError, ValueError):
                        pass
                if odds_uo:
                    results.append(MatchOdds(
                        sport=sport_key, league=league_name,
                        home_team=home, away_team=away,
                        event_name=name, event_time=event_time,
                        match_url=match_url, market=f"Over/Under {sp}",
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_uo}],
                    ))

    return results


# Events API endpoint — {manif_id} is replaced per-competition
EVENTS_API = (
    "https://" + "betting-snai.flutterseatech.it"
    + "/api/lettura-palinsesto-sport/palinsesto/prematch/avvenimentiList"
    + "/{manif_id}?offerId=0&metaTplEnabled=true&deep=true"
)


_SNAI_HEADERS = {
    "User-Agent": _UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "it-IT,it;q=0.9",
    "Referer": "https://www.snai.it/",
    "Origin": "https://www.snai.it",
}

ALBERATURA_URL = (
    "https://" + API_HOST
    + "/api/lettura-palinsesto-sport/palinsesto/prematch/alberaturaPrematch"
)


class SnaiScraper:
    """Snai scraper — Playwright browser intercepts flutterseatech API calls.

    Navigate to snai.it sport pages and capture the API responses from
    betting-snai.flutterseatech.it that the page JS fires automatically.
    Also log all API-looking URLs for diagnostics.
    """

    bookmaker_name = BOOKMAKER

    # Snai sport pages that trigger the flutterseatech API calls
    SPORT_PAGES: list[tuple[str, str]] = [
        ("calcio",  "https://www.snai.it/scommesse/calcio"),
        ("tennis",  "https://www.snai.it/scommesse/tennis"),
        ("basket",  "https://www.snai.it/scommesse/basket"),
    ]

    async def scrape_all(self) -> list[MatchOdds]:
        return await self._run(sport_filter=None)

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        return await self._run(sport_filter=sport)

    async def _run(self, sport_filter: str | None) -> list[MatchOdds]:
        import urllib.parse
        from playwright.async_api import async_playwright, Response as _Response

        proxy_url = os.environ.get("PROXY_URL")
        proxy = None
        if proxy_url:
            p = urllib.parse.urlparse(proxy_url)
            proxy = {
                "server": f"{p.scheme}://{p.hostname}:{p.port}",
                "username": p.username or "",
                "password": p.password or "",
            }
            logger.info("[Snai] Using proxy: %s:%s", p.hostname, p.port)

        all_results: list[MatchOdds] = []

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
                proxy=proxy,
            )
            try:
                context = await browser.new_context(
                    user_agent=_UA,
                    locale="it-IT",
                    timezone_id="Europe/Rome",
                    viewport={"width": 1280, "height": 800},
                )
                try:
                    from playwright_stealth import stealth_async as _stealth_async
                    page = await context.new_page()
                    await _stealth_async(page)
                    logger.info("[Snai] playwright-stealth applied")
                except ImportError:
                    page = await context.new_page()
                    logger.warning("[Snai] playwright-stealth not installed")

                for sport_key, sport_url in self.SPORT_PAGES:
                    if sport_filter and sport_key != sport_filter:
                        continue

                    captured: list[MatchOdds] = []

                    async def _on_response(
                        resp: _Response,
                        _sk: str = sport_key,
                        _cap: list = captured,
                    ) -> None:
                        url = resp.url
                        # Log all JSON responses from flutterseatech for diagnostics
                        if API_HOST in url:
                            ct = resp.headers.get("content-type", "")
                            logger.info("[Snai] API resp (sport=%s) status=%s url=%s",
                                        _sk, resp.status, url[:150])
                            if resp.status != 200:
                                return
                            try:
                                data = await resp.json()
                                # Determine league from URL (manif_id parameter)
                                league_name: str | None = None
                                # Try to find manif_id in URL
                                import re as _re
                                mid_m = _re.search(r"/(\d+)\b", url)
                                if mid_m:
                                    mid = int(mid_m.group(1))
                                    # Find matching competition from our alberatura cache
                                    league_name = self._manif_to_league.get(mid)
                                if not league_name:
                                    # Try all leagues for this sport
                                    rows = []
                                    for lg_name, sp_key, _, _ in getattr(self, "_competitions", []):
                                        if sp_key == _sk:
                                            r = _parse_snai_events(data, lg_name, sp_key)
                                            if r:
                                                rows = r
                                                league_name = lg_name
                                                break
                                else:
                                    rows = _parse_snai_events(data, league_name, _sk)

                                if rows:
                                    logger.info("[Snai] Parsed %d rows from %s (league=%s)",
                                                len(rows), url[:80], league_name)
                                    _cap.extend(rows)
                                else:
                                    preview = _json.dumps(data, ensure_ascii=False)[:300] if data else "empty"
                                    logger.info("[Snai] 0 rows from %s — preview: %s", url[:80], preview)
                            except Exception as exc:
                                logger.info("[Snai] Parse error for %s: %s", url[:80], exc)

                    page.on("response", _on_response)
                    logger.info("[Snai] Navigating to %s", sport_url)
                    try:
                        await page.goto(sport_url, wait_until="networkidle", timeout=45_000)
                        logger.info("[Snai] %s: networkidle", sport_key)
                    except Exception as e:
                        logger.info("[Snai] %s: %s — continuing", sport_key, type(e).__name__)
                    await page.wait_for_timeout(3000)
                    page.remove_listener("response", _on_response)

                    # Deduplicate by (event_name, market)
                    seen: dict[tuple[str, str], MatchOdds] = {}
                    for r in captured:
                        seen[(r.event_name, r.market)] = r
                    deduped = list(seen.values())
                    n_events = len({r.event_name for r in deduped})
                    logger.info("[Snai] %s: %d events, %d market rows (after dedup)",
                                sport_key, n_events, len(deduped))
                    all_results.extend(deduped)

                    import asyncio as _asyncio
                    await _asyncio.sleep(2.0)

            finally:
                await browser.close()

        logger.info("[Snai] Total rows: %d", len(all_results))
        return all_results

    # Cache populated by _find_competitions for URL→league resolution
    _manif_to_league: dict[int, str] = {}
    _competitions: list = []
