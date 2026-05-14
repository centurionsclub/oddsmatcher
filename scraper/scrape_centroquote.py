"""
Centroquote.it scraper — OddsMatcher
=====================================
Strategia:
  1. Per ogni campionato, naviga la pagina principale → raccogli URL partite H2H
  2. Per ogni partita naviga la pagina dettaglio → scrapa le righe bookmaker
     (selettore: div.flex.h-9)
  3. Per ogni mercato (1X2, DC, O/U, BTTS) clicca il tab corrispondente
  4. Salva su Supabase (tabella live_odds) tramite service_role key

Execution:  python scrape_centroquote.py [calcio|tennis|basket|tutti]
Daemon:     python daemon.py (loop ogni 5 min)
"""

import asyncio
import json
import os
import re
import ssl
import sys
import urllib.request
import urllib.parse
import certifi
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Optional

ROME_TZ = ZoneInfo("Europe/Rome")

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page, BrowserContext

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
BASE_URL = "https://www.centroquote.it"
CACHE_TTL_MINUTES = 2880  # 48 ore: dati visibili anche se il scraper salta 2+ giorni
CONCURRENCY = 6          # parallel match pages (ridotto per stabilità su CI)
PAGE_WAIT_MS = 4000      # ms to wait after navigation (GitHub Actions più lento)
GOTO_TIMEOUT_MS = 30000  # page load timeout

# ──────────────────────────────────────────────
# LEAGUES
# ──────────────────────────────────────────────
LEAGUES = [
    # Italia
    {"url": "/football/italy/serie-a/",               "name": "Serie A",          "sport": "calcio"},
    {"url": "/football/italy/serie-b/",               "name": "Serie B",          "sport": "calcio"},
    {"url": "/football/italy/coppa-italia/",           "name": "Coppa Italia",     "sport": "calcio"},
    # Europa
    {"url": "/football/europe/champions-league/",     "name": "Champions League", "sport": "calcio"},
    {"url": "/football/europe/europa-league/",        "name": "Europa League",    "sport": "calcio"},
    {"url": "/football/europe/conference-league/",    "name": "Conference League","sport": "calcio"},
    # Campionati esteri
    {"url": "/football/england/premier-league/",      "name": "Premier League",   "sport": "calcio"},
    {"url": "/football/england/championship/",        "name": "Championship",     "sport": "calcio"},
    {"url": "/football/spain/laliga/",                "name": "LaLiga",           "sport": "calcio"},
    {"url": "/football/spain/laliga2/",               "name": "LaLiga2",          "sport": "calcio"},
    {"url": "/football/germany/bundesliga/",          "name": "Bundesliga",       "sport": "calcio"},
    {"url": "/football/france/ligue-1/",              "name": "Ligue 1",          "sport": "calcio"},
    # Tennis — discovery per tutti i tornei ATP e WTA attivi
    {"url": "/tennis/",  "name": "ATP Singles", "sport": "tennis", "discover": "atp"},
    {"url": "/tennis/",  "name": "WTA Singles", "sport": "tennis", "discover": "wta"},
    # Basket
    {"url": "/basketball/usa/nba/",                   "name": "NBA",              "sport": "basket"},
]

# ──────────────────────────────────────────────
# MARKETS — tab text as it appears on the page
# ──────────────────────────────────────────────
# Football markets
FOOTBALL_MARKET_TABS = [
    {"tab": "1X2",                  "key": "1X2",      "outcomes": ["1", "X", "2"]},
    {"tab": "Double Chance",        "key": "DC",       "outcomes": ["1X", "X2", "12"]},
    {"tab": "Both Teams to Score",  "key": "BTTS",     "outcomes": ["Goal", "No Goal"]},
    # Over/Under shows a submenu — we handle it separately
]
OVER_UNDER_THRESHOLDS = ["0.5", "1.5", "2.5", "3.5", "4.5"]

# Tennis / basket: only winner (moneyline)
TENNIS_BASKET_MARKET_TABS = [
    {"tab": "1X2",  "key": "1X2",  "outcomes": ["1", "2"]},  # no draw
]

# ──────────────────────────────────────────────
# BOOKMAKER NORMALISATION
# ──────────────────────────────────────────────
BM_ALIASES: dict[str, str] = {
    "888sport":       "888sport",
    "bet365.it":      "Bet365",
    "bet365":         "Bet365",
    "betflagit":      "BetFlag Bookmaker",
    "betflag":        "BetFlag Bookmaker",
    "betssonit":      "Betsson",
    "betsson":        "Betsson",
    "bwin.it":        "Bwin",
    "bwin":           "Bwin",
    "eurobet.it":     "Eurobet",
    "eurobet":        "Eurobet",
    "goldbet":        "GoldBet",
    "lottomatica":    "Lottomatica",
    "netwin":         "NetWin",
    "netbet":         "NetBet",
    "planetwin365":   "Planetwin365",
    "sisal":          "Sisal",
    "snai":           "Snai",
    "williamhill.it": "William Hill",
    "williamhill":    "William Hill",
    "william hill":   "William Hill",
    "leovegas":       "LeoVegas",
    "admiralbet":     "AdmiralBet",
    "admiral":        "AdmiralBet",
    "codere":         "Codere",
    "dazn bet":       "DAZN Bet",
    "dazn":           "DAZN Bet",
    "domusbet":       "DomusBet",
    "e-play24":       "E-Play24",
    "fastbet":        "Fastbet",
    "stanleybet":     "Stanleybet",
    # Betfair is scraped directly from Betfair Exchange API (betfair_scraper.py)
    # — do NOT map here or it would overwrite real exchange lay odds with back odds
    "gioco digitale": "Gioco Digitale",
}


def normalise_bookmaker(raw: str) -> str | None:
    """Ritorna il nome canonico del bookmaker, o None se non è un bookmaker italiano noto."""
    key = raw.strip().lower()
    if key in BM_ALIASES:
        return BM_ALIASES[key]
    for alias, canonical in BM_ALIASES.items():
        if alias in key:
            return canonical
    return None  # bookmaker non italiano/non riconosciuto → scarta


# ──────────────────────────────────────────────
# SUPABASE HELPERS (urllib with certifi SSL)
# ──────────────────────────────────────────────
SSL_CTX = ssl.create_default_context(cafile=certifi.where())


def _supabase_request(method: str, path: str, body=None, params: dict | None = None):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("  [ERROR] SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
        return None

    # path may already contain query params (e.g. "live_odds?on_conflict=...")
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    if params:
        sep = "&" if "?" in url else "?"
        url += sep + urllib.parse.urlencode(params)

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode(errors="replace")
        print(f"  [Supabase {method}] HTTP {e.code}: {body_txt[:300]}")
        return None
    except Exception as exc:
        print(f"  [Supabase {method}] {exc}")
        return None


def clean_expired():
    _supabase_request("POST", "rpc/clean_expired_live_odds", {})


def upsert_odds_batch(rows: list[dict]) -> bool:
    if not rows:
        return True

    # Deduplica: se lo stesso (bookmaker, event_name, market, outcome) appare
    # più volte (inline + dettaglio), tieni solo l'ultima occorrenza.
    # PostgreSQL lancia un errore se lo stesso conflict-key appare due volte
    # nello stesso comando ON CONFLICT DO UPDATE.
    seen: dict[tuple, dict] = {}
    for row in rows:
        key = (row["bookmaker"], row["event_name"], row["market"], row["outcome"])
        seen[key] = row  # l'ultimo vince (dati da pagina dettaglio > inline)
    deduped = list(seen.values())

    conflict_cols = "bookmaker,event_name,market,outcome"
    for i in range(0, len(deduped), 500):
        chunk = deduped[i : i + 500]
        result = _supabase_request("POST", f"live_odds?on_conflict={conflict_cols}", chunk)
        if result is None:
            return False
    return True


# ──────────────────────────────────────────────
# PARSING ROW TEXT → odds
# Row inner_text format:
#   "888sport\n\nRICHIEDI BONUS\n2.90\n2.90\n2.50\n91.8%"
# ──────────────────────────────────────────────
ODDS_RE = re.compile(r"^\d{1,3}[.,]\d{2}$")
PAYOUT_RE = re.compile(r"^\d{1,3}[.,]\d+%$")
SKIP_TOKENS = {"richiedi bonus", "richiedi", "bonus"}


def parse_row_text(text: str) -> tuple[str, list[float]]:
    """Return (bookmaker_name, [odd1, odd2, ...])."""
    tokens = [t.strip() for t in text.split("\n") if t.strip()]
    bm_name = ""
    odds: list[float] = []

    for tok in tokens:
        low = tok.lower()
        if low in SKIP_TOKENS or PAYOUT_RE.match(tok):
            continue
        if ODDS_RE.match(tok):
            odds.append(float(tok.replace(",", ".")))
        elif not bm_name and not ODDS_RE.match(tok):
            bm_name = tok

    return bm_name, odds


# ──────────────────────────────────────────────
# SCRAPE ONE MATCH PAGE
# ──────────────────────────────────────────────
async def _extract_event_time_from_page(page: Page, fallback: str) -> str:
    """Try to read the match start time from the already-loaded match detail page."""
    try:
        raw = await page.evaluate(_MATCH_TIME_JS)
        if raw and raw.strip():
            parsed = _parse_time_best_effort(raw.strip())
            # Accept if it looks like a real future (or near-past) datetime,
            # not just the scraper's own "now+1day" fallback sentinel
            now_utc = datetime.now(timezone.utc)
            try:
                from datetime import datetime as dt2
                candidate = dt2.fromisoformat(parsed)
                # Reasonable range: up to 30 days in the future, not >30 days in the past
                if now_utc - timedelta(days=30) < candidate < now_utc + timedelta(days=30):
                    return parsed
            except Exception:
                pass
    except Exception:
        pass
    return fallback


async def scrape_match_page(
    context: BrowserContext,
    match_url: str,
    event_name: str,
    event_time: str,
    league: dict,
) -> list[dict]:
    """Open a match detail page and scrape odds for all markets."""
    page = await context.new_page()
    db_rows: list[dict] = []
    expires = (datetime.now(timezone.utc) + timedelta(minutes=CACHE_TTL_MINUTES)).isoformat()
    cq_url = BASE_URL + match_url  # direct centroquote comparison page URL

    try:
        await page.goto(BASE_URL + match_url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
        # Aspetta networkidle + wait esplicito per almeno 8 bookmaker rows
        try:
            await page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        await page.wait_for_timeout(PAGE_WAIT_MS)
        # Aspetta fino a 10s che compaiano almeno 8 righe bookmaker
        for _ in range(10):
            n = await page.locator("div.flex.h-9").count()
            if n >= 8:
                break
            await page.wait_for_timeout(1000)

        # Try to refine the event_time from the match detail page itself
        event_time = await _extract_event_time_from_page(page, event_time)

        # Skip live/finished matches: if the event started more than 30 min ago, don't save
        try:
            et = datetime.fromisoformat(event_time)
            cutoff_match = datetime.now(timezone.utc) - timedelta(minutes=30)
            if et < cutoff_match:
                return []
        except Exception:
            pass

        sport = league["sport"]

        # --- 1X2 / moneyline (default tab, already loaded) ---
        rows_1x2 = await _extract_bm_rows(page)
        # Se troppo pochi bookmaker, riprova ancora
        if len(rows_1x2) < 5:
            await page.wait_for_timeout(3000)
            rows_1x2 = await _extract_bm_rows(page)
        if sport == "calcio":
            outcomes_1x2 = ["1", "X", "2"]
            market_key = "1X2"
        else:
            outcomes_1x2 = ["1", "2"]
            market_key = "1X2"

        for bm_raw, odds in rows_1x2:
            bm = normalise_bookmaker(bm_raw)
            if not bm:
                continue
            for i, out in enumerate(outcomes_1x2):
                if i < len(odds):
                    db_rows.append(_make_row(bm, league, event_name, event_time, market_key, out, odds[i], expires, cq_url))

        if sport != "calcio":
            # Tennis/basket: only moneyline
            return db_rows

        # --- Other football markets: click tabs ---
        # For each market we read a reference value from 1X2 data to detect if the
        # tab click actually changed the table (Vue re-render).  DC odds are always
        # lower than 1X2 odds for the same slot, so we use that as a sanity check.
        ref_first_odds = rows_1x2[0][1][0] if rows_1x2 and rows_1x2[0][1] else None

        for market_cfg in FOOTBALL_MARKET_TABS[1:]:  # skip 1X2, already done
            clicked = await _click_tab(page, market_cfg["tab"])
            if not clicked:
                continue
            await page.wait_for_timeout(2000)  # wait for Vue re-render
            rows = await _extract_bm_rows(page)

            # Sanity check for DC: first odds value must be < first 1X2 odds
            # (DC covers 2/3 outcomes → always lower than 1X2 single-outcome odds)
            # Retry up to 2 times if the tab didn't switch yet
            if market_cfg["key"] == "DC" and ref_first_odds is not None:
                for _retry in range(2):
                    if rows and rows[0][1] and rows[0][1][0] < ref_first_odds:
                        break  # good data
                    await _click_tab(page, market_cfg["tab"])
                    await page.wait_for_timeout(2000)
                    rows = await _extract_bm_rows(page)
                else:
                    # After retries, still not lower → skip this match's DC
                    if not rows or not rows[0][1] or rows[0][1][0] >= ref_first_odds:
                        continue

            for bm_raw, odds in rows:
                bm = normalise_bookmaker(bm_raw)
                if not bm:
                    continue
                for i, out in enumerate(market_cfg["outcomes"]):
                    if i < len(odds):
                        db_rows.append(_make_row(bm, league, event_name, event_time, market_cfg["key"], out, odds[i], expires, cq_url))

        # --- Over/Under: click tab then expand each threshold row ---
        # centroquote.it shows O/U as an accordion: click "Over/Under" tab to see
        # summary rows ("Over/Under +2.5  13  2.63  1.53"), then click a row to expand
        # individual bookmaker odds below it.
        clicked = await _click_tab(page, "Over/Under")
        if clicked:
            await page.wait_for_timeout(1500)
            for threshold in OVER_UNDER_THRESHOLDS:
                # Click the summary row "Over/Under +{threshold}"
                expanded = await page.evaluate("""
                    (thr) => {
                        const rows = Array.from(document.querySelectorAll('div.flex.h-9'));
                        for (const row of rows) {
                            const t = (row.innerText || row.textContent || '').replace(/\\n/g,' ').trim();
                            if (t.startsWith('Over/Under +' + thr) || t.startsWith('Over/Under ' + thr)) {
                                row.click();
                                return true;
                            }
                        }
                        return false;
                    }
                """, threshold)
                if not expanded:
                    continue
                await page.wait_for_timeout(1500)
                rows = await _extract_bm_rows(page)
                for bm_raw, odds in rows:
                    # Skip the summary threshold rows (e.g. "Over/Under +2.5")
                    if bm_raw.lower().startswith("over/under") or bm_raw.startswith("Over/Under"):
                        continue
                    bm = normalise_bookmaker(bm_raw)
                    if not bm:
                        continue
                    if len(odds) >= 2:
                        db_rows.append(_make_row(bm, league, event_name, event_time, "Over/Under", f"Over {threshold}", odds[0], expires, cq_url))
                        db_rows.append(_make_row(bm, league, event_name, event_time, "Over/Under", f"Under {threshold}", odds[1], expires, cq_url))

    except Exception as exc:
        print(f"    [Match] Error {match_url}: {exc}")
    finally:
        await page.close()

    return db_rows


def _make_row(bm, league, event_name, event_time, market, outcome, odds_val, expires, centroquote_url: str | None = None):
    row = {
        "bookmaker": bm,
        "sport": league["sport"],
        "league": league["name"],
        "event_name": event_name,
        "event_time": event_time,
        "market": market,
        "outcome": outcome,
        "odds": float(odds_val),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires,
    }
    if centroquote_url:
        row["centroquote_url"] = centroquote_url
    return row


async def _extract_bm_rows(page: Page) -> list[tuple[str, list[float]]]:
    """Extract (bookmaker, [odds]) from div.flex.h-9 rows on current page.
    Rows containing ANY struck-through (barrate) odds are skipped entirely."""
    try:
        raw_rows = await page.evaluate("""
            () => {
                const rows = Array.from(document.querySelectorAll('div.flex.h-9'));
                return rows.map(row => {
                    // A row is "struck" if any child element has the Tailwind 'line-through'
                    // class OR an inline text-decoration:line-through style.
                    const hasStruck = Array.from(row.querySelectorAll('*')).some(el => {
                        try {
                            const cls = typeof el.className === 'string' ? el.className : '';
                            if (cls.includes('line-through')) return true;
                            if (el.style && el.style.textDecoration === 'line-through') return true;
                            // Also check computed style for dynamically applied strikethrough
                            const td = window.getComputedStyle(el).textDecorationLine;
                            if (td && td.includes('line-through')) return true;
                        } catch(e) {}
                        return false;
                    });
                    return { text: row.innerText || '', hasStruck };
                });
            }
        """)
        result = []
        for row_data in (raw_rows or []):
            try:
                if row_data.get("hasStruck"):
                    continue  # quota barrata → ignora l'intera riga
                text = row_data.get("text", "")
                bm, odds = parse_row_text(text)
                if bm and len(odds) >= 1:
                    result.append((bm, odds))
            except Exception:
                pass
        return result
    except Exception:
        return []


async def _click_tab(page: Page, tab_text: str) -> bool:
    """Click a market tab by its visible text. Returns True if clicked.
    centroquote.it structure: <a class="flex"><div>Tab Text</div></a>
    We must click the <a> parent, not the inner <div>.
    """
    try:
        # Primary: JS click on the <a> that wraps a div with exact text
        clicked = await page.evaluate(f"""
            (tabText) => {{
                const divs = Array.from(document.querySelectorAll('a div, button div, li div, span div'));
                for (const div of divs) {{
                    if ((div.innerText || div.textContent || '').trim() === tabText) {{
                        const clickable = div.closest('a') || div.closest('button') || div.closest('li') || div;
                        clickable.click();
                        return true;
                    }}
                }}
                return false;
            }}
        """, tab_text)
        if clicked:
            return True

        # Fallback: Playwright locators
        for locator in [
            page.locator(f"a:has-text('{tab_text}')").first,
            page.locator(f"button:has-text('{tab_text}')").first,
            page.locator(f"li:has-text('{tab_text}')").first,
        ]:
            try:
                await locator.click(timeout=2000)
                return True
            except Exception:
                pass
        return False
    except Exception:
        return False


# ──────────────────────────────────────────────
# EXTRACT MATCHES FROM LEAGUE PAGE
# ──────────────────────────────────────────────
_LEAGUE_JS = """
() => {
    const results = [];
    const rows = document.querySelectorAll('.eventRow');
    const itMo = {gen:'01',feb:'02',mar:'03',apr:'04',mag:'05',giu:'06',lug:'07',ago:'08',set:'09',ott:'10',nov:'11',dic:'12'};
    const thisYear = new Date().getFullYear();

    // Extract YYYY-MM-DD from any Italian date string.
    // Handles: "04 Mag 2026" / "Oggi, 01 Mag" / "Domani, 02 Mag" / "Sabato, 03 Mag"
    function extractDatePart(txt) {
        // 1. Full date with year: "04 Mag 2026"
        const m1 = txt.match(/(\\d{1,2})\\s+([A-Za-z]{3,})\\s+(\\d{4})/);
        if (m1) {
            const mo = itMo[m1[2].toLowerCase().slice(0,3)];
            if (mo) return `${m1[3]}-${mo}-${m1[1].padStart(2,'0')}`;
        }
        // 2. "Oggi, 01 Mag" / "Domani, 02 Mag" / "Sabato, 03 Mag" (no year)
        const m2 = txt.match(/(?:Oggi|Domani|Lun|Mar|Mer|Gio|Ven|Sab|Dom)[a-zì]*[,.]?\\s+(\\d{1,2})\\s+([A-Za-z]{3,})/i);
        if (m2) {
            const mo = itMo[m2[2].toLowerCase().slice(0,3)];
            if (mo) return `${thisYear}-${mo}-${m2[1].padStart(2,'0')}`;
        }
        // 3. DD/MM/YYYY
        const m3 = txt.match(/(\\d{1,2})[\\/.]+(\\d{1,2})[\\/.]+(\\d{4})/);
        if (m3) return `${m3[3]}-${m3[2].padStart(2,'0')}-${m3[1].padStart(2,'0')}`;
        return null;
    }

    // Extract HH:MM time from text (avoid matching odds like 2.50)
    function extractTimePart(txt) {
        const m = txt.match(/\\b(\\d{1,2}):(\\d{2})\\b/);
        return m ? `${m[1].padStart(2,'0')}:${m[2]}` : null;
    }

    rows.forEach(row => {
        // Skip live/in-play events
        const rowText = (row.innerText || row.textContent || '');
        const hasLiveBadge = !!(
            row.querySelector('[class*="live"i], [class*="inplay"i], [class*="in-play"i], [class*="inProgress"i], [class*="in-progress"i]') ||
            row.querySelector('[data-testid*="live"i], [data-testid*="inplay"i]')
        );
        const liveTextRe = /\\bLIVE\\b|\\bIn Corso\\b|\\bIn corso\\b|\\bIN CORSO\\b|\\bLive\\b/;
        if (hasLiveBadge || liveTextRe.test(rowText)) return;

        const links = Array.from(row.querySelectorAll('a[href]'));
        const h2hLink = links.find(a => {
            const h = a.getAttribute('href') || '';
            return (h.includes('/h2h/') || h.includes('-v-')) && !h.includes('inplay-odds') && !h.includes('live');
        });
        if (!h2hLink) return;
        const href = h2hLink.getAttribute('href');
        const gameRow = row.querySelector('[data-testid="game-row"]');
        if (!gameRow) return;
        const truncEls = Array.from(gameRow.querySelectorAll('.truncate'));
        const teams = truncEls.map(e => e.innerText.trim()).filter(t => t.length > 1 && t.length < 50);
        if (teams.length < 2) return;

        // ── Extract match datetime ──
        const rowFlat = (row.innerText || row.textContent || '').replace(/\\n/g, ' ');

        // 1. Extract time from this row (HH:MM)
        const justTime = extractTimePart(rowFlat);

        // 2. Try to find the date: first in this row's own text, then walk backwards
        let datePart = extractDatePart(rowFlat);

        // 3. If not found in own text, walk backwards through siblings
        if (!datePart) {
            let el = row.previousElementSibling;
            for (let i = 0; i < 40 && el && !datePart; i++) {
                const t = (el.innerText || el.textContent || '').replace(/\\n/g, ' ');
                datePart = extractDatePart(t);
                el = el.previousElementSibling;
            }
        }
        // 4. Also try parent's previous siblings
        if (!datePart && row.parentElement) {
            let p = row.parentElement.previousElementSibling;
            for (let i = 0; i < 10 && p && !datePart; i++) {
                const t = (p.innerText || p.textContent || '').replace(/\\n/g, ' ');
                datePart = extractDatePart(t);
                p = p.previousElementSibling;
            }
        }

        let timeText = '';
        if (datePart && justTime) {
            timeText = `${datePart}T${justTime}:00`;
        } else if (justTime) {
            // date unknown — fall back to just time, Python will assign today/tomorrow
            timeText = justTime;
        }

        // NOTE: centroquote.it no longer shows per-bookmaker inline rows on league pages.
        // Per-bookmaker odds are only available on match detail pages (scraped in slow mode).
        results.push({ href, home: teams[0], away: teams[1], timeText, bookmakerTexts: [] });
    });
    return results;
}
"""

_MATCH_TIME_JS = """
() => {
    // Extract event datetime from a match detail page.
    // centroquote.it format: "Lunedì, 04 Mag 2026, 20:45" or ISO datetime attribute.
    const selectors = [
        'time[datetime]',
        '[class*="kickoff"]', '[class*="start-time"]', '[class*="match-time"]',
        '[class*="event-date"]', '[class*="event-time"]',
        '[class*="date"]', '[class*="time"]', '[class*="orario"]',
        '[data-testid*="time"]', '[data-testid*="date"]',
        'time',
    ];
    const itMonths = {gen:1,feb:2,mar:3,apr:4,mag:5,giu:6,lug:7,ago:8,set:9,ott:10,nov:11,dic:12};

    for (const sel of selectors) {
        const els = document.querySelectorAll(sel);
        for (const el of els) {
            // Prefer ISO datetime attribute
            const dt = el.getAttribute('datetime');
            if (dt && dt.length > 6) return dt;
            const txt = (el.innerText || el.textContent || '').trim();
            if (!txt || txt.length > 60) continue;
            // Italian full date: "04 Mag 2026, 20:45" or "Lunedì, 04 Mag 2026, 20:45"
            const itM = txt.match(/(\\d{1,2})\\s+([A-Za-z]{3})\\s+(\\d{4})[,\\s]+(\\d{1,2}):(\\d{2})/);
            if (itM) {
                const mo = itMonths[itM[2].toLowerCase()];
                if (mo) return `${itM[3]}-${String(mo).padStart(2,'0')}-${itM[1].padStart(2,'0')}T${itM[4].padStart(2,'0')}:${itM[5]}:00`;
            }
            // DD/MM/YYYY HH:MM
            const dmM = txt.match(/(\\d{1,2})[\\/.](\\d{1,2})[\\/.](\\d{4})\\s+(\\d{1,2}):(\\d{2})/);
            if (dmM) return `${dmM[3]}-${dmM[2].padStart(2,'0')}-${dmM[1].padStart(2,'0')}T${dmM[4].padStart(2,'0')}:${dmM[5]}:00`;
            // Must look like a time/date, not odds
            if (/\\b\\d{1,2}:\\d{2}\\b/.test(txt)) return txt;
        }
    }
    // Body scan for Italian date format
    const body = (document.body.innerText || document.body.textContent || '');
    const itB = body.match(/(\\d{1,2})\\s+(gen|feb|mar|apr|mag|giu|lug|ago|set|ott|nov|dic)\\s+(\\d{4})[,\\s]+(\\d{1,2}):(\\d{2})/i);
    if (itB) {
        const mo = itMonths[itB[2].toLowerCase()];
        if (mo) return `${itB[3]}-${String(mo).padStart(2,'0')}-${itB[1].padStart(2,'0')}T${itB[4].padStart(2,'0')}:${itB[5]}:00`;
    }
    // DD/MM(/YYYY) HH:MM
    const dm = body.match(/\\b(\\d{1,2})[\\/.](\\d{1,2})(?:[\\/.](\\d{2,4}))?\\s+(\\d{1,2}):(\\d{2})\\b/);
    if (dm) return dm[0];
    return '';
}
"""


def _parse_matches_raw(matches_raw: list) -> list[dict]:
    """Parse raw JS output into event dicts; also preserve inline bookmaker texts if present.
    Skips live/in-progress matches (event_time already in the past by >90 min)."""
    events = []
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(minutes=90)  # matches started >90 min ago are likely live/finished
    for m in (matches_raw or []):
        home = m.get("home", "").strip()
        away = m.get("away", "").strip()
        if not home or not away:
            continue
        event_time = _parse_time_best_effort(m.get("timeText", ""))
        # Skip matches that are clearly already live/finished (started >90 min ago)
        try:
            et = datetime.fromisoformat(event_time)
            if et < cutoff:
                continue
        except Exception:
            pass
        events.append({
            "url": m["href"],
            "event_name": f"{home} - {away}",
            "event_time": event_time,
            "bookmaker_texts": m.get("bookmakerTexts", []),  # inline odds from league page
        })
    return events


def _parse_inline_odds(match: dict, league: dict, outcomes: list[str], market_key: str) -> list[dict]:
    """Build DB rows from inline bookmaker texts scraped off the league listing page."""
    rows = []
    expires = (datetime.now(timezone.utc) + timedelta(minutes=CACHE_TTL_MINUTES)).isoformat()
    event_name = match["event_name"]
    event_time = match["event_time"]
    for raw_text in match.get("bookmaker_texts", []):
        bm_raw, odds = parse_row_text(raw_text)
        if not bm_raw or len(odds) < len(outcomes):
            continue
        bm = normalise_bookmaker(bm_raw)
        if not bm:
            continue
        for i, out in enumerate(outcomes):
            rows.append(_make_row(bm, league, event_name, event_time, market_key, out, odds[i], expires))
    return rows


async def _discover_tennis_tournament_urls(context: BrowserContext, gender_keyword: str) -> list[str]:
    """Return all active tennis tournament URLs for a given gender (uomini/donne), excluding doubles."""
    page = await context.new_page()
    try:
        await page.goto(BASE_URL + "/tennis/", wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
        await page.wait_for_timeout(PAGE_WAIT_MS)
        urls = await page.evaluate(f"""
            () => {{
                const kw = '{gender_keyword}';
                return Array.from(document.querySelectorAll('a[href]'))
                    .map(a => a.getAttribute('href'))
                    .filter(h => h && h.startsWith('/tennis/') && h !== '/tennis/' && h.includes(kw) && !h.includes('doppio'))
                    .filter((v, i, a) => a.indexOf(v) === i);
            }}
        """)
        return urls or []
    except Exception as exc:
        print(f"  [Tennis discovery] Error: {exc}")
        return []
    finally:
        await page.close()


async def get_match_urls_from_league(context: BrowserContext, league: dict) -> list[dict]:
    """Open a fresh page per league and return list of {url, event_name, event_time}.
    Retries once if 0 matches are found (handles Vue.js SPA timing issues).
    For tennis with 'discover' key, iterates all matching tournament pages."""
    # Tennis discovery mode: aggregate matches from multiple tournament pages
    if league.get("discover"):
        gender_kw = league["discover"]
        tournament_urls = await _discover_tennis_tournament_urls(context, gender_kw)
        print(f"  [Tennis] {league['name']}: discovered {len(tournament_urls)} tournaments")
        all_events: list[dict] = []
        ok, fail = 0, 0
        for t_url in tournament_urls:
            t_page = await context.new_page()
            try:
                await t_page.goto(BASE_URL + t_url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
                await t_page.wait_for_timeout(2500)
                raw = await t_page.evaluate(_LEAGUE_JS)
                found = _parse_matches_raw(raw)
                all_events.extend(found)
                ok += 1
            except Exception as exc:
                fail += 1
                print(f"    [Tennis] Skip {t_url}: {type(exc).__name__}")
            finally:
                await t_page.close()
            await asyncio.sleep(0.5)
        if fail:
            print(f"  [Tennis] {ok} ok / {fail} failed")
        print(f"  [League] {league['name']}: {len(all_events)} matches found")
        return all_events

    url = BASE_URL + league["url"]
    page = await context.new_page()
    try:
        for attempt in range(3):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                await page.wait_for_timeout(PAGE_WAIT_MS)
                # Aspetta che compaiano le righe evento (Vue.js SPA)
                for _ in range(8):
                    n = await page.locator(".eventRow").count()
                    if n > 0:
                        break
                    await page.wait_for_timeout(1000)
                matches_raw = await page.evaluate(_LEAGUE_JS)
                events = _parse_matches_raw(matches_raw)
                if events or attempt == 2:
                    print(f"  [League] {league['name']}: {len(events)} matches found")
                    return events
                print(f"  [League] {league['name']}: 0 matches (attempt {attempt+1}), retrying...")
                await page.wait_for_timeout(3000)
            except Exception as exc:
                print(f"  [League] {league['name']} attempt {attempt+1} error: {type(exc).__name__}")
                if attempt == 2:
                    return []
                await page.wait_for_timeout(3000)
        return []
    finally:
        await page.close()


def _parse_time_best_effort(raw: str) -> str:
    """Parse a date/time string from centroquote.it into an ISO-8601 UTC string."""
    raw = raw.strip()
    now_utc = datetime.now(timezone.utc)
    fallback = (now_utc + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0).isoformat()
    if not raw:
        return fallback

    # Full datetime formats — centroquote.it shows Italian local time → convert Rome→UTC
    for fmt in ("%d/%m/%Y %H:%M", "%d.%m.%Y %H:%M", "%d/%m/%y %H:%M",
                "%d %b %Y %H:%M", "%d %B %Y %H:%M",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=ROME_TZ).astimezone(timezone.utc).isoformat()
        except ValueError:
            pass

    # ISO with explicit timezone offset (e.g. "2026-05-01T21:00:00+02:00") — use as-is
    try:
        return datetime.fromisoformat(raw).astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        pass

    # DD/MM HH:MM (no year → use current year; treat as Rome time)
    m = re.match(r"(\d{1,2})[/.](\d{1,2})\s+(\d{1,2}):(\d{2})$", raw)
    if m:
        day, month, hour, minute = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        try:
            candidate = datetime(now_utc.year, month, day, hour, minute, tzinfo=ROME_TZ).astimezone(timezone.utc)
            if candidate < now_utc - timedelta(days=1):
                candidate = candidate.replace(year=now_utc.year + 1)
            return candidate.isoformat()
        except ValueError:
            pass

    # HH:MM only (assume today Rome time; if already passed, assume tomorrow)
    m = re.match(r"(\d{1,2}):(\d{2})$", raw)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        try:
            # Build naive local Rome time, then make it tz-aware
            now_rome = datetime.now(ROME_TZ)
            candidate = now_rome.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate < now_rome - timedelta(minutes=30):
                candidate += timedelta(days=1)
            return candidate.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass

    # "DD Mmm YYYY" (Italian/English month abbreviations) — treat as Rome time
    m = re.search(r"(\d{1,2})[/ ](\w+)[/ ](\d{4})", raw)
    if m:
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", fmt).replace(tzinfo=ROME_TZ).astimezone(timezone.utc).isoformat()
            except ValueError:
                pass

    return fallback


# ──────────────────────────────────────────────
# MAIN SCRAPING LOOP
# ──────────────────────────────────────────────
async def scrape_sport(sport_filter: str = "tutti", fast_only: bool = False):
    """
    Scrape centroquote.it.

    fast_only=True  → only 1X2 inline data from league listing pages (fast, ~2 min)
    fast_only=False → full detail pages: 1X2 + DC + BTTS + Over/Under (slow, ~30 min)
    """
    leagues = [lg for lg in LEAGUES if sport_filter == "tutti" or lg["sport"] == sport_filter]
    mode = "FAST(1X2 only)" if fast_only else "FULL(all markets)"

    print(f"\n{'='*60}")
    print(f"CentroQuote Scraper  sport={sport_filter}  mode={mode}  leagues={len(leagues)}")
    print(f"{'='*60}")

    if not fast_only:
        print("\n[DB] Cleaning old rows (>48h)...")
        clean_expired()  # solo dati vecchi di 48h, non la roba appena scaduta

    total_rows = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="it-IT",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        await context.route(
            "**/*.{png,jpg,jpeg,gif,svg,webp,woff,woff2,ttf,otf}",
            lambda route, _: route.abort(),
        )

        for league in leagues:
            print(f"\n[League] {league['name']} ({league['sport']})")

            matches = await get_match_urls_from_league(context, league)
            if not matches:
                print(f"  [!] No matches found")
                continue

            league_rows: list[dict] = []
            sport = league["sport"]
            outcomes_1x2 = ["1", "X", "2"] if sport == "calcio" else ["1", "2"]

            # ── Inline 1X2 from league page (always, both modes) ──
            for match in matches:
                inline_rows = _parse_inline_odds(match, league, outcomes_1x2, "1X2")
                if inline_rows:
                    league_rows.extend(inline_rows)

            if not fast_only:
                # ── Full mode: visit detail pages for DC, BTTS, Over/Under ──
                print(f"  [Detail] Visiting {len(matches)} match pages for all markets")
                for batch_start in range(0, len(matches), CONCURRENCY):
                    batch = matches[batch_start : batch_start + CONCURRENCY]
                    tasks = [
                        scrape_match_page(context, m["url"], m["event_name"], m["event_time"], league)
                        for m in batch
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for res in results:
                        if isinstance(res, list):
                            league_rows.extend(res)
                        elif isinstance(res, Exception):
                            print(f"    [Batch] Error: {res}")

            if league_rows:
                ok = upsert_odds_batch(league_rows)
                status = "✓" if ok else "✗"
                print(f"  [{status}] Saved {len(league_rows)} rows ({len(matches)} matches)")
                total_rows += len(league_rows)
            else:
                print(f"  [!] No odds scraped")

        await browser.close()

    print(f"\n{'='*60}")
    print(f"Done [{mode}]. Total rows upserted: {total_rows}")
    print(f"{'='*60}\n")
    return total_rows


async def main():
    sport_filter = sys.argv[1] if len(sys.argv) > 1 else "tutti"
    await scrape_sport(sport_filter)


if __name__ == "__main__":
    asyncio.run(main())
