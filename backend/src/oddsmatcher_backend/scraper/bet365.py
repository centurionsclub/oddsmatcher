"""Bet365 Italy pregame odds scraper — Playwright + DOM extraction.

Bet365 delivers odds via binary WebSocket (obfuscated protocol), so network
interception captures nothing useful. Strategy:
  1. Navigate to the PRE-MATCH all-competitions page (/#/AC/B<N>/).
     NOTE: /#/IP/ is In-Play (live), /#/AC/ is pre-match.
  2. Wait up to 45s for the betting coupon to render in the DOM.
  3. Extract innerText of the page, parse with regex.

The rendered innerText of a Bet365 pre-match page looks like:
  "Serie A\n21 Mag  21:00\nInter Milan  Juventus  1.75  3.40  4.25\n..."

We parse that text to extract events + 1X2 odds.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from oddsmatcher_backend.scraper._base_playwright import BasePlaywrightScraper
from oddsmatcher_backend.scraper.models import MatchOdds

logger = logging.getLogger(__name__)

BASE_URL = "https://www.bet365.it"
BOOKMAKER = "Bet365"

# fmt: off
# PRE-MATCH sport pages (/#/AC/ = All Competitions, pre-match)
# /#/IP/ is In-Play (live betting) — wrong for pre-match odds!
LEAGUES: list[tuple[str, str, str]] = [
    ("Calcio",  "calcio", "/#/AC/B1/"),
    ("Basket",  "basket", "/#/AC/B18/"),
    ("Tennis",  "tennis", "/#/AC/B13/"),
]
# fmt: on

OUTCOME_MAP: dict[str, str] = {
    "1": "1", "Home": "1", "Casa": "1",
    "X": "X", "Draw": "X", "Pareggio": "X",
    "2": "2", "Away": "2", "Ospite": "2",
}

_ODDS_RE = re.compile(r"^([1-9]\d?(?:\.\d{1,3})?)$")
_TIME_RE = re.compile(r"^\d{1,2}\s+\w{3}\s+\d{1,2}:\d{2}$|^\d{2}/\d{2}\s+\d{2}:\d{2}$|^\d{2}:\d{2}$")


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


def _is_odds(text: str) -> bool:
    if not _ODDS_RE.match(text):
        return False
    try:
        v = float(text)
        return 1.01 <= v <= 100.0
    except ValueError:
        return False


def _parse_innertext(text: str, league_name: str, sport_key: str) -> list[MatchOdds]:
    """Parse Bet365 page innerText into MatchOdds.

    Bet365 pre-match pages render roughly as:
      Competition Name
      DD MMM HH:MM
      Team A  Team B  1.75  3.40  4.25
      ...
    Lines may vary but odds always follow team names as decimal numbers.
    """
    results: list[MatchOdds] = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    i = 0
    while i < len(lines):
        line = lines[i]
        tokens = re.split(r"\s{2,}|\t", line)
        tokens = [t.strip() for t in tokens if t.strip()]

        # Collect all odds-like tokens from this line
        odds_vals: list[float] = []
        name_tokens: list[str] = []
        for t in tokens:
            if _is_odds(t):
                odds_vals.append(float(t))
            elif len(t) > 1 and not re.match(r"^\d+$", t):
                name_tokens.append(t)

        # Need exactly 2 or 3 odds (1X2 or head-to-head) and ≥1 name fragment
        if len(odds_vals) in (2, 3) and name_tokens:
            # Build the event name from non-odds tokens on the same line
            # Bet365 sometimes puts "Team A  Team B  1.75  3.40  4.25" on one line
            # or "Team A" on one line and "Team B" on the next
            raw_name = " ".join(name_tokens)
            # Try splitting on " - " or " v " or middle of name list
            if " - " in raw_name:
                parts = raw_name.split(" - ", 1)
                home, away = parts[0].strip(), parts[1].strip()
            elif " v " in raw_name:
                parts = raw_name.split(" v ", 1)
                home, away = parts[0].strip(), parts[1].strip()
            elif len(name_tokens) >= 2:
                # Split name_tokens in half
                mid = len(name_tokens) // 2
                home = " ".join(name_tokens[:mid]).strip()
                away = " ".join(name_tokens[mid:]).strip()
            else:
                home = raw_name
                away = ""

            # Skip if names look like competition headings (all uppercase, no spaces)
            if home and (away or sport_key == "tennis"):
                if len(odds_vals) == 3:
                    odds_dict = {"1": odds_vals[0], "X": odds_vals[1], "2": odds_vals[2]}
                else:
                    odds_dict = {"1": odds_vals[0], "2": odds_vals[1]}

                event_name = f"{home} - {away}" if away else home
                results.append(MatchOdds(
                    sport=sport_key,
                    league=league_name,
                    home_team=home,
                    away_team=away,
                    event_name=event_name,
                    event_time=None,
                    match_url=f"{BASE_URL}/#/AC/",
                    market="1X2",
                    bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
                ))

        i += 1

    return results


def _parse_events(events: list, league_name: str, sport_key: str) -> list[MatchOdds]:
    """Fallback JSON parser (rarely fires on Bet365 — they use WebSocket)."""
    results: list[MatchOdds] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        name_raw = ev.get("name") or ev.get("nam") or ev.get("N") or ev.get("eventName") or ""
        name = re.sub(r"\s+v\s+", " - ", str(name_raw)).strip()
        if not name:
            continue
        parts = name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else name
        away = parts[1].strip() if len(parts) == 2 else ""
        results.append(MatchOdds(
            sport=sport_key, league=league_name, home_team=home, away_team=away,
            event_name=name, event_time=None, match_url=f"{BASE_URL}/#/AC/",
            market="1X2", bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": {}}],
        ))
    return results


class Bet365Scraper(BasePlaywrightScraper):
    bookmaker_name = BOOKMAKER
    base_url = BASE_URL
    warmup_path = "/#/HO/"
    leagues = LEAGUES

    def parse_response(self, url: str, body: Any, league_name: str, sport_key: str) -> list[MatchOdds]:
        """Try JSON interception (rarely fires on Bet365 — they use WebSocket)."""
        try:
            if isinstance(body, dict):
                for key in ("events", "data", "fixtures", "matches", "eventList", "cl"):
                    val = body.get(key)
                    if isinstance(val, list) and val:
                        rows = _parse_events(val, league_name, sport_key)
                        if rows:
                            logger.info("[Bet365] JSON hit: %s → %d rows", key, len(rows))
                            return rows
            if isinstance(body, list) and body and isinstance(body[0], dict):
                return _parse_events(body, league_name, sport_key)
        except Exception as e:
            logger.debug("[Bet365] JSON parse error for %s: %s", url, e)
        return []

    async def _start(self) -> None:
        """Override: warm up, accept cookie consent."""
        await super()._start()
        assert self._page is not None

        # Dismiss cookie/GDPR consent if shown
        for sel in [
            "button:has-text('Accetta')", "button:has-text('Accept')",
            "#onetrust-accept-btn-handler", ".ccm-OverlayAccept",
        ]:
            try:
                await self._page.click(sel, timeout=3_000)
                logger.info("[Bet365] Cookie consent clicked: %s", sel)
                await self._page.wait_for_timeout(1_500)
                break
            except Exception:
                pass

    async def _scrape_league(
        self,
        league_name: str,
        sport_key: str,
        page_path: str,
    ) -> list[MatchOdds]:
        """Navigate to pre-match page, wait for odds, extract from innerText.

        Bet365 uses binary WebSocket for odds delivery. JSON interception
        never fires. We wait up to 45s for the betting coupon to render in
        the DOM, then parse the page's innerText with regex.
        """
        # Step 1: try JSON interception (base class does the navigation + capture)
        results = await super()._scrape_league(league_name, sport_key, page_path)
        if results:
            return results

        assert self._page is not None
        logger.info("[Bet365] %s: waiting up to 45s for coupon to render…", league_name)

        # Step 2: wait until multiple odds values appear in the page text
        try:
            await self._page.wait_for_function(
                r"""() => {
                    const t = document.body.innerText || '';
                    // Count decimal odds-looking numbers (1.10 – 50.00)
                    const m = t.match(/\b[1-9]\d?(?:\.\d{2})\b/g) || [];
                    // Need at least 6 distinct odd values to be sure it's a coupon
                    return m.length >= 6;
                }""",
                timeout=45_000,
            )
            logger.info("[Bet365] %s: coupon rendered — extracting", league_name)
        except Exception:
            logger.info("[Bet365] %s: 45s timeout — attempting extraction anyway", league_name)

        await self._page.wait_for_timeout(1_000)

        # Step 3: grab innerText and parse
        try:
            page_data = await self._page.evaluate(r"""
                () => {
                    const text = document.body.innerText || '';

                    // Collect odds elements for structural approach
                    const oddsRe = /^[1-9]\d?(?:\.\d{1,3})?$/;
                    const leafEls = Array.from(document.querySelectorAll('div,span,button'))
                        .filter(el =>
                            el.children.length === 0 &&
                            oddsRe.test((el.textContent || '').trim()) &&
                            parseFloat((el.textContent || '').trim()) > 1.0
                        );

                    // Crawl up to find fixture row containers
                    const seen = new Set();
                    const rows = [];
                    for (const el of leafEls) {
                        let node = el;
                        for (let d = 0; d < 8; d++) {
                            if (!node.parentElement || node === document.body) break;
                            node = node.parentElement;
                        }
                        if (!seen.has(node) && node !== document.body) {
                            seen.add(node);
                            rows.push(node);
                        }
                    }

                    const events = rows.slice(0, 50).map(row => {
                        const texts = Array.from(row.querySelectorAll('*'))
                            .filter(e => e.children.length === 0)
                            .map(e => (e.textContent || '').trim())
                            .filter(t => t.length > 0);
                        const odds = texts.filter(t =>
                            oddsRe.test(t) && parseFloat(t) > 1.0);
                        const names = texts.filter(t =>
                            !oddsRe.test(t) && t.length >= 2 && t.length <= 80 &&
                            !/^\d+$/.test(t) && !/^[\d/:]+$/.test(t));
                        return { names, odds };
                    }).filter(e => e.odds.length >= 2 && e.names.length >= 1);

                    return {
                        innerText: text.substring(0, 8000),
                        domEvents: events,
                        oddsElCount: leafEls.length,
                    };
                }
            """)

            inner = page_data.get("innerText", "") if isinstance(page_data, dict) else ""
            dom_events = page_data.get("domEvents", []) if isinstance(page_data, dict) else []
            odds_count = page_data.get("oddsElCount", 0) if isinstance(page_data, dict) else 0

            logger.info("[Bet365] %s: oddsEls=%d domEvents=%d innerText_len=%d",
                        league_name, odds_count, len(dom_events), len(inner))
            logger.info("[Bet365] %s innerText[:3000]: %s", league_name, inner[:3000])
            logger.info("[Bet365] %s domEvents (first 5): %s", league_name, dom_events[:5])

            # Try DOM structural approach first (more reliable)
            dom_results = _parse_dom_structured(dom_events, league_name, sport_key)
            if dom_results:
                logger.info("[Bet365] %s: %d rows from DOM structural", league_name, len(dom_results))
                return dom_results

            # Fall back to innerText parsing
            if inner:
                text_results = _parse_innertext(inner, league_name, sport_key)
                if text_results:
                    logger.info("[Bet365] %s: %d rows from innerText", league_name, len(text_results))
                    return text_results

            logger.warning("[Bet365] %s: no events extracted", league_name)

        except Exception as exc:
            logger.warning("[Bet365] %s extraction failed: %s", league_name, exc)

        return []


def _parse_dom_structured(dom_events: list, league_name: str, sport_key: str) -> list[MatchOdds]:
    """Parse events from DOM structural extraction."""
    results: list[MatchOdds] = []
    for ev in dom_events:
        if not isinstance(ev, dict):
            continue
        names = ev.get("names", [])
        odds_raw = ev.get("odds", [])

        odds_vals: list[float] = []
        for o in odds_raw:
            try:
                f = float(o)
                if 1.01 <= f <= 100.0:
                    odds_vals.append(f)
            except (ValueError, TypeError):
                pass

        if len(odds_vals) < 2:
            continue

        # Build team names from name tokens
        # Filter out competition names (all caps, short) and times
        filtered = [n for n in names if len(n) >= 2 and not n.isupper() or len(n) > 6]
        if not filtered:
            filtered = names

        if len(filtered) >= 2:
            home = filtered[0]
            away = filtered[-1] if filtered[-1] != filtered[0] else filtered[1] if len(filtered) > 1 else ""
        elif filtered:
            home = filtered[0]
            away = ""
        else:
            continue

        if not home:
            continue

        event_name = f"{home} - {away}" if away else home

        if len(odds_vals) == 3:
            odds_dict = {"1": odds_vals[0], "X": odds_vals[1], "2": odds_vals[2]}
        else:
            odds_dict = {"1": odds_vals[0], "2": odds_vals[1]}

        results.append(MatchOdds(
            sport=sport_key, league=league_name,
            home_team=home, away_team=away,
            event_name=event_name, event_time=None,
            match_url=f"{BASE_URL}/#/AC/",
            market="1X2",
            bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_dict}],
        ))
    return results
