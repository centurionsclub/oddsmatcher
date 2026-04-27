"""
Scraper per centroquote.it (OddsPortal IT)
Usa Playwright per navigare le pagine e estrarre le quote dei bookmaker italiani.
I dati vengono salvati su Supabase.
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page, Browser

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

# Leagues to scrape
LEAGUES = {
    "calcio": [
        {"url": "/football/italy/serie-a/", "name": "Serie A", "sport": "calcio"},
        {"url": "/football/italy/serie-b/", "name": "Serie B", "sport": "calcio"},
        {"url": "/football/spain/laliga/", "name": "La Liga", "sport": "calcio"},
        {"url": "/football/england/premier-league/", "name": "Premier League", "sport": "calcio"},
        {"url": "/football/germany/bundesliga/", "name": "Bundesliga", "sport": "calcio"},
        {"url": "/football/france/ligue-1/", "name": "Ligue 1", "sport": "calcio"},
        {"url": "/football/europe/champions-league/", "name": "Champions League", "sport": "calcio"},
        {"url": "/football/europe/europa-league/", "name": "Europa League", "sport": "calcio"},
    ],
    "tennis": [
        {"url": "/tennis/atp-singles/", "name": "ATP Singles", "sport": "tennis"},
        {"url": "/tennis/wta-singles/", "name": "WTA Singles", "sport": "tennis"},
    ],
    "basket": [
        {"url": "/basketball/italy/serie-a/", "name": "Serie A Basket", "sport": "basket"},
        {"url": "/basketball/euroleague/euroleague/", "name": "Euroleague", "sport": "basket"},
    ],
}

BASE_URL = "https://www.centroquote.it"


async def supabase_upsert(table: str, data: list[dict], on_conflict: str = ""):
    """Upsert data to Supabase via REST API."""
    import urllib.request

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }

    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status
    except Exception as e:
        print(f"  [ERROR] Supabase upsert {table}: {e}")
        # Try to read error body
        if hasattr(e, "read"):
            print(f"  [ERROR] Body: {e.read().decode()}")
        return None


async def scrape_league_page(page: Page, league: dict) -> list[dict]:
    """Scrape a single league page for upcoming matches and their 1X2 odds."""
    url = BASE_URL + league["url"]
    print(f"\n  Scraping {league['name']}: {url}")

    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)  # Extra wait for dynamic content
    except Exception as e:
        print(f"  [ERROR] Failed to load {url}: {e}")
        return []

    matches = []

    try:
        # OddsPortal/CentroQuote uses a table-like structure for matches
        # Look for match rows - the structure varies but typically has event links

        # Try to find the main content container
        # CentroQuote uses Tailwind classes, the match data is in divs

        # First, let's extract all the data from the page using JS
        data = await page.evaluate("""() => {
            const matches = [];

            // CentroQuote/OddsPortal new version uses div-based layout
            // Look for event rows containing team names and odds

            // Method 1: Look for eventRow elements
            const eventRows = document.querySelectorAll('[class*="eventRow"], [class*="event-row"], tr[class*="deactivate"], .group\\/event-row');

            if (eventRows.length > 0) {
                eventRows.forEach(row => {
                    try {
                        // Extract team names
                        const teamEls = row.querySelectorAll('a[href*="/football/"], a[href*="/tennis/"], a[href*="/basketball/"], [class*="participant-name"], .truncate');
                        const teams = Array.from(teamEls).map(el => el.textContent.trim()).filter(t => t.length > 1);

                        // Extract odds - usually in cells/divs with numeric content
                        const oddsEls = row.querySelectorAll('[class*="odds"], [class*="border-black"], p.height-content, [data-v-odds]');
                        let odds = Array.from(oddsEls).map(el => {
                            const text = el.textContent.trim();
                            const num = parseFloat(text);
                            return isNaN(num) ? null : num;
                        }).filter(o => o !== null && o > 1.0);

                        // Extract time
                        const timeEl = row.querySelector('[class*="time"], [class*="date"], time, .datet');
                        const timeText = timeEl ? timeEl.textContent.trim() : '';

                        // Extract match URL for detail page
                        const matchLink = row.querySelector('a[href*="/football/"], a[href*="/tennis/"], a[href*="/basketball/"]');
                        const matchUrl = matchLink ? matchLink.getAttribute('href') : '';

                        if (teams.length >= 2 || (teams.length === 1 && teams[0].includes(' - '))) {
                            let home, away;
                            if (teams.length >= 2) {
                                home = teams[0];
                                away = teams[1];
                            } else {
                                const parts = teams[0].split(' - ');
                                home = parts[0]?.trim();
                                away = parts[1]?.trim();
                            }

                            matches.push({
                                home: home || '',
                                away: away || '',
                                time: timeText,
                                odds: odds.slice(0, 3), // First 3 odds = 1X2
                                matchUrl: matchUrl,
                            });
                        }
                    } catch (e) {}
                });
            }

            // Method 2: If no event rows found, try broader search
            if (matches.length === 0) {
                // Look for any links that seem to be match links
                const links = document.querySelectorAll('a[href*="-v-"], a[href*="-vs-"]');
                links.forEach(link => {
                    const text = link.textContent.trim();
                    const href = link.getAttribute('href');
                    if (text && href) {
                        const parts = text.split(/\s+[-v]+\s+/i);
                        if (parts.length >= 2) {
                            matches.push({
                                home: parts[0].trim(),
                                away: parts[1].trim(),
                                time: '',
                                odds: [],
                                matchUrl: href,
                            });
                        }
                    }
                });
            }

            return matches;
        }""")

        print(f"  Found {len(data)} matches on league page")

        for match in data:
            if not match.get("home") or not match.get("away"):
                continue

            matches.append({
                "sport": league["sport"],
                "league": league["name"],
                "home_team": match["home"],
                "away_team": match["away"],
                "event_name": f"{match['home']} v {match['away']}",
                "time_text": match.get("time", ""),
                "match_url": match.get("matchUrl", ""),
                "overview_odds": match.get("odds", []),
            })

    except Exception as e:
        print(f"  [ERROR] Failed to parse {league['name']}: {e}")

    return matches


async def scrape_match_detail(page: Page, match_url: str) -> list[dict]:
    """Scrape a single match detail page for all bookmaker odds."""
    if not match_url:
        return []

    full_url = BASE_URL + match_url if match_url.startswith("/") else match_url

    try:
        await page.goto(full_url, wait_until="networkidle", timeout=20000)
        await page.wait_for_timeout(1500)
    except Exception as e:
        print(f"    [ERROR] Failed to load match detail: {e}")
        return []

    try:
        odds_data = await page.evaluate("""() => {
            const results = [];

            // OddsPortal match detail page shows bookmaker odds in rows
            // Each row typically has: bookmaker name, odds values

            const rows = document.querySelectorAll('[class*="border-black-main"], [class*="odds-row"], tr.lo, tr.avg, .flex.gap-1.h-9, [class*="bookmaker-row"]');

            rows.forEach(row => {
                try {
                    // Get bookmaker name
                    const bmEl = row.querySelector('a[class*="bookmaker"], img[title], a[title], [class*="name"]');
                    let bookmaker = '';
                    if (bmEl) {
                        bookmaker = bmEl.getAttribute('title') || bmEl.textContent.trim();
                    }

                    // Get odds values
                    const oddsEls = row.querySelectorAll('[class*="odds-val"], [class*="border-black"], p.height-content, [class*="cursor-pointer"]');
                    const odds = [];
                    oddsEls.forEach(el => {
                        const text = el.textContent.trim();
                        const num = parseFloat(text);
                        if (!isNaN(num) && num > 1.0 && num < 100) {
                            odds.push(num);
                        }
                    });

                    if (bookmaker && odds.length > 0) {
                        results.push({ bookmaker, odds });
                    }
                } catch (e) {}
            });

            // Also try to get the average odds row
            const avgRow = document.querySelector('[class*="average"], .avg');
            if (avgRow) {
                const oddsEls = avgRow.querySelectorAll('[class*="odds"], p');
                const avgOdds = [];
                oddsEls.forEach(el => {
                    const num = parseFloat(el.textContent.trim());
                    if (!isNaN(num) && num > 1.0) avgOdds.push(num);
                });
                if (avgOdds.length > 0) {
                    results.push({ bookmaker: '_average', odds: avgOdds });
                }
            }

            return results;
        }""")

        return odds_data

    except Exception as e:
        print(f"    [ERROR] Failed to parse match detail: {e}")
        return []


async def save_to_supabase(events_with_odds: list[dict]):
    """Save scraped data to Supabase."""
    if not events_with_odds:
        print("\n  No data to save.")
        return

    print(f"\n  Saving {len(events_with_odds)} events to Supabase...")

    for event in events_with_odds:
        # Upsert event
        event_data = {
            "sport": event["sport"],
            "league": event["league"],
            "home_team": event["home_team"],
            "away_team": event["away_team"],
            "event_name": event["event_name"],
            "event_time": event.get("event_time", datetime.now(timezone.utc).isoformat()),
        }

        status = await supabase_upsert("odds_events", [event_data])
        if status:
            print(f"    Saved event: {event['event_name']}")

        # Get event_id back
        import urllib.request
        import urllib.parse

        query = urllib.parse.urlencode({
            "home_team": f"eq.{event['home_team']}",
            "away_team": f"eq.{event['away_team']}",
            "select": "id",
            "limit": "1",
        })

        req_url = f"{SUPABASE_URL}/rest/v1/odds_events?{query}"
        headers = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        }

        try:
            req = urllib.request.Request(req_url, headers=headers)
            with urllib.request.urlopen(req) as resp:
                rows = json.loads(resp.read().decode())
                if rows:
                    event_id = rows[0]["id"]
                else:
                    continue
        except Exception as e:
            print(f"    [ERROR] Failed to get event_id: {e}")
            continue

        # Upsert odds
        for bm_odds in event.get("bookmaker_odds", []):
            if bm_odds["bookmaker"].startswith("_"):
                continue

            odds_rows = []
            market = "1X2"
            outcomes = ["1", "X", "2"] if len(bm_odds["odds"]) == 3 else ["1", "2"]

            for i, outcome in enumerate(outcomes):
                if i < len(bm_odds["odds"]):
                    odds_rows.append({
                        "event_id": event_id,
                        "bookmaker": bm_odds["bookmaker"],
                        "market": market,
                        "outcome": outcome,
                        "odds": float(bm_odds["odds"][i]),
                    })

            if odds_rows:
                await supabase_upsert("odds_data", odds_rows)


async def main():
    """Main scraper function."""
    sport_filter = sys.argv[1] if len(sys.argv) > 1 else "calcio"

    leagues = LEAGUES.get(sport_filter, LEAGUES["calcio"])

    print(f"=" * 60)
    print(f"CentroQuote Scraper - Sport: {sport_filter}")
    print(f"Leagues: {len(leagues)}")
    print(f"=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="it-IT",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        page = await context.new_page()

        all_events = []

        for league in leagues:
            # Scrape league page for match list
            matches = await scrape_league_page(page, league)

            # For each match, scrape the detail page for bookmaker odds
            for i, match in enumerate(matches):
                print(f"    [{i+1}/{len(matches)}] {match['event_name']}")

                if match.get("match_url"):
                    bookmaker_odds = await scrape_match_detail(page, match["match_url"])
                    match["bookmaker_odds"] = bookmaker_odds
                    print(f"      -> {len(bookmaker_odds)} bookmakers found")
                else:
                    # Use overview odds if no detail URL
                    match["bookmaker_odds"] = []
                    if match.get("overview_odds"):
                        match["bookmaker_odds"].append({
                            "bookmaker": "Average",
                            "odds": match["overview_odds"],
                        })

                all_events.append(match)

                # Delay between requests
                await page.wait_for_timeout(1000)

        await browser.close()

    # Save to Supabase
    if SUPABASE_SERVICE_KEY and SUPABASE_SERVICE_KEY != "your_service_role_key_here":
        await save_to_supabase(all_events)
    else:
        print("\n  [WARN] SUPABASE_SERVICE_KEY not set. Outputting to JSON instead.")
        output_file = f"odds_{sport_filter}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, "w") as f:
            json.dump(all_events, f, indent=2, default=str)
        print(f"  Saved to {output_file}")

    print(f"\n{'=' * 60}")
    print(f"Done! Scraped {len(all_events)} events.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
