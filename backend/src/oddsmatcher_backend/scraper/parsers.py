"""HTML parsing logic for bookmaker odds using BeautifulSoup.

Mirrors the approach from OddsHarvester's OddsParser but tailored
for the centroquote.it variant.
"""

import logging
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

# Regex for fractional odds like "4/5"
_FRACTIONAL_RE = re.compile(r"^(\d+)/(\d+)$")

# Selector patterns (BeautifulSoup class-based)
_BOOKMAKER_ROW_CLASS = re.compile(r"border-black-borders")
_BOOKMAKER_ROW_FALLBACK = re.compile(r"^border-black-borders flex h-9")
_ODDS_BLOCK_CLASS = re.compile(r"flex-center.*flex-col.*font-bold")
_EVENT_ROW_CLASS = re.compile(r"^eventRow")


def parse_odds_value(text: str) -> float | None:
    """Parse a decimal or fractional odds string. Returns None on failure."""
    text = text.strip()
    if not text or text == "-":
        return None
    m = _FRACTIONAL_RE.match(text)
    if m:
        return int(m.group(1)) / int(m.group(2)) + 1
    try:
        val = float(text)
        return val if val > 1.0 else None
    except ValueError:
        return None


def _deduplicate_odds_text(text: str) -> str:
    """Fix doubled odds text like '1.801.80' → '1.80'."""
    return re.sub(r"(\d+\.\d+)\1", r"\1", text)


def extract_bookmaker_name(block: Tag) -> str | None:
    """Extract bookmaker name from a row using a fallback chain.

    1. img.bookmaker-logo[title]
    2. <a title="...">
    3. <img alt="...">
    """
    img = block.find("img", class_="bookmaker-logo")
    if img and img.get("title"):
        return img["title"]

    a_tag = block.find("a", attrs={"title": True})
    if a_tag and a_tag["title"]:
        name = a_tag["title"]
        if name.lower().startswith("go to ") and name.endswith("!"):
            name = name[len("go to "):-1].strip()
            if name.lower().endswith(" website"):
                name = name[:-len(" website")].strip()
        return name

    for img in block.find_all("img"):
        alt = img.get("alt", "")
        if alt and alt.lower() not in ("", "logo"):
            return alt

    return None


def parse_bookmaker_odds_from_text(page_text: str) -> list[dict[str, Any]]:
    """Parse bookmaker odds from page innerText (new CentroQuote React SPA).

    The React page renders this structure in innerText:
        Bookmaker
        1               ← outcome column label
        X
        2
        Payout
        888sport        ← bookmaker name
        RICHIEDI BONUS
        4.80            ← odds[0]
        3.50            ← odds[1]
        1.67            ← odds[2]
        91.5%           ← payout (skipped)
        bet365.it
        …

    Works for any market (1X2, Over/Under, Double Chance, BTTS) because the
    column labels come from the page itself rather than a hardcoded config.
    """
    lines = [l.strip() for l in page_text.split("\n") if l.strip()]

    # Locate the "Bookmaker" table header
    try:
        bm_idx = lines.index("Bookmaker")
    except ValueError:
        logger.warning("No bookmaker rows found in HTML")
        return []

    # Outcome labels sit between "Bookmaker" and "Payout"
    try:
        payout_idx = lines.index("Payout", bm_idx)
    except ValueError:
        logger.warning("No 'Payout' header found after 'Bookmaker'")
        return []

    col_labels = lines[bm_idx + 1 : payout_idx]
    if not col_labels:
        logger.warning("No outcome labels found in odds table")
        return []

    n = len(col_labels)

    # Lines to skip when scanning for bookmaker names
    _SKIP = {
        "Bookmaker", "Payout",
        "RICHIEDI BONUS", "Claim Bonus", "Get Bonus",
        "1X2", "Over/Under", "Asian Handicap", "Both Teams to Score",
        "Double Chance", "European Handicap", "Finale",
        "1° Tempo", "2° Tempo", "Tutti i bonus", "Di più",
        "Matches", "Dropping Odds", "Sure Bets",
    }

    results: list[dict[str, Any]] = []
    i = payout_idx + 1

    while i < len(lines):
        line = lines[i]

        # Skip known non-bookmaker tokens, percentages, or pure numbers
        if (not line
                or line in _SKIP
                or line.endswith("%")
                or _is_number(line)):
            i += 1
            continue

        bm_name = line
        i += 1

        # Skip optional bonus call-to-action text
        if i < len(lines) and lines[i].upper() in (
            "RICHIEDI BONUS", "CLAIM BONUS", "GET BONUS"
        ):
            i += 1

        # Read exactly n numeric odds values
        odds_vals: list[float] = []
        while i < len(lines) and len(odds_vals) < n:
            val = parse_odds_value(lines[i])
            if val is not None:
                odds_vals.append(val)
                i += 1
            else:
                break

        # Skip trailing payout percentage
        if i < len(lines) and lines[i].endswith("%"):
            i += 1

        if len(odds_vals) == n:
            results.append({
                "bookmaker": bm_name,
                "odds": dict(zip(col_labels, odds_vals)),
            })

    logger.info("Parsed odds for %d bookmakers", len(results))
    return results


def _is_number(s: str) -> bool:
    """Return True if *s* looks like a standalone number."""
    try:
        float(s)
        return True
    except ValueError:
        return False


def parse_bookmaker_odds(html: str, outcomes: list[str]) -> list[dict[str, Any]]:
    """Parse all bookmaker rows from a match detail page HTML.

    Args:
        html: Full page HTML content.
        outcomes: Expected outcome labels in order, e.g. ["1", "X", "2"].

    Returns:
        List of dicts like:
          {"bookmaker": "Sisal", "odds": {"1": 2.10, "X": 3.40, "2": 3.20}}
    """
    soup = BeautifulSoup(html, "html.parser")

    rows = soup.find_all("div", class_=_BOOKMAKER_ROW_CLASS)
    if not rows:
        rows = soup.find_all("div", class_=_BOOKMAKER_ROW_FALLBACK)

    if not rows:
        logger.warning("No bookmaker rows found in HTML")
        return []

    results = []
    for row in rows:
        name = extract_bookmaker_name(row)
        if not name:
            continue

        odds_blocks = row.find_all("div", class_=_ODDS_BLOCK_CLASS)
        if len(odds_blocks) < len(outcomes):
            logger.debug("Skipping %s: found %d odds blocks, expected %d", name, len(odds_blocks), len(outcomes))
            continue

        odds: dict[str, float] = {}
        skip = False
        for i, label in enumerate(outcomes):
            raw = _deduplicate_odds_text(odds_blocks[i].get_text(strip=True))
            val = parse_odds_value(raw)
            if val is None:
                skip = True
                break
            odds[label] = val

        if skip:
            continue

        results.append({"bookmaker": name, "odds": odds})

    logger.info("Parsed odds for %d bookmakers", len(results))
    return results


def extract_match_links(html: str) -> list[str]:
    """Extract match detail links from a league listing page.

    Looks for <a> tags inside eventRow divs that link to match pages.
    """
    soup = BeautifulSoup(html, "html.parser")
    event_rows = soup.find_all("div", class_=_EVENT_ROW_CLASS)

    links: set[str] = set()
    for row in event_rows:
        for a in row.find_all("a", href=True):
            href = a["href"]
            # Match detail URLs contain team slugs with hyphens
            if href and "/" in href and href.count("/") >= 3:
                links.add(href)

    logger.info("Extracted %d unique match links from page", len(links))
    return sorted(links)
