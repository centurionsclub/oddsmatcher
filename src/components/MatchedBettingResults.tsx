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

interface MatchedBettingOpportunity {
  bookmaker: string;
  eventName: string;
  league: string;
  eventTime: string;
  market: string;
  backOdds: number;
  layOdds: number;
  rating: number;
  profit: number;
  backStake: number;
  layStake: number;
  liability: number;
}

interface MatchedBettingResultsProps {
  data: {
    data: OddsData[];
    metadata?: {
      totalResults: number;
      bookmakers: number;
      durationMs: number;
    };
  };
  filters: any;
  commission: number;
  loading: boolean;
  error: string | null;
}

export function MatchedBettingResults({ data, filters, commission, loading, error }: MatchedBettingResultsProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-muted-foreground">Caricamento opportunità...</div>
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

  // Calculate matched betting opportunities
  const calculateOpportunities = (): MatchedBettingOpportunity[] => {
    const opportunities: MatchedBettingOpportunity[] = [];
    const stake = parseFloat(filters.stakePunta) || 10;
    const commissionRate = commission / 100;

    data.data.forEach(odds => {
      const { bookmaker, eventName, league, eventTime, market } = odds;
      
      // For each market type, calculate back and lay stakes
      if (market === '1X2') {
        // For 1X2, we can match any outcome
        ['home', 'draw', 'away'].forEach(outcome => {
          const backOdds = odds.odds[outcome as keyof typeof odds.odds];
          if (!backOdds) return;
          
          // Simulate lay odds (typically 5-10% lower than back odds)
          const layOdds = backOdds * 0.95;
          
          // Calculate lay stake
          const layStake = (stake * backOdds) / (layOdds - commissionRate);
          const liability = layStake * (layOdds - 1);
          
          // Calculate profit/loss
          const backWin = stake * (backOdds - 1);
          const layLoss = -liability;
          const layWin = layStake * (1 - commissionRate);
          
          const profit = Math.min(backWin + layLoss, layWin - stake);
          const rating = (profit / stake) * 100;

          // Apply filters
          if (filters.quotaMinima && backOdds < parseFloat(filters.quotaMinima.replace(',', '.'))) return;
          if (filters.quotaMassima && backOdds > parseFloat(filters.quotaMassima.replace(',', '.'))) return;
          if (filters.partita && !eventName.toLowerCase().includes(filters.partita.toLowerCase())) return;
          if (filters.campionato && filters.campionato !== league.toLowerCase()) return;

          opportunities.push({
            bookmaker,
            eventName,
            league,
            eventTime,
            market: `${market} - ${outcome}`,
            backOdds,
            layOdds,
            rating,
            profit,
            backStake: stake,
            layStake,
            liability,
          });
        });
      } else if (market === 'goal' || market.includes('over') || market.includes('under')) {
        // For goal/over/under markets
        const outcomes = market === 'goal' ? ['over', 'under'] : [market.includes('over') ? 'over' : 'under'];
        
        outcomes.forEach(outcome => {
          const backOdds = odds.odds[outcome as keyof typeof odds.odds];
          if (!backOdds) return;
          
          const layOdds = backOdds * 0.95;
          const layStake = (stake * backOdds) / (layOdds - commissionRate);
          const liability = layStake * (layOdds - 1);
          
          const backWin = stake * (backOdds - 1);
          const layLoss = -liability;
          const layWin = layStake * (1 - commissionRate);
          
          const profit = Math.min(backWin + layLoss, layWin - stake);
          const rating = (profit / stake) * 100;

          if (filters.quotaMinima && backOdds < parseFloat(filters.quotaMinima.replace(',', '.'))) return;
          if (filters.quotaMassima && backOdds > parseFloat(filters.quotaMassima.replace(',', '.'))) return;
          if (filters.partita && !eventName.toLowerCase().includes(filters.partita.toLowerCase())) return;

          opportunities.push({
            bookmaker,
            eventName,
            league,
            eventTime,
            market: `${market} - ${outcome}`,
            backOdds,
            layOdds,
            rating,
            profit,
            backStake: stake,
            layStake,
            liability,
          });
        });
      }
    });

    // Sort by rating (best opportunities first)
    return opportunities.sort((a, b) => b.rating - a.rating);
  };

  const opportunities = calculateOpportunities();

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return `${date.getDate().toString().padStart(2, '0')}/${(date.getMonth() + 1).toString().padStart(2, '0')}/${date.getFullYear().toString().slice(-2)} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
  };

  return (
    <div className="mt-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Opportunità Matched Betting</h3>
        <div className="text-sm text-muted-foreground">
          Trovate {opportunities.length} opportunità
        </div>
      </div>

      <div className="border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Evento</TableHead>
              <TableHead>Campionato</TableHead>
              <TableHead>Data/Ora</TableHead>
              <TableHead>Bookmaker</TableHead>
              <TableHead>Mercato</TableHead>
              <TableHead className="text-right">Quota Back</TableHead>
              <TableHead className="text-right">Quota Lay</TableHead>
              <TableHead className="text-right">Rating %</TableHead>
              <TableHead className="text-right">Profitto €</TableHead>
              <TableHead className="text-right">Punta €</TableHead>
              <TableHead className="text-right">Banca €</TableHead>
              <TableHead className="text-right">Passivo €</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {opportunities.map((opp, index) => (
              <TableRow key={index}>
                <TableCell className="font-medium">{opp.eventName}</TableCell>
                <TableCell>{opp.league}</TableCell>
                <TableCell className="text-sm">{formatDate(opp.eventTime)}</TableCell>
                <TableCell>
                  <Badge variant="outline">{opp.bookmaker}</Badge>
                </TableCell>
                <TableCell className="text-sm">{opp.market}</TableCell>
                <TableCell className="text-right font-mono">{opp.backOdds.toFixed(2)}</TableCell>
                <TableCell className="text-right font-mono">{opp.layOdds.toFixed(2)}</TableCell>
                <TableCell className="text-right">
                  <Badge variant={opp.rating > 95 ? "default" : "secondary"}>
                    {opp.rating.toFixed(2)}%
                  </Badge>
                </TableCell>
                <TableCell className="text-right font-mono text-green-600">
                  €{opp.profit.toFixed(2)}
                </TableCell>
                <TableCell className="text-right font-mono">€{opp.backStake.toFixed(2)}</TableCell>
                <TableCell className="text-right font-mono">€{opp.layStake.toFixed(2)}</TableCell>
                <TableCell className="text-right font-mono text-red-600">
                  €{opp.liability.toFixed(2)}
                </TableCell>
                <TableCell>
                  <Button variant="ghost" size="sm">
                    <ExternalLink className="h-4 w-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
