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
    selectors: {
      eventName: '.gl-MarketGroupButton_Text',
      odds: '.gl-ParticipantOddsOnly_Odds',
      market: '.gl-Market_General'
    }
  },
  snai: {
    name: 'Snai',
    baseUrl: 'https://www.snai.it',
    selectors: {
      eventName: '.event-name',
      odds: '.quota-value',
      market: '.market-type'
    }
  },
  sisal: {
    name: 'Sisal',
    baseUrl: 'https://www.sisal.it',
    selectors: {
      eventName: '.match-title',
      odds: '.odd-value',
      market: '.bet-type'
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

// Mock scraping function (placeholder for actual scraping)
// In production, this would use Puppeteer or similar
async function scrapeBookmaker(
  bookmaker: string,
  sport: string,
  market: string,
  filters: any
): Promise<any[]> {
  console.log(`Scraping ${bookmaker} for ${sport} - ${market}`);
  
  // Simulate network delay
  await new Promise(resolve => setTimeout(resolve, 1000 + Math.random() * 2000));

  // Generate mock data for demonstration
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
  
  if (filters.minOdds && market === '1X2') {
    filtered = filtered.filter(e => 
      (e.odds.home ?? 0) >= filters.minOdds || 
      (e.odds.draw ?? 0) >= filters.minOdds || 
      (e.odds.away ?? 0) >= filters.minOdds
    );
  }

  if (filters.maxOdds && market === '1X2') {
    filtered = filtered.filter(e => 
      (e.odds.home ?? 0) <= filters.maxOdds && 
      (e.odds.draw ?? 0) <= filters.maxOdds && 
      (e.odds.away ?? 0) <= filters.maxOdds
    );
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
      Deno.env.get('SUPABASE_ANON_KEY') ?? ''
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
