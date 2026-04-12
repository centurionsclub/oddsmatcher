"""CSS selectors for centroquote.it (OddsPortal Italian version).

Based on OddsHarvester's OddsPortalSelectors — these are the selectors used
by the current OddsPortal/CentroQuote frontend (Tailwind-based SPA).
"""


class Selectors:
    """All CSS selectors in one place for easy maintenance."""

    # ── Cookie banner ───────────────────────────────────────────────
    COOKIE_ACCEPT = "#onetrust-accept-btn-handler"

    # ── Odds format switcher ────────────────────────────────────────
    ODDS_FORMAT_EU = "div[class*='odds-format'] button:has-text('EU')"
    ODDS_FORMAT_DROPDOWN = "div[class*='group']:has(div[class*='odds-format'])"

    # ── League page: event rows ─────────────────────────────────────
    EVENT_ROW = "div[class*='eventRow']"
    EVENT_LINK = "a[href*='/football/'], a[href*='/tennis/'], a[href*='/basketball/'], a[href*='/hockey/']"
    EVENT_TIME = "div[class*='next-m'] p, div.datet, [class*='date']"

    # ── Match detail: market tabs ───────────────────────────────────
    MARKET_TABS = "ul.visible-links.bg-black-main.odds-tabs > li"
    MARKET_TABS_FALLBACK = "ul[class*='odds-tabs'] > li"
    MORE_BUTTON = "button.toggle-odds:has-text('More')"

    # ── Match detail: sub-market selector (e.g. Over/Under 2.5) ────
    SUB_MARKET_SELECTOR = "div.flex.w-full.items-center.justify-start.pl-3.font-bold p"

    # ── Match detail: bookmaker rows ────────────────────────────────
    BOOKMAKER_ROW = "div.border-black-borders.flex.h-9"
    BOOKMAKER_LOGO = "img.bookmaker-logo"
    ODDS_VALUE = "div.flex-center.flex-col.font-bold"

    # ── Match detail: bookies filter (all / classic / crypto) ───────
    BOOKIES_FILTER_NAV = "div[data-testid='bookies-filter-nav']"

    # ── Pagination ──────────────────────────────────────────────────
    PAGINATION_LINK = "a.pagination-link:not([rel='next'])"

    # ── Scroll detection (lazy loading sentinel) ────────────────────
    CONTENT_CHECK = "div[class*='eventRow']"
