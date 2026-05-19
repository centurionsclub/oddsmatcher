"""Snai Italy pregame odds scraper.

Strategy: Playwright browser to get Akamai session cookies from www.snai.it,
then call betting-snai.flutterseatech.it REST API with those cookies.

API base: https://betting-snai.flutterseatech.it/api/lettura-palinsesto-sport
Key endpoints:
  GET /alberaturaPrematch          → tournament tree (sport → country → tournament IDs)
  GET /palinsesto/prematch/...     → events with odds for a specific tournament
"""

import json as _json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from playwright.async_api import async_playwright

from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)

BASE_URL = "https://www.snai.it"
API_BASE = "https://betting-snai.flutterseatech.it/api/lettura-palinsesto-sport"
BOOKMAKER = "Snai"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Sport names in Snai → our sport key
SPORT_MAP = {
    "Calcio": "calcio",
    "CALCIO": "calcio",
    "calcio": "calcio",
    "Tennis": "tennis",
    "TENNIS": "tennis",
    "Basket": "basket",
    "BASKET": "basket",
    "Pallacanestro": "basket",
}

# Leagues to include (by name in Snai's system)
WANTED_LEAGUES = {
    "calcio": {
        "Serie A", "Serie B", "Premier League", "La Liga", "Primera Division",
        "Bundesliga", "Ligue 1", "Champions League", "Europa League",
        "Conference League", "Serie A Italia",
    },
    "tennis": {
        "Roland Garros", "Wimbledon", "US Open", "Australian Open",
        "Amburgo", "Ginevra", "Rabat", "Strasburgo",
    },
    "basket": {
        "NBA", "Serie A", "Serie A Basket", "Eurolega",
    },
}


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
    """Parse Snai API event response (format TBD — logs full structure on first run)."""
    results: list[MatchOdds] = []
    if not data:
        return results

    # Normalise to list of events
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

        # Event name
        name_raw = (
            ev.get("descrizione") or ev.get("description") or
            ev.get("eventDescription") or ev.get("name") or
            ev.get("da") or ev.get("en") or ""
        )
        name = re.sub(r"\s+[-–v]\s+", " - ", str(name_raw)).strip()
        if not name:
            continue

        # Event time
        time_raw = (
            ev.get("dataOra") or ev.get("data") or ev.get("startTime") or
            ev.get("startDate") or ev.get("eventDate") or ev.get("ts") or ""
        )
        event_time = _parse_date(str(time_raw)) if time_raw else None

        match_url = f"{BASE_URL}/scommesse/"
        parts = name.split(" - ", 1)
        home = parts[0].strip() if len(parts) == 2 else name
        away = parts[1].strip() if len(parts) == 2 else ""

        # Markets
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

            # 1X2 detection
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

            # Double Chance
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

            # Over/Under
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


class SnaiScraper:
    """Snai scraper: Playwright for session cookies + direct API calls to flutterseatech.it."""

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
        results: list[MatchOdds] = []

        try:
            # ── Step 1: load homepage to get Akamai cookies ──────────
            logger.info("[Snai] Loading homepage for session cookies...")
            try:
                await page.goto(f"{BASE_URL}/scommesse", wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(4000)
                logger.info("[Snai] Homepage loaded: %s", page.url)
            except Exception as e:
                logger.warning("[Snai] Homepage load failed: %s", e)

            # ── Step 2: get tournament tree via alberaturaPrematch ───
            logger.info("[Snai] Fetching alberaturaPrematch...")
            try:
                resp = await page.request.get(
                    f"{API_BASE}/alberaturaPrematch",
                    headers={"Accept": "application/json", "Referer": BASE_URL},
                )
                tree = await resp.json()
                logger.info("[Snai] alberaturaPrematch: status=%d keys=%s",
                            resp.status, list(tree.keys())[:6] if isinstance(tree, dict) else type(tree).__name__)
                logger.info("[Snai] alberatura preview: %s", _json.dumps(tree)[:1000])
            except Exception as e:
                logger.error("[Snai] alberaturaPrematch failed: %s", e)
                tree = {}

            # ── Step 3: discover tournament IDs from tree ─────────────
            tournament_ids: list[tuple[str, str, int]] = []  # (league_name, sport_key, tournament_id)
            self._walk_tree(tree, sport, tournament_ids)
            logger.info("[Snai] Found %d tournaments to scrape", len(tournament_ids))

            # ── Step 4: fetch events per tournament ───────────────────
            for league_name, sport_key, tid in tournament_ids:
                try:
                    events_url = f"{API_BASE}/palinsesto/prematch/live-ora-for-cards/{tid}?offerId=0&metaTplEnabled=true&deep=true"
                    resp = await page.request.get(
                        events_url,
                        headers={"Accept": "application/json", "Referer": BASE_URL},
                    )
                    body = await resp.json()
                    logger.info("[Snai] %s (id=%d): status=%d keys=%s preview=%s",
                                league_name, tid, resp.status,
                                list(body.keys())[:6] if isinstance(body, dict) else type(body).__name__,
                                _json.dumps(body)[:500])
                    rows = _parse_snai_events(body, league_name, sport_key)
                    logger.info("[Snai] %s: %d match-market rows", league_name, len(rows))
                    results.extend(rows)
                except Exception as e:
                    logger.error("[Snai] %s (id=%d) failed: %s", league_name, tid, e)

        finally:
            await browser.close()
            await pw.stop()

        logger.info("[Snai] Total rows: %d", len(results))
        return results

    def _walk_tree(self, tree: Any, sport_filter: str | None,
                   out: list[tuple[str, str, int]]) -> None:
        """Recursively walk alberaturaPrematch tree to find tournament IDs we want."""
        if not tree:
            return
        if isinstance(tree, list):
            for item in tree:
                self._walk_tree(item, sport_filter, out)
            return
        if not isinstance(tree, dict):
            return

        # Try to detect if this node is a tournament
        node_id = tree.get("id") or tree.get("torneoId") or tree.get("manifestazioneId")
        node_name = str(
            tree.get("descrizione") or tree.get("name") or tree.get("description") or ""
        ).strip()
        node_sport_raw = str(
            tree.get("sport") or tree.get("disciplina") or tree.get("sportName") or ""
        ).strip()
        node_sport = SPORT_MAP.get(node_sport_raw, "")

        # Log everything for discovery
        if node_id and node_name:
            logger.debug("[Snai] Tree node: id=%s name=%r sport=%r", node_id, node_name, node_sport_raw)

        # Check if this node matches a wanted league
        if node_id and node_name:
            for sp_key, wanted_set in WANTED_LEAGUES.items():
                if sport_filter and sp_key != sport_filter:
                    continue
                if node_name in wanted_set:
                    out.append((node_name, sp_key, int(node_id)))
                    logger.info("[Snai] Matched tournament: %r id=%s sport=%s", node_name, node_id, sp_key)

        # Recurse into children
        for child_key in ("figli", "children", "manifestazioni", "tornei",
                          "sports", "items", "subItems", "data"):
            child = tree.get(child_key)
            if child:
                self._walk_tree(child, sport_filter, out)
