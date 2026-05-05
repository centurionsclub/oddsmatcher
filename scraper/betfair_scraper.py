"""
betfair_scraper.py — Recupera quote Exchange (lay) e volume da Betfair API.

Mercati: MATCH_ODDS, OVER_UNDER_05/15/25/35/45/55/65/75/85/95, BOTH_TEAMS_TO_SCORE
Sport: Calcio (1), Tennis (2), Basket (7)

Salva su live_odds con bookmaker="Betfair Exchange", odds=lay_price, volume=available_to_lay
"""

import asyncio
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

# Load .env from same directory as this script
load_dotenv(Path(__file__).parent / ".env")


# ─── Supabase REST upsert (bypasses supabase-py key format validation) ───────

async def _supabase_upsert(rows: list[dict[str, Any]]) -> None:
    """Upsert rows into live_odds via Supabase REST API using httpx directly."""
    if not rows:
        return
    url = f"{SUPABASE_URL}/rest/v1/live_odds"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=rows, headers=headers, params={"on_conflict": "bookmaker,event_name,market,outcome"})
        resp.raise_for_status()

BETFAIR_APP_KEY = os.getenv("BETFAIR_APP_KEY", "")
BETFAIR_USERNAME = os.getenv("BETFAIR_USERNAME", "")
BETFAIR_PASSWORD = os.getenv("BETFAIR_PASSWORD", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

LOGIN_URL = "https://identitysso.betfair.it/api/login"
BETTING_URL = "https://api.betfair.com/exchange/betting/rest/v1.0/"

# Betfair eventTypeId per sport
SPORT_IDS = {
    "calcio": "1",
    "tennis": "2",
    "basket": "7",
}

# Mercati da scrapare
MARKET_TYPES = [
    "MATCH_ODDS",
    "BOTH_TEAMS_TO_SCORE",
    "OVER_UNDER_05",
    "OVER_UNDER_15",
    "OVER_UNDER_25",
    "OVER_UNDER_35",
    "OVER_UNDER_45",
    "OVER_UNDER_55",
    "OVER_UNDER_65",
    "OVER_UNDER_75",
    "OVER_UNDER_85",
    "OVER_UNDER_95",
]

# Mapping Betfair market name → our market label
MARKET_LABEL_MAP: dict[str, str] = {
    "MATCH_ODDS": "1X2",
    "BOTH_TEAMS_TO_SCORE": "BTTS",
}
for _t in ["05", "15", "25", "35", "45", "55", "65", "75", "85", "95"]:
    v = _t[0] + "." + _t[1]
    MARKET_LABEL_MAP[f"OVER_UNDER_{_t}"] = f"Over/Under"

# Mapping Betfair sport name → nostra categoria
BF_SPORT_NAME: dict[str, str] = {
    "1": "calcio",
    "2": "tennis",
    "7": "basket",
}

BOOKMAKER = "Betfair Exchange"
EXPIRES_MINUTES = 90  # match centroquote scraper cycle time


# ─── Auth ────────────────────────────────────────────────────────────────────

async def betfair_login(client: httpx.AsyncClient) -> str:
    """Esegue login non interattivo e restituisce il session token."""
    resp = await client.post(
        LOGIN_URL,
        data={"username": BETFAIR_USERNAME, "password": BETFAIR_PASSWORD},
        headers={
            "X-Application": BETFAIR_APP_KEY,
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
    print(f"  [Betfair] Login OK — token ...{token[-6:]}")
    return token


# ─── API helpers ─────────────────────────────────────────────────────────────

def _bf_headers(token: str) -> dict[str, str]:
    return {
        "X-Application": BETFAIR_APP_KEY,
        "X-Authentication": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# Competizioni target: (region, keyword_in_name) — almeno uno deve matchare
# Le regioni UEFA/GBE/EUR coprono Champions/Europa/Conference League
TARGET_COMPETITIONS: list[tuple[str, str]] = [
    # Italy
    ("ITA", "serie a"),
    ("ITA", "serie b"),
    ("ITA", "coppa italia"),
    # England
    ("GBR", "premier league"),
    ("GBR", "championship"),
    # Germany
    ("DEU", "bundesliga"),
    # Spain
    ("ESP", "la liga"),
    ("ESP", "laliga"),
    # France
    ("FRA", "ligue 1"),
    # European cups (region can be GBE/INT/EUR/GBR depending on Betfair)
    ("", "champions league"),
    ("", "europa league"),
    ("", "europa conference"),
    ("", "conference league"),
    ("", "uefa champions"),
    ("", "uefa europa"),
]


async def list_competitions(
    client: httpx.AsyncClient,
    token: str,
    event_type_id: str = "1",
) -> list[dict[str, Any]]:
    """Restituisce le competition disponibili per un eventType."""
    payload = {"filter": {"eventTypeIds": [event_type_id]}}
    resp = await client.post(
        BETTING_URL + "listCompetitions/",
        json=payload,
        headers=_bf_headers(token),
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    return data or []


async def get_target_competition_ids(
    client: httpx.AsyncClient,
    token: str,
) -> list[str]:
    """Trova i competition IDs Betfair corrispondenti alle leghe di centroquote."""
    comps = await list_competitions(client, token, "1")
    ids: list[str] = []
    for c in comps:
        name = (c.get("competition", {}).get("name", "") or "").lower()
        region = (c.get("competitionRegion", "") or "").upper()
        comp_id = c.get("competition", {}).get("id")
        if not comp_id:
            continue
        for req_region, req_kw in TARGET_COMPETITIONS:
            region_ok = (not req_region) or (region == req_region)
            name_ok = req_kw in name
            if region_ok and name_ok:
                ids.append(comp_id)
                break  # don't add same comp twice
    return ids


async def _fetch_catalogue_page(
    client: httpx.AsyncClient,
    token: str,
    event_type_ids: list[str],
    market_types: list[str],
    hours_ahead: int,
    extra_filter: dict | None = None,
) -> list[dict[str, Any]]:
    """Singola query a listMarketCatalogue con filtri opzionali extra."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=hours_ahead)

    base_filter: dict[str, Any] = {
        "eventTypeIds": event_type_ids,
        "marketTypeCodes": market_types,
        "marketStartTime": {
            "from": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    }
    if extra_filter:
        base_filter.update(extra_filter)

    payload = {
        "filter": base_filter,
        "marketProjection": ["EVENT", "EVENT_TYPE", "COMPETITION", "MARKET_START_TIME", "RUNNER_DESCRIPTION"],
        "maxResults": 1000,
    }
    resp = await client.post(
        BETTING_URL + "listMarketCatalogue/",
        json=payload,
        headers=_bf_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"listMarketCatalogue error: {data}")
    return data or []


async def list_market_catalogue(
    client: httpx.AsyncClient,
    token: str,
    event_type_ids: list[str],
    market_types: list[str],
    hours_ahead: int = 36,
) -> list[dict[str, Any]]:
    """
    Recupera i cataloghi mercato.
    Per calcio (eventTypeId=1): due query separate —
      1. Leghe domestiche filtrate per country code (IT/GB/DE/ES/FR…)
      2. Coppe europee (Champions/Europa/Conference) senza filtro paese
    Per gli altri sport: query singola globale.
    """
    is_football_only = event_type_ids == ["1"]

    if is_football_only:
        # Trova i competition IDs esatti per le leghe che centroquote mostra
        comp_ids = await get_target_competition_ids(client, token)
        print(f"  [Betfair] Competition IDs trovati: {len(comp_ids)}: {comp_ids}")

        if comp_ids:
            # Query a blocchi di 5 competition IDs per non superare il limite 1000
            COMP_BATCH = 5
            all_results: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            for i in range(0, len(comp_ids), COMP_BATCH):
                batch = comp_ids[i : i + COMP_BATCH]
                try:
                    page = await _fetch_catalogue_page(
                        client, token, event_type_ids, market_types,
                        hours_ahead=336,  # 14 giorni
                        extra_filter={"competitionIds": batch},
                    )
                    for m in page:
                        mid = m.get("marketId")
                        if mid and mid not in seen_ids:
                            seen_ids.add(mid)
                            all_results.append(m)
                except Exception as exc:
                    print(f"  [Betfair] Catalogue batch {i} error: {exc}")
            print(f"  [Betfair] Mercati nelle leghe target: {len(all_results)}")
            return all_results
        else:
            # Fallback: query globale con limite 1000
            print("  [Betfair] Nessun competition ID trovato, fallback globale")
            return await _fetch_catalogue_page(
                client, token, event_type_ids, market_types, hours_ahead,
            )
    else:
        # Tennis, basket: query globale
        return await _fetch_catalogue_page(
            client, token, event_type_ids, market_types, hours_ahead,
        )


async def list_market_book(
    client: httpx.AsyncClient,
    token: str,
    market_ids: list[str],
) -> list[dict[str, Any]]:
    """Restituisce i prezzi lay migliori per ogni runner."""
    payload = {
        "marketIds": market_ids,
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
    }

    resp = await client.post(
        BETTING_URL + "listMarketBook/",
        json=payload,
        headers=_bf_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"listMarketBook error: {data}")
    return data  # list of marketBook


# ─── Data extraction ─────────────────────────────────────────────────────────

def _market_label(market_type: str | None, market_name: str) -> tuple[str, str | None]:
    """Restituisce (market_label, threshold_or_None).
    Betfair non restituisce marketType nel catalogue: usiamo marketName."""
    mn = (market_name or "").lower()

    # By marketName (primary — marketType is not returned by Betfair catalogue)
    if "match odds" in mn:
        return "1X2", None
    if "both teams" in mn or "btts" in mn:
        return "BTTS", None
    # "Over/Under 2.5 Goals" → extract threshold
    m = re.search(r"over[/\s]under\s+([\d.]+)", mn)
    if m:
        return "Over/Under", m.group(1)

    # By marketType code (backup, in case Betfair returns it on some endpoints)
    if market_type:
        mt = market_type.upper().replace(" ", "_")
        if mt == "MATCH_ODDS":
            return "1X2", None
        if mt in ("BOTH_TEAMS_TO_SCORE", "BOTHTEAMSTOSCORE"):
            return "BTTS", None
        if mt.startswith("OVER_UNDER_"):
            code = mt.replace("OVER_UNDER_", "")
            if len(code) >= 2:
                return "Over/Under", code[0] + "." + code[1]

    return market_name, None


def _extract_rows(
    catalogue: dict[str, Any],
    book: dict[str, Any],
    sport_label: str,
    market_id: str = "",
) -> list[dict[str, Any]]:
    """Estrae righe ready-to-upsert da un singolo mercato."""
    rows: list[dict[str, Any]] = []

    market_type = catalogue.get("marketType", "")
    market_name = catalogue.get("marketName", "")
    market_label, threshold = _market_label(market_type, market_name)

    event = catalogue.get("event", {})
    competition = catalogue.get("competition", {})
    start_time_str = catalogue.get("marketStartTime", "")

    # Parse event time
    try:
        event_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
    except Exception:
        event_time = datetime.now(timezone.utc)

    # Normalizza "Team A v Team B" → "Team A - Team B" per matchare i bookmaker
    raw_event_name = event.get("name", "Unknown")
    event_name = re.sub(r"\s+v\s+", " - ", raw_event_name)
    event_id = str(event.get("id", ""))
    league = competition.get("name", "Unknown")

    # Build runner map: selectionId → (runnerName, sortPriority)
    runner_map: dict[int, tuple[str, int]] = {}
    for rd in catalogue.get("runners", []):
        runner_map[rd["selectionId"]] = (
            rd.get("runnerName", "Unknown"),
            rd.get("sortPriority", 99),
        )

    # Extract lay prices from book
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=EXPIRES_MINUTES)).isoformat()

    for runner in book.get("runners", []):
        sel_id = runner["selectionId"]
        runner_info = runner_map.get(sel_id, ("Unknown", 99))
        runner_name, sort_priority = runner_info
        status = runner.get("status", "")
        if status != "ACTIVE":
            continue

        ex = runner.get("ex", {})
        available_to_lay = ex.get("availableToLay", [])
        if not available_to_lay:
            continue

        best_lay = available_to_lay[0]
        lay_price = best_lay.get("price")
        lay_size = best_lay.get("size", 0.0)

        if not lay_price or lay_price <= 1.0:
            continue

        # Map Betfair runner names → centroquote outcome format
        mn = (market_name or "").lower()
        if "match odds" in mn:
            # Football 1X2: use sortPriority (1=Home→"1", 2=Away→"2") or name for draw
            if runner_name == "The Draw":
                outcome = "X"
            elif sort_priority == 1:
                outcome = "1"
            elif sort_priority == 2:
                outcome = "2"
            else:
                outcome = runner_name  # tennis/other 2-way: keep team name
        elif "both teams" in mn or "btts" in mn:
            outcome = {"Yes": "Goal", "No": "No Goal"}.get(runner_name, runner_name)
        elif "over" in mn and "under" in mn:
            # "Over 2.5 Goals" → "Over 2.5" / "Under 2.5 Goals" → "Under 2.5"
            outcome = re.sub(r"\s+goals?$", "", runner_name, flags=re.IGNORECASE)
        else:
            outcome = runner_name

        rows.append({
            "bookmaker": BOOKMAKER,
            "sport": sport_label,
            "league": league,
            "event_name": event_name,
            "event_time": event_time.isoformat(),
            "market": market_label,
            "outcome": outcome,
            "odds": float(lay_price),
            "volume": float(lay_size),
            "expires_at": expires_at,
            "market_id": market_id,
            "event_id": event_id,
        })

    return rows


# ─── Main scrape ─────────────────────────────────────────────────────────────

CHUNK_SIZE = 100  # max market IDs per listMarketBook call


async def scrape_betfair(sports: list[str] | None = None) -> int:
    """
    Scrapa Betfair Exchange per i mercati configurati.
    Ritorna il numero di righe inserite/aggiornate.
    """
    if not BETFAIR_APP_KEY or not BETFAIR_USERNAME or not BETFAIR_PASSWORD:
        print("[Betfair] Credenziali mancanti — skip")
        return 0

    if sports is None:
        sports = list(SPORT_IDS.keys())

    # Separate football (needs competition filtering) from other sports (global query)
    football_ids  = ["1"] if "calcio" in sports else []
    other_ids     = [SPORT_IDS[s] for s in sports if s in SPORT_IDS and s != "calcio"]

    async with httpx.AsyncClient() as client:
        try:
            token = await betfair_login(client)
        except Exception as exc:
            print(f"[Betfair] Login error: {exc}")
            return 0

        # Fetch catalogue — football separately to apply competition filter
        catalogue_list: list[dict[str, Any]] = []
        if football_ids:
            try:
                fb_cat = await list_market_catalogue(client, token, football_ids, MARKET_TYPES, hours_ahead=336)
                catalogue_list.extend(fb_cat)
            except Exception as exc:
                print(f"[Betfair] listMarketCatalogue (football) error: {exc}")
        if other_ids:
            try:
                ot_cat = await list_market_catalogue(client, token, other_ids, MARKET_TYPES, hours_ahead=72)
                catalogue_list.extend(ot_cat)
            except Exception as exc:
                print(f"[Betfair] listMarketCatalogue (other sports) error: {exc}")

        print(f"  [Betfair] {len(catalogue_list)} mercati trovati")

        # Build id→catalogue map
        cat_map: dict[str, dict[str, Any]] = {c["marketId"]: c for c in catalogue_list}
        market_ids = list(cat_map.keys())

        # Fetch books in chunks
        all_books: list[dict[str, Any]] = []
        for i in range(0, len(market_ids), CHUNK_SIZE):
            chunk = market_ids[i : i + CHUNK_SIZE]
            try:
                books = await list_market_book(client, token, chunk)
                all_books.extend(books)
            except Exception as exc:
                print(f"  [Betfair] listMarketBook chunk error: {exc}")

        print(f"  [Betfair] {len(all_books)} libri ricevuti")

        # Extract rows
        all_rows: list[dict[str, Any]] = []
        for book in all_books:
            market_id = book.get("marketId", "")
            catalogue = cat_map.get(market_id)
            if not catalogue:
                continue

            market_type = catalogue.get("marketType", "")
            # Determine sport label from eventTypeId
            et = catalogue.get("eventType", {}).get("id", "1")
            sport_label = BF_SPORT_NAME.get(et, "calcio")

            rows = _extract_rows(catalogue, book, sport_label, market_id)
            all_rows.extend(rows)

        print(f"  [Betfair] {len(all_rows)} quote estratte")

        if not all_rows:
            return 0

        # Upsert to Supabase in batches of 500
        total_upserted = 0
        BATCH = 500
        for i in range(0, len(all_rows), BATCH):
            batch = all_rows[i : i + BATCH]
            try:
                await _supabase_upsert(batch)
                total_upserted += len(batch)
            except Exception as exc:
                print(f"  [Betfair] Upsert error (batch {i}): {exc}")

        print(f"  [Betfair] ✓ {total_upserted} righe upsert")
        return total_upserted


if __name__ == "__main__":
    import sys

    sports_arg = sys.argv[1:] if len(sys.argv) > 1 else None
    asyncio.run(scrape_betfair(sports_arg))
