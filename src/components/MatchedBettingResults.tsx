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
  sport: string;
  odds: Record<string, number>;
}

interface MatchedBettingOpportunity {
  bookmaker: string;
  exchange: string;
  eventName: string;
  league: string;
  eventTime: string;
  market: string;
  outcome: string;
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
  } | null;
  filters: any;
  commission: number;
  loading: boolean;
  error: string | null;
}

// Bookmaker names that are exchanges (lay odds source)
const EXCHANGE_NAMES = [
  'betfair exchange', 'betfair', 'betflag exchange', 'betflag',
  'smarkets', 'betdaq', 'matchbook',
];

function isExchange(bookmaker: string): boolean {
  return EXCHANGE_NAMES.some(ex => bookmaker.toLowerCase().includes(ex));
}

function normalizeEventName(name: string): string {
  return name.toLowerCase()
    .replace(/\s+/g, '')
    .replace(/[-–—]/g, '')
    .replace(/\./g, '')
    .replace(/'/g, '');
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
        <div className="text-muted-foreground">
          {data === null
            ? "Clicca CERCA per caricare le quote."
            : "Nessuna opportunità trovata. Prova a modificare i filtri."}
        </div>
      </div>
    );
  }

  const calculateOpportunities = (): MatchedBettingOpportunity[] => {
    const opportunities: MatchedBettingOpportunity[] = [];
    const stakeValue = parseFloat(filters.stakePunta?.toString().replace(',', '.')) || 0;
    const stake = stakeValue > 0 ? stakeValue : 100;
    const commissionRate = commission / 100;

    // Separate bookmaker odds and exchange odds
    const bookmakerOdds = data.data.filter(odd => !isExchange(odd.bookmaker));
    const exchangeOdds = data.data.filter(odd => isExchange(odd.bookmaker));

    // For each bookmaker event, find matching exchange event
    bookmakerOdds.forEach(bmEvent => {
      const normalizedBm = normalizeEventName(bmEvent.eventName);

      // Find matching exchange events
      const matchingExchanges = exchangeOdds.filter(exEvent => {
        const normalizedEx = normalizeEventName(exEvent.eventName);
        return normalizedBm === normalizedEx ||
          normalizedBm.includes(normalizedEx.substring(0, 10)) ||
          normalizedEx.includes(normalizedBm.substring(0, 10));
      });

      if (matchingExchanges.length === 0) return;

      // Determine outcomes based on market
      const outcomes: Array<{ key: string; label: string }> = [];
      if (bmEvent.market === '1X2' || bmEvent.market === 'h2h') {
        if (bmEvent.odds.home) outcomes.push({ key: 'home', label: '1' });
        if (bmEvent.odds.draw) outcomes.push({ key: 'draw', label: 'X' });
        if (bmEvent.odds.away) outcomes.push({ key: 'away', label: '2' });
      } else if (bmEvent.market === '12') {
        if (bmEvent.odds.home) outcomes.push({ key: 'home', label: '1' });
        if (bmEvent.odds.away) outcomes.push({ key: 'away', label: '2' });
      } else {
        if (bmEvent.odds.over) outcomes.push({ key: 'over', label: 'Over' });
        if (bmEvent.odds.under) outcomes.push({ key: 'under', label: 'Under' });
      }

      outcomes.forEach(outcome => {
        const backOdds = bmEvent.odds[outcome.key];
        if (!backOdds || backOdds <= 1) return;

        // Find best lay odds across all matching exchanges
        let bestLayOdds = Infinity;
        let bestExchange = '';

        matchingExchanges.forEach(exEvent => {
          const layOdds = exEvent.odds[outcome.key];
          if (layOdds && layOdds > 1 && layOdds < bestLayOdds) {
            bestLayOdds = layOdds;
            bestExchange = exEvent.bookmaker;
          }
        });

        if (bestLayOdds === Infinity) return;

        // Calculate lay stake and liability
        const layStake = (stake * backOdds) / (bestLayOdds - commissionRate * (bestLayOdds - 1));
        const liability = layStake * (bestLayOdds - 1);

        // Calculate profit/loss for both scenarios
        const backWin = stake * (backOdds - 1);
        const layWin = layStake * (1 - commissionRate);

        const profitIfWin = backWin - liability;
        const profitIfLose = layWin - stake;

        // Rating = qualifying loss percentage
        const averageProfit = (profitIfWin + profitIfLose) / 2;
        const rating = (averageProfit / stake) * 100;

        // Apply filters
        const quotaMin = parseFloat((filters.quotaMinima || '0').replace(',', '.'));
        const quotaMax = parseFloat((filters.quotaMassima || '0').replace(',', '.'));
        if (quotaMin > 0 && backOdds < quotaMin) return;
        if (quotaMax > 0 && backOdds > quotaMax) return;
        if (filters.partita && !bmEvent.eventName.toLowerCase().includes(filters.partita.toLowerCase())) return;

        opportunities.push({
          bookmaker: bmEvent.bookmaker,
          exchange: bestExchange,
          eventName: bmEvent.eventName,
          league: bmEvent.league,
          eventTime: bmEvent.eventTime,
          market: `${bmEvent.market} - ${outcome.label}`,
          outcome: outcome.label,
          backOdds,
          layOdds: bestLayOdds,
          rating,
          profit: averageProfit,
          backStake: stake,
          layStake,
          liability,
        });
      });
    });

    // Sort by rating (closest to 0 = best)
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
          {data.metadata && (
            <span className="mr-4">
              {data.metadata.bookmakers} bookmaker · {data.metadata.totalResults} quote · {data.metadata.durationMs}ms
            </span>
          )}
          Trovate {opportunities.length} opportunità
        </div>
      </div>

      {opportunities.length === 0 ? (
        <div className="flex items-center justify-center py-8">
          <div className="text-muted-foreground">
            Nessuna opportunità di matched betting trovata con i filtri attuali.
          </div>
        </div>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Evento</TableHead>
                <TableHead>Campionato</TableHead>
                <TableHead>Data/Ora</TableHead>
                <TableHead>Bookmaker</TableHead>
                <TableHead>Exchange</TableHead>
                <TableHead>Mercato</TableHead>
                <TableHead className="text-right">Quota Back</TableHead>
                <TableHead className="text-right">Quota Lay</TableHead>
                <TableHead className="text-right">Rating %</TableHead>
                <TableHead className="text-right">Perdita €</TableHead>
                <TableHead className="text-right">Punta €</TableHead>
                <TableHead className="text-right">Banca €</TableHead>
                <TableHead className="text-right">Passivo €</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {opportunities.map((opp, index) => (
                <TableRow key={index}>
                  <TableCell className="font-medium max-w-[200px] truncate">{opp.eventName}</TableCell>
                  <TableCell>
                    <Badge variant="secondary" className="text-xs">{opp.league}</Badge>
                  </TableCell>
                  <TableCell className="text-sm whitespace-nowrap">{formatDate(opp.eventTime)}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{opp.bookmaker}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="bg-blue-500/10 text-blue-400 border-blue-500/30">{opp.exchange}</Badge>
                  </TableCell>
                  <TableCell className="text-sm">{opp.market}</TableCell>
                  <TableCell className="text-right font-mono">{opp.backOdds.toFixed(2)}</TableCell>
                  <TableCell className="text-right font-mono">{opp.layOdds.toFixed(2)}</TableCell>
                  <TableCell className="text-right">
                    <Badge variant={opp.rating > -5 ? "default" : opp.rating > -8 ? "secondary" : "destructive"}>
                      {opp.rating.toFixed(2)}%
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right font-mono text-red-400">
                    €{opp.profit.toFixed(2)}
                  </TableCell>
                  <TableCell className="text-right font-mono">€{opp.backStake.toFixed(2)}</TableCell>
                  <TableCell className="text-right font-mono">€{opp.layStake.toFixed(2)}</TableCell>
                  <TableCell className="text-right font-mono text-red-400">
                    €{opp.liability.toFixed(2)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
