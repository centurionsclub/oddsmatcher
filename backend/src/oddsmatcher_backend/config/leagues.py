"""League definitions for scraping."""

from dataclasses import dataclass


@dataclass(frozen=True)
class League:
    path: str       # URL path on centroquote.it, e.g. "/football/italy/serie-a/"
    name: str       # Display name
    sport: str      # calcio, tennis, basket, etc.


# ── Calcio ──────────────────────────────────────────────────────────
CALCIO_LEAGUES = [
    League("/football/italy/serie-a/", "Serie A", "calcio"),
    League("/football/italy/serie-b/", "Serie B", "calcio"),
    League("/football/spain/laliga/", "La Liga", "calcio"),
    League("/football/england/premier-league/", "Premier League", "calcio"),
    League("/football/germany/bundesliga/", "Bundesliga", "calcio"),
    League("/football/france/ligue-1/", "Ligue 1", "calcio"),
    League("/football/europe/champions-league/", "Champions League", "calcio"),
    League("/football/europe/europa-league/", "Europa League", "calcio"),
    League("/football/europe/conference-league/", "Conference League", "calcio"),
    League("/football/italy/coppa-italia/", "Coppa Italia", "calcio"),
]

# ── Tennis ──────────────────────────────────────────────────────────
TENNIS_LEAGUES = [
    League("/tennis/atp-singles/", "ATP Singles", "tennis"),
    League("/tennis/wta-singles/", "WTA Singles", "tennis"),
]

# ── Basket ──────────────────────────────────────────────────────────
BASKET_LEAGUES = [
    League("/basketball/italy/serie-a/", "Serie A Basket", "basket"),
    League("/basketball/euroleague/euroleague/", "Euroleague", "basket"),
    League("/basketball/usa/nba/", "NBA", "basket"),
]

# ── All grouped by sport ───────────────────────────────────────────
LEAGUES_BY_SPORT: dict[str, list[League]] = {
    "calcio": CALCIO_LEAGUES,
    "tennis": TENNIS_LEAGUES,
    "basket": BASKET_LEAGUES,
}

ALL_LEAGUES: list[League] = [league for leagues in LEAGUES_BY_SPORT.values() for league in leagues]


def get_leagues(sport: str | None = None) -> list[League]:
    """Return leagues for a sport, or all leagues if sport is None."""
    if sport is None:
        return ALL_LEAGUES
    return LEAGUES_BY_SPORT.get(sport, [])
