"""Eurobet Italy pregame odds scraper — Playwright network interception.

Eurobet's internal REST API (detail-service) requires session cookies that
are only set when a real browser loads the page. We use Playwright to navigate
to each competition page and intercept the detail-service JSON responses.

detail-service endpoint (intercepted):
  /detail-service/sport-schedule/services/meeting/{discipline}/{alias}?prematch=1&live=0

Pages we navigate:
  https://www.eurobet.it/scommesse-sportive/{discipline}/{alias}
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
DETAIL_HOST_PATH = "/detail-service/sport-schedule/services/meeting/"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# discipline → list of (league_name, meeting_alias)
# meeting_alias used in both page URL and detail-service URL
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

# alias → (league_name, discipline) for fast lookup during interception
_ALIAS_TO_LEAGUE: dict[str, tuple[str, str]] = {}
for _disc, _entries in MEETINGS.items():
    for _lg, _alias in _entries:
        _ALIAS_TO_LEAGUE[_alias] = (_lg, _disc)


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


def _parse_detail_response(data: Any, league_name: str, discipline: str) -> list[MatchOdds]:
    """Parse a detail-service response JSON into MatchOdds."""
    results: list[MatchOdds] = []
    if not data:
        return results

    # Top-level: {"code": 1, "result": {...}}
    if isinstance(data, dict) and "result" in data:
        data = data["result"]

    events: list = []
    if isinstance(data, list):
        events = data
    elif isinstance(data, dict):
        for key in ("eventList", "events", "avvenimenti", "data"):
            v = data.get(key)
            if isinstance(v, list):
                events = v
                break

    if not events:
        if isinstance(data, dict):
            logger.info("[Eurobet] No events found; result keys: %s", list(data.keys())[:12])
        return results

    logger.info("[Eurobet] %s: %d events in response", league_name, len(events))
    if events:
        first = events[0] if isinstance(events[0], dict) else {}
        logger.info("[Eurobet] First event keys: %s | preview: %.300s",
                    list(first.keys())[:12], _json.dumps(first, ensure_ascii=False)[:300])

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
                    ev.get("name") or ev.get("eventName") or "")
        name = re.sub(r"\s+[-–]\s+", " - ", str(name_raw)).strip()
        if not name:
            continue

        parts = name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else name
        away = parts[1].strip() if len(parts) == 2 else ""

        time_raw = (ev.get("startDate") or ev.get("dataOra") or ev.get("startTime") or
                    ev.get("data") or "")
        event_time = _parse_date(str(time_raw)) if time_raw else None

        bet_groups = (ev.get("betGroupList") or ev.get("betGroups") or
                      ev.get("markets") or ev.get("mercati") or ev.get("scommesse") or [])
        if isinstance(bet_groups, dict):
            bet_groups = list(bet_groups.values())

        for bg in bet_groups:
            if not isinstance(bg, dict):
                continue
            bg_name = str(bg.get("description") or bg.get("descrizione") or
                          bg.get("name") or bg.get("marketType") or "").strip()

            bets = (bg.get("betList") or bg.get("bets") or bg.get("outcomes") or
                    bg.get("esiti") or bg.get("quote") or [])
            if isinstance(bets, dict):
                bets = list(bets.values())

            # ── 1X2 ──
            if any(kw in bg_name for kw in ("Esito Finale", "1X2", "Match Result",
                                             "Testa a Testa", "Head to Head", "Risultato")):
                odds_dict: dict[str, float] = {}
                for bet in bets:
                    if not isinstance(bet, dict):
                        continue
                    lbl = str(bet.get("description") or bet.get("descrizione") or
                              bet.get("name") or "").strip()
                    canonical = OUTCOME_MAP.get(lbl, lbl)
                    q_raw = bet.get("quota") or bet.get("odds") or bet.get("price")
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
                    q_raw = bet.get("quota") or bet.get("odds") or bet.get("price")
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
                    q_raw = bet.get("quota") or bet.get("odds") or bet.get("price")
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
    """Eurobet scraper — Playwright + network interception.

    We navigate to each competition page; the page JS calls detail-service
    with proper session cookies that are set on first page load. We capture
    and parse those API responses.
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

                # Warmup: load homepage to get session cookies
                logger.info("[Eurobet] Warmup: loading homepage…")
                try:
                    await page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=30_000)
                    await page.wait_for_timeout(3000)
                    logger.info("[Eurobet] Homepage loaded OK")
                except Exception as e:
                    logger.warning("[Eurobet] Homepage warmup failed: %s", str(e)[:120])

                # For each competition: use page.evaluate(fetch()) so the browser's
                # session cookies (set during homepage warmup) are automatically included.
                # The Eurobet Next.js app uses ISR — no client-side detail-service calls are
                # made by the page JS. We must initiate them ourselves via the browser.
                for league_name, discipline, alias, page_url in pages:
                    api_path = (
                        f"/detail-service/sport-schedule/services/meeting"
                        f"/{discipline}/{alias}?prematch=1&live=0"
                    )
                    logger.info("[Eurobet] Fetching %s via page.evaluate: %s", league_name, api_path)
                    try:
                        result = await page.evaluate(f"""
                            async () => {{
                                try {{
                                    const resp = await fetch('{api_path}', {{
                                        credentials: 'include',
                                        headers: {{
                                            'Accept': 'application/json',
                                            'Accept-Language': 'it-IT,it;q=0.9'
                                        }}
                                    }});
                                    if (!resp.ok) return {{error: resp.status}};
                                    return await resp.json();
                                }} catch(e) {{
                                    return {{error: String(e)}};
                                }}
                            }}
                        """)
                    except Exception as exc:
                        logger.info("[Eurobet] %s evaluate error: %s", league_name, exc)
                        continue

                    if not result or not isinstance(result, dict):
                        logger.info("[Eurobet] %s: null/non-dict result", league_name)
                        continue

                    if "error" in result:
                        logger.info("[Eurobet] %s: fetch error=%s", league_name, result["error"])
                        continue

                    preview = _json.dumps(result, ensure_ascii=False)[:300]
                    logger.info("[Eurobet] %s: response preview: %s", league_name, preview)

                    rows = _parse_detail_response(result, league_name, discipline)
                    logger.info("[Eurobet] %s: %d rows", league_name, len(rows))
                    all_results.extend(rows)

                    await page.wait_for_timeout(500)

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
