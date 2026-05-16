"""CLI entry point for the Oddsmatcher backend."""

import argparse
import asyncio
import logging
import sys


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Oddsmatcher Backend — CentroQuote scraper",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── scrape ──────────────────────────────────────────────────────
    scrape_parser = subparsers.add_parser("scrape", help="Run a single scrape cycle")
    scrape_parser.add_argument(
        "--sport",
        choices=["calcio", "tennis", "basket"],
        default=None,
        help="Scrape only this sport (default: all)",
    )
    scrape_parser.add_argument(
        "--bookmaker",
        choices=["centroquote", "lottomatica"],
        default=None,
        help="Scrape only this bookmaker (default: all)",
    )
    scrape_parser.add_argument("--verbose", "-v", action="store_true")

    # ── scheduler ───────────────────────────────────────────────────
    sched_parser = subparsers.add_parser("scheduler", help="Run the continuous scheduler")
    sched_parser.add_argument("--verbose", "-v", action="store_true")

    # ── cleanup ─────────────────────────────────────────────────────
    cleanup_parser = subparsers.add_parser("cleanup", help="Remove stale odds data")
    cleanup_parser.add_argument("--hours", type=int, default=48, help="Remove events older than N hours")
    cleanup_parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()
    setup_logging(verbose=args.verbose)

    if args.command == "scrape":
        from oddsmatcher_backend.scheduler.runner import run_scrape_cycle
        stats = asyncio.run(run_scrape_cycle(sport=args.sport, bookmaker=args.bookmaker))
        print(f"\nScrape complete: {stats}")

    elif args.command == "scheduler":
        from oddsmatcher_backend.scheduler.runner import run_scheduler
        asyncio.run(run_scheduler())

    elif args.command == "cleanup":
        from oddsmatcher_backend.db.supabase_client import SupabaseWriter
        writer = SupabaseWriter()
        removed = writer.cleanup_stale_odds(hours=args.hours)
        print(f"Removed {removed} stale events")

    return 0


if __name__ == "__main__":
    sys.exit(main())
