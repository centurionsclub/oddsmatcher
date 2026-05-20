"""Eurobet Italy pregame odds scraper — httpx to web.eurobet.it.

www.eurobet.it is fully protected by Cloudflare Turnstile (blocks Playwright).
web.eurobet.it is the backend subdomain that is NOT behind Cloudflare.

Approach:
  1. Probe the detail-service API on web.eurobet.it with various URL patterns.
  2. Also probe /webeb/rest/... paths (the API observed in network traffic).
  3. Once a working pattern is found, fetch all leagues.

Known working:
  - web.eurobet.it/webeb/rest → {"result": "ok", "version": "1"}
  - The sport data API path is unknown — we probe multiple candidates.
"""

import json as _json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)

BOOKMAKER = "Eurobet"
BASE_URL = "https://www.eurobet.it"
WEB_BASE = "https://web.eurobet.it"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "it-IT,it;q=0.9",
    "Referer": "https://www.eurobet.it/",
    "Origin": "https://www.eurobet.it",
}

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
        if isinstance(data[0], dict) and any(
            k in data[0] for k in ("description", "descrizione", "eventName",
                                    "startDate", "dataOra", "betGroupList",
                                    "betGroups", "markets", "scommesse")
        ):
            return data
        for item in data:
            result = _extract_events(item)
            if result:
                return result

    if isinstance(data, dict):
        for key in ("eventList", "events", "avvenimenti", "items", "data",
                     "meetings", "competitions", "fixtures", "matches", "result"):
            val = data.get(key)
            if val is not None:
                result = _extract_events(val)
                if result:
                    return result
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
    """Eurobet scraper — httpx to web.eurobet.it backend API.

    www.eurobet.it is Cloudflare-protected (Turnstile challenge blocks Playwright).
    web.eurobet.it is the backend subdomain without Cloudflare protection.
    We probe multiple API paths to discover the working endpoint.
    """

    bookmaker_name = BOOKMAKER

    async def scrape_all(self) -> list[MatchOdds]:
        return await self._run(sport_filter=None)

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        return await self._run(sport_filter=sport)

    async def _run(self, sport_filter: str | None) -> list[MatchOdds]:
        proxy_url = os.environ.get("PROXY_URL")
        if proxy_url:
            import urllib.parse as _up
            p = _up.urlparse(proxy_url)
            logger.info("[Eurobet] Using proxy: %s:%s", p.hostname, p.port)

        # Build (league_name, discipline, alias) list
        meetings: list[tuple[str, str, str]] = []
        for discipline, entries in MEETINGS.items():
            if sport_filter and discipline != sport_filter:
                continue
            for league_name, alias in entries:
                meetings.append((league_name, discipline, alias))

        # ── Phase 1: Discover working API on web.eurobet.it ──────────────
        first_disc, first_alias = meetings[0][1], meetings[0][2]
        working_url_template: str | None = None  # with {disc}/{alias} placeholders

        # Probe candidates on web.eurobet.it (not Cloudflare-protected)
        # NOTE: integration-bridge Swagger confirmed it only has Opta/Perform/IMG (stats), NOT odds.
        # detail-service on www.eurobet.it is Cloudflare-protected (403).
        # Priority: try web.eurobet.it/detail-service (same service, CF-free backend).
        get_probe_candidates: list[tuple[str, str]] = [
            # ── web.eurobet.it detail-service (CF-free backend — same service as www.eurobet.it) ──
            (f"{WEB_BASE}/detail-service/sport-schedule/services/meeting/{first_disc}/{first_alias}?prematch=1&live=0",
             f"{WEB_BASE}/detail-service/sport-schedule/services/meeting/{{disc}}/{{alias}}?prematch=1&live=0"),
            (f"{WEB_BASE}/detail-service/sport-schedule/services/meeting/{first_disc}/{first_alias}",
             f"{WEB_BASE}/detail-service/sport-schedule/services/meeting/{{disc}}/{{alias}}"),
            (f"{WEB_BASE}/detail-service/sport-schedule/services/sport/{first_disc}?prematch=1&live=0",
             f"{WEB_BASE}/detail-service/sport-schedule/services/sport/{{disc}}?prematch=1&live=0"),
            # ── Alternative service names on web.eurobet.it ──
            (f"{WEB_BASE}/sport-schedule/services/meeting/{first_disc}/{first_alias}?prematch=1&live=0",
             f"{WEB_BASE}/sport-schedule/services/meeting/{{disc}}/{{alias}}?prematch=1&live=0"),
            (f"{WEB_BASE}/sport-schedule/services/meeting/{first_disc}/{first_alias}",
             f"{WEB_BASE}/sport-schedule/services/meeting/{{disc}}/{{alias}}"),
            (f"{WEB_BASE}/api/sport-schedule/services/meeting/{first_disc}/{first_alias}?prematch=1&live=0",
             f"{WEB_BASE}/api/sport-schedule/services/meeting/{{disc}}/{{alias}}?prematch=1&live=0"),
            (f"{WEB_BASE}/api/detail-service/sport-schedule/services/meeting/{first_disc}/{first_alias}?prematch=1&live=0",
             f"{WEB_BASE}/api/detail-service/sport-schedule/services/meeting/{{disc}}/{{alias}}?prematch=1&live=0"),
            # ── webeb/rest paths ──
            (f"{WEB_BASE}/webeb/rest/api/prematch/{first_disc}/{first_alias}",
             f"{WEB_BASE}/webeb/rest/api/prematch/{{disc}}/{{alias}}"),
            (f"{WEB_BASE}/webeb/rest/prematch/{first_disc}/{first_alias}",
             f"{WEB_BASE}/webeb/rest/prematch/{{disc}}/{{alias}}"),
            (f"{WEB_BASE}/webeb/rest/sport/{first_disc}/meeting/{first_alias}",
             f"{WEB_BASE}/webeb/rest/sport/{{disc}}/meeting/{{alias}}"),
            # ── www.eurobet.it detail-service (Cloudflare, might bypass for API) ──
            (f"{BASE_URL}/detail-service/sport-schedule/services/meeting/{first_disc}/{first_alias}?prematch=1&live=0",
             f"{BASE_URL}/detail-service/sport-schedule/services/meeting/{{disc}}/{{alias}}?prematch=1&live=0"),
        ]

        async with httpx.AsyncClient(
            headers=_HEADERS, timeout=15, follow_redirects=True, proxy=proxy_url,
        ) as client:
            # First verify web.eurobet.it is accessible
            try:
                ping = await client.get(f"{WEB_BASE}/webeb/rest")
                logger.info("[Eurobet] web.eurobet.it ping → %d | %s",
                            ping.status_code, ping.text[:150])
            except Exception as e:
                logger.warning("[Eurobet] web.eurobet.it not reachable: %s", e)

            # ── GET probes ──
            for probe_url, url_template in get_probe_candidates:
                if working_url_template:
                    break
                try:
                    resp = await client.get(probe_url)
                    text = resp.text[:300]
                    logger.info("[Eurobet] GET PROBE %s → %d | %s",
                                probe_url[:110], resp.status_code, text)

                    if resp.status_code == 200:
                        if any(kw in resp.text for kw in (
                            "eventList", "events", "betGroupList", "betGroups",
                            "description", "descrizione", "startDate", "dataOra",
                            "avveniment", "incontro", "partita",
                        )):
                            logger.info("[Eurobet] ✅ Working API (GET): %s", probe_url)
                            working_url_template = url_template
                        else:
                            logger.info("[Eurobet] 200 but no event keywords | full=%.600s",
                                        resp.text)
                    elif resp.status_code not in (404, 403, 520):
                        logger.info("[Eurobet] Unexpected %d for %s | body=%.300s",
                                    resp.status_code, probe_url[:100], resp.text)
                except Exception as exc:
                    logger.info("[Eurobet] GET PROBE error %s: %s", probe_url[:80], str(exc)[:100])

            # webeb/rest action probes: 60+ names tried across multiple runs, all "invalid action"
            # Skipping — webeb/rest is likely a bet-booking API, not the odds feed.

            # ── Probe other services on web.eurobet.it ──────────────────────────────
            if not working_url_template:
                other_services = [
                    f"{WEB_BASE}/odds-service/sport-schedule/services/meeting/{first_disc}/{first_alias}?prematch=1&live=0",
                    f"{WEB_BASE}/betting-service/sport-schedule/services/meeting/{first_disc}/{first_alias}?prematch=1&live=0",
                    f"{WEB_BASE}/schedule-service/sport-schedule/services/meeting/{first_disc}/{first_alias}?prematch=1&live=0",
                    f"{WEB_BASE}/bet-service/sport-schedule/services/meeting/{first_disc}/{first_alias}?prematch=1&live=0",
                ]
                for svc_url in other_services:
                    try:
                        r = await client.get(svc_url)
                        logger.info("[Eurobet] SVC %s → %d | %.300s",
                                    svc_url[:100], r.status_code, r.text)
                        if r.status_code == 200 and any(kw in r.text for kw in
                                                        ("description", "betGroupList", "events", "avveniment")):
                            logger.info("[Eurobet] ✅ SVC works: %s", svc_url)
                            working_url_template = svc_url.replace(
                                f"/{first_disc}/{first_alias}",
                                "/{disc}/{alias}")
                            break
                    except Exception as e:
                        logger.info("[Eurobet] SVC %s error: %s", svc_url[:80], str(e)[:60])

            # ── Fetch www.eurobet.it HTML page for __NEXT_DATA__ (ISR = odds embedded) ──
            if not working_url_template:
                import re as _re
                # Eurobet is Next.js ISR — betting data is embedded in page HTML as __NEXT_DATA__
                html_url_candidates = [
                    (f"https://www.eurobet.it/it/scommesse/calcio/champions-league",
                     f"https://www.eurobet.it/it/scommesse/{{disc}}/{{alias}}"),
                    (f"https://www.eurobet.it/scommesse/calcio/champions-league",
                     f"https://www.eurobet.it/scommesse/{{disc}}/{{alias}}"),
                    (f"https://www.eurobet.it/it/scommesse-sportive/calcio/champions-league",
                     f"https://www.eurobet.it/it/scommesse-sportive/{{disc}}/{{alias}}"),
                ]
                for html_url, html_template in html_url_candidates:
                    try:
                        r = await client.get(html_url, follow_redirects=True)
                        logger.info("[Eurobet] HTML %s → %d | type=%s | len=%d",
                                    html_url, r.status_code,
                                    r.headers.get("content-type", "?"), len(r.text))
                        if r.status_code == 200:
                            nd = _re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                                            r.text, _re.DOTALL)
                            if nd:
                                logger.info("[Eurobet] NEXT_DATA found len=%d | preview=%.3000s",
                                            len(nd.group(1)), nd.group(1))
                                # Try to find events in NEXT_DATA
                                nd_text = nd.group(1)
                                if any(kw in nd_text for kw in ("betGroupList", "betGroups",
                                                                  "description", "startDate")):
                                    logger.info("[Eurobet] ✅ NEXT_DATA has event data!")
                                    working_url_template = "HTML:" + html_template
                                    break
                            else:
                                # Look for API patterns in HTML
                                api_hits = _re.findall(
                                    r'["\']([^"\']*detail-service[^"\']*)["\']', r.text)
                                logger.info("[Eurobet] detail-service URLs in HTML: %s", api_hits[:10])
                                api_hits2 = _re.findall(
                                    r'["\']([^"\']*web\.eurobet[^"\']*)["\']', r.text)
                                logger.info("[Eurobet] web.eurobet URLs in HTML: %s", api_hits2[:10])
                    except Exception as e:
                        logger.info("[Eurobet] HTML %s error: %s", html_url, str(e)[:80])

        # ── Phase 2: Playwright — intercept /_next/data/ + detail-service ──
        # www.eurobet.it is Next.js ISR with isFallback:true — the initial HTML has
        # empty pageProps. The Next.js client auto-fetches /_next/data/{buildId}/{path}.json
        # after page mount to populate actual betting data.
        # Strategy: intercept all responses while page loads with networkidle; capture
        # /_next/data/ JSON (contains pageProps with events) or detail-service API calls.
        if working_url_template is None:
            logger.info("[Eurobet] httpx probes failed — trying Playwright + response interception")
            try:
                import asyncio
                from playwright.async_api import async_playwright
                try:
                    from playwright_stealth import stealth_async as _stealth_async
                    _STEALTH = True
                except ImportError:
                    _STEALTH = False

                proxy_cfg = None
                if proxy_url:
                    import urllib.parse as _up
                    p = _up.urlparse(proxy_url)
                    proxy_cfg = {
                        "server": f"{p.scheme}://{p.hostname}:{p.port}",
                        "username": p.username or "",
                        "password": p.password or "",
                    }

                all_results: list[MatchOdds] = []

                async with async_playwright() as pw:
                    browser = await pw.chromium.launch(
                        headless=True,
                        args=["--no-sandbox", "--disable-dev-shm-usage"],
                        proxy=proxy_cfg,
                    )
                    ctx = await browser.new_context(
                        user_agent=_UA,
                        locale="it-IT",
                        timezone_id="Europe/Rome",
                        viewport={"width": 1280, "height": 800},
                    )
                    page = await ctx.new_page()
                    if _STEALTH:
                        await _stealth_async(page)
                        logger.info("[Eurobet] playwright-stealth applied")

                    # Warmup — establishes Cloudflare session cookies
                    logger.info("[Eurobet] Playwright warmup: navigating to www.eurobet.it…")
                    try:
                        await page.goto("https://www.eurobet.it/", wait_until="domcontentloaded", timeout=30_000)
                        await page.wait_for_timeout(3000)
                        title = await page.title()
                        logger.info("[Eurobet] Warmup page title: %s", title)
                    except Exception as wup_e:
                        logger.warning("[Eurobet] Warmup navigation error: %s", wup_e)

                    async def _browser_fetch(url: str) -> Any:
                        """Fetch URL from within browser context (uses CF session cookies)."""
                        js = f"""
                        async () => {{
                            try {{
                                const r = await fetch('{url}', {{
                                    credentials: 'include',
                                    headers: {{ 'Accept': 'application/json' }}
                                }});
                                if (!r.ok) return {{_status: r.status, _error: 'http_error'}};
                                return await r.json();
                            }} catch(e) {{
                                return {{_error: String(e)}};
                            }}
                        }}
                        """
                        return await page.evaluate(js)

                    def _find_meeting_alias(item_list: list, target_desc: str) -> str | None:
                        """Recursively find meeting aliasUrl matching target_desc."""
                        for item in (item_list or []):
                            if not isinstance(item, dict):
                                continue
                            desc = str(item.get("description") or "").lower()
                            if target_desc.lower() in desc or desc in target_desc.lower():
                                return item.get("aliasUrl")
                            child = _find_meeting_alias(item.get("itemList") or [], target_desc)
                            if child:
                                return child
                        return None

                    # ── Step 1: Get correct meeting aliases from prematch-menu-service ──
                    disc_aliases: dict[str, dict[str, str]] = {}  # disc → {league_name: correct_alias}
                    for disc in set(d for _, d, _ in meetings):
                        url = f"https://www.eurobet.it/prematch-menu-service/api/v2/sport-schedule/services/sport-list/{disc}"
                        result = await _browser_fetch(url)
                        if isinstance(result, dict) and "_error" not in result:
                            sport_result = result.get("result") or {}
                            item_list = sport_result.get("itemList") or []
                            disc_aliases[disc] = {}
                            for league_name, discipline, alias in meetings:
                                if discipline != disc:
                                    continue
                                correct = _find_meeting_alias(item_list, league_name)
                                if correct:
                                    disc_aliases[disc][league_name] = correct
                                    logger.info("[Eurobet] alias found: %s → %r", league_name, correct)
                                else:
                                    logger.info("[Eurobet] alias NOT found for %s (tried desc=%r)", league_name, league_name)
                        else:
                            logger.info("[Eurobet] prematch-menu %s error: %s", disc, result)

                    # ── Step 2: Navigate to each league page, then fetch with correct alias ──
                    # CF only allows detail-service calls when Referer is a valid scommesse page
                    for league_name, discipline, alias in meetings:
                        correct_alias = disc_aliases.get(discipline, {}).get(league_name, alias)
                        nav_url = f"https://www.eurobet.it/it/scommesse/{discipline}/{alias}"
                        try:
                            await page.goto(nav_url, wait_until="domcontentloaded", timeout=30_000)
                            await page.wait_for_timeout(1000)
                        except Exception as e:
                            logger.warning("[Eurobet] %s nav error: %s", league_name, e)

                        # Now fetch detail-service from within this page context (correct Referer)
                        api_url = f"/detail-service/sport-schedule/services/meeting/{discipline}/{correct_alias}?prematch=1&live=0"
                        result = await _browser_fetch(api_url)
                        if isinstance(result, dict) and "_error" not in result:
                            status = result.get("_status")
                            if status:
                                logger.info("[Eurobet] %s → HTTP %d (alias=%r)", league_name, status, correct_alias)
                                continue
                            code = result.get("code")
                            desc_r = result.get("description")
                            logger.info("[Eurobet] %s → code=%s %s alias=%r | preview=%.300s",
                                        league_name, code, desc_r, correct_alias,
                                        _json.dumps(result, ensure_ascii=False)[:300])
                            if code in (1, "1", 1):
                                events = _extract_events(result)
                                if events:
                                    rows = _parse_events(events, league_name, discipline)
                                    logger.info("[Eurobet] %s: %d rows", league_name, len(rows))
                                    all_results.extend(rows)
                                    if rows:
                                        working_url_template = "BROWSER_FETCH"
                        else:
                            logger.info("[Eurobet] %s error: %s (alias=%r)", league_name, result, correct_alias)

                    await browser.close()

            except Exception as pw_err:
                logger.error("[Eurobet] Playwright phase failed: %s", pw_err)

            if not all_results:
                logger.warning("[Eurobet] All approaches failed — 0 rows")
                logger.info("[Eurobet] Total: 0 events, 0 rows")
                return []

            # Dedup and return Playwright results
            seen: dict[tuple[str, str], MatchOdds] = {}
            for r in all_results:
                seen[(r.event_name, r.market)] = r
            deduped = list(seen.values())
            n_events = len({r.event_name for r in deduped})
            logger.info("[Eurobet] Total: %d events, %d rows", n_events, len(deduped))
            return deduped

        # ── Phase 2: Fetch all leagues via httpx ──────────────────────────
        all_results: list[MatchOdds] = []

        async with httpx.AsyncClient(
            headers=_HEADERS, timeout=20, follow_redirects=True, proxy=proxy_url,
        ) as client:
            for league_name, discipline, alias in meetings:
                url = working_url_template.format(disc=discipline, alias=alias)
                logger.info("[Eurobet] Fetching %s…", league_name)
                try:
                    resp = await client.get(url, follow_redirects=True)
                    if resp.status_code != 200:
                        logger.info("[Eurobet] %s → %d", league_name, resp.status_code)
                        continue
                    data = resp.json()
                    if isinstance(data, dict):
                        logger.info("[Eurobet] %s top keys: %s | preview=%.300s",
                                    league_name, list(data.keys())[:10],
                                    _json.dumps(data, ensure_ascii=False)[:300])
                    events = _extract_events(data)
                    if events:
                        logger.info("[Eurobet] %s: %d events | first keys=%s",
                                    league_name, len(events),
                                    list(events[0].keys())[:10] if isinstance(events[0], dict) else "?")
                        rows = _parse_events(events, league_name, discipline)
                        logger.info("[Eurobet] %s: %d rows", league_name, len(rows))
                        all_results.extend(rows)
                    else:
                        logger.info("[Eurobet] %s: no events found in response", league_name)
                except Exception as exc:
                    logger.error("[Eurobet] %s error: %s", league_name, exc)

        # Deduplicate by (event_name, market)
        seen: dict[tuple[str, str], MatchOdds] = {}
        for r in all_results:
            seen[(r.event_name, r.market)] = r
        deduped = list(seen.values())
        n_events = len({r.event_name for r in deduped})
        logger.info("[Eurobet] Total: %d events, %d rows", n_events, len(deduped))
        return deduped
