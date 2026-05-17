"""Supabase client for upserting scraped odds data."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

from supabase import create_client, Client

from oddsmatcher_backend.config.settings import settings

if TYPE_CHECKING:
    from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)


def _normalize_market_outcome(market: str, outcome: str) -> tuple[str, str]:
    """Convert scraper market/outcome names to the live_odds canonical format.

    live_odds expects:
      - market="1X2",       outcome="1" | "X" | "2"
      - market="DC",        outcome="1X" | "X2" | "12"
      - market="BTTS",      outcome="Goal" | "No Goal"
      - market="Over/Under",outcome="Over 1.5" | "Under 2.5" | …
    """
    # Italian / API abbreviation → English outcome names
    OUTCOME_MAP: dict[str, str] = {
        "GG": "Goal",
        "NG": "No Goal",
        "Si": "Goal",
        "No": "No Goal",
        "Oltre": "Over",
        "Meno": "Under",
        "O": "Over",
        "U": "Under",
    }
    outcome_norm = OUTCOME_MAP.get(outcome, outcome)

    # "Over/Under 1.5" → market="Over/Under", outcome="Over 1.5" / "Under 1.5"
    if market.startswith("Over/Under "):
        spread = market.split(" ", 1)[1]          # e.g. "1.5"
        side = outcome_norm if outcome_norm in ("Over", "Under") else outcome_norm
        return "Over/Under", f"{side} {spread}"

    # Scraper market name → live_odds market name
    MARKET_MAP: dict[str, str] = {
        "Goal No Goal": "BTTS",
        "Doppia Chance": "DC",
    }
    market_norm = MARKET_MAP.get(market, market)

    return market_norm, outcome_norm


class SupabaseWriter:
    """Writes scraped odds to Supabase (odds_events + odds_data tables)."""

    def __init__(self):
        cfg = settings.supabase
        if not cfg.url or not cfg.service_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
        self.client: Client = create_client(cfg.url, cfg.service_key)
        logger.info("Supabase client initialized")

    def upsert_event(self, event: dict[str, Any]) -> str | None:
        """Upsert a match event and return its UUID.

        Args:
            event: Dict with keys: sport, league, home_team, away_team, event_name, event_time

        Returns:
            The event UUID, or None on failure.
        """
        try:
            result = (
                self.client.table("odds_events")
                .upsert(event, on_conflict="home_team,away_team")
                .execute()
            )
            if result.data:
                return result.data[0]["id"]
        except Exception as e:
            logger.error("Failed to upsert event %s: %s", event.get("event_name"), e)
        return None

    def upsert_odds(self, odds_rows: list[dict[str, Any]]) -> int:
        """Upsert a batch of odds rows.

        Args:
            odds_rows: List of dicts with keys:
                event_id, bookmaker, market, outcome, odds

        Returns:
            Number of rows successfully upserted.
        """
        if not odds_rows:
            return 0

        try:
            result = (
                self.client.table("odds_data")
                .upsert(odds_rows, on_conflict="event_id,bookmaker,market,outcome")
                .execute()
            )
            return len(result.data) if result.data else 0
        except Exception as e:
            logger.error("Failed to upsert %d odds rows: %s", len(odds_rows), e)
            return 0

    def write_lottomatica_live_odds(self, results: "list[MatchOdds]") -> int:
        """Replace Lottomatica/GoldBet/PlanetWin365 rows in live_odds with freshly scraped data.

        Lottomatica, GoldBet and PlanetWin365 share the same backend and always
        have identical odds, so we write one set of rows and copy it for all three.

        Returns:
            Total number of rows inserted across all three bookmakers.
        """
        if not results:
            return 0

        # Bookmakers to write: (name shown in DB, fallback URL if match_url unavailable)
        TARGETS = [
            ("Lottomatica",  "https://www.lottomatica.it/scommesse/sport/"),
            ("GoldBet",      "https://www.goldbet.it/scommesse/sport/"),
            ("Planetwin365", "https://www.planetwin365.it/it/"),
        ]

        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()

        # Build base rows (bookmaker-agnostic)
        base_rows: list[dict[str, Any]] = []
        for match in results:
            for bm in match.bookmaker_odds:
                for outcome_raw, odds_val in bm["odds"].items():
                    market_norm, outcome_norm = _normalize_market_outcome(match.market, outcome_raw)
                    row: dict[str, Any] = {
                        "sport": match.sport,
                        "league": match.league,
                        "event_name": match.event_name,
                        "market": market_norm,
                        "outcome": outcome_norm,
                        "odds": float(odds_val),
                        "expires_at": expires_at,
                        "match_url": match.match_url,
                    }
                    if match.event_time:
                        row["event_time"] = match.event_time
                    base_rows.append(row)

        if not base_rows:
            logger.warning("write_lottomatica_live_odds: no rows to write after normalization")
            return 0

        event_names = list({r["event_name"] for r in base_rows})
        BATCH = 500
        total_inserted = 0

        for bm_name, fallback_url in TARGETS:
            # Delete stale rows for this bookmaker
            try:
                (
                    self.client.table("live_odds")
                    .delete()
                    .eq("bookmaker", bm_name)
                    .in_("event_name", event_names)
                    .execute()
                )
            except Exception as e:
                logger.error("Failed to delete stale %s live_odds: %s", bm_name, e)

            # Build rows for this bookmaker
            bm_rows = [
                {**r, "bookmaker": bm_name, "match_url": r["match_url"] or fallback_url}
                for r in base_rows
            ]

            # Insert in batches
            for i in range(0, len(bm_rows), BATCH):
                batch = bm_rows[i : i + BATCH]
                try:
                    result = self.client.table("live_odds").insert(batch).execute()
                    total_inserted += len(result.data) if result.data else 0
                except Exception as e:
                    logger.error("Failed to insert %s live_odds batch %d: %s", bm_name, i // BATCH, e)

            logger.info("%s live_odds: %d rows for %d events", bm_name, len(bm_rows), len(event_names))

        logger.info("Total inserted across Lottomatica+GoldBet+PlanetWin365: %d rows", total_inserted)
        return total_inserted

    def cleanup_stale_odds(self, hours: int = 24) -> int:
        """Delete odds for events that have already started (older than N hours).

        Returns number of deleted rows.
        """
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

            # Get old event IDs
            old_events = (
                self.client.table("odds_events")
                .select("id")
                .lt("event_time", cutoff)
                .execute()
            )

            if not old_events.data:
                return 0

            event_ids = [e["id"] for e in old_events.data]

            # Delete odds for old events
            self.client.table("odds_data").delete().in_("event_id", event_ids).execute()

            # Delete old events
            self.client.table("odds_events").delete().in_("id", event_ids).execute()

            logger.info("Cleaned up %d stale events", len(event_ids))
            return len(event_ids)

        except Exception as e:
            logger.error("Failed to cleanup stale odds: %s", e)
            return 0
