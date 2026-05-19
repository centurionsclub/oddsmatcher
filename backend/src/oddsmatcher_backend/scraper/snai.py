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
    + "/api/lettura-palinsesto-sport/palinsesto/prematch/live-ora-for-cards"
    + "/{manif_id}?offerId=0&metaTplEnabled=true&deep=true"
)


class SnaiScraper:
    """Snai scraper — two-phase:
    1. Navigate to /scommesse to trigger alberaturaPrematch (intercepted).
    2. For each wanted competition, use page.evaluate(fetch(...)) to fetch
       events directly from the page JS context — this carries the
       flutterseatech.it session cookies that the page JS already set.
    """

    bookmaker_name = BOOKMAKER

    async def scrape_all(self) -> list[MatchOdds]:
        return await self._run(sport=None)

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        return await self._run(sport=sport)

    async def _run(self, sport: str | None) -> list[MatchOdds]:
        pw = await async_playwright().start()
        proxy_url = os.environ.get("PROXY_URL")
        proxy = None
        if proxy_url:
            import urllib.parse
            p = urllib.parse.urlparse(proxy_url)
            proxy = {
                "server": f"{p.scheme}://{p.hostname}:{p.port}",
                "username": p.username or "",
                "password": p.password or "",
            }
            logger.info("[Snai] Using proxy: %s:%s", p.hostname, p.port)

        browser = await pw.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            proxy=proxy,
        )
        context = await browser.new_context(
            user_agent=_UA, locale="it-IT", timezone_id="Europe/Rome",
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()
        if _STEALTH_AVAILABLE:
            await _stealth_async(page)
            logger.info("[Snai] playwright-stealth applied")
        results: list[MatchOdds] = []

        # ── Phase 1: intercept alberaturaPrematch ─────────────────────
        captured_alberatura: dict = {}
        intercepted_urls: list[str] = []

        async def on_response(response):
            nonlocal captured_alberatura
            url = response.url
            # Log ALL snai/flutterseatech responses for diagnostics
            if "snai" in url.lower() or API_HOST in url:
                logger.info("[Snai] RESP %d: %s", response.status, url)
                intercepted_urls.append(url)
            if API_HOST not in url:
                return
            if "alberatura" not in url.lower():
                return
            try:
                body_bytes = await response.body()
                body = _json.loads(body_bytes)
                captured_alberatura = body
                logger.info("[Snai] alberaturaPrematch captured! keys=%s", list(body.keys()))
            except Exception as e:
                logger.warning("[Snai] Could not parse alberaturaPrematch body: %s", e)

        page.on("response", on_response)

        # ── Step 1: load homepage — warms up session + triggers alberaturaPrematch ──
        logger.info("[Snai] Navigating to homepage...")
        try:
            await page.goto(BASE_URL, wait_until="networkidle", timeout=40_000)
            logger.info("[Snai] Homepage: networkidle")
        except Exception as e:
            logger.info("[Snai] Homepage: %s", type(e).__name__)

        # Wait for alberatura response to arrive (sometimes fires after networkidle)
        await page.wait_for_timeout(4000)

        # ── Step 2: accept cookie consent if present ──────────────────
        COOKIE_SELECTORS = [
            "#onetrust-accept-btn-handler",
            "button:has-text('Accetta tutti')",
            "button:has-text('Accetta')",
            "button:has-text('Consenti tutto')",
            "button:has-text('Consenti')",
            "[data-testid='cookie-accept']",
            ".accept-cookies-button",
        ]
        for sel in COOKIE_SELECTORS:
            try:
                await page.click(sel, timeout=3000)
                logger.info("[Snai] Cookie consent clicked: %s", sel)
                await page.wait_for_timeout(1500)
                break
            except Exception:
                pass

        # ── Step 3: if alberatura not yet captured, navigate to sport page ──
        # We intentionally avoid /scommesse which causes ERR_HTTP2_PROTOCOL_ERROR
        # via the proxy. The alberatura is usually captured during the homepage load.
        if not captured_alberatura:
            logger.info("[Snai] alberatura not yet captured, trying /scommesse/calcio…")
            try:
                await page.goto(BASE_URL + "/scommesse/calcio", wait_until="networkidle", timeout=40_000)
                logger.info("[Snai] /scommesse/calcio: networkidle")
            except Exception as e:
                logger.info("[Snai] /scommesse/calcio: %s", type(e).__name__)
            await page.wait_for_timeout(5000)

        logger.info("[Snai] intercepted_urls (%d): %s", len(intercepted_urls), intercepted_urls[:30])

        page.remove_listener("response", on_response)
        logger.info("[Snai] alberatura captured: %s", bool(captured_alberatura))

        # ── Step 4: make sure we're on a snai.it page for CORS-safe fetch() calls ──
        # If the page ended up on an error page, navigate back to homepage.
        current_url = page.url
        if not current_url.startswith("https://www.snai.it") and not current_url.startswith("https://betting-snai"):
            logger.info("[Snai] Page drifted to %s — navigating back to homepage", current_url)
            try:
                await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(2000)
            except Exception as e:
                logger.warning("[Snai] Could not return to homepage: %s", e)

        # ── Find wanted competitions ───────────────────────────────────
        competitions = self._find_competitions(captured_alberatura, sport)
        logger.info("[Snai] %d competitions found", len(competitions))
        if not competitions:
            logger.warning("[Snai] No competitions matched — check alberaturaPrematch keys: %s",
                           list(captured_alberatura.keys())[:10])
            await browser.close()
            await pw.stop()
            return results

        # ── Phase 2: fetch events via page.evaluate() ─────────────────
        # page.evaluate() runs JS inside the browser — carries flutterseatech.it
        # cookies already set by the Snai page JS during phase 1.
        for league_name, sport_key, disc_id, manif_id in competitions:
            url = EVENTS_API.format(manif_id=manif_id)
            logger.info("[Snai] Fetching events for %s (manif=%d)…", league_name, manif_id)
            try:
                body = await page.evaluate(f"""
                    async () => {{
                        try {{
                            const resp = await fetch({_json.dumps(url)}, {{
                                headers: {{
                                    'Accept': 'application/json, text/plain, */*',
                                    'Accept-Language': 'it-IT,it;q=0.9',
                                    'X-Requested-With': 'XMLHttpRequest'
                                }},
                                credentials: 'include'
                            }});
                            if (!resp.ok) {{
                                return {{'_error': resp.status, '_url': resp.url}};
                            }}
                            return resp.json();
                        }} catch(e) {{
                            return {{'_error': String(e)}};
                        }}
                    }}
                """)
            except Exception as exc:
                logger.error("[Snai] page.evaluate failed for %s: %s", league_name, exc)
                continue

            if isinstance(body, dict) and "_error" in body:
                logger.warning("[Snai] %s fetch error: %s", league_name, body)
                continue

            preview = _json.dumps(body, ensure_ascii=False)[:400] if body else "empty"
            logger.info("[Snai] %s response preview: %s", league_name, preview)

            rows = _parse_snai_events(body, league_name, sport_key)
            logger.info("[Snai] %s: %d rows", league_name, len(rows))
            results.extend(rows)

        await browser.close()
        await pw.stop()

        logger.info("[Snai] Total rows: %d", len(results))
        return results

    def _find_competitions(
        self, alberatura: dict, sport_filter: str | None
    ) -> list[tuple[str, str, int, int]]:
        """
        Parse manifestazioneMap (flat dict) to find competitions we want.
        Returns list of (league_name, sport_key, codiceDisciplina, codiceManifestazione).
        """
        out: list[tuple[str, str, int, int]] = []
        if not isinstance(alberatura, dict):
            return out

        manif_map = alberatura.get("manifestazioneMap", {})
        if not isinstance(manif_map, dict):
            logger.warning("[Snai] manifestazioneMap missing or wrong type: %s", type(manif_map))
            return out

        logger.info("[Snai] manifestazioneMap has %d entries", len(manif_map))

        for key, entry in manif_map.items():
            if not isinstance(entry, dict):
                continue

            disc_id = entry.get("codiceDisciplina")
            manif_id = entry.get("codiceManifestazione")
            descrizione = str(entry.get("descrizione") or "").strip()

            if not disc_id or not manif_id or not descrizione:
                continue

            sport_key = SPORT_CODE_MAP.get(int(disc_id))
            if not sport_key:
                continue

            if sport_filter and sport_key != sport_filter:
                continue

            league_name = _match_league(descrizione, sport_key)
            if league_name:
                out.append((league_name, sport_key, int(disc_id), int(manif_id)))
                logger.info("[Snai] Matched: %r → %r (disc=%s manif=%s)",
                            descrizione, league_name, disc_id, manif_id)

        return out
