"""Eurobet Italy pregame odds scraper — __NEXT_DATA__ extraction.

Eurobet uses Next.js ISR (Incremental Static Regeneration). All event odds
are rendered server-side and embedded in <script id="__NEXT_DATA__"> on the
page. The browser makes no API calls for sport data — it's all in the HTML.

We navigate to each competition page, extract __NEXT_DATA__, and parse events
from props.pageProps.
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

BOOKMAKER = "Eurobet"
BASE_URL = "https://www.eurobet.it"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# discipline → list of (league_name, meeting_alias)
MEETINGS: dict[str, list[tuple[str, str]]] = {
    "calcio": [
        ("Champions League",  "champions-league"),
        ("Europa League",     "europa-league"),
        ("Conference League", "conference-league"),
        ("Premier League",    "premier-league"),
        ("La Liga",           "prima-divisione"),
        ("Bundesliga",        "bundesliga"),
        ("Ligue 1",           "ligue-1"),
        ("Serie A",           "serie-a"),
        ("Serie B",           "serie-b"),
    ],
    "tennis": [
        ("Roland Garros",   "roland-garros"),
        ("Wimbledon",       "wimbledon"),
        ("US Open",         "us-open"),
        ("Australian Open", "australian-open"),
    ],
    "basket": [
        ("NBA",            "nba"),
        ("Eurolega",       "euroleague"),
        ("Serie A Basket", "serie-a"),
    ],
}


def _parse_date(s: str | None) -> str | None:
    if not s:
        return None
    FMTS = [
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
        "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S",
    ]
    for fmt in FMTS:
        try:
            dt = datetime.strptime(str(s).strip()[:19], fmt)
            off = 2 if 3 <= dt.month <= 10 else 1
            return dt.replace(tzinfo=timezone(timedelta(hours=off))).astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        return str(s)


def _extract_events(data: Any) -> list[dict]:
    """Recursively search for a list of event-like dicts."""
    if isinstance(data, list) and data:
        # Check if elements look like events
        if isinstance(data[0], dict) and any(
            k in data[0] for k in ("description", "descrizione", "eventName",
                                    "startDate", "dataOra", "betGroupList",
                                    "betGroups", "markets", "scommesse")
        ):
            return data
        # Recurse into list elements
        for item in data:
            result = _extract_events(item)
            if result:
                return result

    if isinstance(data, dict):
        # Try common event list keys first
        for key in ("eventList", "events", "avvenimenti", "items", "data",
                     "meetings", "competitions", "fixtures", "matches"):
            val = data.get(key)
            if val is not None:
                result = _extract_events(val)
                if result:
                    return result
        # Recurse into all values
        for val in data.values():
            if isinstance(val, (dict, list)):
                result = _extract_events(val)
                if result:
                    return result

    return []


def _parse_events(events: list, league_name: str, discipline: str) -> list[MatchOdds]:
    """Parse a list of event dicts into MatchOdds rows."""
    results: list[MatchOdds] = []

    OUTCOME_MAP = {
        "1": "1", "Casa": "1", "Home": "1",
        "X": "X", "Pareggio": "X", "Draw": "X",
        "2": "2", "Ospite": "2", "Away": "2",
        "1X": "1X", "X2": "X2", "12": "12",
        "Over": "Over", "Under": "Under",
        "Sì": "Goal", "Si": "Goal", "Yes": "Goal", "No": "No Goal",
    }

    for ev in events:
        if not isinstance(ev, dict):
            continue

        name_raw = (ev.get("description") or ev.get("descrizione") or
                    ev.get("name") or ev.get("eventName") or
                    ev.get("eventDescription") or "")
        name = re.sub(r"\s+[-–]\s+", " - ", str(name_raw)).strip()
        if not name:
            continue

        parts = name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else name
        away = parts[1].strip() if len(parts) == 2 else ""

        time_raw = (ev.get("startDate") or ev.get("dataOra") or ev.get("startTime") or
                    ev.get("data") or ev.get("eventDate") or "")
        event_time = _parse_date(str(time_raw)) if time_raw else None

        bet_groups = (ev.get("betGroupList") or ev.get("betGroups") or
                      ev.get("markets") or ev.get("mercati") or ev.get("scommesse") or [])
        if isinstance(bet_groups, dict):
            bet_groups = list(bet_groups.values())

        for bg in bet_groups:
            if not isinstance(bg, dict):
                continue
            bg_name = str(bg.get("description") or bg.get("descrizione") or
                          bg.get("name") or bg.get("marketType") or bg.get("tipo") or "").strip()

            bets = (bg.get("betList") or bg.get("bets") or bg.get("outcomes") or
                    bg.get("esiti") or bg.get("selections") or bg.get("quote") or [])
            if isinstance(bets, dict):
                bets = list(bets.values())

            # ── 1X2 ──
            if any(kw in bg_name for kw in ("Esito Finale", "1X2", "Match Result",
                                             "Testa a Testa", "Head to Head", "Risultato",
                                             "1 X 2")):
                odds_dict: dict[str, float] = {}
                for bet in bets:
                    if not isinstance(bet, dict):
                        continue
                    lbl = str(bet.get("description") or bet.get("descrizione") or
                              bet.get("name") or bet.get("outcome") or "").strip()
                    canonical = OUTCOME_MAP.get(lbl, lbl)
                    q_raw = bet.get("quota") or bet.get("odds") or bet.get("price") or bet.get("value")
                    try:
                        q = float(str(q_raw).replace(",", ".")) if q_raw is not None else None
                        if q and q > 1.0:
                            odds_dict[canonical] = round(q, 3)
                    except (TypeError, ValueError):
                        pass
                if odds_dict:
                    results.append(MatchOdds(
                        sport=discipline, league=league_name,
                        home_team=home, away_team=away,
                        event_name=name, event_time=event_time,
                        match_url=f"{BASE_URL}/scommesse-sportive/", market="1X2",
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                    ))

            # ── Double Chance ──
            elif any(kw in bg_name for kw in ("Doppia Chance", "Double Chance")):
                odds_dict = {}
                for bet in bets:
                    if not isinstance(bet, dict):
                        continue
                    lbl = str(bet.get("description") or bet.get("descrizione") or
                              bet.get("name") or "").strip()
                    canonical = OUTCOME_MAP.get(lbl, lbl)
                    q_raw = bet.get("quota") or bet.get("odds") or bet.get("price") or bet.get("value")
                    try:
                        q = float(str(q_raw).replace(",", ".")) if q_raw is not None else None
                        if q and q > 1.0:
                            odds_dict[canonical] = round(q, 3)
                    except (TypeError, ValueError):
                        pass
                if odds_dict:
                    results.append(MatchOdds(
                        sport=discipline, league=league_name,
                        home_team=home, away_team=away,
                        event_name=name, event_time=event_time,
                        match_url=f"{BASE_URL}/scommesse-sportive/", market="DC",
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                    ))

            # ── Over/Under ──
            elif any(kw in bg_name for kw in ("Over/Under", "O/U", "Totale Gol", "Over Under")):
                sp_m = re.search(r"(\d+[.,]\d+)", bg_name)
                if not sp_m:
                    continue
                sp = sp_m.group(1).replace(",", ".")
                if sp not in {"1.5", "2.5", "3.5"}:
                    continue
                odds_dict = {}
                for bet in bets:
                    if not isinstance(bet, dict):
                        continue
                    lbl = str(bet.get("description") or bet.get("descrizione") or
                              bet.get("name") or "").strip()
                    side = "Over" if "over" in lbl.lower() else ("Under" if "under" in lbl.lower() else None)
                    if not side:
                        continue
                    q_raw = bet.get("quota") or bet.get("odds") or bet.get("price") or bet.get("value")
                    try:
                        q = float(str(q_raw).replace(",", ".")) if q_raw is not None else None
                        if q and q > 1.0:
                            odds_dict[f"{side} {sp}"] = round(q, 3)
                    except (TypeError, ValueError):
                        pass
                if odds_dict:
                    results.append(MatchOdds(
                        sport=discipline, league=league_name,
                        home_team=home, away_team=away,
                        event_name=name, event_time=event_time,
                        match_url=f"{BASE_URL}/scommesse-sportive/", market=f"Over/Under {sp}",
                        bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                    ))

    return results


class EurobetScraper:
    """Eurobet scraper — parses __NEXT_DATA__ from SSR pages.

    Eurobet uses Next.js ISR: event data is embedded in <script id="__NEXT_DATA__">
    on every competition page. We extract and parse it directly.
    """

    bookmaker_name = BOOKMAKER

    async def scrape_all(self) -> list[MatchOdds]:
        return await self._run(sport_filter=None)

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        return await self._run(sport_filter=sport)

    async def _run(self, sport_filter: str | None) -> list[MatchOdds]:
        proxy_url = os.environ.get("PROXY_URL")
        proxy_dict = None
        if proxy_url:
            import urllib.parse as _up
            p = _up.urlparse(proxy_url)
            proxy_dict = {
                "server": f"{p.scheme}://{p.hostname}:{p.port}",
                "username": p.username or "",
                "password": p.password or "",
            }
            logger.info("[Eurobet] Using proxy: %s:%s", p.hostname, p.port)

        # Build list of (league_name, discipline, alias, page_url)
        pages: list[tuple[str, str, str, str]] = []
        for discipline, entries in MEETINGS.items():
            if sport_filter and discipline != sport_filter:
                continue
            for league_name, alias in entries:
                page_url = f"{BASE_URL}/scommesse-sportive/{discipline}/{alias}"
                pages.append((league_name, discipline, alias, page_url))

        all_results: list[MatchOdds] = []

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
                proxy=proxy_dict,
            )
            try:
                context = await browser.new_context(
                    user_agent=_UA,
                    locale="it-IT",
                    timezone_id="Europe/Rome",
                    viewport={"width": 1280, "height": 800},
                )
                page = await context.new_page()
                if _STEALTH_AVAILABLE:
                    await _stealth_async(page)
                    logger.info("[Eurobet] playwright-stealth applied")
                else:
                    logger.warning("[Eurobet] playwright-stealth not available")

                # Homepage warm-up to get session cookies
                logger.info("[Eurobet] Warming up on homepage...")
                try:
                    await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=25_000)
                    await page.wait_for_timeout(3000)
                    logger.info("[Eurobet] Homepage loaded")
                except Exception as e:
                    logger.warning("[Eurobet] Homepage warm-up failed: %s", str(e)[:100])

                for league_name, discipline, alias, page_url in pages:
                    try:
                        logger.info("[Eurobet] Navigating to %s", page_url)
                        try:
                            await page.goto(page_url, wait_until="networkidle", timeout=30_000)
                        except Exception:
                            pass  # timeout is ok — page still has content
                        await page.wait_for_timeout(2000)

                        # Extract __NEXT_DATA__ from the page
                        next_data_str = await page.evaluate("""
                            () => {
                                const el = document.getElementById('__NEXT_DATA__');
                                return el ? el.textContent : null;
                            }
                        """)

                        if not next_data_str:
                            logger.warning("[Eurobet] %s: no __NEXT_DATA__ found", league_name)
                            # Log HTML snippet to understand page structure
                            try:
                                html = await page.evaluate("document.documentElement.innerHTML")
                                logger.info("[Eurobet] %s: HTML snippet=%.2000s", league_name, html)
                            except Exception:
                                pass
                            continue

                        try:
                            next_data = _json.loads(next_data_str)
                        except Exception as e:
                            logger.warning("[Eurobet] %s: __NEXT_DATA__ JSON parse error: %s", league_name, e)
                            continue

                        # Log structure for discovery (first league)
                        if not all_results:
                            logger.info("[Eurobet] %s: __NEXT_DATA__ top keys=%s",
                                        league_name, list(next_data.keys()))
                            page_props = (next_data.get("props") or {}).get("pageProps") or {}
                            logger.info("[Eurobet] %s: pageProps keys=%s | preview=%.2000s",
                                        league_name, list(page_props.keys())[:20],
                                        _json.dumps(page_props, ensure_ascii=False)[:2000])

                        # Parse events from pageProps
                        page_props = (next_data.get("props") or {}).get("pageProps") or {}
                        events = _extract_events(page_props)

                        if not events:
                            logger.warning("[Eurobet] %s: no events found in __NEXT_DATA__ pageProps "
                                           "(pageProps keys=%s)", league_name,
                                           list(page_props.keys())[:15])
                            continue

                        logger.info("[Eurobet] %s: found %d events in __NEXT_DATA__", league_name, len(events))
                        if events:
                            logger.info("[Eurobet] %s: first event keys=%s | preview=%.400s",
                                        league_name, list(events[0].keys())[:15] if isinstance(events[0], dict) else "?",
                                        _json.dumps(events[0], ensure_ascii=False)[:400])

                        rows = _parse_events(events, league_name, discipline)
                        logger.info("[Eurobet] %s: %d rows parsed", league_name, len(rows))
                        all_results.extend(rows)

                    except Exception as exc:
                        logger.error("[Eurobet] %s error: %s", league_name, exc, exc_info=True)

            finally:
                await browser.close()

        # Deduplicate by (event_name, market)
        seen: dict[tuple[str, str], MatchOdds] = {}
        for r in all_results:
            seen[(r.event_name, r.market)] = r
        deduped = list(seen.values())
        n_events = len({r.event_name for r in deduped})
        logger.info("[Eurobet] Total: %d events, %d rows", n_events, len(deduped))
        return deduped
