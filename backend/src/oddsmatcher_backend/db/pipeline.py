"""Data pipeline: transforms scraped MatchOdds into DB rows and writes them."""

import logging
from datetime import datetime, timezone

from oddsmatcher_backend.db.supabase_client import SupabaseWriter
from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)


class OddsPipeline:
    """Transforms and persists scraped odds data."""

    def __init__(self, writer: SupabaseWriter | None = None):
        self.writer = writer or SupabaseWriter()

    def process(self, results: list[MatchOdds]) -> dict[str, int]:
        """Process a batch of scraped results into the database.

        Returns:
            Stats dict with events_saved, odds_saved, errors counts.
        """
        stats = {"events_saved": 0, "odds_saved": 0, "errors": 0}

        # Group by unique event (same match can appear multiple times for different markets)
        events_seen: dict[str, str] = {}  # "home|away|time" → event_id

        for match in results:
            try:
                event_key = f"{match.home_team}|{match.away_team}|{match.event_time}"

                # Upsert event if not already done
                if event_key not in events_seen:
                    event_id = self.writer.upsert_event({
                        "sport": match.sport,
                        "league": match.league,
                        "home_team": match.home_team,
                        "away_team": match.away_team,
                        "event_name": match.event_name,
                        "event_time": match.event_time or datetime.now(timezone.utc).isoformat(),
                    })

                    if event_id is None:
                        stats["errors"] += 1
                        continue

                    events_seen[event_key] = event_id
                    stats["events_saved"] += 1

                event_id = events_seen[event_key]

                # Build odds rows for this match+market
                odds_rows = []
                for bm in match.bookmaker_odds:
                    bookmaker = bm["bookmaker"]
                    for outcome, value in bm["odds"].items():
                        odds_rows.append({
                            "event_id": event_id,
                            "bookmaker": bookmaker,
                            "market": match.market,
                            "outcome": outcome,
                            "odds": float(value),
                        })

                saved = self.writer.upsert_odds(odds_rows)
                stats["odds_saved"] += saved

            except Exception as e:
                logger.error("Pipeline error for %s: %s", match.event_name, e)
                stats["errors"] += 1

        logger.info(
            "Pipeline complete: %d events, %d odds rows, %d errors",
            stats["events_saved"], stats["odds_saved"], stats["errors"],
        )
        return stats
