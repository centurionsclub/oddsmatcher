"""Bookmaker definitions and classification (bookmaker vs exchange)."""

# Italian ADM bookmakers tracked by Club Élite
BOOKMAKERS: list[str] = [
    "888sport",
    "AdmiralBet",
    "Bet365",
    "Betfair",  # Betfair Bookmaker (sportsbook)
    "BetFlag",  # BetFlag Bookmaker
    "Betsson",
    "Bwin",
    "Codere",
    "DAZN Bet",
    "DomusBet",
    "E-Play24",
    "Eurobet",
    "Fastbet",
    "Gioca7",
    "Gioco Digitale",
    "GoldBet",
    "LeoVegas",
    "Lottomatica",
    "MarathonBet",
    "MyLotteriesPlay",
    "NetBet",
    "Planetwin365",
    "PokerStars",
    "QuiGioco",
    "Sisal",
    "Snai",
    "Sportium",
    "Stanleybet",
    "StarCasinò",
    "StarVegas",
    "Staryes",
    "Totosì",
    "Vincitu",
    "William Hill",
]

# Exchanges (provide lay odds)
EXCHANGES: list[str] = [
    "Betfair Exchange",
    "BetFlag Exchange",
]

# Keywords to detect exchange names in scraped data
EXCHANGE_KEYWORDS: list[str] = [
    "exchange",
    "smarkets",
    "betdaq",
    "matchbook",
]


def is_exchange(bookmaker_name: str) -> bool:
    """Check if a bookmaker name refers to an exchange."""
    name_lower = bookmaker_name.lower()
    return any(kw in name_lower for kw in EXCHANGE_KEYWORDS)
