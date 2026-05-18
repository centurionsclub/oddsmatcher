"""Sisal pregame odds scraper.

Strategy: Playwright browser + network response interception on betting.sisal.it.

The SPA loads data from betting.sisal.it/api/lettura-palinsesto-sport/palinsesto/
prematch/v1/schedaManifestazione/... which returns:
  - avvenimentoFeList: list of events with descrizione ("INTER - MILAN"), data
  - scommessaMap:      bet types keyed by "codAvv-codPal-codGruppo"
  - infoAggiuntivaMap: actual quota values keyed by "codAvv-codPal-codGruppo-codInfoAgg"

We capture this response and parse it directly — no content-type filtering
(Sisal uses non-standard headers), domcontentloaded + 8s wait.
"""

import asyncio
import logging
import os
import re
import unicodedata
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, Response, async_playwright

from oddsmatcher_backend.scraper.centroquote import MatchOdds

logger = logging.getLogger(__name__)

BASE_URL = "https://www.sisal.it"
BETTING_URL = "https://betting.sisal.it"
BOOKMAKER = "Sisal"

# fmt: off
LEAGUES: list[tuple[str, str, str, str]] = [
    ("Serie A",          "calcio", "calcio/serie-a",                    "italia"),
    ("Serie B",          "calcio", "calcio/serie-b",                    "italia"),
    ("Premier League",   "calcio", "calcio/inghilterra/premier-league", "inghilterra"),
    ("La Liga",          "calcio", "calcio/spagna/liga",                "spagna"),
    ("Bundesliga",       "calcio", "calcio/germania/bundesliga",        "germania"),
    ("Ligue 1",          "calcio", "calcio/francia/ligue-1",            "francia"),
    ("Champions League", "calcio", "calcio/europa/champions-league",    "europa"),
    ("Europa League",    "calcio", "calcio/europa/europa-league",       "europa"),
    ("Conference League","calcio", "calcio/europa/conference-league",   "europa"),
]
# fmt: on

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Descrizioni outcomes Sisal → canonical (codiceScommessa=1, Esito Finale)
ESITO_MAP = {"1": "1", "X": "X", "2": "2"}


def _slugify(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_str.lower()).strip("-")


class SisalScraper:
    """Scrapes pregame odds from Sisal via Playwright network interception."""

    def __init__(self, browser=None):
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def _start(self) -> None:
        self._playwright = await async_playwright().start()

        proxy_url = os.environ.get("PROXY_URL")
        proxy = None
        if proxy_url:
            # http://user:pass@host:port → Playwright proxy dict
            import urllib.parse
            p = urllib.parse.urlparse(proxy_url)
            proxy = {
                "server": f"{p.scheme}://{p.hostname}:{p.port}",
                "username": p.username or "",
                "password": p.password or "",
            }
            logger.info("[Sisal] Usando proxy: %s:%s", p.hostname, p.port)

        self._browser = await self._playwright.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            proxy=proxy,
        )
        self._context = await self._browser.new_context(
            user_agent=_USER_AGENT,
            locale="it-IT",
            timezone_id="Europe/Rome",
            viewport={"width": 1280, "height": 900},
        )
        self._page = await self._context.new_page()

        logger.info("[Sisal] Navigating to homepage for Akamai warm-up...")
        try:
            await self._page.goto(
                f"{BASE_URL}/scommesse-matchpoint",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            await self._page.wait_for_timeout(4000)
            logger.info("[Sisal] Homepage loaded")
        except Exception as e:
            logger.warning("[Sisal] Homepage warm-up failed: %s", e)

    async def _stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._page = self._context = self._browser = self._playwright = None

    async def scrape_all(self) -> list[MatchOdds]:
        await self._start()
        try:
            return await self._scrape_leagues(None)
        finally:
            await self._stop()

    async def scrape_sport(self, sport: str) -> list[MatchOdds]:
        await self._start()
        try:
            return await self._scrape_leagues(sport)
        finally:
            await self._stop()

    async def _scrape_leagues(self, sport: str | None) -> list[MatchOdds]:
        all_results: list[MatchOdds] = []
        for league_name, sport_key, sisal_slug, country_slug in LEAGUES:
            if sport and sport_key != sport:
                continue
            try:
                results = await self._scrape_league(league_name, sport_key, sisal_slug, country_slug)
                all_results.extend(results)
                logger.info("[Sisal] %s — %d match+market rows", league_name, len(results))
            except Exception as exc:
                logger.error("[Sisal] %s failed: %s", league_name, exc, exc_info=True)
            await asyncio.sleep(1.0)

        logger.info("[Sisal] Total rows: %d", len(all_results))
        return all_results

    async def _scrape_league(
        self,
        league_name: str,
        sport_key: str,
        sisal_slug: str,
        country_slug: str,
    ) -> list[MatchOdds]:
        assert self._page is not None

        captured: list[dict[str, Any]] = []

        async def on_response(response: Response) -> None:
            url = response.url
            if "sisal.it" not in url:
                return
            try:
                body = await response.json()
                if isinstance(body, dict) and "avvenimentoFeList" in body:
                    captured.append({"url": url, "body": body})
                    logger.info("[Sisal] %s: catturata schedaManifestazione da %s", league_name, url)
                elif "schedaManifestazione" in url:
                    # Risposta JSON ma senza i dati attesi — log per diagnosi
                    logger.warning(
                        "[Sisal] %s: schedaManifestazione senza avvenimentoFeList: keys=%s",
                        league_name, list(body.keys())[:8],
                    )
            except Exception:
                if "schedaManifestazione" in url:
                    # Risposta non-JSON (probabile blocco Akamai)
                    logger.warning(
                        "[Sisal] %s: schedaManifestazione non-JSON status=%d url=%s",
                        league_name, response.status, url[:120],
                    )

        self._page.on("response", on_response)

        url = f"{BASE_URL}/scommesse-matchpoint/quote/{sisal_slug}"
        logger.info("[Sisal] Loading %s", url)
        try:
            # networkidle fa sempre timeout sulle SPA (polling continuo) — va bene:
            # il timeout scatta dopo 65s durante i quali on_response cattura schedaManifestazione
            await self._page.goto(url, wait_until="networkidle", timeout=65_000)
            logger.info("[Sisal] %s: networkidle raggiunto (inatteso)", league_name)
        except Exception as e:
            logger.info("[Sisal] %s: networkidle timeout (atteso): %s", league_name, type(e).__name__)

        page_title = await self._page.title()
        logger.info(
            "[Sisal] %s: page.url=%s title=%r",
            league_name, self._page.url, page_title,
        )
        await self._page.wait_for_timeout(500)
        self._page.remove_listener("response", on_response)

        if not captured:
            logger.warning("[Sisal] %s: nessuna schedaManifestazione catturata", league_name)
            return []

        # Prova ogni risposta catturata e restituisce la prima con risultati
        for item in sorted(captured, key=lambda x: len(x["body"].get("avvenimentoFeList", [])), reverse=True):
            rows = _parse_scheda(item["body"], league_name, sport_key, country_slug)
            if rows:
                logger.info("[Sisal] %s: %d righe da %s", league_name, len(rows), item["url"])
                return rows

        logger.warning("[Sisal] %s: nessuna riga estratta da %d risposte", league_name, len(captured))
        return []


# ── parser ────────────────────────────────────────────────────────────────────

def _parse_scheda(
    body: dict,
    league_name: str,
    sport_key: str,
    country_slug: str,
) -> list[MatchOdds]:
    """Parse a schedaManifestazione response into MatchOdds.

    Struttura reale API Sisal:
      avvenimentoFeList[i].key = 'codicePalinsesto-codiceAvvenimento'  e.g. '36211-257'
      scommessaMap key         = 'codicePalinsesto-codiceAvvenimento-codiceScommessa'
      infoAggiuntivaMap key    = 'codicePalinsesto-codiceAvvenimento-codiceScommessa-idInfoAggiuntiva'
    """
    avvenimenti: list[dict] = body.get("avvenimentoFeList", [])
    scommessa_map: dict = body.get("scommessaMap", {})
    info_map: dict = body.get("infoAggiuntivaMap", {})

    results: list[MatchOdds] = []

    for avv in avvenimenti:
        descrizione: str = avv.get("descrizione", "")
        data: str = avv.get("data", "") or ""
        avv_key: str = avv.get("key", "")

        parts = descrizione.split(" - ", 1)
        if len(parts) != 2:
            continue
        home = parts[0].strip().title()
        away = parts[1].strip().title()
        if not home or not away:
            continue

        event_name = f"{home} - {away}"
        event_time = data if data else None
        home_slug = _slugify(home)
        away_slug = _slugify(away)
        match_url = f"{BASE_URL}/scommesse-matchpoint/quote/{sport_key}/{home_slug}-{away_slug}"

        odds_1x2 = _extract_1x2(avv_key, scommessa_map, info_map)
        if odds_1x2:
            results.append(MatchOdds(
                sport=sport_key,
                league=league_name,
                home_team=home,
                away_team=away,
                event_name=event_name,
                event_time=event_time,
                match_url=match_url,
                market="1X2",
                bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": odds_1x2}],
            ))

    return results


def _extract_1x2(
    avv_key: str,
    scommessa_map: dict,
    info_map: dict,
) -> dict[str, float] | None:
    """Estrae le quote 1X2 per un avvenimento.

    avv_key = 'codicePalinsesto-codiceAvvenimento' (e.g. '36211-257')
    Le scommesse di questo avvenimento hanno chiavi che iniziano con avv_key + '-'.
    Il mercato Esito Finale (1X2) ha codiceScommessa=1.
    Le info (quote) hanno chiave avv_key + '-' + codiceScommessa + '-' + idInfoAggiuntiva.
    """
    prefix = avv_key + "-"

    # Trova la scommessa Esito Finale: prova codiceScommessa=1, poi cerca per descrizione
    esito_cod: str | None = None

    # Prima prova diretta con codiceScommessa=1
    if (prefix + "1") in scommessa_map:
        esito_cod = "1"
    else:
        # Cerca tra tutte le scommesse di questo avvenimento
        for k, scom in scommessa_map.items():
            if not k.startswith(prefix):
                continue
            desc = scom.get("descrizione", "").upper().strip()
            if "ESITO" in desc or "1X2" in desc or desc in ("1 X 2",):
                # Il codiceScommessa è l'ultima parte della key
                esito_cod = k.split("-")[-1]
                break

    if esito_cod is None:
        return None

    # Leggi le info (quote) per questo mercato
    odds: dict[str, float] = {}
    for i in range(10):
        info_key = f"{avv_key}-{esito_cod}-{i}"
        info = info_map.get(info_key)
        if info is None:
            if i > 0:
                break
            continue
        desc = info.get("descrizione", "").strip()
        quota = (
            info.get("quota")
            or info.get("multipla")
            or info.get("singola")
            or info.get("coeff")
        )
        if quota and float(quota) > 1.0:
            if desc in ESITO_MAP:
                odds[ESITO_MAP[desc]] = float(quota)
            elif not desc and len(odds) < 3:
                # Fallback posizionale: 0→1, 1→X, 2→2
                pos_map = {0: "1", 1: "X", 2: "2"}
                if i in pos_map:
                    odds[pos_map[i]] = float(quota)

    return odds if len(odds) == 3 else None
