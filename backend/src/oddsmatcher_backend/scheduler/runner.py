"""Scheduler that runs the scraping pipeline at configured intervals."""

import asyncio
import logging
from datetime import datetime, timezone

from oddsmatcher_backend.config.settings import settings
from oddsmatcher_backend.db.supabase_client import SupabaseWriter
from oddsmatcher_backend.scraper.bet365 import Bet365Scraper
from oddsmatcher_backend.scraper.betfair import BetfairScraper
from oddsmatcher_backend.scraper.betsson import BetssonScraper
from oddsmatcher_backend.scraper.bwin import BwinScraper
from oddsmatcher_backend.scraper.eurobet import EurobetScraper
from oddsmatcher_backend.scraper.lottomatica import LottomaticaScraper
from oddsmatcher_backend.scraper.sisal import SisalScraper
from oddsmatcher_backend.scraper.snai import SnaiScraper
from oddsmatcher_backend.scraper.theoddsapi import TheOddsAPIScraper
from oddsmatcher_backend.scraper.williamhill import WilliamHillScraper

logger = logging.getLogger(__name__)


async def run_scrape_cycle(sport: str | None = None, bookmaker: str | None = None) -> dict:
    """Execute a single scrape cycle for one or all bookmakers.

    Args:
        sport:      Scrape only this sport, or all if None.
        bookmaker:  bookmaker key or None (= all)

    Returns:
        Stats dict.
    """
    start = datetime.now(timezone.utc)
    logger.info(
        "Starting scrape cycle at %s (sport=%s, bookmaker=%s)",
        start.isoformat(), sport or "all", bookmaker or "all",
    )

    stats: dict = {}

    # ── helpers ───────────────────────────────────────────────────────────────

    async def _run_direct(name: str, scraper_cls, bm_key: str) -> int:
        """Run a direct Playwright scraper and return rows inserted."""
        if bookmaker not in (None, bm_key):
            return 0
        try:
            sc = scraper_cls()
            res = await (sc.scrape_sport(sport) if sport else sc.scrape_all())
            w = SupabaseWriter()
            inserted = w.write_direct_live_odds(name, res)
            logger.info(
                "%s done: %d match-market results → %d live_odds rows",
                name, len(res), inserted,
            )
            return inserted
        except Exception as exc:
            logger.error("%s scrape cycle failed: %s", name, exc, exc_info=True)
            return 0

    # ── Sisal ─────────────────────────────────────────────────────────────────
    sisal_rows = 0
    if bookmaker in (None, "sisal"):
        try:
            sisal_scraper = SisalScraper()
            sisal_results = await (sisal_scraper.scrape_sport(sport) if sport else sisal_scraper.scrape_all())
            sisal_writer = SupabaseWriter()
            sisal_rows = sisal_writer.write_direct_live_odds("Sisal", sisal_results)
            logger.info("Sisal done: %d match-market results → %d live_odds rows", len(sisal_results), sisal_rows)
        except Exception as exc:
            logger.error("Sisal scrape cycle failed: %s", exc, exc_info=True)

    # ── Lottomatica (+ GoldBet + Planetwin365) ────────────────────────────────
    lotto_rows = 0
    if bookmaker in (None, "lottomatica"):
        try:
            lotto_scraper = LottomaticaScraper()
            lotto_results = await (lotto_scraper.scrape_sport(sport) if sport else lotto_scraper.scrape_all())
            lotto_writer = SupabaseWriter()
            lotto_rows = lotto_writer.write_lottomatica_live_odds(lotto_results)
            logger.info(
                "Lottomatica done: %d match-market results → %d live_odds rows",
                len(lotto_results), lotto_rows,
            )
        except Exception as exc:
            logger.error("Lottomatica scrape cycle failed: %s", exc, exc_info=True)

    # ── Direct scrapers ───────────────────────────────────────────────────────
    eurobet_rows  = await _run_direct("Eurobet",      EurobetScraper,     "eurobet")
    snai_rows     = await _run_direct("Snai",          SnaiScraper,        "snai")
    bwin_rows     = await _run_direct("Bwin",          BwinScraper,        "bwin")
    betsson_rows  = await _run_direct("Betsson",       BetssonScraper,     "betsson")
    wh_rows       = await _run_direct("William Hill",  WilliamHillScraper, "williamhill")
    bet365_rows   = await _run_direct("Bet365",        Bet365Scraper,      "bet365")

    # ── The Odds API — Pinnacle, Codere IT, MarathonBet ──────────────────────
    # 1 HTTP request per sport (EU region), ~12 req per full scrape.
    # Free plan: 500 req/month → safe at max 2 cycles/day.
    theodds_rows = 0
    if bookmaker in (None, "codere", "marathonbet", "theoddsapi"):
        try:
            theodds_scraper = TheOddsAPIScraper()
            theodds_results = await (theodds_scraper.scrape_sport(sport) if sport else theodds_scraper.scrape_all())
            theodds_writer = SupabaseWriter()
            theodds_rows = theodds_writer.write_direct_live_odds("TheOddsAPI", theodds_results)
            logger.info(
                "TheOddsAPI done: %d market rows → %d live_odds rows",
                len(theodds_results), theodds_rows,
            )
        except Exception as exc:
            logger.error("TheOddsAPI scrape cycle failed: %s", exc, exc_info=True)

    # ── Betfair Exchange — official API (httpx, no Playwright) ───────────────
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

    # ── Cleanup stale data ────────────────────────────────────────────────────
    cleaned = SupabaseWriter().cleanup_stale_odds(hours=48)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    stats = {
        "sisal_live_rows":    sisal_rows,
        "lotto_live_rows":    lotto_rows,
        "eurobet_live_rows":  eurobet_rows,
        "snai_live_rows":     snai_rows,
        "bwin_live_rows":     bwin_rows,
        "betsson_live_rows":  betsson_rows,
        "wh_live_rows":       wh_rows,
        "bet365_live_rows":   bet365_rows,
        "theodds_live_rows":  theodds_rows,
        "betfair_live_rows":  betfair_rows,
        "stale_cleaned":      cleaned,
        "duration_s":         round(elapsed, 1),
    }
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
