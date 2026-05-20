"""Scheduler that runs the scraping pipeline at configured intervals."""

import asyncio
import logging
from datetime import datetime, timezone

from oddsmatcher_backend.config.settings import settings
from oddsmatcher_backend.db.pipeline import OddsPipeline
from oddsmatcher_backend.db.supabase_client import SupabaseWriter
from oddsmatcher_backend.scraper.browser import BrowserManager
from oddsmatcher_backend.scraper.bet365 import Bet365Scraper
from oddsmatcher_backend.scraper.betfair import BetfairScraper
from oddsmatcher_backend.scraper.betsson import BetssonScraper
from oddsmatcher_backend.scraper.bwin import BwinScraper
from oddsmatcher_backend.scraper.centroquote import CentroQuoteScraper
from oddsmatcher_backend.scraper.eurobet import EurobetScraper
from oddsmatcher_backend.scraper.lottomatica import LottomaticaScraper
from oddsmatcher_backend.scraper.sisal import SisalScraper
from oddsmatcher_backend.scraper.snai import SnaiScraper
from oddsmatcher_backend.scraper.williamhill import WilliamHillScraper

logger = logging.getLogger(__name__)


async def run_scrape_cycle(sport: str | None = None, bookmaker: str | None = None) -> dict:
    """Execute a single scrape cycle: scrape → pipeline → cleanup.

    Args:
        sport:      Scrape only this sport, or all if None.
        bookmaker:  'centroquote' | 'lottomatica' | 'sisal' | 'eurobet' | None (= tutti)

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

    # Sisal scraping — Playwright browser + network interception
    sisal_live_inserted = 0
    if bookmaker in (None, "sisal"):
        try:
            sisal_scraper = SisalScraper()
            sisal_results = await (sisal_scraper.scrape_sport(sport) if sport else sisal_scraper.scrape_all())
            sisal_writer = SupabaseWriter()
            sisal_live_inserted = sisal_writer.write_direct_live_odds("Sisal", sisal_results)
            logger.info("Sisal done: %d match-market results → %d live_odds rows", len(sisal_results), sisal_live_inserted)
        except Exception as exc:
            logger.error("Sisal scrape cycle failed: %s", exc, exc_info=True)

    # Lottomatica scraping — Playwright browser + page.request.get()
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

    # ── Bookmaker diretti: Eurobet, Snai, Bwin, Betsson, William Hill, Bet365 ──

    async def _run_direct(name: str, scraper_cls, bm_key: str) -> int:
        """Run a direct Playwright scraper and return rows inserted."""
        if bookmaker not in (None, bm_key):
            return 0
        try:
            sc = scraper_cls()
            res = await (sc.scrape_sport(sport) if sport else sc.scrape_all())
            w = SupabaseWriter()
            inserted = w.write_direct_live_odds(name, res)
            logger.info("%s done: %d match-market results → %d live_odds rows", name, len(res), inserted)
            return inserted
        except Exception as exc:
            logger.error("%s scrape cycle failed: %s", name, exc, exc_info=True)
            return 0

    eurobet_rows   = await _run_direct("Eurobet",      EurobetScraper,      "eurobet")
    snai_rows      = await _run_direct("Snai",          SnaiScraper,         "snai")
    bwin_rows      = await _run_direct("Bwin",          BwinScraper,         "bwin")
    betsson_rows   = await _run_direct("Betsson",       BetssonScraper,      "betsson")
    wh_rows        = await _run_direct("William Hill",  WilliamHillScraper,  "williamhill")
    bet365_rows    = await _run_direct("Bet365",        Bet365Scraper,       "bet365")

    # Betfair Exchange — uses official API (httpx, no Playwright)
    betfair_rows = 0
    if bookmaker in (None, "betfair"):
        try:
            bf_scraper = BetfairScraper()
            bf_results = await (bf_scraper.scrape_sport(sport) if sport else bf_scraper.scrape_all())
            bf_writer = SupabaseWriter()
            betfair_rows = bf_writer.write_betfair_live_odds(bf_results)
            logger.info("Betfair Exchange done: %d quote → %d live_odds rows", len(bf_results), betfair_rows)
        except Exception as exc:
            logger.error("Betfair Exchange scrape cycle failed: %s", exc, exc_info=True)

    logger.info("Scrape phase done: %d CentroQuote match-market results", len(results))

    # Pipeline: write CentroQuote results to odds_events + odds_data
    writer = SupabaseWriter()
    pipeline = OddsPipeline(writer)
    stats = pipeline.process(results)
    stats["lotto_live_rows"]    = lotto_live_inserted
    stats["sisal_live_rows"]    = sisal_live_inserted
    stats["eurobet_live_rows"]  = eurobet_rows
    stats["snai_live_rows"]     = snai_rows
    stats["bwin_live_rows"]     = bwin_rows
    stats["betsson_live_rows"]  = betsson_rows
    stats["wh_live_rows"]         = wh_rows
    stats["bet365_live_rows"]     = bet365_rows
    stats["betfair_live_rows"]    = betfair_rows

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
