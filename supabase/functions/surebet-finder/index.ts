import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.7.1";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

interface SurebetOpportunity {
  id: string;
  sport: string;
  event: {
    home: string;
    away: string;
    startTime: string;
    league: string;
  };
  market: string;
  legs: Array<{
    bookmaker: string;
    outcome: string;
    odds: number;
    stake?: number;
    potentialReturn?: number;
  }>;
  profitPercentage: number;
  guaranteedProfit?: number;
  totalStake?: number;
  arbitrageRatio: number;
}

// Sport keys mapping for The Odds API
const SPORT_KEYS: Record<string, string> = {
  'calcio': 'soccer_italy_serie_a',
  'basket': 'basketball_nba',
  'tennis': 'tennis_atp_singles',
  'all': 'soccer_italy_serie_a' // Default
};

// Fetch from The Odds API
async function fetchFromTheOddsAPI(sport: string, market: string): Promise<any[]> {
  const apiKey = Deno.env.get('THE_ODDS_API_KEY');
  if (!apiKey) {
    throw new Error('THE_ODDS_API_KEY not configured');
  }

  const sportKey = SPORT_KEYS[sport.toLowerCase()] || SPORT_KEYS['calcio'];
  
  const url = new URL(`https://api.the-odds-api.com/v4/sports/${sportKey}/odds/`);
  url.searchParams.set('apiKey', apiKey);
  url.searchParams.set('regions', 'eu');
  url.searchParams.set('markets', market === '1X2' ? 'h2h' : 'totals');
  url.searchParams.set('oddsFormat', 'decimal');

  console.log(`Fetching odds from The Odds API for ${sportKey}...`);

  const response = await fetch(url.toString(), {
    signal: AbortSignal.timeout(15000),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`The Odds API error: ${response.status} - ${errorText}`);
  }

  const data = await response.json();
  console.log(`The Odds API returned ${data.length} events`);

  return data;
}

// Calculate arbitrage for 1X2 market (3-way)
function calculateThreeWayArbitrage(odds: { home: number; draw: number; away: number }): {
  hasArbitrage: boolean;
  profitPercentage: number;
  arbitrageRatio: number;
} {
  const { home, draw, away } = odds;
  
  if (!home || !draw || !away || home <= 1 || draw <= 1 || away <= 1) {
    return { hasArbitrage: false, profitPercentage: 0, arbitrageRatio: 0 };
  }

  const arbitrageRatio = (1 / home) + (1 / draw) + (1 / away);
  const hasArbitrage = arbitrageRatio < 1;
  const profitPercentage = hasArbitrage ? ((1 / arbitrageRatio) - 1) * 100 : 0;

  return { hasArbitrage, profitPercentage, arbitrageRatio };
}

// Calculate arbitrage for 2-way market (Over/Under, Home/Away)
function calculateTwoWayArbitrage(odds1: number, odds2: number): {
  hasArbitrage: boolean;
  profitPercentage: number;
  arbitrageRatio: number;
} {
  if (!odds1 || !odds2 || odds1 <= 1 || odds2 <= 1) {
    return { hasArbitrage: false, profitPercentage: 0, arbitrageRatio: 0 };
  }

  const arbitrageRatio = (1 / odds1) + (1 / odds2);
  const hasArbitrage = arbitrageRatio < 1;
  const profitPercentage = hasArbitrage ? ((1 / arbitrageRatio) - 1) * 100 : 0;

  return { hasArbitrage, profitPercentage, arbitrageRatio };
}

// Calculate stakes for each leg
function calculateStakes(
  legs: Array<{ odds: number }>,
  totalBudget: number,
  arbitrageRatio: number
): number[] {
  return legs.map(leg => {
    return (totalBudget / arbitrageRatio) / leg.odds;
  });
}

// Find surebet opportunities
function findSurebets(
  events: any[],
  market: string,
  minProfit: number,
  budget: number
): SurebetOpportunity[] {
  const opportunities: SurebetOpportunity[] = [];

  events.forEach((event) => {
    const bookmakers = event.bookmakers || [];
    if (bookmakers.length < 2) return; // Need at least 2 bookmakers

    // Extract all odds from all bookmakers
    const bookmakerOdds: Array<{
      bookmaker: string;
      home?: number;
      draw?: number;
      away?: number;
      over?: number;
      under?: number;
    }> = [];

    bookmakers.forEach((bm: any) => {
      const markets = bm.markets || [];
      markets.forEach((mkt: any) => {
        if ((mkt.key === 'h2h' && market === '1X2') || (mkt.key === 'totals' && market !== '1X2')) {
          const outcomes = mkt.outcomes || [];
          const oddsData: any = { bookmaker: bm.title };
          
          outcomes.forEach((outcome: any) => {
            if (mkt.key === 'h2h') {
              if (outcome.name === event.home_team) oddsData.home = outcome.price;
              if (outcome.name === event.away_team) oddsData.away = outcome.price;
              if (outcome.name === 'Draw') oddsData.draw = outcome.price;
            } else if (mkt.key === 'totals') {
              if (outcome.name === 'Over') oddsData.over = outcome.price;
              if (outcome.name === 'Under') oddsData.under = outcome.price;
            }
          });

          bookmakerOdds.push(oddsData);
        }
      });
    });

    if (market === '1X2') {
      // Find best combination for 3-way arbitrage
      const bestHome = bookmakerOdds.reduce((max, b) => (b.home || 0) > (max.home || 0) ? b : max, { home: 0, bookmaker: '' });
      const bestDraw = bookmakerOdds.reduce((max, b) => (b.draw || 0) > (max.draw || 0) ? b : max, { draw: 0, bookmaker: '' });
      const bestAway = bookmakerOdds.reduce((max, b) => (b.away || 0) > (max.away || 0) ? b : max, { away: 0, bookmaker: '' });

      if (bestHome.home && bestDraw.draw && bestAway.away) {
        const arb = calculateThreeWayArbitrage({
          home: bestHome.home,
          draw: bestDraw.draw,
          away: bestAway.away
        });

        if (arb.hasArbitrage && arb.profitPercentage >= minProfit) {
          const legs = [
            { bookmaker: bestHome.bookmaker, outcome: '1', odds: bestHome.home },
            { bookmaker: bestDraw.bookmaker, outcome: 'X', odds: bestDraw.draw },
            { bookmaker: bestAway.bookmaker, outcome: '2', odds: bestAway.away }
          ];

          const stakes = calculateStakes(legs, budget, arb.arbitrageRatio);
          const guaranteedProfit = budget * (arb.profitPercentage / 100);

          opportunities.push({
            id: `${event.id}-${Date.now()}`,
            sport: event.sport_title,
            event: {
              home: event.home_team,
              away: event.away_team,
              startTime: event.commence_time,
              league: event.sport_title
            },
            market: '1X2',
            legs: legs.map((leg, idx) => ({
              ...leg,
              stake: stakes[idx],
              potentialReturn: stakes[idx] * leg.odds
            })),
            profitPercentage: arb.profitPercentage,
            guaranteedProfit,
            totalStake: budget,
            arbitrageRatio: arb.arbitrageRatio
          });
        }
      }
    } else {
      // Find best combination for 2-way arbitrage (Over/Under)
      const bestOver = bookmakerOdds.reduce((max, b) => (b.over || 0) > (max.over || 0) ? b : max, { over: 0, bookmaker: '' });
      const bestUnder = bookmakerOdds.reduce((max, b) => (b.under || 0) > (max.under || 0) ? b : max, { under: 0, bookmaker: '' });

      if (bestOver.over && bestUnder.under) {
        const arb = calculateTwoWayArbitrage(bestOver.over, bestUnder.under);

        if (arb.hasArbitrage && arb.profitPercentage >= minProfit) {
          const legs = [
            { bookmaker: bestOver.bookmaker, outcome: 'Over', odds: bestOver.over },
            { bookmaker: bestUnder.bookmaker, outcome: 'Under', odds: bestUnder.under }
          ];

          const stakes = calculateStakes(legs, budget, arb.arbitrageRatio);
          const guaranteedProfit = budget * (arb.profitPercentage / 100);

          opportunities.push({
            id: `${event.id}-${Date.now()}`,
            sport: event.sport_title,
            event: {
              home: event.home_team,
              away: event.away_team,
              startTime: event.commence_time,
              league: event.sport_title
            },
            market: market,
            legs: legs.map((leg, idx) => ({
              ...leg,
              stake: stakes[idx],
              potentialReturn: stakes[idx] * leg.odds
            })),
            profitPercentage: arb.profitPercentage,
            guaranteedProfit,
            totalStake: budget,
            arbitrageRatio: arb.arbitrageRatio
          });
        }
      }
    }
  });

  // Sort by profit percentage (highest first)
  return opportunities.sort((a, b) => b.profitPercentage - a.profitPercentage);
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const { sport = 'calcio', market = '1X2', minProfit = 0.5, budget = 100 } = await req.json();

    console.log(`Surebet finder called with: sport=${sport}, market=${market}, minProfit=${minProfit}%`);

    // Fetch odds from The Odds API
    const events = await fetchFromTheOddsAPI(sport, market);

    // Find arbitrage opportunities
    const surebets = findSurebets(events, market, minProfit, budget);

    console.log(`Found ${surebets.length} surebet opportunities`);

    return new Response(
      JSON.stringify({
        success: true,
        count: surebets.length,
        surebets,
        timestamp: new Date().toISOString()
      }),
      {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      }
    );

  } catch (error) {
    console.error('Surebet finder error:', error);
    return new Response(
      JSON.stringify({
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
        surebets: []
      }),
      {
        status: 500,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      }
    );
  }
});
