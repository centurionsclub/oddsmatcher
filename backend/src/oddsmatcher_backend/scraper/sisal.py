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

        logger.debug("[Sisal] %s: page.url=%s", league_name, self._page.url)
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

# Keywords che identificano il mercato Over/Under nella descrizione scommessa Sisal
_OU_KEYWORDS = ("TOTALE GOL", "OVER/UNDER", "TOTAL GOALS", "O/U")

# Keywords che identificano il mercato Goal/No Goal
_GNG_KEYWORDS = ("GOAL/NOGOAL", "GOAL/NO GOAL", "GG/NG")


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
    _logged_scommesse = False  # log scommesse disponibili solo una volta per lega

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

        # Log tutte le scommesse disponibili per il primo avvenimento (debug struttura API)
        if not _logged_scommesse:
            _logged_scommesse = True
            avv_scommesse = {
                k: v.get("descrizione", "")
                for k, v in scommessa_map.items()
                if k.startswith(avv_key + "-")
            }
            logger.info(
                "[Sisal] %s — scommesse disponibili per '%s': %s",
                league_name, event_name, avv_scommesse,
            )
            # Log anche alcune chiavi infoAggiuntivaMap per capire la struttura
            avv_info_keys = [k for k in info_map if k.startswith(avv_key + "-")][:20]
            logger.info(
                "[Sisal] %s — info keys (prime 20): %s",
                league_name, avv_info_keys,
            )

        # 1X2
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

        # Over/Under
        ou_rows = _extract_over_under(avv_key, scommessa_map, info_map)
        for ou_odds in ou_rows:
            results.append(MatchOdds(
                sport=sport_key,
                league=league_name,
                home_team=home,
                away_team=away,
                event_name=event_name,
                event_time=event_time,
                match_url=match_url,
                market="Over/Under",
                bookmaker_odds=[{"bookmaker": BOOKMAKER, "odds": ou_odds}],
            ))

    return results


_ESITO_FINALE_COD = "3"  # codiceScommessa=3 → "1X2 ESITO FINALE"


def _extract_1x2(
    avv_key: str,
    scommessa_map: dict,
    info_map: dict,
) -> dict[str, float] | None:
    """Estrae le quote 1X2 per un avvenimento.

    Struttura reale:
      - codiceScommessa=3 → "1X2 ESITO FINALE"
      - info key = avv_key + '-3-0'  (idInfoAggiuntiva sempre 0)
      - odds in info['esitoList'][i]['quota'] (intero, es. 172 = 1.72)
      - descrizione esito: "1", "X", "2"
    """
    # Verifica che il mercato 1X2 esista per questo avvenimento
    scom_key = f"{avv_key}-{_ESITO_FINALE_COD}"
    if scom_key not in scommessa_map:
        # Fallback: cerca per descrizione
        found = False
        for k, scom in scommessa_map.items():
            if k.startswith(avv_key + "-"):
                desc = scom.get("descrizione", "").upper().strip()
                if "1X2" in desc or "ESITO FINALE" in desc:
                    scom_key = k
                    found = True
                    break
        if not found:
            return None

    esito_cod = scom_key.split("-")[-1]
    info_key = f"{avv_key}-{esito_cod}-0"
    info = info_map.get(info_key)
    if not info:
        return None

    esito_list = info.get("esitoList", [])
    odds: dict[str, float] = {}
    for esito in esito_list:
        desc = esito.get("descrizione", "").strip()
        quota = esito.get("quota")
        stato = esito.get("stato", 0)
        if quota and stato == 1 and desc in ESITO_MAP:
            # quota è intero centesimale: 172 → 1.72
            odds[ESITO_MAP[desc]] = round(float(quota) / 100.0, 2)

    return odds if len(odds) == 3 else None


def _decode_ou_line(id_info_str: str, info: dict) -> str | None:
    """Cerca di ricavare la linea Over/Under (es. '2.5') da una voce infoAggiuntivaMap.

    Strategie (dalla più affidabile alla meno):
      1. info['descrizione'] contiene direttamente la linea (es. "2.5")
      2. idInfoAggiuntiva è la linea * 10 (es. 25 → "2.5", 35 → "3.5")
      3. idInfoAggiuntiva è la linea * 100 (es. 250 → "2.5")
    """
    # Strategia 1: campo descrizione sull'info
    desc = str(info.get("descrizione", "")).strip()
    if re.match(r'^\d+[.,]\d+$', desc):
        return desc.replace(",", ".")

    # Strategia 2/3: decodifica numerica dell'id
    try:
        val = int(id_info_str)
        if val > 0:
            # X.5 pattern: val % 10 == 5 (es. 25→2.5, 35→3.5, 45→4.5)
            if val % 10 == 5 and 5 <= val <= 995:
                return f"{val // 10}.5"
            # X.5 pattern * 100 (es. 250→2.5, 350→3.5)
            if val % 100 == 50 and 50 <= val <= 9950:
                return f"{val // 100}.5"
    except (ValueError, TypeError):
        pass

    # Strategia 4: la chiave stessa è già una stringa decimale
    if re.match(r'^\d+[.,]\d+$', id_info_str):
        return id_info_str.replace(",", ".")

    return None


def _extract_over_under(
    avv_key: str,
    scommessa_map: dict,
    info_map: dict,
) -> list[dict[str, float]]:
    """Estrae le quote Over/Under per tutte le linee disponibili.

    Returns: lista di dict con chiavi tipo "Over 2.5" / "Under 2.5"
    Ogni dict = una linea (es. [{"Over 2.5": 1.65, "Under 2.5": 2.15}, ...])
    """
    results: list[dict[str, float]] = []

    # Trova i codiceScommessa corrispondenti a Over/Under
    ou_cod_scommessa: list[str] = []
    for k, scom in scommessa_map.items():
        if not k.startswith(avv_key + "-"):
            continue
        desc = scom.get("descrizione", "").upper().strip()
        if any(kw in desc for kw in _OU_KEYWORDS):
            # k = "avv_key-codiceScommessa"
            cod = k[len(avv_key) + 1:]
            ou_cod_scommessa.append(cod)
            logger.debug("[Sisal] O/U scommessa trovata: cod=%s desc='%s'", cod, scom.get("descrizione"))

    if not ou_cod_scommessa:
        return results

    for cod in ou_cod_scommessa:
        prefix = f"{avv_key}-{cod}-"
        for info_key, info in info_map.items():
            if not info_key.startswith(prefix):
                continue

            id_info_str = info_key[len(prefix):]
            line = _decode_ou_line(id_info_str, info)
            if not line:
                logger.debug("[Sisal] O/U linea non decodificabile: key=%s info_keys=%s", info_key, list(info.keys())[:6])
                continue

            esito_list = info.get("esitoList", [])
            odds: dict[str, float] = {}
            for esito in esito_list:
                desc = esito.get("descrizione", "").strip().upper()
                quota = esito.get("quota")
                stato = esito.get("stato", 0)
                if quota and stato == 1:
                    if "OVER" in desc or desc == "O":
                        odds[f"Over {line}"] = round(float(quota) / 100.0, 2)
                    elif "UNDER" in desc or desc == "U":
                        odds[f"Under {line}"] = round(float(quota) / 100.0, 2)

            if len(odds) == 2:
                results.append(odds)
                logger.debug("[Sisal] O/U estratto: linea=%s odds=%s", line, odds)

    return results
