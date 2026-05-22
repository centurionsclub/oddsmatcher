"""Supabase client for upserting scraped odds data."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

from supabase import create_client, Client

from oddsmatcher_backend.config.settings import settings

if TYPE_CHECKING:
    from oddsmatcher_backend.scraper.models import MatchOdds

logger = logging.getLogger(__name__)

# ── Team-name normalisation ──────────────────────────────────────────────────
# Maps lowercase alias → canonical name used across all bookmakers.
# Canonical = short Italian-style form used by the majority of Italian sites.
_TEAM_ALIASES: dict[str, str] = {
    # ── Italian Serie A / Serie B ────────────────────────────────────────────
    "hellas verona":            "Verona",
    "as roma":                  "Roma",
    "a.s. roma":                "Roma",
    "ac milan":                 "Milan",
    "a.c. milan":               "Milan",
    "inter milan":              "Inter",
    "fc internazionale":        "Inter",
    "internazionale":           "Inter",
    "internazionale milano":    "Inter",
    "juventus fc":              "Juventus",
    "juventus f.c.":            "Juventus",
    "ssc napoli":               "Napoli",
    "ss lazio":                 "Lazio",
    "s.s. lazio":               "Lazio",
    "acf fiorentina":           "Fiorentina",
    "udinese calcio":           "Udinese",
    "bologna fc":               "Bologna",
    "torino fc":                "Torino",
    "cagliari calcio":          "Cagliari",
    "atalanta bc":              "Atalanta",
    "genoa cfc":                "Genoa",
    "genoa fc":                 "Genoa",
    "empoli fc":                "Empoli",
    "como 1907":                "Como",
    "venezia fc":               "Venezia",
    "us lecce":                 "Lecce",
    "ac monza":                 "Monza",
    "us salernitana":           "Salernitana",
    "frosinone calcio":         "Frosinone",
    "us cremonese":             "Cremonese",
    "ac cesena":                "Cesena",
    "cosenza calcio":           "Cosenza",
    "us catanzaro":             "Catanzaro",
    "ssd palermo":              "Palermo",
    "palermo fc":               "Palermo",
    "us sassuolo":              "Sassuolo",
    "sassuolo calcio":          "Sassuolo",
    "parma calcio":             "Parma",
    "fc sudtirol":              "Sudtirol",
    # ── Spanish La Liga / lower ──────────────────────────────────────────────
    "fc barcelona":             "Barcellona",
    "barcelona fc":             "Barcellona",
    "barcelona":                "Barcellona",
    "atletico madrid":          "Atletico Madrid",
    "atlético madrid":          "Atletico Madrid",
    "atlético de madrid":       "Atletico Madrid",
    "atletico de madrid":       "Atletico Madrid",
    "atletico":                 "Atletico Madrid",
    "athletic bilbao":          "Athletic Bilbao",
    "athletic club":            "Athletic Bilbao",
    "real betis":               "Betis",
    "betis balompie":           "Betis",
    "rc celta":                 "Celta Vigo",
    "celta de vigo":            "Celta Vigo",
    "rcd espanyol":             "Espanyol",
    "rcd mallorca":             "Maiorca",
    "mallorca":                 "Maiorca",
    "deportivo alaves":         "Alavés",
    "alaves":                   "Alavés",
    "ca osasuna":               "Osasuna",
    "getafe cf":                "Getafe",
    "girona fc":                "Girona",
    "villarreal cf":            "Villarreal",
    "sevilla fc":               "Siviglia",
    "sevilla":                  "Siviglia",
    "real valladolid":          "Valladolid",
    "ud las palmas":            "Las Palmas",
    "real madrid cf":           "Real Madrid",
    "rayo vallecano":           "Rayo Vallecano",
    "ud almeria":               "Almeria",
    "cadiz cf":                 "Cadiz",
    # ── English Premier League / Championship ────────────────────────────────
    "manchester utd":           "Manchester United",
    "man united":               "Manchester United",
    "man utd":                  "Manchester United",
    "man city":                 "Manchester City",
    "manchester city fc":       "Manchester City",
    "wolverhampton wanderers":  "Wolverhampton",
    "wolves":                   "Wolverhampton",
    "nottingham forest":        "Nottingham",
    "newcastle united":         "Newcastle",
    "aston villa fc":           "Aston Villa",
    "west ham united":          "West Ham",
    "chelsea fc":               "Chelsea",
    "brighton & hove albion":   "Brighton",
    "brighton and hove albion": "Brighton",
    "tottenham hotspur":        "Tottenham",
    "spurs":                    "Tottenham",
    "crystal palace fc":        "Crystal Palace",
    "liverpool fc":             "Liverpool",
    "arsenal fc":               "Arsenal",
    "fulham fc":                "Fulham",
    "burnley fc":               "Burnley",
    "leeds united":             "Leeds",
    "leicester city":           "Leicester",
    "leicester city fc":        "Leicester",
    "bournemouth afc":          "Bournemouth",
    "sunderland afc":           "Sunderland",
    "ipswich town":             "Ipswich",
    "sheffield united":         "Sheffield United",
    "brentford fc":             "Brentford",
    # ── German Bundesliga ────────────────────────────────────────────────────
    "bayer leverkusen":         "Leverkusen",
    "bayer 04 leverkusen":      "Leverkusen",
    "borussia dortmund":        "Dortmund",
    "bvb":                      "Dortmund",
    "rb leipzig":               "RB Leipzig",
    "rasenballsport leipzig":   "RB Leipzig",
    "eintracht frankfurt":      "Frankfurt",
    "sc freiburg":              "Freiburg",
    "vfl wolfsburg":            "Wolfsburg",
    "vfb stuttgart":            "Stuttgart",
    "tsg hoffenheim":           "Hoffenheim",
    "tsg 1899 hoffenheim":      "Hoffenheim",
    "fc augsburg":              "Augsburg",
    "sv werder bremen":         "Werder Bremen",
    "werder bremen":            "Werder Bremen",
    "1. fc union berlin":       "Union Berlin",
    "1. fc koln":               "Colonia",
    "fc koln":                  "Colonia",
    "borussia monchengladbach": "M'gladbach",
    "borussia mönchengladbach": "M'gladbach",
    "greuther fürth":           "Greuther Furth",
    "fc heidenheim":            "Heidenheim",
    "1. fc heidenheim":         "Heidenheim",
    "sv darmstadt 98":          "Darmstadt",
    "darmstadt":                "Darmstadt",
    # ── French Ligue 1 ──────────────────────────────────────────────────────
    "paris saint-germain":      "PSG",
    "paris sg":                 "PSG",
    "olympique marseille":      "Marsiglia",
    "marseille":                "Marsiglia",
    "olympique lyonnais":       "Lione",
    "olympique lione":          "Lione",
    "lyon":                     "Lione",
    "stade rennais":            "Rennes",
    "stade rennais fc":         "Rennes",
    "as monaco":                "Monaco",
    "losc lille":               "Lille",
    "lille osc":                "Lille",
    "ogc nice":                 "Nizza",
    "rc strasbourg":            "Strasburgo",
    "stade de reims":           "Reims",
    "stade brestois 29":        "Brest",
    "stade brestois":           "Brest",
    "montpellier hsc":          "Montpellier",
    "rc lens":                  "Lens",
    "toulouse fc":              "Tolosa",
    "havre ac":                 "Le Havre",
    "le havre ac":              "Le Havre",
    "clermont foot":            "Clermont",
    "fc metz":                  "Metz",
    # ── European / International ─────────────────────────────────────────────
    "olympiakos":               "Olympiacos",
    "olympiakos cfp":           "Olympiacos",
    "fenerbahce sk":            "Fenerbahce",
    "galatasaray sk":           "Galatasaray",
    "besiktas jk":              "Besiktas",
}


def _normalize_team(name: str) -> str:
    """Return canonical team name for cross-bookmaker event matching."""
    s = name.strip()
    return _TEAM_ALIASES.get(s.lower(), s)


def _normalize_event_name(event_name: str) -> str:
    """Normalize both team names in 'Home - Away' for cross-bookmaker matching."""
    sep = " - "
    idx = event_name.find(sep)
    if idx >= 0:
        home = _normalize_team(event_name[:idx])
        away = _normalize_team(event_name[idx + len(sep):])
        return f"{home}{sep}{away}"
    return event_name


def _normalize_market_outcome(market: str, outcome: str) -> tuple[str, str]:
    """Convert scraper market/outcome names to the live_odds canonical format.

    live_odds expects:
      - market="1X2",       outcome="1" | "X" | "2"
      - market="DC",        outcome="1X" | "X2" | "12"
      - market="BTTS",      outcome="Goal" | "No Goal"
      - market="Over/Under",outcome="Over 1.5" | "Under 2.5" | …
    """
    # Italian / API abbreviation → English outcome names
    OUTCOME_MAP: dict[str, str] = {
        "GG": "Goal",
        "NG": "No Goal",
        "Si": "Goal",
        "No": "No Goal",
        "Oltre": "Over",
        "Meno": "Under",
        "O": "Over",
        "U": "Under",
    }
    outcome_norm = OUTCOME_MAP.get(outcome, outcome)

    # "Over/Under 1.5" → market="Over/Under", outcome="Over 1.5" / "Under 1.5"
    if market.startswith("Over/Under "):
        spread = market.split(" ", 1)[1]          # e.g. "1.5"
        side = outcome_norm if outcome_norm in ("Over", "Under") else outcome_norm
        return "Over/Under", f"{side} {spread}"

    # Scraper market name → live_odds market name
    MARKET_MAP: dict[str, str] = {
        "Goal No Goal": "BTTS",
        "Doppia Chance": "DC",
    }
    market_norm = MARKET_MAP.get(market, market)

    return market_norm, outcome_norm


class SupabaseWriter:
    """Writes scraped odds to Supabase (odds_events + odds_data tables)."""

    def __init__(self):
        cfg = settings.supabase
        if not cfg.url or not cfg.service_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
        self.client: Client = create_client(cfg.url, cfg.service_key)
        logger.info("Supabase client initialized")

    def upsert_event(self, event: dict[str, Any]) -> str | None:
        """Upsert a match event and return its UUID.

        Args:
            event: Dict with keys: sport, league, home_team, away_team, event_name, event_time

        Returns:
            The event UUID, or None on failure.
        """
        try:
            result = (
                self.client.table("odds_events")
                .upsert(event, on_conflict="home_team,away_team")
                .execute()
            )
            if result.data:
                return result.data[0]["id"]
        except Exception as e:
            logger.error("Failed to upsert event %s: %s", event.get("event_name"), e)
        return None

    def upsert_odds(self, odds_rows: list[dict[str, Any]]) -> int:
        """Upsert a batch of odds rows.

        Args:
            odds_rows: List of dicts with keys:
                event_id, bookmaker, market, outcome, odds

        Returns:
            Number of rows successfully upserted.
        """
        if not odds_rows:
            return 0

        try:
            result = (
                self.client.table("odds_data")
                .upsert(odds_rows, on_conflict="event_id,bookmaker,market,outcome")
                .execute()
            )
            return len(result.data) if result.data else 0
        except Exception as e:
            logger.error("Failed to upsert %d odds rows: %s", len(odds_rows), e)
            return 0

    def write_direct_live_odds(self, bookmaker_name: str, results: "list[MatchOdds]") -> int:
        """Generic writer for directly-scraped bookmakers (Sisal, Snai, etc.).

        Deletes existing rows for affected events and inserts fresh ones.
        """
        if not results:
            return 0

        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
        rows: list[dict[str, Any]] = []

        for match in results:
            for bm in match.bookmaker_odds:
                # Use the per-entry bookmaker name (e.g. Pinnacle, Codere, MarathonBet)
                # falling back to the scraper-level bookmaker_name for single-bk scrapers.
                bk_name = bm.get("bookmaker") or bookmaker_name
                bk_url  = bm.get("url") or match.match_url
                for outcome_raw, odds_val in bm["odds"].items():
                    market_norm, outcome_norm = _normalize_market_outcome(match.market, outcome_raw)
                    row: dict[str, Any] = {
                        "bookmaker": bk_name,
                        "sport": match.sport,
                        "league": match.league,
                        "event_name": _normalize_event_name(match.event_name),
                        "market": market_norm,
                        "outcome": outcome_norm,
                        "odds": float(odds_val),
                        "expires_at": expires_at,
                        "match_url": bk_url,
                    }
                    if match.event_time:
                        row["event_time"] = match.event_time
                    rows.append(row)

        if not rows:
            return 0

        # Diagnostic: log breakdown by market before writing
        from collections import Counter, defaultdict
        market_counts = Counter(r["market"] for r in rows)
        event_names = list({r["event_name"] for r in rows})
        logger.info("%s live_odds pre-write: %d rows, markets=%s, events=%d",
                    bookmaker_name, len(rows), dict(market_counts), len(event_names))

        # Delete stale rows grouped by actual bookmaker (handles multi-bk scrapers)
        bk_events: dict[str, set] = defaultdict(set)
        for r in rows:
            bk_events[r["bookmaker"]].add(r["event_name"])

        for bk, evts in bk_events.items():
            try:
                del_result = (
                    self.client.table("live_odds")
                    .delete()
                    .eq("bookmaker", bk)
                    .in_("event_name", list(evts))
                    .execute()
                )
                logger.info("%s live_odds: deleted %d stale rows for %s",
                            bookmaker_name, len(del_result.data) if del_result.data else 0, bk)
            except Exception as e:
                logger.error("Failed to delete stale %s live_odds: %s", bk, e)

        BATCH = 500
        inserted = 0
        for i in range(0, len(rows), BATCH):
            batch = rows[i : i + BATCH]
            batch_markets = Counter(r["market"] for r in batch)
            try:
                result = self.client.table("live_odds").insert(batch).execute()
                n = len(result.data) if result.data else 0
                inserted += n
                logger.info("%s live_odds batch %d: inserted %d/%d rows markets=%s",
                            bookmaker_name, i // BATCH, n, len(batch), dict(batch_markets))
            except Exception as e:
                logger.error("Failed to insert %s live_odds batch %d (markets=%s): %s",
                             bookmaker_name, i // BATCH, dict(batch_markets), e)

        logger.info("%s live_odds: %d rows for %d events", bookmaker_name, inserted, len(event_names))
        return inserted

    def write_lottomatica_live_odds(self, results: "list[MatchOdds]") -> int:
        """Replace Lottomatica/GoldBet/PlanetWin365 rows in live_odds with freshly scraped data.

        Lottomatica, GoldBet and PlanetWin365 share the same backend and always
        have identical odds, so we write one set of rows and copy it for all three.

        Returns:
            Total number of rows inserted across all three bookmakers.
        """
        if not results:
            return 0

        # Bookmakers to write: (name, base URL per riscrivere match_url, fallback URL)
        LOTTOMATICA_BASE = "https://www.lottomatica.it"
        TARGETS = [
            ("Lottomatica",  LOTTOMATICA_BASE,                    "https://www.lottomatica.it/scommesse/sport/"),
            ("GoldBet",      "https://www.goldbet.it",            "https://www.goldbet.it/scommesse/sport/"),
            ("Planetwin365", "https://www.planetwin365.it/it",    "https://www.planetwin365.it/it/scommesse/sport/"),
        ]

        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()

        # Build base rows (bookmaker-agnostic)
        base_rows: list[dict[str, Any]] = []
        for match in results:
            for bm in match.bookmaker_odds:
                for outcome_raw, odds_val in bm["odds"].items():
                    market_norm, outcome_norm = _normalize_market_outcome(match.market, outcome_raw)
                    row: dict[str, Any] = {
                        "sport": match.sport,
                        "league": match.league,
                        "event_name": _normalize_event_name(match.event_name),
                        "market": market_norm,
                        "outcome": outcome_norm,
                        "odds": float(odds_val),
                        "expires_at": expires_at,
                        "match_url": match.match_url,
                    }
                    if match.event_time:
                        row["event_time"] = match.event_time
                    base_rows.append(row)

        if not base_rows:
            logger.warning("write_lottomatica_live_odds: no rows to write after normalization")
            return 0

        event_names = list({r["event_name"] for r in base_rows})
        BATCH = 500
        total_inserted = 0

        for bm_name, bm_base, fallback_url in TARGETS:
            # Delete stale rows for this bookmaker
            try:
                (
                    self.client.table("live_odds")
                    .delete()
                    .eq("bookmaker", bm_name)
                    .in_("event_name", event_names)
                    .execute()
                )
            except Exception as e:
                logger.error("Failed to delete stale %s live_odds: %s", bm_name, e)

            # Build rows for this bookmaker — riscrivi il dominio base nell'URL
            def _rewrite(url: str, base: str, fallback: str) -> str:
                if url and url.startswith(LOTTOMATICA_BASE):
                    return url.replace(LOTTOMATICA_BASE, base, 1)
                return url or fallback

            bm_rows = [
                {**r, "bookmaker": bm_name, "match_url": _rewrite(r["match_url"], bm_base, fallback_url)}
                for r in base_rows
            ]

            # Insert in batches
            for i in range(0, len(bm_rows), BATCH):
                batch = bm_rows[i : i + BATCH]
                try:
                    result = self.client.table("live_odds").insert(batch).execute()
                    total_inserted += len(result.data) if result.data else 0
                except Exception as e:
                    logger.error("Failed to insert %s live_odds batch %d: %s", bm_name, i // BATCH, e)

            logger.info("%s live_odds: %d rows for %d events", bm_name, len(bm_rows), len(event_names))

        logger.info("Total inserted across Lottomatica+GoldBet+PlanetWin365: %d rows", total_inserted)
        return total_inserted

    def write_betfair_live_odds(self, rows: list[dict[str, Any]]) -> int:
        """Write Betfair Exchange rows to live_odds.

        Deletes existing rows for affected event_names then inserts fresh ones.
        Rows must already be fully formatted (bookmaker, sport, league, event_name,
        event_time, market, outcome, odds, volume, expires_at, market_id, event_id).

        Returns number of rows inserted.
        """
        if not rows:
            return 0

        bookmaker_name = "Betfair Exchange"
        # Normalize team names so Betfair events match other bookmakers in the DB
        rows = [{**r, "event_name": _normalize_event_name(r["event_name"])} for r in rows]
        event_names = list({r["event_name"] for r in rows})

        try:
            (
                self.client.table("live_odds")
                .delete()
                .eq("bookmaker", bookmaker_name)
                .in_("event_name", event_names)
                .execute()
            )
        except Exception as e:
            logger.error("Failed to delete stale Betfair Exchange live_odds: %s", e)

        BATCH = 500
        inserted = 0
        for i in range(0, len(rows), BATCH):
            batch = rows[i : i + BATCH]
            try:
                result = self.client.table("live_odds").insert(batch).execute()
                inserted += len(result.data) if result.data else 0
            except Exception as e:
                logger.error("Failed to insert Betfair Exchange live_odds batch %d: %s", i // BATCH, e)

        logger.info("Betfair Exchange live_odds: %d rows for %d events", inserted, len(event_names))
        return inserted

    def cleanup_stale_odds(self, hours: int = 24) -> int:
        """Delete odds for events that have already started (older than N hours).

        Returns number of deleted rows.
        """
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

            # Get old event IDs
            old_events = (
                self.client.table("odds_events")
                .select("id")
                .lt("event_time", cutoff)
                .execute()
            )

            if not old_events.data:
                return 0

            event_ids = [e["id"] for e in old_events.data]

            # Delete odds for old events
            self.client.table("odds_data").delete().in_("event_id", event_ids).execute()

            # Delete old events
            self.client.table("odds_events").delete().in_("id", event_ids).execute()

            logger.info("Cleaned up %d stale events", len(event_ids))
            return len(event_ids)

        except Exception as e:
            logger.error("Failed to cleanup stale odds: %s", e)
            return 0
