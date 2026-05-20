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
# (league_name, sport_key, sisal_slug, country_slug, url_type)
# url_type = "quote" → /scommesse-matchpoint/quote/{sisal_slug}   (singola lega)
# url_type = "sport" → /scommesse-matchpoint/sport/{sisal_slug}   (intero sport, più risposte)
LEAGUES: list[tuple[str, str, str, str, str]] = [
    ("Serie A",           "calcio",  "calcio/serie-a",                    "italia",         "quote"),
    ("Serie B",           "calcio",  "calcio/serie-b",                    "italia",         "quote"),
    ("Premier League",    "calcio",  "calcio/inghilterra/premier-league", "inghilterra",    "quote"),
    ("La Liga",           "calcio",  "calcio/spagna/liga",                "spagna",         "quote"),
    ("Bundesliga",        "calcio",  "calcio/germania/bundesliga",        "germania",       "quote"),
    ("Ligue 1",           "calcio",  "calcio/francia/ligue-1",            "francia",        "quote"),
    ("Champions League",  "calcio",  "calcio/champions-league",           "europa",         "quote"),
    ("Europa League",     "calcio",  "calcio/europa-league",              "europa",         "quote"),
    ("Conference League", "calcio",  "calcio/conference-league",          "europa",         "quote"),
    ("Tennis",            "tennis",  "tennis",                                        "internazionale", "sport"),
    ("NBA",               "basket",  "basket/stati-uniti-d-america/nba",              "stati-uniti",    "quote"),
    ("Eurolega",          "basket",  "basket/eurolega",                               "europa",         "quote"),
    ("Serie A Basket",    "basket",  "basket/serie-a",                                "italia",         "quote"),
    ("Serie A2 Basket",   "basket",  "basket/serie-a2",                               "italia",         "quote"),
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


def _parse_sisal_date(date_str: str) -> str | None:
    """Normalise a Sisal date string to a UTC ISO-8601 string.

    Sisal's API returns dates in Italian local time (CEST = UTC+2 in summer,
    CET = UTC+1 in winter) in various formats.  We try the known patterns and
    fall back to returning the original string unchanged.
    """
    if not date_str:
        return None
    from datetime import datetime, timezone, timedelta

    FORMATS = [
        "%d/%m/%Y %H:%M:%S",   # "20/05/2026 20:30:00"
        "%d/%m/%Y %H:%M",      # "20/05/2026 20:30"
        "%Y-%m-%dT%H:%M:%S",   # "2026-05-20T20:30:00"
        "%Y-%m-%d %H:%M:%S",   # "2026-05-20 20:30:00"
        "%Y-%m-%d %H:%M",      # "2026-05-20 20:30"
    ]
    for fmt in FORMATS:
        try:
            dt_naive = datetime.strptime(date_str.strip(), fmt)
            # Treat as Italian local time → convert to UTC
            italy_offset = 2 if 3 <= dt_naive.month <= 10 else 1
            dt_local = dt_naive.replace(tzinfo=timezone(timedelta(hours=italy_offset)))
            return dt_local.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue

    # Already has TZ info (e.g. "2026-05-20T18:30:00Z" or "+02:00") — return as-is
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        pass

    return date_str  # unknown format — return unchanged


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
        for league_name, sport_key, sisal_slug, country_slug, url_type in LEAGUES:
            if sport and sport_key != sport:
                continue
            try:
                results = await self._scrape_league(league_name, sport_key, sisal_slug, url_type)
                all_results.extend(results)
                logger.info("[Sisal] %s — %d match+market rows", league_name, len(results))
            except Exception as exc:
                logger.error("[Sisal] %s failed: %s", league_name, exc, exc_info=True)
            await asyncio.sleep(0.3)  # breve pausa tra leghe (era 1.0s)

        logger.info("[Sisal] Total rows: %d", len(all_results))
        return all_results

    async def _scrape_league(
        self,
        league_name: str,
        sport_key: str,
        sisal_slug: str,
        url_type: str = "quote",
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
                    logger.info("[Sisal] %s: catturata schedaManifestazione (%d eventi)",
                                league_name, len(body.get("avvenimentoFeList", [])))
                elif "schedaManifestazione" in url:
                    logger.warning("[Sisal] %s: schedaManifestazione senza avvenimentoFeList: keys=%s",
                                   league_name, list(body.keys())[:8])
            except Exception:
                if "schedaManifestazione" in url:
                    logger.warning("[Sisal] %s: schedaManifestazione non-JSON status=%d url=%s",
                                   league_name, response.status, url[:120])

        self._page.on("response", on_response)

        if url_type == "sport":
            page_url = f"{BASE_URL}/scommesse-matchpoint/sport/{sisal_slug}"
        else:
            page_url = f"{BASE_URL}/scommesse-matchpoint/quote/{sisal_slug}"
        logger.info("[Sisal] Loading %s", page_url)

        if url_type == "quote":
            # Pagina singola lega: aspetta la PRIMA risposta schedaManifestazione,
            # poi smetti — non serve aspettare networkidle (65s inutili).
            try:
                async with self._page.expect_response(
                    lambda r: "schedaManifestazione" in r.url and "sisal.it" in r.url,
                    timeout=15_000,
                ) as _resp_info:
                    await self._page.goto(page_url, wait_until="domcontentloaded", timeout=15_000)
                # risposta già catturata da on_response; aspetta brevemente eventuali extra
                await self._page.wait_for_timeout(400)
            except Exception as e:
                logger.info("[Sisal] %s: nessuna schedaManifestazione in 15s (%s)", league_name, type(e).__name__)
                await self._page.wait_for_timeout(200)
        else:
            # Pagina sport (tennis): genera PIÙ risposte, una per torneo —
            # aspetta domcontentloaded + pausa fissa per raccoglierle tutte.
            try:
                await self._page.goto(page_url, wait_until="domcontentloaded", timeout=15_000)
            except Exception as e:
                logger.info("[Sisal] %s: goto error: %s", league_name, type(e).__name__)
            await self._page.wait_for_timeout(8_000)

        self._page.remove_listener("response", on_response)

        if not captured:
            logger.warning("[Sisal] %s: nessuna schedaManifestazione catturata", league_name)
            return []

        if url_type == "sport":
            # Pagine sport-level: combina TUTTE le risposte (una per torneo/competizione)
            all_rows: list[MatchOdds] = []
            seen_events: set[str] = set()
            for item in captured:
                rows = _parse_scheda(item["body"], league_name, sport_key, sisal_slug)
                for row in rows:
                    key = f"{row.event_name}|{row.market}|{row.bookmaker_odds[0]['bookmaker'] if row.bookmaker_odds else ''}"
                    if key not in seen_events:
                        seen_events.add(key)
                        all_rows.append(row)
            logger.info("[Sisal] %s: %d righe da %d risposte", league_name, len(all_rows), len(captured))
            return all_rows
        else:
            # Pagina singola lega: prima risposta con risultati
            for item in sorted(captured, key=lambda x: len(x["body"].get("avvenimentoFeList", [])), reverse=True):
                rows = _parse_scheda(item["body"], league_name, sport_key, sisal_slug)
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
    sisal_slug: str,
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
        event_time = _parse_sisal_date(data) if data else None
        home_slug = _slugify(home)
        away_slug = _slugify(away)
        match_url = f"{BASE_URL}/scommesse-matchpoint/evento/{sisal_slug}/{home_slug}-{away_slug}"

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
                if "1X2" in desc or "ESITO FINALE" in desc or "TESTA A TESTA RISULTATO" in desc or "T/T MATCH" in desc:
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

    return odds if len(odds) >= 2 else None  # 3 per calcio, 2 per tennis/basket (no pareggio)


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
            # X.5 pattern * 100 (es. 250→2.5, 350→3.5, 19150→191.5 per basket)
            if val % 100 == 50 and val >= 50:
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

    Strategia: scansiona tutte le voci infoAggiuntivaMap dell'avvenimento e
    controlla se la esitoList contiene esiti "OVER"/"UNDER" — così non dipende
    dalla descrizione del mercato (che varia tra versioni API Sisal).

    Returns: lista di dict con chiavi tipo "Over 2.5" / "Under 2.5"
    """
    results: list[dict[str, float]] = []
    seen_lines: set[str] = set()

    prefix = avv_key + "-"
    for info_key, info in info_map.items():
        if not info_key.startswith(prefix):
            continue

        esito_list = info.get("esitoList", [])
        if not esito_list:
            continue

        # Controlla se questa entry ha esiti Over/Under
        odds: dict[str, float] = {}
        for esito in esito_list:
            desc = esito.get("descrizione", "").strip().upper()
            quota = esito.get("quota")
            stato = esito.get("stato", 0)
            if not quota or stato != 1:
                continue
            if "OVER" in desc or desc == "O":
                odds["__over__"] = round(float(quota) / 100.0, 2)
            elif "UNDER" in desc or desc == "U":
                odds["__under__"] = round(float(quota) / 100.0, 2)

        if len(odds) != 2:
            continue  # non è un mercato Over/Under

        # Determina la linea dal key (ultima parte dopo "avv_key-cod-")
        parts = info_key[len(prefix):].split("-")
        id_info_str = parts[-1] if parts else ""
        line = _decode_ou_line(id_info_str, info)
        if not line:
            logger.debug("[Sisal] O/U linea non decodificabile: key=%s info=%s", info_key, {k: info.get(k) for k in ("descrizione", "quota", "idInfoAggiuntiva")})
            continue

        if line in seen_lines:
            continue
        seen_lines.add(line)

        result = {f"Over {line}": odds["__over__"], f"Under {line}": odds["__under__"]}
        results.append(result)
        logger.debug("[Sisal] O/U estratto: key=%s linea=%s odds=%s", info_key, line, result)

    return results
