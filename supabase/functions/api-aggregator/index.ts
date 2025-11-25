import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.76.1";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

interface OddsCache {
  id: string;
  bookmaker: string;
  sport: string;
  event_name: string;
  league: string;
  market: string;
  event_time: string;
  odds: Record<string, number>;
  scraped_at: string;
  expires_at: string;
}

interface AggregatedOdds {
  event_id?: string;
  market: string;
  outcome: string;
  best_back_odds: number;
  best_back_bookmaker: string;
  best_lay_odds: number;
  best_lay_bookmaker: string;
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
    const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const supabase = createClient(supabaseUrl, supabaseKey);

    console.log('Starting aggregation process...');

    // Fetch all active odds from cache
    const { data: oddsData, error: oddsError } = await supabase
      .from('odds_cache')
      .select('*')
      .gt('expires_at', new Date().toISOString());

    if (oddsError) {
      console.error('Error fetching odds cache:', oddsError);
      throw oddsError;
    }

    console.log(`Fetched ${oddsData?.length || 0} active odds records`);

    if (!oddsData || oddsData.length === 0) {
      return new Response(
        JSON.stringify({ 
          message: 'No active odds to aggregate',
          aggregated_count: 0,
          matched_bets_count: 0 
        }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    // Group odds by event, market, and outcome
    const groupedOdds: Record<string, OddsCache[]> = {};
    
    for (const odds of oddsData as OddsCache[]) {
      const oddsObj = odds.odds as Record<string, number>;
      
      for (const [outcome, value] of Object.entries(oddsObj)) {
        const key = `${odds.event_name}|${odds.market}|${outcome}`;
        if (!groupedOdds[key]) {
          groupedOdds[key] = [];
        }
        groupedOdds[key].push({ ...odds, odds: { [outcome]: value } });
      }
    }

    console.log(`Grouped into ${Object.keys(groupedOdds).length} unique combinations`);

    const aggregatedResults: AggregatedOdds[] = [];
    const matchedBets = [];

    // Find best back and lay odds for each combination
    for (const [key, oddsArray] of Object.entries(groupedOdds)) {
      const [event_name, market, outcome] = key.split('|');
      
      let bestBackOdds = 0;
      let bestBackBookmaker = '';
      let bestLayOdds = Infinity;
      let bestLayBookmaker = '';

      for (const oddsEntry of oddsArray) {
        const oddsValue = Object.values(oddsEntry.odds)[0];
        const bookmaker = oddsEntry.bookmaker.toLowerCase();

        // Betfair is for lay odds, others for back odds
        if (bookmaker === 'betfair') {
          if (oddsValue < bestLayOdds && oddsValue > 1) {
            bestLayOdds = oddsValue;
            bestLayBookmaker = oddsEntry.bookmaker;
          }
        } else {
          if (oddsValue > bestBackOdds) {
            bestBackOdds = oddsValue;
            bestBackBookmaker = oddsEntry.bookmaker;
          }
        }
      }

      // Only create aggregated odds if we have both back and lay
      if (bestBackOdds > 0 && bestLayOdds !== Infinity) {
        const aggregated: AggregatedOdds = {
          market,
          outcome,
          best_back_odds: bestBackOdds,
          best_back_bookmaker: bestBackBookmaker,
          best_lay_odds: bestLayOdds,
          best_lay_bookmaker: bestLayBookmaker,
        };

        aggregatedResults.push(aggregated);

        // Calculate rating for matched betting
        const rating = (1 / ((1 / bestBackOdds) + (1 / bestLayOdds))) * 100;

        console.log(`${event_name} - ${market} - ${outcome}: Rating ${rating.toFixed(2)}%`);

        // If rating >= 95%, calculate matched bet
        if (rating >= 95) {
          const backStake = 100; // Default stake
          const commission = 5.0; // Default commission
          const layStake = (bestBackOdds * backStake) / bestLayOdds;

          // Calculate profits
          const backWinProfit = (bestBackOdds - 1) * backStake;
          const layLoss = (bestLayOdds - 1) * layStake;
          const profitIfBackWins = backWinProfit - layLoss;

          const layWinProfit = layStake * (1 - commission / 100);
          const backLoss = backStake;
          const profitIfLayWins = layWinProfit - backLoss;

          const profit = Math.min(profitIfBackWins, profitIfLayWins);

          matchedBets.push({
            back_bookmaker: bestBackBookmaker,
            lay_bookmaker: bestLayBookmaker,
            back_odds: bestBackOdds,
            lay_odds: bestLayOdds,
            back_stake: backStake,
            lay_stake: Math.round(layStake * 100) / 100,
            profit: Math.round(profit * 100) / 100,
            rating: Math.round(rating * 100) / 100,
            commission_rate: commission,
            market,
            outcome,
          });

          console.log(`✓ Matched bet found: ${event_name} - Profit: ${profit.toFixed(2)}`);
        }
      }
    }

    // Insert/update aggregated odds
    let aggregatedCount = 0;
    if (aggregatedResults.length > 0) {
      // Delete old aggregated odds
      await supabase.from('aggregated_odds').delete().neq('id', '00000000-0000-0000-0000-000000000000');

      // Insert new aggregated odds
      const { error: aggError } = await supabase
        .from('aggregated_odds')
        .insert(aggregatedResults);

      if (aggError) {
        console.error('Error inserting aggregated odds:', aggError);
      } else {
        aggregatedCount = aggregatedResults.length;
        console.log(`Inserted ${aggregatedCount} aggregated odds`);
      }
    }

    // Insert matched bets
    let matchedBetsCount = 0;
    if (matchedBets.length > 0) {
      // Delete old matched bets
      await supabase.from('matched_bets').delete().neq('id', '00000000-0000-0000-0000-000000000000');

      const { error: matchedError } = await supabase
        .from('matched_bets')
        .insert(matchedBets);

      if (matchedError) {
        console.error('Error inserting matched bets:', matchedError);
      } else {
        matchedBetsCount = matchedBets.length;
        console.log(`Inserted ${matchedBetsCount} matched bets`);
      }
    }

    return new Response(
      JSON.stringify({
        success: true,
        message: 'Aggregation completed successfully',
        aggregated_count: aggregatedCount,
        matched_bets_count: matchedBetsCount,
        timestamp: new Date().toISOString()
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );

  } catch (error) {
    console.error('Aggregation error:', error);
    return new Response(
      JSON.stringify({ 
        error: error instanceof Error ? error.message : 'Internal server error',
        timestamp: new Date().toISOString()
      }),
      { 
        status: 500, 
        headers: { ...corsHeaders, 'Content-Type': 'application/json' } 
      }
    );
  }
});
