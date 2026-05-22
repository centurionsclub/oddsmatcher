"""Bet365 / BetFlag / 888sport scraper via centroquote.it comparison site.

Navigates centroquote.it league/match pages with Playwright, extracts
odds for Bet365, BetFlag Bookmaker and 888sport for 1X2, Double Chance,
BTTS, and Over/Under markets.

Configuration
-------------
CENTROQUOTE_CONCURRENCY – parallel match-detail pages (default: 4)
"""

import asyncio
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from playwright.async_api import BrowserContext, Page, async_playwright

from oddsmatcher_backend.scraper.models import MatchOdds

logger = logging.getLogger(__name__)

ROME_TZ   = ZoneInfo("Europe/Rome")
BASE_URL  = "https://www.centroquote.it"

# Bookmakers to extract from centroquote pages
_TARGET_BOOKMAKERS = {"Bet365", "BetFlag Bookmaker", "888sport"}

CONCURRENCY    = 8
PAGE_WAIT_MS   = 2000
GOTO_TIMEOUT   = 25_000
CACHE_MINUTES  = 20        # expires_at window for DB rows

# ── leagues ────────────────────────────────────────────────────────────────────

_LEAGUES: list[dict] = [
    {"url": "/football/italy/serie-a/",           "name": "Serie A",          "sport": "calcio"},
    {"url": "/football/italy/serie-b/",           "name": "Serie B",          "sport": "calcio"},
    {"url": "/football/italy/coppa-italia/",       "name": "Coppa Italia",     "sport": "calcio"},
    {"url": "/football/europe/champions-league/", "name": "Champions League", "sport": "calcio"},
    {"url": "/football/europe/europa-league/",    "name": "Europa League",    "sport": "calcio"},
    {"url": "/football/europe/conference-league/","name": "Conference League","sport": "calcio"},
    {"url": "/football/england/premier-league/",  "name": "Premier League",   "sport": "calcio"},
    {"url": "/football/spain/laliga/",            "name": "LaLiga",           "sport": "calcio"},
    {"url": "/football/germany/bundesliga/",      "name": "Bundesliga",       "sport": "calcio"},
    {"url": "/football/france/ligue-1/",          "name": "Ligue 1",          "sport": "calcio"},
    {"url": "/basketball/usa/nba/",               "name": "NBA",              "sport": "basket"},
]

_SPORT_LEAGUES: dict[str, list[dict]] = defaultdict(list)
for _lg in _LEAGUES:
    _SPORT_LEAGUES[_lg["sport"]].append(_lg)

# ── bookmaker alias → canonical name ──────────────────────────────────────────

_BM_ALIASES: dict[str, str] = {
    "bet365.it":   "Bet365",
    "bet365":      "Bet365",
    "betflagit":   "BetFlag Bookmaker",
    "betflag":     "BetFlag Bookmaker",
    "888sport":    "888sport",
    "888":         "888sport",
}

def _normalise_bm(raw: str) -> str | None:
    key = raw.strip().lower()
    for alias, name in _BM_ALIASES.items():
        if alias in key:
            return name
    return None

# ── row text parser ────────────────────────────────────────────────────────────

_ODDS_RE   = re.compile(r"^\d{1,3}[.,]\d{2}$")
_PAYOUT_RE = re.compile(r"^\d{1,3}[.,]\d+%$")
_SKIP_TOKENS = {"richiedi bonus", "richiedi", "bonus"}

def _parse_row_text(text: str) -> tuple[str, list[float]]:
    tokens = [t.strip() for t in text.split("\n") if t.strip()]
    bm_name = ""
    odds: list[float] = []
    for tok in tokens:
        low = tok.lower()
        if low in _SKIP_TOKENS or _PAYOUT_RE.match(tok):
            continue
        if _ODDS_RE.match(tok):
            odds.append(float(tok.replace(",", ".")))
        elif not bm_name:
            bm_name = tok
    return bm_name, odds

# ── time parsing ───────────────────────────────────────────────────────────────

def _parse_time(raw: str) -> str:
    raw = raw.strip()
    now_utc  = datetime.now(timezone.utc)
    fallback = (now_utc + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0).isoformat()
    if not raw:
        return fallback
    for fmt in ("%d/%m/%Y %H:%M", "%d.%m.%Y %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=ROME_TZ).astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw).astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        pass
    m = re.match(r"(\d{1,2})[/.](\d{1,2})\s+(\d{1,2}):(\d{2})$", raw)
    if m:
        try:
            c = datetime(now_utc.year, int(m.group(2)), int(m.group(1)),
                         int(m.group(3)), int(m.group(4)), tzinfo=ROME_TZ).astimezone(timezone.utc)
            if c < now_utc - timedelta(days=1):
                c = c.replace(year=now_utc.year + 1)
            return c.isoformat()
        except ValueError:
            pass
    m = re.match(r"(\d{1,2}):(\d{2})$", raw)
    if m:
        try:
            now_rome = datetime.now(ROME_TZ)
            c = now_rome.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
            if c < now_rome - timedelta(minutes=30):
                c += timedelta(days=1)
            return c.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    return fallback

# ── JS snippets ────────────────────────────────────────────────────────────────

_LEAGUE_JS = """
() => {
    const results = [];
    const rows = document.querySelectorAll('.eventRow');
    const itMo = {gen:'01',feb:'02',mar:'03',apr:'04',mag:'05',giu:'06',lug:'07',ago:'08',set:'09',ott:'10',nov:'11',dic:'12'};
    const thisYear = new Date().getFullYear();
    function extractDate(txt) {
        const m1 = txt.match(/(\\d{1,2})\\s+([A-Za-z]{3,})\\s+(\\d{4})/);
        if (m1) { const mo = itMo[m1[2].toLowerCase().slice(0,3)]; if (mo) return `${m1[3]}-${mo}-${m1[1].padStart(2,'0')}`; }
        const m2 = txt.match(/(?:Oggi|Domani|Lun|Mar|Mer|Gio|Ven|Sab|Dom)[a-zì]*[,.]?\\s+(\\d{1,2})\\s+([A-Za-z]{3,})/i);
        if (m2) { const mo = itMo[m2[2].toLowerCase().slice(0,3)]; if (mo) return `${thisYear}-${mo}-${m2[1].padStart(2,'0')}`; }
        return null;
    }
    function extractTime(txt) { const m = txt.match(/\\b(\\d{1,2}):(\\d{2})\\b/); return m ? `${m[1].padStart(2,'0')}:${m[2]}` : null; }
    const liveRe = /\\bLIVE\\b|\\bIn Corso\\b|\\bIN CORSO\\b/;
    rows.forEach(row => {
        const rowText = row.innerText || '';
        if (liveRe.test(rowText)) return;
        const h2hLink = Array.from(row.querySelectorAll('a[href]')).find(a => {
            const h = a.getAttribute('href') || '';
            return (h.includes('/h2h/') || h.includes('-v-')) && !h.includes('inplay') && !h.includes('live');
        });
        if (!h2hLink) return;
        const href = h2hLink.getAttribute('href');
        const gameRow = row.querySelector('[data-testid="game-row"]');
        if (!gameRow) return;
        const teams = Array.from(gameRow.querySelectorAll('.truncate')).map(e => e.innerText.trim()).filter(t => t.length > 1 && t.length < 50);
        if (teams.length < 2) return;
        const flat = rowText.replace(/\\n/g,' ');
        let datePart = extractDate(flat);
        if (!datePart) {
            let el = row.previousElementSibling;
            for (let i = 0; i < 40 && el && !datePart; i++) { datePart = extractDate((el.innerText||'').replace(/\\n/g,' ')); el = el.previousElementSibling; }
        }
        const timePart = extractTime(flat);
        const timeText = (datePart && timePart) ? `${datePart}T${timePart}:00` : (timePart || '');
        results.push({ href, home: teams[0], away: teams[1], timeText });
    });
    return results;
}
"""

_MATCH_TIME_JS = """
() => {
    const itM = {gen:1,feb:2,mar:3,apr:4,mag:5,giu:6,lug:7,ago:8,set:9,ott:10,nov:11,dic:12};
    for (const sel of ['time[datetime]','[class*="kickoff"]','[class*="match-time"]','[class*="event-date"]','time']) {
        for (const el of document.querySelectorAll(sel)) {
            const dt = el.getAttribute('datetime');
            if (dt && dt.length > 6) return dt;
            const txt = (el.innerText||'').trim();
            if (!txt || txt.length > 60) continue;
            const m = txt.match(/(\\d{1,2})\\s+([A-Za-z]{3})\\s+(\\d{4})[,\\s]+(\\d{1,2}):(\\d{2})/);
            if (m) { const mo = itM[m[2].toLowerCase()]; if (mo) return `${m[3]}-${String(mo).padStart(2,'0')}-${m[1].padStart(2,'0')}T${m[4].padStart(2,'0')}:${m[5]}:00`; }
        }
    }
    return '';
}
"""

# ── page helpers ───────────────────────────────────────────────────────────────

async def _extract_bm_rows(page: Page) -> list[tuple[str, list[float]]]:
    try:
        raw = await page.evaluate("""
            () => {
                return Array.from(document.querySelectorAll('div.flex.h-9')).map(row => {
                    const hasStruck = Array.from(row.querySelectorAll('*')).some(el => {
                        try {
                            if ((el.className||'').includes('line-through')) return true;
                            if (window.getComputedStyle(el).textDecorationLine.includes('line-through')) return true;
                        } catch(e) {}
                        return false;
                    });
                    return { text: row.innerText || '', hasStruck };
                });
            }
        """)
        result = []
        for r in (raw or []):
            if r.get("hasStruck"):
                continue
            bm, odds = _parse_row_text(r.get("text", ""))
            if bm and odds:
                result.append((bm, odds))
        return result
    except Exception:
        return []

async def _click_tab(page: Page, tab_text: str) -> bool:
    try:
        clicked = await page.evaluate("""
            (t) => {
                for (const div of document.querySelectorAll('a div, button div, li div')) {
                    if ((div.innerText||'').trim() === t) {
                        (div.closest('a') || div.closest('button') || div.closest('li') || div).click();
                        return true;
                    }
                }
                return false;
            }
        """, tab_text)
        if clicked:
            return True
        for loc in [page.locator(f"a:has-text('{tab_text}')").first,
                    page.locator(f"button:has-text('{tab_text}')").first]:
            try:
                await loc.click(timeout=2000)
                return True
            except Exception:
                pass
        return False
    except Exception:
        return False

# ── match detail scraper ───────────────────────────────────────────────────────

async def _scrape_match(
    context: BrowserContext,
    match_url: str,
    event_name: str,
    event_time: str,
    sport: str,
    league_name: str,
) -> list[dict]:
    """Scrape one match detail page; return flat rows for Bet365 only."""
    page = await context.new_page()
    rows: list[dict] = []
    cq_url = BASE_URL + match_url

    try:
        await page.goto(cq_url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT)
        await page.wait_for_timeout(PAGE_WAIT_MS)
        for _ in range(5):
            if await page.locator("div.flex.h-9").count() >= 5:
                break
            await page.wait_for_timeout(800)

        # refine event_time from detail page
        try:
            raw_t = await page.evaluate(_MATCH_TIME_JS)
            if raw_t:
                parsed = _parse_time(raw_t)
                now = datetime.now(timezone.utc)
                try:
                    cand = datetime.fromisoformat(parsed)
                    if now - timedelta(days=30) < cand < now + timedelta(days=30):
                        event_time = parsed
                except Exception:
                    pass
        except Exception:
            pass

        # skip live/finished
        try:
            et = datetime.fromisoformat(event_time)
            if et < datetime.now(timezone.utc) - timedelta(minutes=30):
                return []
        except Exception:
            pass

        def _add(bookmaker: str, market: str, outcome: str, odds_val: float):
            rows.append({"bookmaker": bookmaker, "market": market, "outcome": outcome,
                         "odds": odds_val, "event_name": event_name, "event_time": event_time,
                         "sport": sport, "league": league_name, "match_url": cq_url})

        def _extract_targets(bm_rows, outcomes: list[str], market: str):
            """Collect rows for all target bookmakers from a list of (bm_raw, odds) pairs."""
            found: set[str] = set()
            for bm_raw, odds in bm_rows:
                bm = _normalise_bm(bm_raw)
                if bm and bm in _TARGET_BOOKMAKERS and bm not in found and len(odds) >= len(outcomes):
                    for i, out in enumerate(outcomes):
                        _add(bm, market, out, odds[i])
                    found.add(bm)
                if found == _TARGET_BOOKMAKERS:
                    break

        # 1X2
        outcomes_1x2 = ["1", "X", "2"] if sport == "calcio" else ["1", "2"]
        _extract_targets(await _extract_bm_rows(page), outcomes_1x2, "1X2")

        if sport != "calcio":
            return rows

        # Double Chance
        if await _click_tab(page, "Double Chance"):
            await page.wait_for_timeout(2000)
            _extract_targets(await _extract_bm_rows(page), ["1X", "X2", "12"], "DC")

        # BTTS
        if await _click_tab(page, "Both Teams to Score"):
            await page.wait_for_timeout(2000)
            _extract_targets(await _extract_bm_rows(page), ["Goal", "No Goal"], "BTTS")

        # Over/Under
        if await _click_tab(page, "Over/Under"):
            await page.wait_for_timeout(1500)
            for threshold in ["1.5", "2.5", "3.5", "4.5"]:
                expanded = await page.evaluate("""
                    (thr) => {
                        for (const row of document.querySelectorAll('div.flex.h-9')) {
                            const t = (row.innerText||'').replace(/\\n/g,' ').trim();
                            if (t.startsWith('Over/Under +'+thr) || t.startsWith('Over/Under '+thr)) {
                                row.click(); return true;
                            }
                        }
                        return false;
                    }
                """, threshold)
                if not expanded:
                    continue
                await page.wait_for_timeout(1200)
                ou_rows = [(bm_raw, odds) for bm_raw, odds in await _extract_bm_rows(page)
                           if not bm_raw.lower().startswith("over/under")]
                found: set[str] = set()
                for bm_raw, odds in ou_rows:
                    bm = _normalise_bm(bm_raw)
                    if bm and bm in _TARGET_BOOKMAKERS and bm not in found and len(odds) >= 2:
                        _add(bm, "Over/Under", f"Over {threshold}",  odds[0])
                        _add(bm, "Over/Under", f"Under {threshold}", odds[1])
                        found.add(bm)

    except Exception as exc:
        logger.warning("[Bet365/CQ] Match %s error: %s", match_url, exc)
    finally:
        await page.close()

    return rows

# ── league page ────────────────────────────────────────────────────────────────

async def _discover_tennis(context: BrowserContext, gender_kw: str) -> list[str]:
    page = await context.new_page()
    try:
        await page.goto(BASE_URL + "/tennis/", wait_until="domcontentloaded", timeout=GOTO_TIMEOUT)
        await page.wait_for_timeout(PAGE_WAIT_MS)
        urls = await page.evaluate(f"""
            () => Array.from(document.querySelectorAll('a[href]'))
                .map(a => a.getAttribute('href'))
                .filter(h => h && h.startsWith('/tennis/') && h !== '/tennis/' && h.includes('{gender_kw}') && !h.includes('doppio'))
                .filter((v,i,a) => a.indexOf(v) === i)
        """)
        return urls or []
    except Exception:
        return []
    finally:
        await page.close()

async def _get_matches(context: BrowserContext, league: dict) -> list[dict]:
    if league.get("discover"):
        urls = await _discover_tennis(context, league["discover"])
        events: list[dict] = []
        for t_url in urls:
            page = await context.new_page()
            try:
                await page.goto(BASE_URL + t_url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT)
                await page.wait_for_timeout(2500)
                raw = await page.evaluate(_LEAGUE_JS)
                events.extend(_parse_matches(raw))
            except Exception:
                pass
            finally:
                await page.close()
            await asyncio.sleep(0.3)
        return events

    page = await context.new_page()
    try:
        for attempt in range(3):
            await page.goto(BASE_URL + league["url"], wait_until="domcontentloaded", timeout=GOTO_TIMEOUT)
            await page.wait_for_timeout(PAGE_WAIT_MS)
            for _ in range(6):
                if await page.locator(".eventRow").count() > 0:
                    break
                await page.wait_for_timeout(800)
            raw = await page.evaluate(_LEAGUE_JS)
            events = _parse_matches(raw)
            if events or attempt == 2:
                return events
            await page.wait_for_timeout(3000)
        return []
    except Exception:
        return []
    finally:
        await page.close()

def _parse_matches(raw: list) -> list[dict]:
    seen: set = set()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=90)
    events = []
    for m in (raw or []):
        home, away = m.get("home", "").strip(), m.get("away", "").strip()
        if not home or not away:
            continue
        pair = frozenset({home.lower(), away.lower()})
        if pair in seen:
            continue
        seen.add(pair)
        event_time = _parse_time(m.get("timeText", ""))
        try:
            if datetime.fromisoformat(event_time) < cutoff:
                continue
        except Exception:
            pass
        events.append({"url": m["href"], "event_name": f"{home} - {away}", "event_time": event_time})
    return events

# ── flat rows → MatchOdds ──────────────────────────────────────────────────────

def _rows_to_match_odds(flat_rows: list[dict]) -> list[MatchOdds]:
    """Group flat per-outcome rows into MatchOdds objects (one per event+market)."""
    # key: (event_name, sport, league, market, match_url, event_time)
    # value: {bookmaker: {outcome: odds}}
    grouped: dict[tuple, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))

    for r in flat_rows:
        key = (r["event_name"], r["sport"], r["league"], r["market"], r["match_url"], r["event_time"])
        grouped[key][r["bookmaker"]][r["outcome"]] = r["odds"]

    results = []
    for key, bk_odds in grouped.items():
        event_name, sport, league, market, match_url, event_time = key
        parts = event_name.split(" - ", 1)
        home = parts[0] if len(parts) == 2 else event_name
        away = parts[1] if len(parts) == 2 else ""
        bookmaker_odds = [{"bookmaker": bk, "odds": odds} for bk, odds in bk_odds.items() if odds]
        if not bookmaker_odds:
            continue
        results.append(MatchOdds(
            sport=sport,
            league=league,
            home_team=home,
            away_team=away,
            event_name=event_name,
            event_time=event_time,
            match_url=match_url,
            market=market,
            bookmaker_odds=bookmaker_odds,
        ))
    return results

# ── scraper class ──────────────────────────────────────────────────────────────

class Bet365Scraper:
    """Scrapes Bet365 odds from centroquote.it comparison site."""

    bookmaker_name = "Centroquote"  # internal label; rows carry individual bookmaker names

    def __init__(self):
        self._log = logging.getLogger(f"{__name__}.Bet365Scraper")

    async def scrape_all(self) -> list[MatchOdds]:
        return await self._run(sport_filter=None)

    async def scrape_sport(self, sport_key: str) -> list[MatchOdds]:
        return await self._run(sport_filter=sport_key)

    async def _run(self, sport_filter: str | None) -> list[MatchOdds]:
        leagues = [lg for lg in _LEAGUES if sport_filter is None or lg["sport"] == sport_filter]
        if not leagues:
            return []

        self._log.info("[Bet365/CQ] Scraping %d leagues (sport=%s)", len(leagues), sport_filter or "all")
        flat_rows: list[dict] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="it-IT",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            # Stealth: nascondi navigator.webdriver e altri segnali bot su tutte le pagine
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => {const ps=[1,2,3,4,5]; ps.__proto__=PluginArray.prototype; return ps;}});
                Object.defineProperty(navigator, 'languages', {get: () => ['it-IT','it','en-US','en']});
                if (!window.chrome) window.chrome = {runtime: {}};
            """)
            await context.route(
                "**/*.{png,jpg,jpeg,gif,svg,webp,woff,woff2,ttf,otf}",
                lambda route, _: route.abort(),
            )

            for league in leagues:
                self._log.info("[Bet365/CQ] League: %s", league["name"])
                matches = await _get_matches(context, league)
                if not matches:
                    self._log.info("[Bet365/CQ]   0 matches")
                    continue
                self._log.info("[Bet365/CQ]   %d matches → scraping detail pages", len(matches))

                for batch_start in range(0, len(matches), CONCURRENCY):
                    batch = matches[batch_start : batch_start + CONCURRENCY]
                    tasks = [
                        _scrape_match(context, m["url"], m["event_name"], m["event_time"],
                                      league["sport"], league["name"])
                        for m in batch
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for res in results:
                        if isinstance(res, list):
                            flat_rows.extend(res)
                        elif isinstance(res, Exception):
                            self._log.warning("[Bet365/CQ] Batch error: %s", res)

                self._log.info("[Bet365/CQ]   %s: %d rows so far", league["name"], len(flat_rows))

            await browser.close()

        match_odds = _rows_to_match_odds(flat_rows)
        n_events = len({mo.event_name for mo in match_odds})
        self._log.info("[Bet365/CQ] Total: %d events, %d market rows", n_events, len(match_odds))
        return match_odds
