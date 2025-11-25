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

    if (req.method !== 'POST') {
      return new Response(
        JSON.stringify({ error: 'Method not allowed' }),
        { status: 405, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    const body = await req.json();
    const { 
      back_odds, 
      lay_odds, 
      back_stake, 
      commission = 5.0,
      event_id,
      back_bookmaker,
      market = '1X2',
      outcome = 'home'
    } = body;

    // Validate inputs
    if (!back_odds || !lay_odds || !back_stake) {
      return new Response(
        JSON.stringify({ error: 'Missing required fields: back_odds, lay_odds, back_stake' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    console.log('Calculating matched bet:', { back_odds, lay_odds, back_stake, commission });

    // Calculate lay stake
    const layStake = (back_odds * back_stake) / lay_odds;

    // Calculate potential profit/loss scenarios
    // If back bet wins
    const backWinProfit = (back_odds - 1) * back_stake;
    const layLoss = (lay_odds - 1) * layStake;
    const profitIfBackWins = backWinProfit - layLoss;

    // If lay bet wins (back bet loses)
    const layWinProfit = layStake * (1 - commission / 100);
    const backLoss = back_stake;
    const profitIfLayWins = layWinProfit - backLoss;

    // Overall profit (should be roughly equal for matched betting)
    const profit = Math.min(profitIfBackWins, profitIfLayWins);

    // Calculate rating (arbitrage percentage)
    const rating = (1 / ((1 / back_odds) + (1 / lay_odds))) * 100;

    const result = {
      back_odds,
      lay_odds,
      back_stake,
      lay_stake: Math.round(layStake * 100) / 100,
      profit: Math.round(profit * 100) / 100,
      profit_if_back_wins: Math.round(profitIfBackWins * 100) / 100,
      profit_if_lay_wins: Math.round(profitIfLayWins * 100) / 100,
      rating: Math.round(rating * 100) / 100,
      commission_rate: commission,
      is_arbitrage: rating >= 95,
      timestamp: new Date().toISOString()
    };

    console.log('Matched bet calculation result:', result);

    // Store in database if rating is good and event_id provided
    if (rating >= 95 && event_id && back_bookmaker) {
      const { error: insertError } = await supabase
        .from('matched_bets')
        .insert({
          event_id,
          back_bookmaker,
          lay_bookmaker: 'betfair',
          back_odds,
          lay_odds,
          back_stake,
          lay_stake: result.lay_stake,
          profit: result.profit,
          rating: result.rating,
          commission_rate: commission,
          market,
          outcome
        });

      if (insertError) {
        console.error('Error storing matched bet:', insertError);
      } else {
        console.log('Matched bet stored successfully');
      }
    }

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