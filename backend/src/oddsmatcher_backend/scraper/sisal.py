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
    ("Serie A",          "calcio", "calcio/serie-a",                "italia"),
    ("Serie B",          "calcio", "calcio/serie-b",                "italia"),
    ("Champions League", "calcio", "calcio/calcio-champions-league","europa"),
    ("Europa League",    "calcio", "calcio/calcio-europa-league",   "europa"),
    ("Conference League","calcio", "calcio/calcio-conference-league","europa"),
    ("Premier League",   "calcio", "calcio/calcio-premier-league",  "inghilterra"),
    ("La Liga",          "calcio", "calcio/calcio-la-liga",         "spagna"),
    ("Bundesliga",       "calcio", "calcio/calcio-bundesliga",      "germania"),
    ("Ligue 1",          "calcio", "calcio/calcio-ligue-1",         "francia"),
]
# fmt: on

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# codiceGruppo = 1 → Esito finale (1X2)
ESITO_GRUPPO = 1
# Descrizioni outcomes Sisal → canonical
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
        self._browser = await self._playwright.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
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
            # Cattura da betting.sisal.it E www.sisal.it — senza filtro content-type
            if "sisal.it" not in url:
                return
            try:
                body = await response.json()
                # Interessa solo la risposta con i dati prematch
                if isinstance(body, dict) and "avvenimentoFeList" in body:
                    captured.append({"url": url, "body": body})
                    logger.info("[Sisal] %s: catturata schedaManifestazione da %s", league_name, url)
            except Exception:
                pass

        self._page.on("response", on_response)

        url = f"{BASE_URL}/scommesse-matchpoint/quote/{sisal_slug}"
        logger.info("[Sisal] Loading %s", url)
        try:
            # Usa expect_response per attendere esattamente la schedaManifestazione
            # (si registra PRIMA della navigazione per non perdere la risposta)
            async with self._page.expect_response(
                lambda r: "schedaManifestazione" in r.url and "sisal.it" in r.url,
                timeout=55_000,
            ):
                await self._page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            # Brevissima pausa per assicurarsi che on_response abbia elaborato
            await self._page.wait_for_timeout(500)
        except Exception as e:
            logger.warning("[Sisal] %s: timeout/errore navigazione: %s", league_name, e)

        self._page.remove_listener("response", on_response)

        if not captured:
            logger.warning("[Sisal] %s: nessuna schedaManifestazione catturata", league_name)
            return []

        # Prendi la risposta più ricca (più eventi)
        best = max(captured, key=lambda x: len(x["body"].get("avvenimentoFeList", [])))
        logger.info(
            "[Sisal] %s: parsing %d eventi da %s",
            league_name,
            len(best["body"].get("avvenimentoFeList", [])),
            best["url"],
        )
        return _parse_scheda(best["body"], league_name, sport_key, country_slug)


# ── parser ────────────────────────────────────────────────────────────────────

def _parse_scheda(
    body: dict,
    league_name: str,
    sport_key: str,
    country_slug: str,
) -> list[MatchOdds]:
    """Parse a schedaManifestazione response into MatchOdds."""
    avvenimenti: list[dict] = body.get("avvenimentoFeList", [])
    scommessa_map: dict = body.get("scommessaMap", {})
    info_map: dict = body.get("infoAggiuntivaMap", {})

    results: list[MatchOdds] = []

    for avv in avvenimenti:
        descrizione: str = avv.get("descrizione", "")
        data: str = avv.get("data", "") or ""
        avv_key: str = avv.get("key", "")

        # "INTER - MILAN" → home, away
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

        # Trova la scommessa Esito finale (codiceGruppo == 1)
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
    """Estrae le quote 1X2 dall'infoAggiuntivaMap per un avvenimento."""
    # Cerca scommesse per questo avvenimento con codiceGruppo == 1 (Esito finale)
    esito_scommessa = None
    for key, scom in scommessa_map.items():
        if not key.startswith(avv_key.split("-")[0]):  # stesso codiceAvvenimento
            continue
        if scom.get("codiceGruppo") == ESITO_GRUPPO:
            esito_scommessa = scom
            break

    if not esito_scommessa:
        # Fallback: cerca per descrizione
        for scom in scommessa_map.values():
            desc = scom.get("descrizione", "").upper()
            if "ESITO" in desc or "1X2" in desc:
                cod_avv = str(scom.get("codiceAvvenimento", ""))
                if avv_key.startswith(cod_avv):
                    esito_scommessa = scom
                    break

    if not esito_scommessa:
        return None

    # Estrai le infoAggiuntive (esiti) di questa scommessa
    info_keys = [item.get("key", "") for item in esito_scommessa.get("infoAggiuntivaKeyDataList", [])]
    odds: dict[str, float] = {}

    for ik in info_keys:
        info = info_map.get(ik, {})
        desc = info.get("descrizione", "").strip()
        # La quota può essere in 'quota', 'multipla', 'singola', 'coeff'
        quota = (
            info.get("quota")
            or info.get("multipla")
            or info.get("singola")
            or info.get("coeff")
        )
        if desc in ESITO_MAP and quota and float(quota) > 1.0:
            odds[ESITO_MAP[desc]] = float(quota)

    if len(odds) == 3:
        return odds

    # Fallback: i valori numerici >1.0 ordinati potrebbero essere 1, X, 2
    if not odds and info_keys:
        vals = []
        for ik in info_keys[:3]:
            info = info_map.get(ik, {})
            q = info.get("quota") or info.get("multipla") or info.get("singola")
            if q and float(q) > 1.0:
                vals.append(float(q))
        if len(vals) == 3:
            return {"1": vals[0], "X": vals[1], "2": vals[2]}

    return None
