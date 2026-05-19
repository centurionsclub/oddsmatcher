"""Bet365 Italy pregame odds scraper — Playwright + network interception.

Bet365 has very heavy anti-bot protection. The strategy is the same
(capture all JSON responses) but the URL structure is different:
Bet365 uses numeric sport/competition codes in the hash fragment.

Known codes (Italian version):
  B1 = calcio, C1 = Serie A, etc.
We try the main sports page and let the API calls reveal the structure.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from oddsmatcher_backend.scraper._base_playwright import BasePlaywrightScraper
from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)

BASE_URL = "https://www.bet365.it"
BOOKMAKER = "Bet365"

# fmt: off
# Bet365 uses a hash-based URL scheme with numeric codes.
# We start from sport-level pages which load all competitions.
LEAGUES: list[tuple[str, str, str]] = [
    # Calcio — page per singola lega (codici comuni Bet365)
    ("Serie A",           "calcio", "/#/IP/B1/C1/D13/E107601003/F2/"),
    ("Serie B",           "calcio", "/#/IP/B1/C1/D13/E107601004/F2/"),
    ("Premier League",    "calcio", "/#/IP/B1/C1/D13/E107601001/F2/"),
    ("La Liga",           "calcio", "/#/IP/B1/C1/D13/E107601002/F2/"),
    ("Bundesliga",        "calcio", "/#/IP/B1/C1/D13/E107601005/F2/"),
    ("Ligue 1",           "calcio", "/#/IP/B1/C1/D13/E107601006/F2/"),
    ("Champions League",  "calcio", "/#/IP/B1/C1/D13/E107601014/F2/"),
    # Fallback: landing page calcio (cattura tutte le leghe in un colpo)
    ("Calcio Landing",    "calcio", "/#/IP/B1/"),
    # Basket
    ("NBA",               "basket", "/#/IP/B18/"),
    # Tennis
    ("ATP",               "tennis", "/#/IP/B13/"),
]
# fmt: on

SIMPLE_MARKET_MAP: dict[str, str] = {
    "Match Result": "1X2", "1X2": "1X2", "Match Betting": "1X2",
    "Moneyline": "1X2", "To Win": "1X2", "Esito Finale": "1X2",
    "Double Chance": "DC", "Doppia Chance": "DC",
    "Both Teams to Score": "BTTS", "Goal/No Goal": "BTTS",
}
UO_SPREADS_WANTED: set[str] = {"1.5", "2.5", "3.5"}
OUTCOME_MAP: dict[str, str] = {
    "1": "1", "Home": "1", "Casa": "1",
    "X": "X", "Draw": "X", "The Draw": "X", "Pareggio": "X",
    "2": "2", "Away": "2", "Ospite": "2",
    "1X": "1X", "X2": "X2", "12": "12",
    "Yes": "Goal", "Goal": "Goal", "GG": "Goal",
    "No": "No Goal", "No Goal": "No Goal", "NG": "No Goal",
    "Over": "Over", "Under": "Under",
}


def _parse_date(s: str) -> str | None:
    if not s:
        return None
    FMTS = ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
            "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"]
    for fmt in FMTS:
        try:
            dt = datetime.strptime(s.strip(), fmt)
            off = 2 if 3 <= dt.month <= 10 else 1
            return dt.replace(tzinfo=timezone(timedelta(hours=off))).astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        return s


def _v(d: dict, *keys: str) -> Any:
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def _odds_val(sel: dict) -> float | None:
    # Bet365 sometimes returns odds as fractional or decimal
    v = _v(sel, "price", "odds", "d", "dec", "decimal", "value", "odd")
    if v is None:
        return None
    # Handle "3/1" fractional format
    if isinstance(v, str) and "/" in v:
        try:
            n, d = v.split("/")
            f = float(n) / float(d) + 1.0
            return f if f > 1.0 else None
        except Exception:
            return None
    try:
        f = float(v)
        return f if f > 1.0 else None
    except (TypeError, ValueError):
        return None


def _label(sel: dict) -> str:
    v = _v(sel, "name", "nam", "N", "description", "selectionName", "participant", "outcome")
    return str(v).strip() if v else ""


def _parse_dom_events(dom_events: list, league_name: str, sport_key: str) -> list[MatchOdds]:
    """Parse events extracted from Bet365 DOM (fallback when WebSocket used)."""
    results: list[MatchOdds] = []
    for ev in dom_events:
        if not isinstance(ev, dict):
            continue
        names = ev.get("names", [])
        odds_raw = ev.get("odds", [])
        time_str = ev.get("time", "")

        if len(names) < 2:
            continue

        home = names[0]
        away = names[-1]
        event_name = f"{home} - {away}"
        event_time = _parse_date(time_str) if time_str else None
        murl = f"{BASE_URL}/#/IP/B1/"

        # Try to map odds to 1X2 (3 odds) or 1X2 without draw (2 odds)
        odds_floats: list[float] = []
        for o in odds_raw:
            try:
                f = float(o)
                if f > 1.0:
                    odds_floats.append(f)
            except (ValueError, TypeError):
                pass

        if len(odds_floats) == 3:
            odds_dict = {"1": odds_floats[0], "X": odds_floats[1], "2": odds_floats[2]}
            results.append(MatchOdds(
                sport=sport_key, league=league_name,
                home_team=home, away_team=away,
                event_name=event_name, event_time=event_time,
                match_url=murl, market="1X2",
                bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
            ))
        elif len(odds_floats) == 2:
            odds_dict = {"1": odds_floats[0], "2": odds_floats[1]}
            results.append(MatchOdds(
                sport=sport_key, league=league_name,
                home_team=home, away_team=away,
                event_name=event_name, event_time=event_time,
                match_url=murl, market="1X2",
                bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
            ))
    return results


def _parse_events(events: list, league_name: str, sport_key: str) -> list[MatchOdds]:
    results: list[MatchOdds] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        name_raw = _v(ev, "name", "nam", "N", "eventName", "eventDescription", "fixture") or ""
        name = re.sub(r"\s+v\s+", " - ", str(name_raw)).strip()
        if not name:
            continue
        raw_time = _v(ev, "startTime", "startDate", "eventDate", "date", "dtm", "D") or ""
        etime = _parse_date(str(raw_time)) if raw_time else None
        murl = f"{BASE_URL}/#/IP/B1/"
        parts = name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else name
        away = parts[1].strip() if len(parts) == 2 else ""

        mkts_raw = _v(ev, "markets", "market", "Markets", "bets", "mkt") or []
        if isinstance(mkts_raw, dict):
            mkts_raw = list(mkts_raw.values())

        for mkt in mkts_raw:
            if not isinstance(mkt, dict):
                continue
            mname = str(_v(mkt, "name", "nam", "N", "marketName", "description", "betType") or "").strip()
            canonical = SIMPLE_MARKET_MAP.get(mname)
            sels_raw = _v(mkt, "selections", "sel", "outcomes", "runners", "prices", "Prices") or []
            if isinstance(sels_raw, dict):
                sels_raw = list(sels_raw.values())

            if canonical:
                odds_dict = {OUTCOME_MAP.get(_label(s), _label(s)): v
                             for s in sels_raw if isinstance(s, dict) and (v := _odds_val(s)) and _label(s)}
                if odds_dict:
                    results.append(MatchOdds(sport=sport_key, league=league_name, home_team=home, away_team=away,
                                             event_name=name, event_time=etime, match_url=murl, market=canonical,
                                             bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}]))
                continue

            if any(kw in mname for kw in ("Over/Under", "Total Goals", "Goals Over", "Over Under", "Gol")):
                sp_m = re.search(r"(\d+[.,]\d+)", mname)
                if sp_m:
                    sp = sp_m.group(1).replace(",", ".")
                    if sp in UO_SPREADS_WANTED:
                        SIDE = {"Over": "Over", "Under": "Under"}
                        odds_dict = {}
                        for s in sels_raw:
                            if not isinstance(s, dict):
                                continue
                            side = SIDE.get(_label(s))
                            v = _odds_val(s)
                            if side and v:
                                odds_dict[f"{side} {sp}"] = v
                        if odds_dict:
                            results.append(MatchOdds(sport=sport_key, league=league_name, home_team=home, away_team=away,
                                                     event_name=name, event_time=etime, match_url=murl,
                                                     market=f"Over/Under {sp}",
                                                     bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}]))
    return results


class Bet365Scraper(BasePlaywrightScraper):
    bookmaker_name = BOOKMAKER
    base_url = BASE_URL
    warmup_path = "/#/HO/"  # Bet365 homepage — hash routing, root alone has no content
    leagues = LEAGUES

    def parse_response(self, url: str, body: Any, league_name: str, sport_key: str) -> list[MatchOdds]:
        """Try JSON interception (rarely fires on Bet365 — they use WebSocket)."""
        try:
            if isinstance(body, dict):
                for key in ("events", "data", "fixtures", "matches", "fixtureList",
                            "eventList", "matchList", "competitions", "cl"):
                    val = body.get(key)
                    if isinstance(val, list) and val:
                        rows = _parse_events(val, league_name, sport_key)
                        if rows:
                            return rows
                    if isinstance(val, dict):
                        for k2 in ("events", "fixtures", "matches", "ev"):
                            v2 = val.get(k2)
                            if isinstance(v2, list) and v2:
                                rows = _parse_events(v2, league_name, sport_key)
                                if rows:
                                    return rows
            if isinstance(body, list) and body and isinstance(body[0], dict):
                return _parse_events(body, league_name, sport_key)
        except Exception as e:
            logger.debug("[Bet365] parse error for %s: %s", url, e)
        return []

    async def _scrape_league(
        self,
        league_name: str,
        sport_key: str,
        page_path: str,
    ) -> list[MatchOdds]:
        """Override: first try JSON interception, then fall back to DOM scraping.

        Bet365 delivers odds via WebSocket (binary), so the base interceptor
        captures 0 JSON responses. We fall back to reading the rendered DOM.
        """
        # Step 1: let base handle navigation + response interception
        results = await super()._scrape_league(league_name, sport_key, page_path)
        if results:
            return results

        # Step 2: DOM scraping fallback (Bet365 uses WebSocket for odds)
        assert self._page is not None
        logger.info("[Bet365] %s: 0 JSON captured → trying DOM extraction", league_name)

        # Wait for WebSocket data to populate the DOM
        # Try to wait for a known Bet365 odds element to appear
        for ws_selector in [
            "[class*='gl-MarketGroup']",
            "[class*='Participant_Name']",
            "[class*='OddsLabel']",
            "[class*='couponRow']",
            "[class*='EventRow']",
        ]:
            try:
                await self._page.wait_for_selector(ws_selector, timeout=8000)
                logger.info("[Bet365] %s: found selector %s", league_name, ws_selector)
                break
            except Exception:
                pass

        await self._page.wait_for_timeout(2000)

        try:
            dom_data = await self._page.evaluate("""
                () => {
                    // Collect all CSS classes for diagnostics
                    const relClasses = new Set();
                    document.querySelectorAll('[class]').forEach(el => {
                        String(el.className).split(' ').forEach(c => {
                            if (c && /Market|Participant|Coupon|Event|Fixture|gl-|sl-|sc-|cl-|OddsLabel|Price/i.test(c))
                                relClasses.add(c);
                        });
                    });

                    // Try known Bet365 selectors (tried in priority order)
                    const SELECTORS = [
                        '.gl-MarketGroup_Wrapper',
                        '.gl-MarketGroup',
                        '[class*="MarketGroup_Wrapper"]',
                        '[class*="MarketColumnHeader"]',
                        '[class*="couponRow"]',
                        '[class*="EventRow"]',
                        '[class*="Fixture"]',
                    ];
                    let rows = [];
                    let usedSel = '';
                    for (const sel of SELECTORS) {
                        const found = document.querySelectorAll(sel);
                        if (found.length) { rows = Array.from(found); usedSel = sel; break; }
                    }

                    const events = rows.map(row => {
                        const names = Array.from(
                            row.querySelectorAll('[class*="Participant_Name"],[class*="participantName"],[class*="TeamName"]')
                        ).map(el => el.textContent.trim()).filter(Boolean);

                        const odds = Array.from(
                            row.querySelectorAll('[class*="OddsLabel"],[class*="oddsLabel"],[class*="Price"],[class*="price"]')
                        ).map(el => el.textContent.trim()).filter(Boolean);

                        const timeEl = row.querySelector('[class*="Time"],[class*="time"],[class*="StartTime"],[class*="date"]');
                        return { names, odds, time: timeEl ? timeEl.textContent.trim() : '' };
                    });

                    return {
                        rowCount: rows.length,
                        usedSelector: usedSel,
                        events: events.slice(0, 5),
                        relevantClasses: Array.from(relClasses).sort().slice(0, 80),
                        bodySnippet: document.body.innerHTML.substring(0, 5000),
                    };
                }
            """)

            if isinstance(dom_data, dict):
                logger.info("[Bet365] %s DOM: rowCount=%s selector=%s classes=%s",
                            league_name,
                            dom_data.get("rowCount"),
                            dom_data.get("usedSelector"),
                            dom_data.get("relevantClasses", [])[:30])
                logger.info("[Bet365] %s DOM events preview: %s",
                            league_name, dom_data.get("events", []))
                logger.info("[Bet365] %s body snippet: %.4000s",
                            league_name, dom_data.get("bodySnippet", ""))
                if dom_data.get("rowCount", 0) > 0:
                    return _parse_dom_events(dom_data.get("events", []), league_name, sport_key)

        except Exception as exc:
            logger.warning("[Bet365] %s DOM extraction failed: %s", league_name, exc)

        return []
