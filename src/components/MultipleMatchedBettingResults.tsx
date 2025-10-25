import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ExternalLink } from "lucide-react";

interface OddsData {
  bookmaker: string;
  eventName: string;
  league: string;
  eventTime: string;
  market: string;
  odds: {
    home?: number;
    draw?: number;
    away?: number;
    over?: number;
    under?: number;
  };
}

interface MultipleOpportunity {
  events: {
    eventName: string;
    bookmaker: string;
    market: string;
    backOdds: number;
  }[];
  totalBackOdds: number;
  totalLayOdds: number;
  rating: number;
  profit: number;
  backStake: number;
  layStake: number;
  liability: number;
}

interface MultipleMatchedBettingResultsProps {
  data: {
    data: OddsData[];
    metadata?: any;
  };
  filters: any;
  commission: number;
  loading: boolean;
  error: string | null;
}

export function MultipleMatchedBettingResults({ data, filters, commission, loading, error }: MultipleMatchedBettingResultsProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-muted-foreground">Caricamento opportunità multiple...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-destructive">Errore: {error}</div>
      </div>
    );
  }

  if (!data?.data || data.data.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-muted-foreground">Nessuna opportunità trovata. Prova a modificare i filtri.</div>
      </div>
    );
  }

  // Calculate multiple betting opportunities
  const calculateMultipleOpportunities = (): MultipleOpportunity[] => {
    const opportunities: MultipleOpportunity[] = [];
    const stakeValue = parseFloat(filters.stakeMultipla?.toString().replace(',', '.')) || 0;
    const stake = stakeValue > 0 ? stakeValue : 10; // Minimo 10€ se non specificato
    const nEventi = parseInt(filters.nEventi) || 2;
    const commissionRate = commission / 100;

    // Filter odds based on criteria
    let filteredOdds = data.data.filter(odds => {
      const backOdds = odds.odds.home || odds.odds.over || 0;
      
      if (filters.quotaPartitaMinima && backOdds < parseFloat(filters.quotaPartitaMinima.replace(',', '.'))) return false;
      if (filters.quotaPartitaMassima && backOdds > parseFloat(filters.quotaPartitaMassima.replace(',', '.'))) return false;
      if (filters.partita && !odds.eventName.toLowerCase().includes(filters.partita.toLowerCase())) return false;
      if (filters.campionato && filters.campionato !== odds.league.toLowerCase()) return false;
      
      return true;
    });

    // Generate combinations of events
    const generateCombinations = (arr: OddsData[], size: number): OddsData[][] => {
      if (size === 1) return arr.map(item => [item]);
      
      const combinations: OddsData[][] = [];
      for (let i = 0; i <= arr.length - size; i++) {
        const smallerCombos = generateCombinations(arr.slice(i + 1), size - 1);
        smallerCombos.forEach(combo => {
          combinations.push([arr[i], ...combo]);
        });
      }
      return combinations;
    };

    const combinations = generateCombinations(filteredOdds.slice(0, 20), nEventi); // Limit to first 20 to avoid too many combinations

    combinations.forEach(combo => {
      const events = combo.map(odds => {
        const backOdds = odds.odds.home || odds.odds.over || odds.odds.away || 1.5;
        return {
          eventName: odds.eventName,
          bookmaker: odds.bookmaker,
          market: odds.market,
          backOdds,
        };
      });

      // Calculate total odds
      const totalBackOdds = events.reduce((acc, event) => acc * event.backOdds, 1);
      const totalLayOdds = totalBackOdds * 0.93; // Exchange typically offers ~7% worse odds

      // Calculate stakes
      const layStake = (stake * totalBackOdds) / (totalLayOdds - commissionRate);
      const liability = layStake * (totalLayOdds - 1);

      // Calculate profit/loss
      const backWin = stake * (totalBackOdds - 1);
      const layLoss = -liability;
      const layWin = layStake * (1 - commissionRate);

      const profit = Math.min(backWin + layLoss, layWin - stake);
      const rating = (profit / stake) * 100;

      // Filter by minimum multiple odds
      if (filters.quotaMinimaMultipla && totalBackOdds < parseFloat(filters.quotaMinimaMultipla.replace(',', '.'))) return;

      opportunities.push({
        events,
        totalBackOdds,
        totalLayOdds,
        rating,
        profit,
        backStake: stake,
        layStake,
        liability,
      });
    });

    return opportunities.sort((a, b) => b.rating - a.rating).slice(0, 50); // Show top 50
  };

  const opportunities = calculateMultipleOpportunities();

  return (
    <div className="mt-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Opportunità Matched Betting Multiple</h3>
        <div className="text-sm text-muted-foreground">
          Trovate {opportunities.length} combinazioni
        </div>
      </div>

      <div className="space-y-4">
        {opportunities.map((opp, index) => (
          <div key={index} className="border rounded-lg p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="font-semibold">Multipla #{index + 1}</div>
              <Badge variant={opp.rating > 95 ? "default" : "secondary"}>
                Rating: {opp.rating.toFixed(2)}%
              </Badge>
            </div>

            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">Quota Totale Back:</span>
                <span className="ml-2 font-mono font-semibold">{opp.totalBackOdds.toFixed(2)}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Quota Totale Lay:</span>
                <span className="ml-2 font-mono font-semibold">{opp.totalLayOdds.toFixed(2)}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Punta:</span>
                <span className="ml-2 font-mono font-semibold text-blue-600">€{opp.backStake.toFixed(2)}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Banca:</span>
                <span className="ml-2 font-mono font-semibold text-blue-600">€{opp.layStake.toFixed(2)}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Profitto:</span>
                <span className="ml-2 font-mono font-semibold text-green-600">€{opp.profit.toFixed(2)}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Passivo:</span>
                <span className="ml-2 font-mono font-semibold text-red-600">€{opp.liability.toFixed(2)}</span>
              </div>
            </div>

            <div className="border-t pt-3">
              <div className="text-sm font-medium mb-2">Eventi nella multipla:</div>
              <div className="space-y-2">
                {opp.events.map((event, eventIndex) => (
                  <div key={eventIndex} className="flex items-center justify-between bg-secondary/30 p-2 rounded text-sm">
                    <div className="flex-1">
                      <div className="font-medium">{event.eventName}</div>
                      <div className="text-xs text-muted-foreground">{event.market}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-xs">{event.bookmaker}</Badge>
                      <span className="font-mono font-semibold">{event.backOdds.toFixed(2)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex justify-end">
              <Button variant="outline" size="sm">
                <ExternalLink className="h-4 w-4 mr-2" />
                Apri Bookmaker
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
