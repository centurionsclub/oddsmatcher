"""
betfair.py — Recupera quote Exchange (lay) e volume da Betfair API.

Mercati: MATCH_ODDS, OVER_UNDER_05/15/25/35/45, BOTH_TEAMS_TO_SCORE
Sport: Calcio (1), Tennis (2), Basket (7522)

Salva su live_odds con bookmaker="Betfair Exchange".
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

LOGIN_URLS = [
    "https://identitysso.betfair.com/api/login",   # global (works from non-IT IPs)
    "https://identitysso.betfair.it/api/login",    # Italian domain (fallback)
]
BETTING_URL  = "https://api.betfair.com/exchange/betting/rest/v1.0/"
BOOKMAKER    = "Betfair Exchange"
EXPIRES_HOURS = 36   # keep rows visible even if scraper skips a cycle (30-min schedule → buffer)

# Betfair eventTypeId → our sport key
# NOTE: 7 = Horse Racing (NOT basketball). Basketball is 7522.
SPORT_IDS = {
    "calcio": "1",
    "tennis": "2",
    "basket": "7522",
}
BF_SPORT_NAME = {v: k for k, v in SPORT_IDS.items()}

# Target competitions for football — keyword sul nome (con prefisso paese
# dove il nome da solo è troppo generico, es. "premier league").
# Betfair include il paese nel nome: "English Premier League", "Italian Serie A", ecc.
TARGET_COMPETITION_KEYWORDS: list[str] = [
    # Italy
    "italian serie a", "italian serie b", "coppa italia",
    # England — "english" evita "Kuwaiti/Nigerian Premier League"
    "english premier league", "english championship", "sky bet championship", "fa cup",
    # Germany — "german bundesliga" evita "Austrian Bundesliga"; playoff = spareggi; cup = DFB Pokal
    "german bundesliga", "german playoff", "german cup",
    # Spain — "spanish la liga" evita "Peruvian/Uruguayan Primera Division"
    "spanish la liga", "la liga", "laliga",
    # France — "french ligue 1" evita "Algerian Ligue 1"
    "french ligue 1",
    # European cups
    "champions league", "europa league", "europa conference",
    "conference league", "uefa champions", "uefa europa",
]

# Market types to fetch
MARKET_TYPES = [
    "MATCH_ODDS",
    "BOTH_TEAMS_TO_SCORE",
    "OVER_UNDER_05",
    "OVER_UNDER_15",
    "OVER_UNDER_25",
    "OVER_UNDER_35",
    "OVER_UNDER_45",
    "OVER_UNDER_55",
]

CHUNK_SIZE = 100   # max market IDs per listMarketBook call


# ─── Auth ─────────────────────────────────────────────────────────────────────

async def _login(client: httpx.AsyncClient, app_key: str, username: str, password: str) -> str:
    """Perform non-interactive login and return session token.

    Tries global endpoint first (works from non-Italian IPs like GitHub Actions),
    then falls back to the Italian endpoint.
    """
    last_exc: Exception | None = None
    for login_url in LOGIN_URLS:
        try:
            resp = await client.post(
                login_url,
                data={"username": username, "password": password},
                headers={
                    "X-Application": app_key,
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=20,
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("status") != "SUCCESS":
                raise RuntimeError(f"Betfair login failed: {body}")
            token = body["token"]
            logger.info("[Betfair] Login OK via %s — token ...%s", login_url, token[-6:])
            return token
        except Exception as exc:
            logger.warning("[Betfair] Login attempt %s failed: %s", login_url, exc)
            last_exc = exc
    raise RuntimeError(f"All Betfair login endpoints failed. Last: {last_exc}")


def _bf_headers(token: str, app_key: str) -> dict[str, str]:
    return {
        "X-Application": app_key,
        "X-Authentication": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ─── API helpers ──────────────────────────────────────────────────────────────

async def _api_post(
    client: httpx.AsyncClient,
    token: str,
    app_key: str,
    endpoint: str,
    payload: dict,
    timeout: float = 30,
) -> Any:
    resp = await client.post(
        BETTING_URL + endpoint,
        json=payload,
        headers=_bf_headers(token, app_key),
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"Betfair API {endpoint} error: {data}")
    return data or []


async def _get_football_comp_ids(
    client: httpx.AsyncClient, token: str, app_key: str
) -> list[str]:
    """Return Betfair competition IDs matching our target leagues.

    Filters by name only — competitionRegion is unreliable on Betfair
    (German Bundesliga may come back as DEU, GER, EUR, or blank).
    """
    comps = await _api_post(
        client, token, app_key,
        "listCompetitions/",
        {"filter": {"eventTypeIds": ["1"]}},
    )
    ids: list[str] = []
    matched_names: list[str] = []
    skipped_names: list[str] = []
    for c in comps:
        raw_name = (c.get("competition", {}).get("name", "") or "")
        name     = raw_name.lower()
        region   = (c.get("competitionRegion", "") or "").upper()
        comp_id  = c.get("competition", {}).get("id")
        if not comp_id:
            continue
        matched = False
        for kw in TARGET_COMPETITION_KEYWORDS:
            if kw in name:
                ids.append(comp_id)
                matched_names.append(f"{raw_name} [{region}]")
                matched = True
                break
        if not matched:
            skipped_names.append(f"{raw_name} [{region}]")

    logger.info("[Betfair] Competizioni INCLUSE (%d): %s", len(matched_names), matched_names)
    logger.info("[Betfair] Competizioni ESCLUSE (%d): %s", len(skipped_names), skipped_names)
    logger.info("[Betfair] %d competition IDs totali", len(ids))
    return ids


async def _fetch_catalogue(
    client: httpx.AsyncClient,
    token: str,
    app_key: str,
    event_type_ids: list[str],
    extra_filter: dict | None = None,
    hours_ahead: int = 336,
) -> list[dict]:
    """Fetch market catalogue for given event types."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=hours_ahead)
    base_filter: dict[str, Any] = {
        "eventTypeIds": event_type_ids,
        "marketTypeCodes": MARKET_TYPES,
        "marketStartTime": {
            "from": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to":   end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    }
    if extra_filter:
        base_filter.update(extra_filter)
    return await _api_post(
        client, token, app_key,
        "listMarketCatalogue/",
        {
            "filter": base_filter,
            "marketProjection": [
                "EVENT", "EVENT_TYPE", "COMPETITION",
                "MARKET_START_TIME", "RUNNER_DESCRIPTION",
            ],
            "maxResults": 1000,
        },
        timeout=30,
    )


# ─── Parsing ──────────────────────────────────────────────────────────────────

def _market_label(market_name: str) -> tuple[str, str | None]:
    """Return (market, threshold_or_None) from a Betfair market name."""
    mn = market_name.lower()
    if "match odds" in mn or "moneyline" in mn:
        return "1X2", None
    if "both teams" in mn or "btts" in mn:
        return "BTTS", None
    m = re.search(r"over[/\s]under\s+([\d.]+)", mn)
    if m:
        return "Over/Under", m.group(1)
    return market_name, None


def _extract_rows(
    catalogue: dict,
    book: dict,
    sport_label: str,
    expires_at: str,
) -> list[dict]:
    rows: list[dict] = []
    market_id   = catalogue.get("marketId", "")
    market_name = catalogue.get("marketName", "")
    market_label, threshold = _market_label(market_name)

    event       = catalogue.get("event", {})
    competition = catalogue.get("competition", {})
    start_time  = catalogue.get("marketStartTime", "")

    try:
        event_time = datetime.fromisoformat(start_time.replace("Z", "+00:00")).isoformat()
    except Exception:
        event_time = datetime.now(timezone.utc).isoformat()

    # Normalise "Team A v Team B" → "Team A - Team B" to match other bookmakers
    raw_name   = event.get("name", "Unknown")
    event_name = re.sub(r"\s+v\s+", " - ", raw_name)
    event_id   = str(event.get("id", ""))
    league     = competition.get("name", "Unknown")

    # runner selectionId → (name, sortPriority)
    runner_map: dict[int, tuple[str, int]] = {}
    for rd in catalogue.get("runners", []):
        runner_map[rd["selectionId"]] = (
            rd.get("runnerName", "Unknown"),
            rd.get("sortPriority", 99),
        )

    mn = market_name.lower()
    for runner in book.get("runners", []):
        if runner.get("status") != "ACTIVE":
            continue
        sel_id = runner["selectionId"]
        runner_name, sort_priority = runner_map.get(sel_id, ("Unknown", 99))

        atl = runner.get("ex", {}).get("availableToLay", [])
        if not atl:
            continue
        lay_price = atl[0].get("price")
        lay_size  = atl[0].get("size", 0.0)
        if not lay_price or lay_price <= 1.0:
            continue

        # Map runner → outcome label
        if "match odds" in mn or "moneyline" in mn:
            if runner_name == "The Draw":
                outcome = "X"
            elif sort_priority == 1:
                outcome = "1"
            elif sort_priority == 2:
                outcome = "2"
            else:
                outcome = runner_name
        elif "both teams" in mn or "btts" in mn:
            outcome = {"Yes": "Goal", "No": "No Goal"}.get(runner_name, runner_name)
        elif "over" in mn and "under" in mn:
            base = re.sub(r"\s+goals?$", "", runner_name, flags=re.IGNORECASE)
            # "Over 2.5" / "Under 2.5" — keep threshold from market name
            if threshold and not re.search(r"[\d.]", base):
                base = f"{base} {threshold}"
            outcome = base
        else:
            outcome = runner_name

        rows.append({
            "bookmaker":  BOOKMAKER,
            "sport":      sport_label,
            "league":     league,
            "event_name": event_name,
            "event_time": event_time,
            "market":     market_label,
            "outcome":    outcome,
            "odds":       float(lay_price),
            "volume":     float(lay_size),
            "expires_at": expires_at,
            "market_id":  market_id,
            "event_id":   event_id,
        })

    return rows


# ─── Main scraper class ───────────────────────────────────────────────────────

class BetfairScraper:
    """Fetch Betfair Exchange lay odds via the official API."""

    def __init__(self) -> None:
        self._app_key  = os.getenv("BETFAIR_APP_KEY", "")
        self._username = os.getenv("BETFAIR_USERNAME", "")
        self._password = os.getenv("BETFAIR_PASSWORD", "")
        self._log = logger

    def _make_client(self) -> httpx.AsyncClient:
        """Build an httpx client with optional proxy (for geo-restricted login)."""
        proxy_url = os.getenv("PROXY_URL")
        if proxy_url:
            logger.info("[Betfair] Using proxy: %s", proxy_url.split("@")[-1])
            return httpx.AsyncClient(proxy=proxy_url, timeout=30)
        return httpx.AsyncClient(timeout=30)

    async def scrape_all(self, sport: str | None = None) -> list[dict]:
        """Scrape all sports (or a specific one) and return ready-to-insert rows."""
        if not self._app_key or not self._username or not self._password:
            logger.warning("[Betfair] Credenziali mancanti — skip")
            return []

        if sport:
            sports = [sport] if sport in SPORT_IDS else []
        else:
            sports = list(SPORT_IDS.keys())

        expires_at = (datetime.now(timezone.utc) + timedelta(hours=EXPIRES_HOURS)).isoformat()

        async with self._make_client() as client:
            try:
                token = await _login(client, self._app_key, self._username, self._password)
            except Exception as exc:
                logger.error("[Betfair] Login error: %s", exc)
                return []

            catalogue_list: list[dict] = []
            seen_ids: set[str] = set()

            # Football: filtered by target competition IDs
            if "calcio" in sports:
                try:
                    comp_ids = await _get_football_comp_ids(client, token, self._app_key)
                    COMP_BATCH = 5
                    for i in range(0, len(comp_ids), COMP_BATCH):
                        batch = comp_ids[i : i + COMP_BATCH]
                        try:
                            page = await _fetch_catalogue(
                                client, token, self._app_key, ["1"],
                                extra_filter={"competitionIds": batch},
                                hours_ahead=336,
                            )
                            for m in page:
                                mid = m.get("marketId")
                                if mid and mid not in seen_ids:
                                    seen_ids.add(mid)
                                    catalogue_list.append(m)
                        except Exception as exc:
                            logger.error("[Betfair] Catalogue batch %d error: %s", i, exc)
                except Exception as exc:
                    logger.error("[Betfair] Football catalogue error: %s", exc)

            # Other sports: global query
            other_type_ids = [SPORT_IDS[s] for s in sports if s != "calcio" and s in SPORT_IDS]
            if other_type_ids:
                try:
                    page = await _fetch_catalogue(
                        client, token, self._app_key, other_type_ids, hours_ahead=72,
                    )
                    for m in page:
                        mid = m.get("marketId")
                        if mid and mid not in seen_ids:
                            seen_ids.add(mid)
                            catalogue_list.append(m)
                except Exception as exc:
                    logger.error("[Betfair] Other sports catalogue error: %s", exc)

            logger.info("[Betfair] %d mercati nel catalogo", len(catalogue_list))

            # Build id→catalogue map
            cat_map = {c["marketId"]: c for c in catalogue_list}
            market_ids = list(cat_map.keys())

            # Fetch books in chunks
            all_books: list[dict] = []
            for i in range(0, len(market_ids), CHUNK_SIZE):
                chunk = market_ids[i : i + CHUNK_SIZE]
                try:
                    books = await _api_post(
                        client, token, self._app_key,
                        "listMarketBook/",
                        {
                            "marketIds": chunk,
                            "priceProjection": {
                                "priceData": ["EX_BEST_OFFERS"],
                                "exBestOffersOverrides": {
                                    "bestPricesDepth": 1,
                                    "rollupModel": "STAKE",
                                    "rollupLimit": 0,
                                },
                            },
                            "orderProjection": "EXECUTABLE",
                            "matchProjection": "NO_ROLLUP",
                        },
                        timeout=30,
                    )
                    all_books.extend(books)
                except Exception as exc:
                    logger.error("[Betfair] listMarketBook chunk %d error: %s", i, exc)

            logger.info("[Betfair] %d libri ricevuti", len(all_books))

            # Extract rows
            all_rows: list[dict] = []
            for book in all_books:
                market_id = book.get("marketId", "")
                catalogue = cat_map.get(market_id)
                if not catalogue:
                    continue
                et = (catalogue.get("eventType") or {}).get("id", "1")
                sport_label = BF_SPORT_NAME.get(str(et), "calcio")
                rows = _extract_rows(catalogue, book, sport_label, expires_at)
                all_rows.extend(rows)

            logger.info("[Betfair] %d quote estratte", len(all_rows))
            return all_rows

    async def scrape_sport(self, sport: str) -> list[dict]:
        return await self.scrape_all(sport=sport)
