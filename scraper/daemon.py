"""
Daemon — due velocità in parallelo:

  FAST (ogni ~60s):  Betfair Exchange (quote exchange aggiornate ogni minuto)
  SLOW (ogni 30min): CentroQuote — visita pagine dettaglio per 1X2, DC, BTTS, Over/Under

Nota: centroquote.it ha cambiato struttura — le quote per bookmaker non sono più
disponibili inline nelle pagine campionato, solo nelle pagine dettaglio partita.
Il loop fast aggiorna solo Betfair; CentroQuote si aggiorna ogni 30 min (slow loop).

Avvio:
    cd /path/to/Oddsmatcher/scraper
    python daemon.py [calcio|tennis|basket|tutti]
"""

import asyncio
import sys
from datetime import datetime

from scrape_centroquote import scrape_sport
from betfair_scraper import scrape_betfair

FAST_INTERVAL   = 60        # secondi tra un ciclo fast e l'altro
SLOW_INTERVAL   = 30 * 60  # 30 minuti tra slow full-scrape
SLOW_INIT_DELAY = 30        # secondi prima del primo slow pass (lascia partire il fast)


async def fast_loop(sport_filter: str, bf_sports: list[str]):
    """Ogni ~60s: solo Betfair Exchange (CentroQuote gestito dal slow loop ogni 30 min)."""
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


async def slow_loop(sport_filter: str):
    """Ogni 30 min: pagine dettaglio per DC, BTTS, Over/Under."""
    await asyncio.sleep(SLOW_INIT_DELAY)  # lascia avviare il fast loop
    run = 0
    while True:
        run += 1
        start = datetime.now()
        print(f"\n[Slow #{run}] {start.strftime('%H:%M:%S')} — full detail pages")
        try:
            total = await scrape_sport(sport_filter, fast_only=False)
            elapsed = (datetime.now() - start).total_seconds()
            print(f"[Slow #{run}] done in {elapsed:.1f}s — {total} rows upserted")
        except Exception as exc:
            print(f"[Slow #{run}] ERROR: {exc}")

        print(f"[Slow] next in {SLOW_INTERVAL//60} min")
        await asyncio.sleep(SLOW_INTERVAL)


async def run_daemon():
    sport_filter = sys.argv[1] if len(sys.argv) > 1 else "tutti"
    bf_sports = ["calcio", "tennis", "basket"] if sport_filter == "tutti" else [sport_filter]

    print(f"[Daemon] Starting — sport={sport_filter}")
    print(f"[Daemon] Fast loop: ogni {FAST_INTERVAL}s  |  Slow loop: ogni {SLOW_INTERVAL//60} min")
    print(f"[Daemon] Press Ctrl+C to stop\n")

    await asyncio.gather(
        fast_loop(sport_filter, bf_sports),
        slow_loop(sport_filter),
    )


if __name__ == "__main__":
    try:
        asyncio.run(run_daemon())
    except KeyboardInterrupt:
        print("\n[Daemon] Stopped.")
