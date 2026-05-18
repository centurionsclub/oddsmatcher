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

        logger.info("[Sisal] %s: page.url after nav = %s", league_name, self._page.url)
        await self._page.wait_for_timeout(500)
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

    # ── diagnostica struttura risposta ──────────────────────────────
    if avvenimenti:
        avv0 = avvenimenti[0]
        logger.info("[Sisal] DEBUG avv fields=%s", list(avv0.keys())[:12])
        logger.info(
            "[Sisal] DEBUG avv[0] key=%r descrizione=%r",
            avv0.get("key"), avv0.get("descrizione"),
        )
    if scommessa_map:
        sk0 = list(scommessa_map.keys())[0]
        sv0 = scommessa_map[sk0]
        logger.info("[Sisal] DEBUG scom key0=%r fields=%s", sk0, list(sv0.keys())[:10])
        logger.info(
            "[Sisal] DEBUG scom[0] codiceGruppo=%r descrizione=%r",
            sv0.get("codiceGruppo"), sv0.get("descrizione"),
        )
    if info_map:
        ik0 = list(info_map.keys())[0]
        iv0 = info_map[ik0]
        logger.info("[Sisal] DEBUG info key0=%r fields=%s", ik0, list(iv0.keys())[:10])
        logger.info(
            "[Sisal] DEBUG info[0] descrizione=%r quota=%r multipla=%r singola=%r",
            iv0.get("descrizione"), iv0.get("quota"), iv0.get("multipla"), iv0.get("singola"),
        )
    # ─────────────────────────────────────────────────────────────────

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
        logger.info(
            "[Sisal] DEBUG _extract_1x2 avv_key=%r prefix=%r — nessuna scommessa trovata",
            avv_key, avv_key.split("-")[0] if avv_key else "(vuoto)",
        )
        return None

    # Estrai le infoAggiuntive (esiti) di questa scommessa
    info_keys = [item.get("key", "") for item in esito_scommessa.get("infoAggiuntivaKeyDataList", [])]
    logger.info("[Sisal] DEBUG esito_scommessa trovata: desc=%r info_keys=%s", esito_scommessa.get("descrizione"), info_keys[:5])
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
