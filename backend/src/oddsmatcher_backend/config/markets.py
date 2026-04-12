"""Market definitions and outcome mappings."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Market:
    name: str                   # Display name used in the UI
    tab_label: str              # Label on centroquote.it market tabs
    outcomes: list[str]         # Expected outcome labels in order


# Standard markets
MARKET_1X2 = Market("1X2", "1X2", ["1", "X", "2"])
MARKET_12 = Market("12", "Home/Away", ["1", "2"])
MARKET_OVER_UNDER = Market("Over/Under", "Over/Under", ["Over", "Under"])
MARKET_BTTS = Market("BTTS", "Both Teams to Score", ["Yes", "No"])
MARKET_DOUBLE_CHANCE = Market("Double Chance", "Double Chance", ["1X", "12", "X2"])

# Markets by sport
MARKETS_BY_SPORT: dict[str, list[Market]] = {
    "calcio": [MARKET_1X2, MARKET_OVER_UNDER, MARKET_BTTS, MARKET_DOUBLE_CHANCE],
    "tennis": [MARKET_12],
    "basket": [MARKET_12, MARKET_OVER_UNDER],
}

# Default market per sport (first tab on centroquote.it)
DEFAULT_MARKET: dict[str, Market] = {
    "calcio": MARKET_1X2,
    "tennis": MARKET_12,
    "basket": MARKET_12,
}
