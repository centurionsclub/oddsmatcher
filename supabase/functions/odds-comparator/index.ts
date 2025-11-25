import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.76.1';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

interface ComparatorEvent {
  event: string;
  eventTime: string;
  league: string;
  market: string;
  bestOdds: {
    home: { bookmaker: string; odds: number };
    draw?: { bookmaker: string; odds: number };
    away: { bookmaker: string; odds: number };
  };
  allBookmakers: Array<{
    bookmaker: string;
    home: number;
    draw?: number;
    away: number;
  }>;
}

Deno.serve(async (req) => {
  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
    const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const supabase = createClient(supabaseUrl, supabaseKey);

    const { sport = 'calcio', market = '1X2', league } = await req.json();

    console.log(`[Comparator] Fetching odds for sport=${sport}, market=${market}, league=${league}`);

    // Fetch active odds from cache
    let query = supabase
      .from('odds_cache')
      .select('*')
      .eq('sport', sport)
      .eq('market', market)
      .gt('expires_at', new Date().toISOString());

    if (league) {
      query = query.eq('league', league);
    }

    const { data: oddsData, error } = await query;

    if (error) {
      throw new Error(`Database error: ${error.message}`);
    }

    if (!oddsData || oddsData.length === 0) {
      return new Response(
        JSON.stringify({ data: [], message: 'No odds found' }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    console.log(`[Comparator] Found ${oddsData.length} odds records`);

    // Group by event
    const eventMap = new Map<string, any>();

    for (const odd of oddsData) {
      const key = `${odd.event_name}:${odd.market}`;
      
      if (!eventMap.has(key)) {
        eventMap.set(key, {
          event: odd.event_name,
          eventTime: odd.event_time,
          league: odd.league,
          market: odd.market,
          bookmakers: []
        });
      }
      
      const odds = odd.odds as Record<string, number>;
      eventMap.get(key).bookmakers.push({
        bookmaker: odd.bookmaker,
        home: odds['1'] || 0,
        draw: odds['X'] || undefined,
        away: odds['2'] || 0
      });
    }

    // Find best odds for each event
    const comparatorData: ComparatorEvent[] = Array.from(eventMap.values()).map(event => {
      const best = {
        home: { bookmaker: '', odds: 0 },
        draw: { bookmaker: '', odds: 0 },
        away: { bookmaker: '', odds: 0 }
      };
      
      for (const bm of event.bookmakers) {
        if (bm.home > best.home.odds) {
          best.home = { bookmaker: bm.bookmaker, odds: bm.home };
        }
        if (bm.draw && bm.draw > best.draw.odds) {
          best.draw = { bookmaker: bm.bookmaker, odds: bm.draw };
        }
        if (bm.away > best.away.odds) {
          best.away = { bookmaker: bm.bookmaker, odds: bm.away };
        }
      }
      
      return {
        event: event.event,
        eventTime: event.eventTime,
        league: event.league,
        market: event.market,
        bestOdds: best.draw.odds > 0 ? best : {
          home: best.home,
          away: best.away
        },
        allBookmakers: event.bookmakers
      };
    });

    console.log(`[Comparator] Processed ${comparatorData.length} events`);

    return new Response(
      JSON.stringify({ 
        data: comparatorData,
        count: comparatorData.length 
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );

  } catch (error) {
    console.error('[Comparator Error]', error);
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    return new Response(
      JSON.stringify({ error: errorMessage }),
      { 
        status: 500,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      }
    );
  }
});
