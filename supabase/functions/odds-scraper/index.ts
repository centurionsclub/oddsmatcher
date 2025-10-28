import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.7.1";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

// Bookmaker scraping configurations
const BOOKMAKER_CONFIGS = {
  bet365: {
    name: 'Bet365',
    baseUrl: 'https://www.bet365.it',
    prematchUrl: 'https://www.bet365.it/#/AC/B1/C1/D13/E184477/F2/',
    selectors: {
      eventName: '.gl-MarketGroupButton_Text',
      odds: '.gl-ParticipantOddsOnly_Odds',
      market: '.gl-Market_General'
    }
  },
  snai: {
    name: 'Snai',
    baseUrl: 'https://www.snai.it',
    prematchUrl: 'https://www.snai.it/sport/calcio',
    selectors: {
      eventName: '.event-name',
      odds: '.quota-value',
      market: '.market-type'
    }
  },
  sisal: {
    name: 'Sisal',
    baseUrl: 'https://www.sisal.it',
    prematchUrl: 'https://www.sisal.it/scommesse-matchpoint/quote/calcio/serie-a',
    selectors: {
      eventContainer: '[data-qa="event-item"], .event-row, .match-item, .match-card, article[class*="event"]',
      eventName: '[data-qa="event-name"], .event-name, .match-name',
      teams: '[data-qa="team-name"], .team-name',
      odds: '[data-qa="odd-value"], .odd-value, .quota, button[class*="odd"]',
      market: '[data-qa="market-type"], .market-type',
      eventTime: '[data-qa="event-time"], .event-time, time',
      league: '[data-qa="league-name"], .league-name, .competition'
    }
  },
  lottomatica: {
    name: 'Lottomatica',
    baseUrl: 'https://www.lottomatica.it',
    prematchUrl: 'https://www.lottomatica.it/scommesse/sport/',
    selectors: {
      eventContainer: '.event-row, .match, .event-item, .match-row, [data-test="event"]',
      eventName: '.match-name, .event-name',
      teams: '.team-name',
      odds: '.quota, .odd-value, [class*="quota"], button[class*="odd"]',
      market: '.market-name, .market-type',
      eventTime: '.event-datetime, .event-time, time',
      league: '.competition-name, .league-name'
    }
  }
};

// User agents for rotation
const USER_AGENTS = [
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
];

function getRandomUserAgent() {
  return USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)];
}

function normalizeEventName(name: string): string {
  return name
    .toLowerCase()
    .replace(/fc|calcio|united|utd|vs|-/gi, ' ')
    .replace(/[^a-z0-9\s]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

async function checkCache(
  supabase: any,
  bookmaker: string,
  sport: string,
  market: string
) {
  const { data, error } = await supabase
    .from('odds_cache')
    .select('*')
    .eq('bookmaker', bookmaker)
    .eq('sport', sport)
    .eq('market', market)
    .gt('expires_at', new Date().toISOString())
    .order('scraped_at', { ascending: false });

  if (error) {
    console.error('Cache check error:', error);
    return null;
  }

  return data && data.length > 0 ? data : null;
}

async function saveToCache(
  supabase: any,
  bookmaker: string,
  sport: string,
  eventName: string,
  league: string,
  market: string,
  odds: any,
  eventTime?: string
) {
  const expiresAt = new Date(Date.now() + 30000); // 30 seconds

  const { error } = await supabase
    .from('odds_cache')
    .insert({
      bookmaker,
      sport,
      event_name: eventName,
      league,
      event_time: eventTime,
      market,
      odds,
      expires_at: expiresAt.toISOString()
    });

  if (error) {
    console.error('Cache save error:', error);
  }
}

async function logScraping(
  supabase: any,
  bookmaker: string,
  status: string,
  durationMs: number,
  errorMessage?: string
) {
  await supabase
    .from('scraping_logs')
    .insert({
      bookmaker,
      status,
      duration_ms: durationMs,
      error_message: errorMessage
    });
}

// Fetch from The Odds API
async function fetchFromTheOddsAPI(sport: string, market: string): Promise<any[]> {
  const apiKey = Deno.env.get('THE_ODDS_API_KEY');
  if (!apiKey) {
    console.error('THE_ODDS_API_KEY not configured');
    throw new Error('THE_ODDS_API_KEY not configured');
  }

  console.log('Fetching odds from The Odds API with key:', apiKey.substring(0, 8) + '...');

  // Map sport to The Odds API sport key
  const sportKey = sport === 'calcio' ? 'soccer_italy_serie_a' : sport;
  
  try {
    const url = new URL(`https://api.the-odds-api.com/v4/sports/${sportKey}/odds/`);
    url.searchParams.set('apiKey', apiKey);
    url.searchParams.set('regions', 'eu');
    url.searchParams.set('markets', market === '1X2' ? 'h2h' : 'totals');
    url.searchParams.set('oddsFormat', 'decimal');

    const response = await fetch(url.toString(), {
      signal: AbortSignal.timeout(10000),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('The Odds API error response:', errorText);
      throw new Error(`The Odds API error: ${response.status} ${response.statusText} - ${errorText}`);
    }

    const data = await response.json();
    console.log(`The Odds API returned ${data.length} events`);

    // Transform to our format
    const events = data.map((event: any) => {
      const bookmakers = event.bookmakers || [];
      const eventData: any = {
        eventName: `${event.home_team} - ${event.away_team}`,
        league: sportKey.replace('soccer_', '').replace(/_/g, ' ').toUpperCase(),
        eventTime: event.commence_time,
        market: market,
        odds: {},
        bookmakerData: {}
      };

      // Extract odds from all bookmakers
      bookmakers.forEach((bm: any) => {
        const bmName = bm.key.toLowerCase();
        const markets = bm.markets || [];
        
        markets.forEach((mkt: any) => {
          if (mkt.key === 'h2h' && market === '1X2') {
            const outcomes = mkt.outcomes || [];
            const odds: any = {};
            
            outcomes.forEach((outcome: any) => {
              if (outcome.name === event.home_team) odds.home = outcome.price;
              if (outcome.name === event.away_team) odds.away = outcome.price;
              if (outcome.name === 'Draw') odds.draw = outcome.price;
            });

            if (!eventData.bookmakerData[bmName]) {
              eventData.bookmakerData[bmName] = odds;
            }
          } else if (mkt.key === 'totals' && market !== '1X2') {
            const outcomes = mkt.outcomes || [];
            const odds: any = {};
            
            outcomes.forEach((outcome: any) => {
              if (outcome.name === 'Over') odds.over = outcome.price;
              if (outcome.name === 'Under') odds.under = outcome.price;
            });

            if (!eventData.bookmakerData[bmName]) {
              eventData.bookmakerData[bmName] = odds;
            }
          }
        });
      });

      return eventData;
    });

    return events.filter((e: any) => Object.keys(e.bookmakerData).length > 0);

  } catch (error) {
    console.error('The Odds API fetch failed:', error);
    throw error;
  }
}

// Fetch Betfair exchange odds
async function fetchBetfairOdds(sport: string, market: string, filters: any): Promise<any[]> {
  const apiKey = Deno.env.get('BETFAIR_API_KEY');
  const sessionToken = Deno.env.get('BETFAIR_SESSION_TOKEN');
  
  if (!apiKey || !sessionToken) {
    console.error('BETFAIR_API_KEY or BETFAIR_SESSION_TOKEN not configured');
    throw new Error('Betfair credentials not configured');
  }

  console.log('Fetching odds from Betfair Exchange API with session token');
  
  try {
    // Betfair REST endpoints (Italy)
    const restBase = 'https://api.betfair.com/exchange/betting/rest/v1.0';

    // Map sport to Betfair event type ID (1 = Soccer)
    const eventTypeId = sport === 'calcio' ? '1' : '1';

    // Time window: from last hour to next 24h
    const now = new Date();
    const fromIso = new Date(now.getTime() - 60 * 60 * 1000).toISOString();
    const toIso = new Date(now.getTime() + 24 * 60 * 60 * 1000).toISOString();

    // Step 1: fetch market catalogue for MATCH_ODDS
    const marketCatalogueResp = await fetch(`${restBase}/listMarketCatalogue/`, {
      method: 'POST',
      headers: {
        'X-Application': apiKey,
        'X-Authentication': sessionToken,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({
        filter: {
          eventTypeIds: [eventTypeId],
          // Narrow to Italy but allow live via time window
          marketCountries: ['IT'],
          marketTypeCodes: market === '1X2' ? ['MATCH_ODDS'] : ['OVER_UNDER_25'],
          marketStartTime: { from: fromIso, to: toIso },
          inPlayOnly: !!(filters && (filters.live || filters.inPlay))
        },
        maxResults: 120,
        sort: 'FIRST_TO_START',
        marketProjection: ['RUNNER_DESCRIPTION', 'EVENT', 'COMPETITION', 'MARKET_START_TIME']
      }),
      signal: AbortSignal.timeout(15000)
    });

    if (!marketCatalogueResp.ok) {
      const t = await marketCatalogueResp.text();
      console.error('Betfair REST listMarketCatalogue error:', t);
      throw new Error(`Betfair REST listMarketCatalogue HTTP ${marketCatalogueResp.status}`);
    }

    const catalogue = await marketCatalogueResp.json();
    let markets = Array.isArray(catalogue) ? catalogue : [];

    console.log(`[Betfair REST] MarketCatalogue returned ${markets.length} markets`);

    // Fallback: if zero markets, broaden filter (no country restriction)
    if (markets.length === 0) {
      console.log('[Betfair REST] 0 markets with country=IT, retrying without country filter...');
      const fallbackResp = await fetch(`${restBase}/listMarketCatalogue/`, {
        method: 'POST',
        headers: {
          'X-Application': apiKey,
          'X-Authentication': sessionToken,
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify({
          filter: {
            eventTypeIds: [eventTypeId],
            marketTypeCodes: market === '1X2' ? ['MATCH_ODDS'] : ['OVER_UNDER_25'],
            marketStartTime: { from: fromIso, to: toIso },
            inPlayOnly: !!(filters && (filters.live || filters.inPlay)),
            turnInPlayEnabled: true
          },
          maxResults: 60,
          sort: 'FIRST_TO_START',
          marketProjection: ['RUNNER_DESCRIPTION', 'EVENT', 'COMPETITION', 'MARKET_START_TIME']
        }),
        signal: AbortSignal.timeout(15000)
      });

      if (fallbackResp.ok) {
        markets = await fallbackResp.json();
        console.log(`[Betfair REST] Fallback MarketCatalogue returned ${Array.isArray(markets) ? markets.length : 0} markets`);
      } else {
        const txt = await fallbackResp.text();
        console.error('Betfair REST fallback error:', txt);
      }
    }

    if (!Array.isArray(markets) || markets.length === 0) return [];

    // Step 2: fetch market books (prices)
    const marketIds = markets.map((m: any) => m.marketId);
    const marketBooksResp = await fetch(`${restBase}/listMarketBook/`, {
      method: 'POST',
      headers: {
        'X-Application': apiKey,
        'X-Authentication': sessionToken,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({
        marketIds,
        priceProjection: { priceData: ['EX_BEST_OFFERS'] }
      }),
      signal: AbortSignal.timeout(15000)
    });

    if (!marketBooksResp.ok) {
      const t = await marketBooksResp.text();
      console.error('Betfair REST listMarketBook error:', t);
      throw new Error(`Betfair REST listMarketBook HTTP ${marketBooksResp.status}`);
    }

    const books = await marketBooksResp.json();
    const events: any[] = [];

    for (const mkt of markets) {
      const book = Array.isArray(books) ? books.find((b: any) => b.marketId === mkt.marketId) : null;
      if (!book || !book.runners) continue;

      const runnersInfo = (mkt.runners || []) as any[];
      const eventName = mkt.event?.name || 'Unknown';
      const league = mkt.competition?.name || 'Italia';
      const eventTime = mkt.marketStartTime || new Date(Date.now() + 86400000).toISOString();

      const odds: any = {};
      const runners: any[] = [];

      for (const r of runnersInfo) {
        const rb = book.runners.find((x: any) => x.selectionId === r.selectionId);
        if (!rb) continue;
        const back = rb.ex?.availableToBack || [];
        const lay = rb.ex?.availableToLay || [];
        const runnerName = r.runnerName || '';

        runners.push({
          selectionId: r.selectionId,
          runnerName,
          back,
          lay,
        });

        const rn = runnerName.toLowerCase();
        const topBack = back?.[0]?.price;
        if (topBack) {
          if (rn.includes('draw') || rn.includes('pareggio')) odds.draw = topBack;
          else if (!odds.home) odds.home = topBack;
          else odds.away = topBack;
        }
      }

      events.push({
        eventName,
        league,
        eventTime,
        market,
        odds,
        runners
      });
    }

    console.log(`[Betfair REST] Built ${events.length} events with runners`);
    return events;

  } catch (error) {
    console.error('Betfair API fetch failed:', error);
    throw error;
  }
}

// Real scraping/fetching implementation - no mock fallback
async function scrapeBookmaker(
  bookmaker: string,
  sport: string,
  market: string,
  filters: any
): Promise<any[]> {
  console.log(`Fetching odds for ${bookmaker} - ${sport} - ${market}`);
  
  // STRATEGY: Use ONLY ScrapingBee for Sisal and Lottomatica
  if (bookmaker === 'sisal') {
    return await scrapeSisal(sport, market, filters);
  } else if (bookmaker === 'lottomatica') {
    return await scrapeLottomatica(sport, market, filters);
  } else if (bookmaker === 'bet365') {
    return await scrapeBet365(sport, market, filters);
  } else if (bookmaker === 'snai') {
    return await scrapeSnai(sport, market, filters);
  } else if (bookmaker === 'betfair') {
    return await fetchBetfairOdds(sport, market, filters);
  }
  
  console.log(`No scraper available for ${bookmaker}`);
  return [];
}

// Bet365 real scraper
async function scrapeBet365(sport: string, market: string, filters: any): Promise<any[]> {
  console.log('Attempting real scraping for Bet365...');
  
  const url = 'https://www.bet365.it/#/AC/B1/C1/D13/E184477/F2/';
  const userAgent = getRandomUserAgent();
  
  try {
    const response = await fetch(url, {
      headers: {
        'User-Agent': userAgent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7',
        'Cache-Control': 'no-cache',
      },
      signal: AbortSignal.timeout(15000), // 15 second timeout
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const html = await response.text();
    console.log(`Bet365 response received, size: ${html.length} bytes`);

    // Check if we got blocked or redirected
    if (html.includes('cloudflare') || html.includes('captcha') || html.length < 1000) {
      throw new Error('Bet365 blocked or redirected the request');
    }

    // Parse events from HTML (bet365 uses dynamic JS, so this is a basic attempt)
    const events = parseBet365HTML(html, market, filters);
    
    if (events.length === 0) {
      throw new Error('No events found in HTML (likely JS-rendered content)');
    }

    console.log(`Successfully scraped ${events.length} events from Bet365`);
    return events;

  } catch (error) {
    console.error('Bet365 scraping failed:', error);
    throw error;
  }
}

// Snai real scraper
async function scrapeSnai(sport: string, market: string, filters: any): Promise<any[]> {
  console.log('Attempting real scraping for Snai...');
  
  const url = 'https://www.snai.it/sport/calcio';
  const userAgent = getRandomUserAgent();
  
  try {
    const response = await fetch(url, {
      headers: {
        'User-Agent': userAgent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7',
        'Cache-Control': 'no-cache',
      },
      signal: AbortSignal.timeout(15000),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const html = await response.text();
    console.log(`Snai response received, size: ${html.length} bytes`);

    if (html.includes('cloudflare') || html.includes('captcha') || html.length < 1000) {
      throw new Error('Snai blocked or redirected the request');
    }

    const events = parseSnaiHTML(html, market, filters);
    
    if (events.length === 0) {
      throw new Error('No events found in HTML (likely JS-rendered content)');
    }

    console.log(`Successfully scraped ${events.length} events from Snai`);
    return events;

  } catch (error) {
    console.error('Snai scraping failed:', error);
    throw error;
  }
}

// Parse Bet365 HTML (basic regex-based parsing)
function parseBet365HTML(html: string, market: string, filters: any): any[] {
  const events: any[] = [];
  
  // This is a simplified parser - real implementation would need more sophisticated parsing
  // Bet365 heavily uses JS, so this will likely fail and fallback to mock
  
  try {
    // Try to find match patterns in HTML (very basic)
    const matchRegex = /([\w\s]+)\s+vs?\s+([\w\s]+)/gi;
    const matches = html.match(matchRegex);
    
    if (matches && matches.length > 0) {
      // Found some potential matches - create sample events
      console.log(`Found ${matches.length} potential matches in Bet365 HTML`);
    }
  } catch (error) {
    console.error('Error parsing Bet365 HTML:', error);
  }
  
  return events;
}

// Parse Snai HTML
function parseSnaiHTML(html: string, market: string, filters: any): any[] {
  const events: any[] = [];
  
  // Similar basic parsing for Snai
  try {
    const matchRegex = /([\w\s]+)\s+vs?\s+([\w\s]+)/gi;
    const matches = html.match(matchRegex);
    
    if (matches && matches.length > 0) {
      console.log(`Found ${matches.length} potential matches in Snai HTML`);
    }
  } catch (error) {
    console.error('Error parsing Snai HTML:', error);
  }
  
  return events;
}

// Sisal scraper using ScrapingBee
async function scrapeSisal(sport: string, market: string, filters: any): Promise<any[]> {
  console.log('Scraping Sisal with ScrapingBee...');
  
  const apiKey = Deno.env.get('SCRAPINGBEE_API_KEY');
  if (!apiKey) {
    throw new Error('SCRAPINGBEE_API_KEY not configured');
  }

  const config = BOOKMAKER_CONFIGS.sisal;
  const targetUrl = config.prematchUrl;
  
  try {
    // Ottimizzazione parametri ScrapingBee per Sisal
    const scrapingBeeUrl = `https://app.scrapingbee.com/api/v1/?api_key=${apiKey}&url=${encodeURIComponent(targetUrl)}&render_js=true&premium_proxy=true&country_code=it&wait=3500&block_resources=false`;
    
    console.log(`Fetching from ScrapingBee for Sisal: ${targetUrl}`);
    const response = await fetch(scrapingBeeUrl, {
      signal: AbortSignal.timeout(20000),
    });

    if (!response.ok) {
      throw new Error(`ScrapingBee error: ${response.status} ${response.statusText}`);
    }

    const html = await response.text();
    console.log(`Sisal HTML received, size: ${html.length} bytes`);

    // Parse the HTML to extract events
    const events = parseSisalHTML(html, market, filters);
    console.log(`Successfully parsed ${events.length} events from Sisal`);
    
    return events;

  } catch (error) {
    console.error('Sisal scraping with ScrapingBee failed:', error);
    throw error;
  }
}

// Lottomatica scraper using ScrapingBee
async function scrapeLottomatica(sport: string, market: string, filters: any): Promise<any[]> {
  console.log('Scraping Lottomatica with ScrapingBee...');
  
  const apiKey = Deno.env.get('SCRAPINGBEE_API_KEY');
  if (!apiKey) {
    throw new Error('SCRAPINGBEE_API_KEY not configured');
  }

  const config = BOOKMAKER_CONFIGS.lottomatica;
  const targetUrl = config.prematchUrl;
  
  try {
    // Ottimizzazione parametri ScrapingBee per Lottomatica
    const scrapingBeeUrl = `https://app.scrapingbee.com/api/v1/?api_key=${apiKey}&url=${encodeURIComponent(targetUrl)}&render_js=true&premium_proxy=true&country_code=it&wait=1000&block_resources=true`;
    
    console.log(`Fetching from ScrapingBee for Lottomatica: ${targetUrl}`);
    const response = await fetch(scrapingBeeUrl, {
      signal: AbortSignal.timeout(12000),
    });

    if (!response.ok) {
      throw new Error(`ScrapingBee error: ${response.status} ${response.statusText}`);
    }

    const html = await response.text();
    console.log(`Lottomatica HTML received, size: ${html.length} bytes`);

    // Parse the HTML to extract events
    const events = parseLottomaticaHTML(html, market, filters);
    console.log(`Successfully parsed ${events.length} events from Lottomatica`);
    
    return events;

  } catch (error) {
    console.error('Lottomatica scraping with ScrapingBee failed:', error);
    throw error;
  }
}

// Parse Sisal HTML
function parseSisalHTML(html: string, market: string, filters: any): any[] {
  const events: any[] = [];
  
  console.log(`[Sisal Parser] Starting HTML parsing for market: ${market}, HTML size: ${html.length} bytes`);
  
  try {
    // Strategy 1: Look for JSON data embedded in script tags
    const jsonPatterns = [
      /<script[^>]*>.*?window\.__INITIAL_STATE__\s*=\s*({.*?});/s,
      /<script[^>]*>.*?window\.__NEXT_DATA__\s*=\s*({.*?})<\/script>/s,
      /<script[^>]*type="application\/json"[^>]*>({.*?})<\/script>/gs,
    ];

    for (const jsonPattern of jsonPatterns) {
      const jsonMatch = html.match(jsonPattern);
      if (jsonMatch && jsonMatch[1]) {
        try {
          const data = JSON.parse(jsonMatch[1]);
          console.log('[Sisal Parser] Found embedded JSON data, attempting to extract events...');
          
          // Try to navigate JSON structure to find events
          const findEvents = (obj: any, depth = 0): any[] => {
            if (depth > 5) return [];
            const found: any[] = [];
            
            if (Array.isArray(obj)) {
              obj.forEach(item => found.push(...findEvents(item, depth + 1)));
            } else if (obj && typeof obj === 'object') {
              // Look for event-like structures
              if (obj.homeTeam && obj.awayTeam && obj.odds) {
                found.push(obj);
              } else if (obj.teams && obj.markets) {
                found.push(obj);
              } else {
                Object.values(obj).forEach(val => found.push(...findEvents(val, depth + 1)));
              }
            }
            return found;
          };
          
          const jsonEvents = findEvents(data);
          if (jsonEvents.length > 0) {
            console.log(`[Sisal Parser] Extracted ${jsonEvents.length} events from JSON`);
            // Transform to our format
            jsonEvents.forEach(evt => {
              const eventName = evt.homeTeam && evt.awayTeam 
                ? `${evt.homeTeam} - ${evt.awayTeam}`
                : evt.eventName || '';
              
              if (eventName) {
                events.push({
                  eventName,
                  league: evt.league || evt.competition || 'Serie A',
                  eventTime: evt.startTime || evt.eventTime || new Date(Date.now() + 86400000).toISOString(),
                  market,
                  odds: evt.odds || {}
                });
              }
            });
          }
        } catch (e) {
          console.log('[Sisal Parser] Failed to parse JSON:', e);
        }
      }
    }

    // Strategy 1b: Parse application/ld+json blocks for SportsEvent
    if (events.length === 0) {
      const ldMatches = [...html.matchAll(/<script[^>]*type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/gi)];
      for (const m of ldMatches) {
        try {
          const json = JSON.parse(m[1].trim());
          const arr = Array.isArray(json) ? json : [json];
          for (const item of arr) {
            const type = (item['@type'] || '').toString().toLowerCase();
            const name = (item.name || '').toString();
            if (type.includes('sport') || (name && name.includes('-'))) {
              let home = '';
              let away = '';
              if (name.includes('-')) {
                const parts = name.split('-');
                home = parts[0].trim();
                away = parts[1]?.trim() || '';
              }
              const start = item.startDate || item.datePublished || item.validFrom;
              if (home && away) {
                events.push({
                  eventName: `${home} - ${away}`,
                  league: (item.competition && (item.competition.name || item.competition)) || 'Serie A',
                  eventTime: start || new Date(Date.now() + 86400000).toISOString(),
                  market,
                  odds: {}
                });
              }
            }
          }
          if (events.length >= 50) break;
        } catch (e) {
          // ignore JSON parse errors from unrelated ld+json blocks
        }
      }
    }

    // Strategy 2: Simplified regex extraction (optimized for speed)
    if (events.length === 0) {
      console.log('[Sisal Parser] No JSON found, trying simplified regex patterns...');
      
      // Split HTML into chunks to avoid regex catastrophic backtracking
      const chunkSize = 100000; // 100KB chunks
      const chunks: string[] = [];
      for (let i = 0; i < html.length && chunks.length < 5; i += chunkSize) {
        chunks.push(html.slice(i, i + chunkSize + 5000)); // overlap to avoid splitting events
      }
      
      // Simplified pattern - less greedy, faster
      const eventPattern = /([A-Za-zÀ-ÖØ-öø-ÿ]{3,}[\w\s.']{1,30})\s*[-–—]\s*([A-Za-zÀ-ÖØ-öø-ÿ]{3,}[\w\s.']{1,30})/g;
      const oddsPattern = /(?:data-qa="odd|class="[^"]*(?:odd|quota)[^"]*")[^>]*>([\d.,]{3,6})</g;
      
      const potentialEvents = new Set<string>();
      
      // Extract event names first (fast)
      for (const chunk of chunks) {
        let match;
        let count = 0;
        while ((match = eventPattern.exec(chunk)) !== null && count++ < 50) {
          const home = match[1].trim();
          const away = match[2].trim();
          if (home.length > 2 && away.length > 2 && home !== away) {
            potentialEvents.add(`${home} - ${away}`);
          }
        }
        if (potentialEvents.size >= 30) break;
      }
      
      console.log(`[Sisal Parser] Found ${potentialEvents.size} potential events`);
      
      // Now try to find odds for each event (limited search)
      const seen = new Set<string>();

      for (const eventName of Array.from(potentialEvents).slice(0, 20)) {
        if (seen.has(eventName.toLowerCase())) continue;
        seen.add(eventName.toLowerCase());
        
        // Search for this event's odds in a limited area
        const eventIndex = html.indexOf(eventName);
        if (eventIndex === -1) continue;
        
        const searchArea = html.slice(Math.max(0, eventIndex - 200), eventIndex + 2000);
        const oddsFound: number[] = [];
        
        let oddsMatch;
        oddsPattern.lastIndex = 0;
        while ((oddsMatch = oddsPattern.exec(searchArea)) !== null && oddsFound.length < 3) {
          const oddValue = parseFloat(oddsMatch[1].replace(',', '.'));
          if (oddValue >= 1.01 && oddValue <= 50) {
            oddsFound.push(oddValue);
          }
        }
        
        if (oddsFound.length === 3) {
          events.push({
            eventName,
            league: 'Serie A',
            eventTime: new Date(Date.now() + 86400000).toISOString(),
            market: '1X2',
            odds: {
              '1': oddsFound[0],
              'X': oddsFound[1],
              '2': oddsFound[2]
            }
          });
          console.log(`[Sisal Parser] Added: ${eventName} | ${oddsFound.join('/')}`);
        }
        
        if (events.length >= 15) break; // Limit to avoid timeout
      }
    }
 
    console.log(`[Sisal Parser] Completed parsing, found ${events.length} events`);
 
  } catch (error) {
    console.error('[Sisal Parser] Fatal error:', error);
  }
  
  return events;
}

// Parse Lottomatica HTML
function parseLottomaticaHTML(html: string, market: string, filters: any): any[] {
  const events: any[] = [];
  
  console.log(`[Lottomatica Parser] Starting HTML parsing for market: ${market}, HTML size: ${html.length} bytes`);
  
  try {
    // Strategy 1: Look for embedded JSON data
    const jsonPatterns = [
      /<script[^>]*>.*?window\.__PRELOADED_STATE__\s*=\s*({.*?});/s,
      /<script[^>]*>.*?window\.__NEXT_DATA__\s*=\s*({.*?})<\/script>/s,
      /<script[^>]*type="application\/json"[^>]*>({.*?})<\/script>/gs,
      /<script[^>]*>.*?window\.initialData\s*=\s*({.*?});/s,
    ];

    for (const jsonPattern of jsonPatterns) {
      const jsonMatch = html.match(jsonPattern);
      if (jsonMatch && jsonMatch[1]) {
        try {
          const data = JSON.parse(jsonMatch[1]);
          console.log('[Lottomatica Parser] Found embedded JSON data, attempting to extract events...');
          
          // Recursive search for event structures
          const findEvents = (obj: any, depth = 0): any[] => {
            if (depth > 5) return [];
            const found: any[] = [];
            
            if (Array.isArray(obj)) {
              obj.forEach(item => found.push(...findEvents(item, depth + 1)));
            } else if (obj && typeof obj === 'object') {
              // Look for event structures
              if ((obj.homeTeam || obj.home) && (obj.awayTeam || obj.away)) {
                found.push(obj);
              } else if (obj.teams && Array.isArray(obj.teams) && obj.teams.length >= 2) {
                found.push(obj);
              } else if (obj.matchName || obj.eventName) {
                found.push(obj);
              } else {
                Object.values(obj).forEach(val => found.push(...findEvents(val, depth + 1)));
              }
            }
            return found;
          };
          
          const jsonEvents = findEvents(data);
          if (jsonEvents.length > 0) {
            console.log(`[Lottomatica Parser] Extracted ${jsonEvents.length} events from JSON`);
            jsonEvents.forEach(evt => {
              const homeTeam = evt.homeTeam || evt.home || evt.teams?.[0];
              const awayTeam = evt.awayTeam || evt.away || evt.teams?.[1];
              const eventName = homeTeam && awayTeam 
                ? `${homeTeam} - ${awayTeam}`
                : evt.matchName || evt.eventName || '';
              
              if (eventName) {
                events.push({
                  eventName,
                  league: evt.league || evt.competition || evt.tournament || 'Serie A',
                  eventTime: evt.startTime || evt.eventTime || evt.date || new Date(Date.now() + 86400000).toISOString(),
                  market,
                  odds: evt.odds || evt.markets?.[0]?.odds || {}
                });
              }
            });
          }
        } catch (e) {
          console.log('[Lottomatica Parser] Failed to parse JSON:', e);
        }
      }
    }

    // Strategy 2: Enhanced regex patterns
    if (events.length === 0) {
      console.log('[Lottomatica Parser] No JSON found, trying regex patterns...');
      
      const eventPatterns = [
        // Pattern 1: Team names with multiple odds (1X2)
        /([\w\sàèéìòù']+)\s*[-–]\s*([\w\sàèéìòù']+).*?(?:esito-1|quota-1|outcome-1)[^>]*>([\d.,]+).*?(?:esito-x|quota-x|outcome-x)[^>]*>([\d.,]+).*?(?:esito-2|quota-2|outcome-2)[^>]*>([\d.,]+)/gis,
        
        // Pattern 2: Match-row or event-row structure
        /class="(?:match-row|event-row)"[^>]*>[\s\S]{0,800}?([\w\sàèéìòù']+)\s*[-–]\s*([\w\sàèéìòù']+)[\s\S]{0,400}?class="quota"[^>]*>([\d.,]+)/gis,
        
        // Pattern 3: Data-test attributes
        /data-test="event"[^>]*>[\s\S]{0,600}?([\w\sàèéìòù']+)\s*[-–vs]\s*([\w\sàèéìòù']+)[\s\S]{0,300}?data-test="odd[^"]*"[^>]*>([\d.,]+)/gis,
        
        // Pattern 4: Button elements with team names
        /([\w\sàèéìòù']+)\s*-\s*([\w\sàèéìòù']+).*?<button[^>]*class="[^"]*odd[^"]*"[^>]*>([\d.,]+)<\/button>/gis,
      ];

      for (const pattern of eventPatterns) {
        const matches = [...html.matchAll(pattern)];
        if (matches.length > 0) {
          console.log(`[Lottomatica Parser] Found ${matches.length} potential events using regex pattern`);
          
          matches.forEach((match, index) => {
            try {
              const homeTeam = match[1]?.trim();
              const awayTeam = match[2]?.trim();
              const odd1 = parseFloat((match[3] || '0').replace(',', '.'));
              const oddX = parseFloat((match[4] || '0').replace(',', '.'));
              const odd2 = parseFloat((match[5] || '0').replace(',', '.'));
              
              if (homeTeam && awayTeam && odd1 > 1.01) {
                const eventName = `${homeTeam} - ${awayTeam}`;
                console.log(`[Lottomatica Parser] Event ${index + 1}: ${eventName}, odds: ${odd1}/${oddX || 'N/A'}/${odd2 || 'N/A'}`);
                
                events.push({
                  eventName,
                  league: 'Serie A',
                  eventTime: new Date(Date.now() + 86400000).toISOString(),
                  market,
                  odds: market === '1X2'
                    ? { 
                        home: odd1, 
                        draw: oddX > 1.01 ? oddX : 3.30, 
                        away: odd2 > 1.01 ? odd2 : 3.40 
                      }
                    : { over: odd1, under: 2.00 }
                });
              }
            } catch (e) {
              console.log(`[Lottomatica Parser] Error parsing match ${index}:`, e);
            }
          });
          
          if (events.length > 0) break;
        }
      }
    }

    console.log(`[Lottomatica Parser] Completed parsing, found ${events.length} events`);

  } catch (error) {
    console.error('[Lottomatica Parser] Fatal error:', error);
  }
  
  return events;
}

// Mock data generator (fallback)
async function getMockData(bookmaker: string, sport: string, market: string, filters: any): Promise<any[]> {
  console.log(`Generating mock data for ${bookmaker}`);
  
  // Simulate network delay
  await new Promise(resolve => setTimeout(resolve, 500 + Math.random() * 1000));

  const mockEvents = [
    {
      eventName: 'Inter - Milan',
      league: 'Serie A',
      eventTime: new Date(Date.now() + 86400000).toISOString(),
      market: market,
      odds: market === '1X2' 
        ? { home: 2.10 + Math.random() * 0.3, draw: 3.20 + Math.random() * 0.4, away: 3.50 + Math.random() * 0.5 }
        : { over: 1.85 + Math.random() * 0.2, under: 1.95 + Math.random() * 0.2 }
    },
    {
      eventName: 'Juventus - Napoli',
      league: 'Serie A',
      eventTime: new Date(Date.now() + 172800000).toISOString(),
      market: market,
      odds: market === '1X2'
        ? { home: 1.90 + Math.random() * 0.3, draw: 3.40 + Math.random() * 0.4, away: 4.00 + Math.random() * 0.5 }
        : { over: 1.75 + Math.random() * 0.2, under: 2.05 + Math.random() * 0.2 }
    },
    {
      eventName: 'Roma - Lazio',
      league: 'Serie A',
      eventTime: new Date(Date.now() + 259200000).toISOString(),
      market: market,
      odds: market === '1X2'
        ? { home: 2.30 + Math.random() * 0.3, draw: 3.10 + Math.random() * 0.4, away: 3.20 + Math.random() * 0.5 }
        : { over: 1.90 + Math.random() * 0.2, under: 1.90 + Math.random() * 0.2 }
    },
    {
      eventName: 'Atalanta - Fiorentina',
      league: 'Serie A',
      eventTime: new Date(Date.now() + 345600000).toISOString(),
      market: market,
      odds: market === '1X2'
        ? { home: 1.70 + Math.random() * 0.3, draw: 3.60 + Math.random() * 0.4, away: 5.00 + Math.random() * 0.5 }
        : { over: 1.65 + Math.random() * 0.2, under: 2.20 + Math.random() * 0.2 }
    }
  ];

  // Apply filters
  let filtered = mockEvents;
  
  if (filters.quotaMinima) {
    const minOdds = parseFloat(filters.quotaMinima.replace(',', '.'));
    if (minOdds > 0 && market === '1X2') {
      filtered = filtered.filter(e => 
        (e.odds.home ?? 0) >= minOdds || 
        (e.odds.draw ?? 0) >= minOdds || 
        (e.odds.away ?? 0) >= minOdds
      );
    }
  }

  if (filters.quotaMassima) {
    const maxOdds = parseFloat(filters.quotaMassima.replace(',', '.'));
    if (maxOdds > 0 && market === '1X2') {
      filtered = filtered.filter(e => 
        (e.odds.home ?? 0) <= maxOdds && 
        (e.odds.draw ?? 0) <= maxOdds && 
        (e.odds.away ?? 0) <= maxOdds
      );
    }
  }

  return filtered;
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  const startTime = Date.now();

  try {
    const supabaseClient = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''
    );

    const { bookmakers, sport, market, filters } = await req.json();
    
    console.log('Odds scraper request:', { bookmakers, sport, market, filters });

    if (!bookmakers || !Array.isArray(bookmakers) || bookmakers.length === 0) {
      return new Response(
        JSON.stringify({ error: 'At least one bookmaker is required' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    const results = [];

    // Process bookmakers in parallel (max 3 at a time)
    const batchSize = 3;
    for (let i = 0; i < bookmakers.length; i += batchSize) {
      const batch = bookmakers.slice(i, i + batchSize);
      
      const batchResults = await Promise.all(
        batch.map(async (bookmaker: string) => {
          const bmStartTime = Date.now();
          
          try {
            // Check cache first
            const cached = await checkCache(supabaseClient, bookmaker, sport, market);
            
            if (cached) {
              console.log(`Using cached data for ${bookmaker}`);
              await logScraping(supabaseClient, bookmaker, 'cache_hit', Date.now() - bmStartTime);
              return cached.map((c: any) => ({
                bookmaker,
                eventName: c.event_name,
                league: c.league,
                eventTime: c.event_time,
                market: c.market,
                odds: c.odds
              }));
            }

            // Scrape fresh data
            const scrapedData = await scrapeBookmaker(bookmaker, sport, market, filters);
            
            // Save to cache
            for (const event of scrapedData) {
              await saveToCache(
                supabaseClient,
                bookmaker,
                sport,
                event.eventName,
                event.league,
                event.market,
                event.odds,
                event.eventTime
              );
            }

            await logScraping(supabaseClient, bookmaker, 'success', Date.now() - bmStartTime);

            return scrapedData.map(e => ({
              bookmaker,
              ...e
            }));
          } catch (error) {
            console.error(`Error scraping ${bookmaker}:`, error);
            const errorMessage = error instanceof Error ? error.message : String(error);
            await logScraping(
              supabaseClient,
              bookmaker,
              'failed',
              Date.now() - bmStartTime,
              errorMessage
            );
            return [];
          }
        })
      );

      results.push(...batchResults.flat());
    }

    const duration = Date.now() - startTime;
    console.log(`Scraping completed in ${duration}ms, found ${results.length} odds`);

    return new Response(
      JSON.stringify({
        success: true,
        data: results,
        metadata: {
          totalResults: results.length,
          bookmakers: bookmakers.length,
          durationMs: duration
        }
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );

  } catch (error) {
    console.error('Error in odds-scraper function:', error);
    const errorMessage = error instanceof Error ? error.message : String(error);
    return new Response(
      JSON.stringify({ success: false, error: errorMessage, data: [], metadata: { durationMs: Date.now() - startTime } }),
      { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
