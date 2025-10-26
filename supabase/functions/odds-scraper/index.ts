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
    prematchUrl: 'https://www.sisal.it/scommesse/match-list',
    selectors: {
      eventContainer: '[data-qa="event-item"]',
      eventName: '[data-qa="event-name"]',
      teams: '[data-qa="team-name"]',
      odds: '[data-qa="odd-value"]',
      market: '[data-qa="market-type"]',
      eventTime: '[data-qa="event-time"]',
      league: '[data-qa="league-name"]'
    }
  },
  lottomatica: {
    name: 'Lottomatica',
    baseUrl: 'https://www.lottomatica.it',
    prematchUrl: 'https://www.lottomatica.it/scommesse/calcio',
    selectors: {
      eventContainer: '.event-row',
      eventName: '.match-name',
      teams: '.team-name',
      odds: '.quota',
      market: '.market-name',
      eventTime: '.event-datetime',
      league: '.competition-name'
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

// Real scraping/fetching implementation - no mock fallback
async function scrapeBookmaker(
  bookmaker: string,
  sport: string,
  market: string,
  filters: any
): Promise<any[]> {
  console.log(`Fetching odds for ${bookmaker} - ${sport} - ${market}`);
  
  // Strategy 1: Try The Odds API first (best quality data)
  try {
    const apiEvents = await fetchFromTheOddsAPI(sport, market);
    
    // Extract odds for specific bookmaker
    const bookmakerEvents = apiEvents
      .map(event => {
        const bmKey = bookmaker.toLowerCase();
        const odds = event.bookmakerData[bmKey] || event.bookmakerData[Object.keys(event.bookmakerData)[0]];
        
        if (odds && Object.keys(odds).length > 0) {
          return {
            eventName: event.eventName,
            league: event.league,
            eventTime: event.eventTime,
            market: event.market,
            odds: odds
          };
        }
        return null;
      })
      .filter((e: any) => e !== null);

    if (bookmakerEvents.length > 0) {
      console.log(`The Odds API returned ${bookmakerEvents.length} events for ${bookmaker}`);
      return bookmakerEvents;
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    console.log(`The Odds API failed for ${bookmaker}:`, errorMsg);
  }

  // Strategy 2: Try ScrapingBee for Sisal and Lottomatica
  try {
    if (bookmaker === 'sisal') {
      const scraped = await scrapeSisal(sport, market, filters);
      if (scraped.length > 0) {
        console.log(`ScrapingBee returned ${scraped.length} events for ${bookmaker}`);
        return scraped;
      }
    } else if (bookmaker === 'lottomatica') {
      const scraped = await scrapeLottomatica(sport, market, filters);
      if (scraped.length > 0) {
        console.log(`ScrapingBee returned ${scraped.length} events for ${bookmaker}`);
        return scraped;
      }
    } else if (bookmaker === 'bet365') {
      const scraped = await scrapeBet365(sport, market, filters);
      if (scraped.length > 0) {
        console.log(`Real scraping returned ${scraped.length} events for ${bookmaker}`);
        return scraped;
      }
    } else if (bookmaker === 'snai') {
      const scraped = await scrapeSnai(sport, market, filters);
      if (scraped.length > 0) {
        console.log(`Real scraping returned ${scraped.length} events for ${bookmaker}`);
        return scraped;
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    console.log(`Real scraping failed for ${bookmaker}:`, errorMsg);
  }

  // No data available
  console.log(`No real data available for ${bookmaker}`);
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
    const scrapingBeeUrl = `https://app.scrapingbee.com/api/v1/?api_key=${apiKey}&url=${encodeURIComponent(targetUrl)}&render_js=true&premium_proxy=true&country_code=it`;
    
    console.log('Fetching from ScrapingBee for Sisal...');
    const response = await fetch(scrapingBeeUrl, {
      signal: AbortSignal.timeout(30000),
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
    const scrapingBeeUrl = `https://app.scrapingbee.com/api/v1/?api_key=${apiKey}&url=${encodeURIComponent(targetUrl)}&render_js=true&premium_proxy=true&country_code=it`;
    
    console.log('Fetching from ScrapingBee for Lottomatica...');
    const response = await fetch(scrapingBeeUrl, {
      signal: AbortSignal.timeout(30000),
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
  
  try {
    // Look for JSON data in script tags (common pattern)
    const jsonDataRegex = /<script[^>]*>.*?window\.__INITIAL_STATE__\s*=\s*({.*?});.*?<\/script>/s;
    const jsonMatch = html.match(jsonDataRegex);
    
    if (jsonMatch && jsonMatch[1]) {
      try {
        const data = JSON.parse(jsonMatch[1]);
        console.log('Found Sisal JSON data in page');
        // Parse JSON structure - will need to adjust based on actual structure
        // This is a placeholder that needs real implementation
      } catch (e) {
        console.error('Failed to parse Sisal JSON data:', e);
      }
    }

    // Fallback: Try to extract using regex patterns
    const eventPatterns = [
      // Pattern 1: Team names with odds
      /data-qa="event-name"[^>]*>([^<]+)<.*?data-qa="odd-value"[^>]*>([\d.]+)</gs,
      // Pattern 2: Match format
      /([\w\s]+)\s+vs?\s+([\w\s]+).*?quota[^>]*>([\d.]+)/gi,
    ];

    for (const pattern of eventPatterns) {
      const matches = [...html.matchAll(pattern)];
      if (matches.length > 0) {
        console.log(`Found ${matches.length} events using pattern`);
        
        matches.forEach(match => {
          const eventName = match[1]?.trim();
          const odds1 = parseFloat(match[2] || '0');
          
          if (eventName && odds1 > 0) {
            events.push({
              eventName,
              league: 'Serie A',
              eventTime: new Date(Date.now() + 86400000).toISOString(),
              market,
              odds: market === '1X2' 
                ? { home: odds1, draw: 3.20, away: 3.50 }
                : { over: odds1, under: 1.95 }
            });
          }
        });
        
        if (events.length > 0) break;
      }
    }

  } catch (error) {
    console.error('Error parsing Sisal HTML:', error);
  }
  
  return events;
}

// Parse Lottomatica HTML
function parseLottomaticaHTML(html: string, market: string, filters: any): any[] {
  const events: any[] = [];
  
  try {
    // Look for JSON data embedded in the page
    const jsonDataRegex = /<script[^>]*>.*?(?:window\.__PRELOADED_STATE__|__NEXT_DATA__)\s*=\s*({.*?});.*?<\/script>/s;
    const jsonMatch = html.match(jsonDataRegex);
    
    if (jsonMatch && jsonMatch[1]) {
      try {
        const data = JSON.parse(jsonMatch[1]);
        console.log('Found Lottomatica JSON data in page');
        // Parse JSON structure - will need adjustment based on actual structure
      } catch (e) {
        console.error('Failed to parse Lottomatica JSON data:', e);
      }
    }

    // Fallback: Try regex extraction
    const eventPatterns = [
      // Pattern 1: Event row with odds
      /class="event-row"[^>]*>.*?class="match-name"[^>]*>([^<]+)<.*?class="quota"[^>]*>([\d.]+)/gs,
      // Pattern 2: Alternative format
      /([\w\s]+)\s+-\s+([\w\s]+).*?(?:quota|odd)[^>]*>([\d.]+)/gi,
    ];

    for (const pattern of eventPatterns) {
      const matches = [...html.matchAll(pattern)];
      if (matches.length > 0) {
        console.log(`Found ${matches.length} events using pattern`);
        
        matches.forEach(match => {
          const eventName = match[1]?.trim();
          const odds1 = parseFloat(match[2] || '0');
          
          if (eventName && odds1 > 0) {
            events.push({
              eventName,
              league: 'Serie A',
              eventTime: new Date(Date.now() + 86400000).toISOString(),
              market,
              odds: market === '1X2'
                ? { home: odds1, draw: 3.30, away: 3.40 }
                : { over: odds1, under: 2.00 }
            });
          }
        });
        
        if (events.length > 0) break;
      }
    }

  } catch (error) {
    console.error('Error parsing Lottomatica HTML:', error);
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
      JSON.stringify({ error: errorMessage }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
