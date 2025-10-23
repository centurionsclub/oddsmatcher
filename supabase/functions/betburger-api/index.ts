import "https://deno.land/x/xhr@0.1.0/mod.ts";
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const BETBURGER_API_KEY = Deno.env.get('BETBURGER_API_KEY');
const BETBURGER_API_URL = 'https://rest-api.betburger.com/api/v1';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

interface BetburgerFilters {
  sport?: string;
  market?: string;
  bookmakers?: string[];
  exchanges?: string[];
  minProfit?: number;
  maxProfit?: number;
  minOdds?: number;
  maxOdds?: number;
  startedAtFrom?: string;
  startedAtTo?: string;
  eventName?: string;
  league?: string;
  freebet?: boolean;
  page?: number;
  perPage?: number;
}

serve(async (req) => {
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    console.log('Betburger API request received');

    if (!BETBURGER_API_KEY) {
      throw new Error('BETBURGER_API_KEY not configured');
    }

    const { filters, endpoint = 'arbs' } = await req.json();
    console.log('Filters received:', filters);

    // Build query parameters
    const params = new URLSearchParams();
    params.append('token', BETBURGER_API_KEY);

    // Map filters to Betburger API parameters
    if (filters.sport && filters.sport !== 'tutti') {
      // Sport mapping (you may need to adjust IDs based on Betburger's sport IDs)
      const sportMap: Record<string, string> = {
        'calcio': '1',
        'tennis': '2',
        'basket': '3',
      };
      if (sportMap[filters.sport]) {
        params.append('sport_id', sportMap[filters.sport]);
      }
    }

    if (filters.bookmakers && filters.bookmakers.length > 0) {
      params.append('bookmakers', filters.bookmakers.join(','));
    }

    if (filters.minProfit) {
      params.append('min_profit', filters.minProfit.toString());
    }

    if (filters.maxProfit) {
      params.append('max_profit', filters.maxProfit.toString());
    }

    if (filters.minOdds) {
      params.append('min_coef', filters.minOdds.toString());
    }

    if (filters.maxOdds) {
      params.append('max_coef', filters.maxOdds.toString());
    }

    if (filters.startedAtFrom) {
      params.append('started_at_from', filters.startedAtFrom);
    }

    if (filters.startedAtTo) {
      params.append('started_at_to', filters.startedAtTo);
    }

    // Pagination
    params.append('page', (filters.page || 1).toString());
    params.append('per_page', (filters.perPage || 50).toString());

    const apiUrl = `${BETBURGER_API_URL}/${endpoint}?${params.toString()}`;
    console.log('Calling Betburger API:', apiUrl);

    const response = await fetch(apiUrl, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('Betburger API error:', response.status, errorText);
      throw new Error(`Betburger API returned ${response.status}: ${errorText}`);
    }

    const data = await response.json();
    console.log('Betburger API response received:', data?.arbs?.length || 0, 'arbs found');

    return new Response(JSON.stringify(data), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Error in betburger-api function:', error);
    const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
    return new Response(
      JSON.stringify({ 
        error: errorMessage,
        details: 'Failed to fetch data from Betburger API'
      }), 
      {
        status: 500,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      }
    );
  }
});
