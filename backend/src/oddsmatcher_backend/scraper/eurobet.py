"""Eurobet Italy pregame odds scraper — web.eurobet.it/webeb/sport legacy API.

www.eurobet.it is fully protected by Cloudflare Turnstile (blocks Playwright).
web.eurobet.it/webeb/sport is the legacy JBoss/WebEb backend that is NOT
behind Cloudflare — simple httpx GET requests return ALL matches for any league.

Verified working:
  GET https://web.eurobet.it/webeb/sport?action=scommesseV2_meeting_comm
      &meetingsParam=21&chooseSport=1&betTypesParam=3&betTypeGroupSel=1&showSplash=0
  → HTML with all 10 Serie A matches (1X2 odds in placeBet() onMouseUp attrs)
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone

import httpx

from oddsmatcher_backend.scraper.models import MatchOdds

logger = logging.getLogger(__name__)

BOOKMAKER = "Eurobet"
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

# (league_name, chooseSport, meetingsParam)
# chooseSport: 1=calcio, 2=basket, 3=tennis
# meetingsParam: league/meeting ID
WEBEB_MEETINGS: dict[str, list[tuple[str, int, int]]] = {
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
    "tennis": [
        ("Roland Garros", 3, 145),
    ],
    "basket": [
        ("NBA",            2, 12),
        ("Eurolega",       2, 9),
        ("Serie A Basket", 2, 3),
    ],
}

# betTypesParam → market label used internally
BET_TYPES: list[tuple[int, str]] = [
    (3,      "1X2"),
    (200018, "DC"),
    (18,     "BTTS"),
    (7989,   "OU"),
]


def _webeb_url(choose_sport: int, meetings_param: int, bet_types_param: int) -> str:
    return (
        f"{WEBEB_URL}?action=scommesseV2_meeting_comm"
        f"&meetingsParam={meetings_param}"
        f"&chooseSport={choose_sport}"
        f"&betTypesParam={bet_types_param}"
        f"&betTypeGroupSel=1&showSplash=0"
    )


def _parse_italy_date(date_str: str, time_str: str = "") -> str | None:
    """Parse 'DD/MM/YYYY' + optional 'HH:MM' into UTC ISO string."""
    try:
        s = f"{date_str.strip()} {time_str.strip()}".strip()
        fmt = "%d/%m/%Y %H:%M" if time_str.strip() else "%d/%m/%Y"
        dt = datetime.strptime(s, fmt)
        off = 2 if 3 <= dt.month <= 10 else 1  # Italy: CEST/CET
        return dt.replace(tzinfo=timezone(timedelta(hours=off))).astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def _extract_event_times(html: str) -> dict[str, str]:
    """Build map of event_code → ISO datetime from HTML blocks."""
    # Each event row has:
    #   <div class="box_container_scommesse_info..."><h4>DD/MM</h4><p>HH:MM</p></div>
    #   <div class="box_container_scommesse_nomeEvento...">
    #       <a href="javascript:loadSingleEventPage(CONV, EVENT_CODE, 0)">Name</a>
    # We extract parallel lists of (date, time) and event_code and zip them.
    date_times = re.findall(
        r'class="box_container_scommesse_info[^"]*"[^>]*>.*?'
        r'<h4>\s*(\d+/\d+)\s*</h4>\s*<p>\s*(\d+:\d+)',
        html, re.DOTALL,
    )
    event_codes = re.findall(
        r'loadSingleEventPage\s*\(\s*\d+\s*,\s*(\d+)\s*,',
        html,
    )
    result: dict[str, str] = {}
    if len(date_times) == len(event_codes) and date_times:
        current_year = datetime.now().year
        for (date_part, time_part), code in zip(date_times, event_codes):
            full_date = f"{date_part}/{current_year}"
            parsed = _parse_italy_date(full_date, time_part)
            if parsed:
                result[code] = parsed
    return result


def _parse_webeb_html(
    html: str,
    league_name: str,
    sport_key: str,
    bet_label: str,
) -> list[MatchOdds]:
    """Parse onMouseUp placeBet() calls from a single webeb/sport response.

    placeBet() argument positions (0-indexed, all single-quoted strings):
      [0]  convCode        (e.g. '15016')
      [1]  ?               ('1')
      [2]  progCode        (booking code, e.g. '36211')
      [3-7] internal flags
      [8]  betCode         (e.g. '3', '200018', '18', '7989')
      [9]  betName         (e.g. '1X2', 'Doppia Chance', 'Goal/No Goal', 'U/O Goal( +2.5)')
      [10] eventCode       (meeting event ID, e.g. '256')
      [11] eventName       (e.g. 'Fiorentina - Atalanta')
      [12] '0'
      [13] pos             ('1', '2', '3' — bet position)
      [14] outcome         (e.g. '1', 'X', '2', 'Under', 'Over', 'Goal', 'Nogoal')
      [15] decimalOdds     (e.g. '2.55')
      [16] odds×100        (e.g. '255')
      [17] '1'
      [18] '30'
      [19] spread          (e.g. '0000000250' for 2.50, '0' for non-OU markets)
      [20] meetingId       (e.g. '21')
      [21] date            (e.g. '22/05/2026')
    """
    bets = re.findall(r'onMouseUp="placeBet\(([^"]+)\)"', html)
    if not bets:
        logger.info("[Eurobet] %s / %s: 0 placeBet calls in HTML (len=%d)",
                    league_name, bet_label, len(html))
        return []

    logger.info("[Eurobet] %s / %s: %d placeBet calls", league_name, bet_label, len(bets))

    # Extract event times (date + time) keyed by eventCode
    event_times = _extract_event_times(html)

    # Accumulate: (event_name, market_key) → {home, away, event_time, odds}
    market_data: dict[tuple[str, str], dict] = {}

    for bet_str in bets:
        args = re.findall(r"'([^']*)'", bet_str)
        if len(args) < 22:
            continue

        bet_code  = args[8]   # e.g. "3"
        bet_name  = args[9]   # e.g. "1X2" / "U/O Goal( +2.5)"
        ev_code   = args[10]  # meeting event code (for time lookup)
        ev_name   = args[11]  # e.g. "Fiorentina - Atalanta"
        outcome   = args[14]  # e.g. "1", "X", "2", "Under", "Over", "Goal", "Nogoal"
        odds_str  = args[15]  # e.g. "2.55"
        spread_raw = args[19] # e.g. "0000000250"
        date_str  = args[21]  # e.g. "22/05/2026"

        if not ev_name or not odds_str:
            continue

        # Parse odds value
        try:
            odds_val = float(odds_str)
        except (ValueError, TypeError):
            continue
        if odds_val <= 1.0:
            continue

        # Determine market key and map outcome label
        bn_lower = bet_name.lower()
        if bet_code == "3" or "1x2" in bn_lower or "1 x 2" in bn_lower:
            market_key = "1X2"
            outcome_mapped = {"1": "1", "X": "X", "2": "2"}.get(outcome, outcome)

        elif bet_code == "200018" or "doppia" in bn_lower or "double" in bn_lower:
            market_key = "DC"
            outcome_mapped = {"1X": "1X", "X2": "X2", "12": "12"}.get(outcome, outcome)

        elif bet_code == "18" or "goal/no goal" in bn_lower or "goal no goal" in bn_lower:
            market_key = "BTTS"
            ol = outcome.lower()
            if ol in ("goal", "si", "sì", "yes", "gg"):
                outcome_mapped = "Goal"
            elif ol in ("nogoal", "no goal", "no", "ng"):
                outcome_mapped = "No Goal"
            else:
                outcome_mapped = outcome

        elif bet_code == "7989" or "u/o" in bn_lower or "over" in bn_lower:
            # Extract spread from betName e.g. "U/O Goal( +2.5)" → "2.5"
            sp_m = re.search(r"(\d+[.,]\d+)", bet_name)
            if sp_m:
                spread = sp_m.group(1).replace(",", ".")
            else:
                # Decode from spread_raw: "0000000250" → 250 → /100 → 2.5
                try:
                    sp_int = int(spread_raw)
                    spread = f"{sp_int / 100:.1f}"
                except (ValueError, TypeError):
                    continue
            if spread not in {"0.5", "1.5", "2.5", "3.5", "4.5", "5.5"}:
                continue
            market_key = f"Over/Under {spread}"
            ol = outcome.lower()
            if ol in ("over", "o"):
                outcome_mapped = "Over"
            elif ol in ("under", "u"):
                outcome_mapped = "Under"
            else:
                outcome_mapped = outcome

        else:
            # Unknown bet type — skip
            continue

        # Parse team names
        parts = ev_name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else ev_name
        away = parts[1].strip() if len(parts) == 2 else ""

        # Event time: prefer extracted time, fall back to date-only
        ev_time = event_times.get(ev_code) or _parse_italy_date(date_str)

        key = (ev_name, market_key)
        if key not in market_data:
            market_data[key] = {
                "home": home,
                "away": away,
                "event_time": ev_time,
                "odds": {},
            }
        market_data[key]["odds"][outcome_mapped] = odds_val

    results: list[MatchOdds] = []
    for (ev_name, market_key), data in market_data.items():
        odds = data["odds"]
        if not odds:
            continue
        # Require at least 2 outcomes for BTTS; at least 1 for others
        if market_key == "BTTS" and len(odds) < 2:
            continue
        results.append(MatchOdds(
            sport=sport_key,
            league=league_name,
            home_team=data["home"],
            away_team=data["away"],
            event_name=ev_name,
            event_time=data["event_time"],
            match_url="https://www.eurobet.it/it/scommesse/",
            market=market_key,
            bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds}],
        ))

    return results


class EurobetScraper:
    """Eurobet scraper — httpx to web.eurobet.it/webeb/sport (no Cloudflare).

    Fetches all leagues by calling the legacy JBoss API directly.
    Each league requires 4 calls (one per bet type: 1X2, DC, BTTS, O/U).
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

        all_results: list[MatchOdds] = []

        async with httpx.AsyncClient(
            headers=_HEADERS,
            timeout=20,
            follow_redirects=True,
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
                            logger.info(
                                "[Eurobet] %s / %s: GET %s → %d (len=%d)",
                                league_name, bet_label, url[:120],
                                resp.status_code, len(resp.text),
                            )
                            if resp.status_code != 200:
                                continue
                            rows = _parse_webeb_html(
                                resp.text, league_name, sport_key, bet_label
                            )
                            logger.info(
                                "[Eurobet] %s / %s: %d rows",
                                league_name, bet_label, len(rows),
                            )
                            league_rows.extend(rows)
                        except Exception as exc:
                            logger.error(
                                "[Eurobet] %s / %s error: %s",
                                league_name, bet_label, exc,
                            )

                    n_events = len({r.event_name for r in league_rows})
                    logger.info(
                        "[Eurobet] %s: %d events, %d rows total",
                        league_name, n_events, len(league_rows),
                    )
                    all_results.extend(league_rows)

        # Deduplicate by (event_name, market)
        seen: dict[tuple[str, str], MatchOdds] = {}
        for r in all_results:
            seen[(r.event_name, r.market)] = r
        deduped = list(seen.values())

        n_events = len({r.event_name for r in deduped})
        logger.info("[Eurobet] Total: %d events, %d rows", n_events, len(deduped))
        return deduped
