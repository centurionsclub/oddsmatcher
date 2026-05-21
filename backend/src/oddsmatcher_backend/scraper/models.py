"""Shared data models used by all direct bookmaker scrapers."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MatchOdds:
    """Structured result for a single match / market combination."""
    sport: str
    league: str
    home_team: str
    away_team: str
    event_name: str
    event_time: str | None
    match_url: str
    market: str
    bookmaker_odds: list[dict[str, Any]] = field(default_factory=list)
