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

    // Get aggregated odds from cache
    let query = supabase
      .from('odds_cache')
      .select('*')
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

    console.log(`Found ${oddsData?.length || 0} odds records`);

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

    // Group odds by event
    const eventMap = new Map();
    
    for (const odd of oddsData || []) {
      const key = `${odd.event_name}_${odd.market}`;
      if (!eventMap.has(key)) {
        eventMap.set(key, {
          event_name: odd.event_name,
          event_time: odd.event_time,
          league: odd.league,
          sport: odd.sport,
          market: odd.market,
          bookmakers: []
        });
      }
      
      eventMap.get(key).bookmakers.push({
        bookmaker: odd.bookmaker,
        odds: odd.odds,
        scraped_at: odd.scraped_at
      });
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