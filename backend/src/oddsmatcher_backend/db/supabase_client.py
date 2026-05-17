"""Supabase client for upserting scraped odds data."""

import logging
from typing import Any

from supabase import create_client, Client

from oddsmatcher_backend.config.settings import settings

logger = logging.getLogger(__name__)


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

    def cleanup_stale_odds(self, hours: int = 24) -> int:
        """Delete odds for events that have already started (older than N hours).

        Returns number of deleted rows.
        """
        try:
            from datetime import datetime, timedelta, timezone
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
