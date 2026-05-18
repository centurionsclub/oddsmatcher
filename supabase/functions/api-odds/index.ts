import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.76.1";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
    const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const supabase = createClient(supabaseUrl, supabaseKey);

    const url = new URL(req.url);
    const sport = url.searchParams.get('sport') || 'calcio';
    const market = url.searchParams.get('market') || '1X2';
    const league = url.searchParams.get('league');
    const minRating = parseFloat(url.searchParams.get('min_rating') || '0');

    console.log('Fetching odds for:', { sport, market, league, minRating });

    // Read directly from live_odds (one row per bookmaker+event+market+outcome)
    let query = supabase
      .from('live_odds')
      .select('bookmaker, sport, league, event_name, event_time, market, outcome, odds, scraped_at, expires_at')
      .eq('sport', sport)
      .eq('market', market)
      .gt('expires_at', new Date().toISOString())
      .order('scraped_at', { ascending: false });

    if (league) {
      query = query.eq('league', league);
    }

    const { data: oddsData, error: oddsError } = await query;

    if (oddsError) {
      console.error('Error fetching odds:', oddsError);
      throw oddsError;
    }

    console.log(`Found ${oddsData?.length || 0} odds rows`);

    // Get matched bets with rating filter
    const { data: matchedData, error: matchedError } = await supabase
      .from('matched_bets')
      .select('*')
      .gte('rating', minRating)
      .gt('expires_at', new Date().toISOString())
      .order('rating', { ascending: false })
      .limit(100);

    if (matchedError) {
      console.error('Error fetching matched bets:', matchedError);
    }

    // Group by event+market, then by bookmaker, collecting outcomes into odds object
    // live_odds has one row per outcome; we rebuild {outcome: value} per bookmaker
    const eventMap = new Map<string, {
      event_name: string;
      event_time: string | null;
      league: string;
      sport: string;
      market: string;
      bookmakers: { bookmaker: string; odds: Record<string, number>; scraped_at: string }[];
    }>();

    for (const row of oddsData || []) {
      const eventKey = `${row.event_name}_${row.market}`;

      if (!eventMap.has(eventKey)) {
        eventMap.set(eventKey, {
          event_name: row.event_name,
          event_time: row.event_time,
          league: row.league,
          sport: row.sport,
          market: row.market,
          bookmakers: [],
        });
      }

      const event = eventMap.get(eventKey)!;

      // Find or create bookmaker entry
      let bm = event.bookmakers.find(b => b.bookmaker === row.bookmaker);
      if (!bm) {
        bm = { bookmaker: row.bookmaker, odds: {}, scraped_at: row.scraped_at };
        event.bookmakers.push(bm);
      }
      bm.odds[row.outcome] = parseFloat(row.odds);
    }

    const result = {
      total: eventMap.size,
      sport,
      market,
      league,
      events: Array.from(eventMap.values()),
      matched_opportunities: matchedData || [],
      timestamp: new Date().toISOString()
    };

    return new Response(
      JSON.stringify(result),
      {
        headers: {
          ...corsHeaders,
          'Content-Type': 'application/json'
        }
      }
    );

  } catch (error) {
    console.error('API error:', error);
    return new Response(
      JSON.stringify({
        error: error instanceof Error ? error.message : 'Internal server error',
        timestamp: new Date().toISOString()
      }),
      {
        status: 500,
        headers: {
          ...corsHeaders,
          'Content-Type': 'application/json'
        }
      }
    );
  }
});
