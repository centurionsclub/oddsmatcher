"""Scheduler that runs the scraping pipeline at configured intervals."""

import asyncio
import logging
from datetime import datetime, timezone

from oddsmatcher_backend.config.settings import settings
from oddsmatcher_backend.db.pipeline import OddsPipeline
from oddsmatcher_backend.db.supabase_client import SupabaseWriter
from oddsmatcher_backend.scraper.browser import BrowserManager
from oddsmatcher_backend.scraper.centroquote import CentroQuoteScraper
from oddsmatcher_backend.scraper.lottomatica import LottomaticaScraper

logger = logging.getLogger(__name__)


async def run_scrape_cycle(sport: str | None = None, bookmaker: str | None = None) -> dict:
    """Execute a single scrape cycle: scrape → pipeline → cleanup.

    Args:
        sport:      Scrape only this sport, or all if None.
        bookmaker:  'centroquote' | 'lottomatica' | None (= entrambi)

    Returns:
        Stats from the pipeline.
    """
    start = datetime.now(timezone.utc)
    logger.info("Starting scrape cycle at %s (sport=%s, bookmaker=%s)", start.isoformat(), sport or "all", bookmaker or "all")

    results: list = []

    # CentroQuote scraping
    if bookmaker in (None, "centroquote"):
        async with BrowserManager(headless_override=False) as browser:
            scraper = CentroQuoteScraper(browser)
            cq_results = await (scraper.scrape_sport(sport) if sport else scraper.scrape_all())

        # Rimuovi eventuali quote Lottomatica da CentroQuote:
        # Lottomatica viene solo dal nostro scraper diretto su lottomatica.it
        DIRECT_ONLY = {"lottomatica"}
        cq_filtered = []
        for r in cq_results:
            r.bookmaker_odds = [
                bm for bm in r.bookmaker_odds
                if bm["bookmaker"].lower() not in DIRECT_ONLY
            ]
            if r.bookmaker_odds:
                cq_filtered.append(r)

        dropped = len(cq_results) - len(cq_filtered)
        if dropped:
            logger.info("CentroQuote: rimossi %d risultati Lottomatica (verranno da scraper diretto)", dropped)
        results.extend(cq_filtered)
        logger.info("CentroQuote done: %d match-market results", len(cq_filtered))

    # Lottomatica scraping — direct HTTP (no browser needed)
    lotto_live_inserted = 0
    if bookmaker in (None, "lottomatica"):
        try:
            lotto_scraper = LottomaticaScraper()
            lotto_results = await (lotto_scraper.scrape_sport(sport) if sport else lotto_scraper.scrape_all())

            # Write Lottomatica directly to live_odds (the table the frontend reads)
            lotto_writer = SupabaseWriter()
            lotto_live_inserted = lotto_writer.write_lottomatica_live_odds(lotto_results)
            logger.info(
                "Lottomatica done: %d match-market results → %d live_odds rows",
                len(lotto_results), lotto_live_inserted,
            )
        except Exception as exc:
            logger.error("Lottomatica scrape cycle failed: %s", exc, exc_info=True)

    logger.info("Scrape phase done: %d CentroQuote match-market results", len(results))

    # Pipeline: write CentroQuote results to odds_events + odds_data
    writer = SupabaseWriter()
    pipeline = OddsPipeline(writer)
    stats = pipeline.process(results)
    stats["lotto_live_rows"] = lotto_live_inserted

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
