"""
Daemon — Betfair Exchange (fast loop ogni ~60s)

  FAST (ogni ~60s): Betfair Exchange (quote exchange aggiornate ogni minuto)

I bookmaker (Sisal, Lottomatica ecc.) sono scraped da GitHub Actions ogni 15 min.

Avvio:
    cd /path/to/Oddsmatcher/scraper
    python daemon.py [calcio|tennis|basket|tutti]
"""

import asyncio
import sys
from datetime import datetime

from betfair_scraper import scrape_betfair

FAST_INTERVAL = 60  # secondi tra un ciclo fast e l'altro


async def fast_loop(bf_sports: list[str]):
    """Ogni ~60s: Betfair Exchange."""
    run = 0
    while True:
        run += 1
        start = datetime.now()
        print(f"\n[Fast #{run}] {start.strftime('%H:%M:%S')} — Betfair Exchange")
        try:
            bf_total = await scrape_betfair(bf_sports)
            if isinstance(bf_total, Exception):
                print(f"  [Fast] Betfair error: {bf_total}")
                bf_total = 0
            elapsed = (datetime.now() - start).total_seconds()
            print(f"[Fast #{run}] done in {elapsed:.1f}s — BF: {bf_total} rows")
        except Exception as exc:
            print(f"[Fast #{run}] ERROR: {exc}")

        elapsed = (datetime.now() - start).total_seconds()
        sleep_for = max(5, FAST_INTERVAL - elapsed)
        print(f"[Fast] next in {sleep_for:.0f}s")
        await asyncio.sleep(sleep_for)


async def run_daemon():
    sport_filter = sys.argv[1] if len(sys.argv) > 1 else "tutti"
    bf_sports = ["calcio", "tennis", "basket"] if sport_filter == "tutti" else [sport_filter]

    print(f"[Daemon] Starting — sport={sport_filter}")
    print(f"[Daemon] Fast loop: ogni {FAST_INTERVAL}s")
    print(f"[Daemon] Press Ctrl+C to stop\n")

    await fast_loop(bf_sports)


if __name__ == "__main__":
    try:
        asyncio.run(run_daemon())
    except KeyboardInterrupt:
        print("\n[Daemon] Stopped.")
