import { useState, useCallback } from "react";
import { supabase } from "@/integrations/supabase/client";

export interface OddsData {
  bookmaker: string;
  eventName: string;
  league: string;
  eventTime: string;
  market: string;
  sport: string;
  odds: Record<string, number>;
}

export interface OddsResponse {
  data: OddsData[];
  metadata: {
    totalResults: number;
    bookmakers: number;
    durationMs: number;
    sports?: string[];
    markets?: string[];
  };
  error?: string;
}

interface SearchFilters {
  sport?: string;
  mercato?: string;
  bookmaker?: string[];
  exchange?: string[];
  partita?: string;
  campionato?: string;
  daData?: Date;
  aData?: Date;
}

export function useOddsSearch() {
  const [data, setData] = useState<OddsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = useCallback(async (filters: SearchFilters) => {
    setLoading(true);
    setError(null);

    try {
      // Map frontend sport names to API sport names
      const sport = filters.sport === "tutti" ? "calcio" : (filters.sport || "calcio");

      // Map market filter
      const market = filters.mercato === "tutti" || filters.mercato === "nessuno"
        ? "tutti"
        : (filters.mercato || "tutti");

      const { data: responseData, error: fnError } = await supabase.functions.invoke(
        "odds-scraper",
        {
          body: {
            sport,
            market,
            bookmakers: filters.bookmaker || [],
            exchange: filters.exchange || ["betfair_exchange"],
          },
        }
      );

      if (fnError) {
        throw new Error(fnError.message || "Errore nella chiamata all'edge function");
      }

      const response = responseData as OddsResponse;

      // Client-side filters
      let filteredData = response.data || [];

      // Filter by match name
      if (filters.partita && filters.partita.trim()) {
        const search = filters.partita.toLowerCase().trim();
        filteredData = filteredData.filter((d) =>
          d.eventName.toLowerCase().includes(search)
        );
      }

      // Filter by league
      if (filters.campionato && filters.campionato !== "") {
        const search = filters.campionato.toLowerCase();
        filteredData = filteredData.filter((d) =>
          d.league.toLowerCase().includes(search)
        );
      }

      // Filter by date range
      if (filters.daData) {
        filteredData = filteredData.filter(
          (d) => new Date(d.eventTime) >= filters.daData!
        );
      }
      if (filters.aData) {
        const endOfDay = new Date(filters.aData);
        endOfDay.setHours(23, 59, 59, 999);
        filteredData = filteredData.filter(
          (d) => new Date(d.eventTime) <= endOfDay
        );
      }

      const result: OddsResponse = {
        ...response,
        data: filteredData,
        metadata: {
          ...response.metadata,
          totalResults: filteredData.length,
        },
      };

      // Check if the API key is missing
      if (response.error && response.error.includes("ODDS_API_KEY")) {
        setError("API Key non configurata. Configura ODDS_API_KEY nelle secrets di Supabase.");
        setData(result);
      } else {
        setData(result);
      }
    } catch (err: any) {
      setError(err.message || "Errore durante la ricerca");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setData(null);
    setError(null);
    setLoading(false);
  }, []);

  return { data, loading, error, search, reset };
}
