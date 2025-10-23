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
  };
}

interface ArbitrageOpportunity {
  eventName: string;
  league: string;
  eventTime: string;
  bookmaker1: string;
  bookmaker2: string;
  bookmaker3: string;
  odds1: number;
  oddsX: number;
  odds2: number;
  stake1: number;
  stakeX: number;
  stake2: number;
  totalStake: number;
  profit: number;
  profitPercent: number;
  arbitragePercent: number;
}

interface ThreeWayArbitrageResultsProps {
  data: {
    data: OddsData[];
    metadata?: any;
  };
  filters: any;
  loading: boolean;
  error: string | null;
}

export function ThreeWayArbitrageResults({ data, filters, loading, error }: ThreeWayArbitrageResultsProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-muted-foreground">Caricamento opportunità arbitraggio...</div>
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

  // Calculate three-way arbitrage opportunities
  const calculateArbitrageOpportunities = (): ArbitrageOpportunity[] => {
    const opportunities: ArbitrageOpportunity[] = [];
    const stake = parseFloat(filters.stakePunta) || 100;

    // Group odds by event
    const eventGroups = new Map<string, OddsData[]>();
    data.data.forEach(odds => {
      if (odds.market !== '1X2') return; // Only 1X2 markets
      
      const key = `${odds.eventName}-${odds.league}`;
      if (!eventGroups.has(key)) {
        eventGroups.set(key, []);
      }
      eventGroups.get(key)!.push(odds);
    });

    // Find best odds for each outcome
    eventGroups.forEach((oddsArray, eventKey) => {
      // Filter by bookmakers if specified
      let filteredOdds = oddsArray;
      if (filters.bookmakerPrincipale && filters.bookmakerPrincipale !== 'nessuno') {
        filteredOdds = oddsArray.filter(o => 
          o.bookmaker === filters.bookmakerPrincipale || 
          (filters.bookmakersSecondari && filters.bookmakersSecondari.includes(o.bookmaker))
        );
      }

      if (filteredOdds.length < 3) return; // Need at least 3 bookmakers

      // Find best odds for each outcome
      let best1 = { odds: 0, bookmaker: '', data: null as OddsData | null };
      let bestX = { odds: 0, bookmaker: '', data: null as OddsData | null };
      let best2 = { odds: 0, bookmaker: '', data: null as OddsData | null };

      filteredOdds.forEach(odds => {
        if (odds.odds.home && odds.odds.home > best1.odds) {
          best1 = { odds: odds.odds.home, bookmaker: odds.bookmaker, data: odds };
        }
        if (odds.odds.draw && odds.odds.draw > bestX.odds) {
          bestX = { odds: odds.odds.draw, bookmaker: odds.bookmaker, data: odds };
        }
        if (odds.odds.away && odds.odds.away > best2.odds) {
          best2 = { odds: odds.odds.away, bookmaker: odds.bookmaker, data: odds };
        }
      });

      if (!best1.data || !bestX.data || !best2.data) return;

      // Calculate arbitrage percentage
      const arbitragePercent = (1 / best1.odds + 1 / bestX.odds + 1 / best2.odds) * 100;

      // Only consider if there's a potential profit
      if (arbitragePercent >= 100) return;

      // Calculate stakes for each outcome
      const stake1 = (stake / arbitragePercent) * (100 / best1.odds);
      const stakeX = (stake / arbitragePercent) * (100 / bestX.odds);
      const stake2 = (stake / arbitragePercent) * (100 / best2.odds);
      const totalStake = stake1 + stakeX + stake2;

      // Calculate profit
      const payout = stake1 * best1.odds; // Same for all outcomes in perfect arbitrage
      const profit = payout - totalStake;
      const profitPercent = (profit / totalStake) * 100;

      // Apply filters
      if (filters.quotaMinima && Math.min(best1.odds, bestX.odds, best2.odds) < parseFloat(filters.quotaMinima.replace(',', '.'))) return;
      if (filters.quotaMassima && Math.max(best1.odds, bestX.odds, best2.odds) > parseFloat(filters.quotaMassima.replace(',', '.'))) return;
      if (filters.partita && !best1.data.eventName.toLowerCase().includes(filters.partita.toLowerCase())) return;
      if (filters.campionato && filters.campionato !== best1.data.league.toLowerCase()) return;

      opportunities.push({
        eventName: best1.data.eventName,
        league: best1.data.league,
        eventTime: best1.data.eventTime,
        bookmaker1: best1.bookmaker,
        bookmaker2: bestX.bookmaker,
        bookmaker3: best2.bookmaker,
        odds1: best1.odds,
        oddsX: bestX.odds,
        odds2: best2.odds,
        stake1,
        stakeX,
        stake2,
        totalStake,
        profit,
        profitPercent,
        arbitragePercent,
      });
    });

    // Sort by profit percentage
    return opportunities.sort((a, b) => b.profitPercent - a.profitPercent);
  };

  const opportunities = calculateArbitrageOpportunities();

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return `${date.getDate().toString().padStart(2, '0')}/${(date.getMonth() + 1).toString().padStart(2, '0')}/${date.getFullYear().toString().slice(-2)} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
  };

  return (
    <div className="mt-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Opportunità Arbitraggio Tre Vie</h3>
        <div className="text-sm text-muted-foreground">
          Trovate {opportunities.length} opportunità
        </div>
      </div>

      {opportunities.length === 0 ? (
        <div className="border rounded-lg p-8 text-center text-muted-foreground">
          Nessuna opportunità di arbitraggio trovata. Le opportunità di arbitraggio sono rare e richiedono quote ottimali su tre bookmaker diversi.
        </div>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Evento</TableHead>
                <TableHead>Campionato</TableHead>
                <TableHead>Data/Ora</TableHead>
                <TableHead>1 (Book)</TableHead>
                <TableHead>X (Book)</TableHead>
                <TableHead>2 (Book)</TableHead>
                <TableHead className="text-right">Quota 1</TableHead>
                <TableHead className="text-right">Quota X</TableHead>
                <TableHead className="text-right">Quota 2</TableHead>
                <TableHead className="text-right">Punta 1</TableHead>
                <TableHead className="text-right">Punta X</TableHead>
                <TableHead className="text-right">Punta 2</TableHead>
                <TableHead className="text-right">Profitto</TableHead>
                <TableHead className="text-right">% Arb</TableHead>
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
                    <Badge variant="outline" className="text-xs">{opp.bookmaker1}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs">{opp.bookmaker2}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs">{opp.bookmaker3}</Badge>
                  </TableCell>
                  <TableCell className="text-right font-mono">{opp.odds1.toFixed(2)}</TableCell>
                  <TableCell className="text-right font-mono">{opp.oddsX.toFixed(2)}</TableCell>
                  <TableCell className="text-right font-mono">{opp.odds2.toFixed(2)}</TableCell>
                  <TableCell className="text-right font-mono">€{opp.stake1.toFixed(2)}</TableCell>
                  <TableCell className="text-right font-mono">€{opp.stakeX.toFixed(2)}</TableCell>
                  <TableCell className="text-right font-mono">€{opp.stake2.toFixed(2)}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex flex-col items-end">
                      <span className="font-mono text-green-600 font-semibold">
                        €{opp.profit.toFixed(2)}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        ({opp.profitPercent.toFixed(2)}%)
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    <Badge variant={opp.arbitragePercent < 99 ? "default" : "secondary"}>
                      {opp.arbitragePercent.toFixed(2)}%
                    </Badge>
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
      )}
    </div>
  );
}
