"""Scheduler that runs the scraping pipeline at configured intervals."""

import asyncio
import logging
from datetime import datetime, timezone

from oddsmatcher_backend.config.settings import settings
from oddsmatcher_backend.db.pipeline import OddsPipeline
from oddsmatcher_backend.db.supabase_client import SupabaseWriter
from oddsmatcher_backend.scraper.browser import BrowserManager
from oddsmatcher_backend.scraper.centroquote import CentroQuoteScraper

logger = logging.getLogger(__name__)


async def run_scrape_cycle(sport: str | None = None) -> dict:
    """Execute a single scrape cycle: scrape → pipeline → cleanup.

    Args:
        sport: Scrape only this sport, or all if None.

    Returns:
        Stats from the pipeline.
    """
    start = datetime.now(timezone.utc)
    logger.info("Starting scrape cycle at %s (sport=%s)", start.isoformat(), sport or "all")

    async with BrowserManager() as browser:
        scraper = CentroQuoteScraper(browser)

        if sport:
            results = await scraper.scrape_sport(sport)
        else:
            results = await scraper.scrape_all()

        logger.info("Scrape phase done: %d match-market results", len(results))

    # Pipeline: write to Supabase
    writer = SupabaseWriter()
    pipeline = OddsPipeline(writer)
    stats = pipeline.process(results)

    # Cleanup stale data
    cleaned = writer.cleanup_stale_odds(hours=48)
    stats["stale_cleaned"] = cleaned

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    stats["duration_s"] = round(elapsed, 1)
    logger.info("Scrape cycle complete in %.1fs: %s", elapsed, stats)

    return stats


async def run_scheduler():
    """Run the scraper on a loop at the configured interval."""
    interval = settings.scheduler.scrape_interval_minutes * 60
    logger.info("Scheduler started — interval: %d minutes", settings.scheduler.scrape_interval_minutes)

    while True:
        try:
            stats = await run_scrape_cycle()
            logger.info("Cycle stats: %s", stats)
        except Exception as e:
            logger.error("Scrape cycle failed: %s", e, exc_info=True)

        logger.info("Sleeping %d seconds until next cycle...", interval)
        await asyncio.sleep(interval)
