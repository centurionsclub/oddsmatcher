import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.76.1';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

const THRESHOLD_PERCENTAGE = 5; // 5% better than average

Deno.serve(async (req) => {
  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
    const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const supabase = createClient(supabaseUrl, supabaseKey);

    console.log('[Monitor] Starting odds anomaly detection...');

    // Fetch all active odds
    const { data: odds, error: fetchError } = await supabase
      .from('odds_cache')
      .select('*')
      .gt('expires_at', new Date().toISOString());

    if (fetchError) {
      throw new Error(`Failed to fetch odds: ${fetchError.message}`);
    }

    if (!odds || odds.length === 0) {
      console.log('[Monitor] No active odds found');
      return new Response(
        JSON.stringify({ message: 'No active odds to monitor', alerts: 0 }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    console.log(`[Monitor] Analyzing ${odds.length} odds records...`);

    // Group by event and outcome
    const eventOutcomes = new Map<string, any[]>();
    
    for (const odd of odds) {
      const oddsData = odd.odds as Record<string, number>;
      
      for (const [outcome, value] of Object.entries(oddsData)) {
        if (typeof value !== 'number' || value <= 0) continue;
        
        const key = `${odd.event_name}:${outcome}`;
        
        if (!eventOutcomes.has(key)) {
          eventOutcomes.set(key, []);
        }
        
        const outcomes = eventOutcomes.get(key);
        if (outcomes) {
          outcomes.push({
            bookmaker: odd.bookmaker,
            odds: value,
            event: odd.event_name,
            outcome,
            eventTime: odd.event_time,
            market: odd.market
          });
        }
      }
    }

    console.log(`[Monitor] Grouped into ${eventOutcomes.size} unique event-outcomes`);

    // Find anomalous odds
    const alerts: any[] = [];
    
    for (const [key, oddsArray] of eventOutcomes.entries()) {
      if (oddsArray.length < 3) continue; // Need at least 3 bookmakers
      
      const values = oddsArray.map(o => o.odds).filter(v => v > 0);
      const average = values.reduce((a, b) => a + b, 0) / values.length;
      const max = Math.max(...values);
      
      // If max odds is at least 5% higher than average
      const difference = (max - average) / average;
      if (difference >= THRESHOLD_PERCENTAGE / 100) {
        const bestBookmaker = oddsArray.find(o => o.odds === max)!;
        
        alerts.push({
          event_name: bestBookmaker.event,
          outcome: bestBookmaker.outcome,
          bookmaker: bestBookmaker.bookmaker,
          odds: max,
          average_odds: parseFloat(average.toFixed(2)),
          difference_percentage: parseFloat((difference * 100).toFixed(1)),
          event_time: bestBookmaker.eventTime,
          created_at: new Date().toISOString(),
          expires_at: new Date(Date.now() + 15 * 60 * 1000).toISOString() // 15 min
        });
      }
    }

    console.log(`[Monitor] Found ${alerts.length} anomalous odds`);

    // Save alerts to database
    if (alerts.length > 0) {
      const { error: insertError } = await supabase
        .from('odds_alerts')
        .insert(alerts);

      if (insertError) {
        console.error('[Monitor] Failed to insert alerts:', insertError);
        throw new Error(`Failed to save alerts: ${insertError.message}`);
      }

      console.log(`[Monitor] Saved ${alerts.length} alerts to database`);
    }

    return new Response(
      JSON.stringify({ 
        message: 'Monitoring complete',
        alerts: alerts.length,
        details: alerts.slice(0, 5) // Return first 5 for logging
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );

  } catch (error) {
    console.error('[Monitor Error]', error);
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
