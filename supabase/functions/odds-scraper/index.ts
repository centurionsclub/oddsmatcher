import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.7.1";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

interface OddsData {
  bookmaker: string;
  eventName: string;
  league: string;
  eventTime: string;
  market: string;
  sport: string;
  odds: Record<string, number>;
  volume: Record<string, number>;  // lay volume per outcome (Betfair only)
  marketId?: string;               // Betfair market ID (e.g. "1.234567890")
  eventId?: string;                // Betfair event ID for direct URL (e.g. "35512774")
  centroquoteUrl?: string;         // centroquote.it comparison page URL (bookmaker side)
}

serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  const startTime = Date.now();

  try {
    const supabase = createClient(
      Deno.env.get("SUPABASE_URL") ?? "",
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? ""
    );

    const body = await req.json().catch(() => ({}));
    const {
      sport = "tutti",
      market = "tutti",
      partita = "",
      campionato = "",
    } = body as Record<string, string>;

    // Query live_odds — rows inserted by the Python scraper.
    // Only filter by event_time: show prematch events starting at least 20 min from now.
    // expires_at is NOT used as a gate — stale rows are still shown if the event hasn't started.
    // We paginate in chunks of 5000 to bypass Supabase's PostgREST max_rows cap.
    const cutoff = new Date(Date.now() + 20 * 60 * 1000).toISOString();
    const PAGE_SIZE = 1000;
    let allRows: Record<string, unknown>[] = [];
    let offset = 0;
    while (true) {
      let query = supabase
        .from("live_odds")
        .select("bookmaker, sport, league, event_name, event_time, market, outcome, odds, volume, market_id, event_id, centroquote_url")
        .gt("event_time", cutoff)
        .order("event_time", { ascending: true })
        .range(offset, offset + PAGE_SIZE - 1);

      if (sport && sport !== "tutti") {
        query = query.eq("sport", sport);
      }
      if (campionato && campionato.trim()) {
        query = query.ilike("league", `%${campionato.trim()}%`);
      }
      if (partita && partita.trim()) {
        query = query.ilike("event_name", `%${partita.trim()}%`);
      }

      const { data: pageRows, error: pageError } = await query;
      if (pageError) {
        console.error("[odds-scraper] DB error:", pageError);
        throw new Error(pageError.message);
      }
      if (!pageRows || pageRows.length === 0) break;
      allRows = allRows.concat(pageRows as Record<string, unknown>[]);
      if (pageRows.length < PAGE_SIZE) break; // last page
      offset += PAGE_SIZE;
    }

    const rows = allRows;

    console.log(`[odds-scraper] Fetched ${rows.length} raw rows (paginated)`);

    if (!rows || rows.length === 0) {
      console.log("[odds-scraper] No live odds in DB — scraper may not have run yet.");
      return new Response(
        JSON.stringify({
          data: [],
          metadata: { totalResults: 0, bookmakers: 0, durationMs: Date.now() - startTime },
        }),
        { headers: { ...corsHeaders, "Content-Type": "application/json" } }
      );
    }

    // Group rows → OddsData objects
    // Key: bookmaker || eventName || market
    const grouped = new Map<string, OddsData>();

    for (const row of rows) {
      // Market filter (client can pass specific market like "Over 2.5")
      if (market && market !== "tutti" && row.market !== market) {
        // For Over/Under, the market stored is "Over/Under" but the outcome
        // contains the specific threshold like "Over 2.5".
        // Match if the requested market appears as outcome.
        if (row.market === "Over/Under") {
          if (row.outcome !== market) continue;
        } else {
          continue;
        }
      }

      const key = `${row.bookmaker}||${row.event_name}||${row.market}`;
      if (!grouped.has(key)) {
        grouped.set(key, {
          bookmaker: row.bookmaker,
          eventName: row.event_name,
          league: row.league,
          eventTime: row.event_time ?? new Date().toISOString(),
          market: row.market,
          sport: row.sport,
          odds: {},
          volume: {},
          marketId: row.market_id ?? undefined,
          eventId: row.event_id ?? undefined,
          centroquoteUrl: row.centroquote_url ?? undefined,
        });
      }
      const entry = grouped.get(key)!;
      entry.odds[row.outcome] = Number(row.odds);
      if (row.volume != null) {
        entry.volume[row.outcome] = Number(row.volume);
      }
    }

    const results = Array.from(grouped.values());
    const duration = Date.now() - startTime;

    console.log(`[odds-scraper] Returning ${results.length} records in ${duration}ms`);

    return new Response(
      JSON.stringify({
        data: results,
        metadata: {
          totalResults: results.length,
          bookmakers: new Set(results.map((r) => r.bookmaker)).size,
          durationMs: duration,
        },
      }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  } catch (err) {
    console.error("[odds-scraper] Fatal:", err);
    const msg = err instanceof Error ? err.message : String(err);
    return new Response(
      JSON.stringify({
        data: [],
        error: msg,
        metadata: { totalResults: 0, bookmakers: 0, durationMs: Date.now() - startTime },
      }),
      { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  }
});
