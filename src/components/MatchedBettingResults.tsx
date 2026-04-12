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

    // Helper: get outcomes for a market
    const getOutcomes = (event: OddsData): Array<{ key: string; label: string }> => {
      const outcomes: Array<{ key: string; label: string }> = [];
      if (event.market === '1X2' || event.market === 'h2h') {
        if (event.odds.home) outcomes.push({ key: 'home', label: '1' });
        if (event.odds.draw) outcomes.push({ key: 'draw', label: 'X' });
        if (event.odds.away) outcomes.push({ key: 'away', label: '2' });
      } else if (event.market === '12') {
        if (event.odds.home) outcomes.push({ key: 'home', label: '1' });
        if (event.odds.away) outcomes.push({ key: 'away', label: '2' });
      } else {
        if (event.odds.over) outcomes.push({ key: 'over', label: 'Over' });
        if (event.odds.under) outcomes.push({ key: 'under', label: 'Under' });
      }
      return outcomes;
    };

    // Helper: apply user filters
    const passesFilters = (backOdds: number, eventName: string): boolean => {
      const quotaMin = parseFloat((filters.quotaMinima || '0').replace(',', '.'));
      const quotaMax = parseFloat((filters.quotaMassima || '0').replace(',', '.'));
      if (quotaMin > 0 && backOdds < quotaMin) return false;
      if (quotaMax > 0 && backOdds > quotaMax) return false;
      if (filters.partita && !eventName.toLowerCase().includes(filters.partita.toLowerCase())) return false;
      return true;
    };

    // Helper: find matching events by name
    const findMatchingEvents = (sourceEvent: OddsData, pool: OddsData[]): OddsData[] => {
      const normalized = normalizeEventName(sourceEvent.eventName);
      return pool.filter(ev => {
        const norm = normalizeEventName(ev.eventName);
        return normalized === norm ||
          normalized.includes(norm.substring(0, 10)) ||
          norm.includes(normalized.substring(0, 10));
      });
    };

    // ── 1) BOOK vs EXCHANGE (lay classico) ────────────────────────
    bookmakerOdds.forEach(bmEvent => {
      const matchingExchanges = findMatchingEvents(bmEvent, exchangeOdds);
      if (matchingExchanges.length === 0) return;

      const outcomes = getOutcomes(bmEvent);

      outcomes.forEach(outcome => {
        const backOdds = bmEvent.odds[outcome.key];
        if (!backOdds || backOdds <= 1) return;
        if (!passesFilters(backOdds, bmEvent.eventName)) return;

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

        const layStake = (stake * backOdds) / (bestLayOdds - commissionRate * (bestLayOdds - 1));
        const liability = layStake * (bestLayOdds - 1);
        const profitIfWin = stake * (backOdds - 1) - liability;
        const profitIfLose = layStake * (1 - commissionRate) - stake;
        const averageProfit = (profitIfWin + profitIfLose) / 2;
        const rating = (averageProfit / stake) * 100;

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

    // ── 2) BOOK vs BOOK (contropuntata) ───────────────────────────
    // For 2-way markets: back outcome A at book1, back opposite at book2
    // For 3-way (1X2): back "1" at book1, best combo of "X"+"2" at book2
    // Simplified: for each pair of bookmakers on the same event,
    // find the best counter-bet on opposite outcomes
    const eventGroups = new Map<string, OddsData[]>();
    bookmakerOdds.forEach(bm => {
      const key = normalizeEventName(bm.eventName) + '|' + bm.market;
      if (!eventGroups.has(key)) eventGroups.set(key, []);
      eventGroups.get(key)!.push(bm);
    });

    eventGroups.forEach(group => {
      if (group.length < 2) return;

      const outcomes = getOutcomes(group[0]);

      // For 2-way markets (Over/Under, 12): back one side, counter the other
      if (outcomes.length === 2) {
        const [outcomeA, outcomeB] = outcomes;

        for (let i = 0; i < group.length; i++) {
          for (let j = 0; j < group.length; j++) {
            if (i === j) continue;
            if (group[i].bookmaker === group[j].bookmaker) continue;

            const backOdds = group[i].odds[outcomeA.key];
            const counterOdds = group[j].odds[outcomeB.key];
            if (!backOdds || backOdds <= 1 || !counterOdds || counterOdds <= 1) continue;
            if (!passesFilters(backOdds, group[i].eventName)) continue;

            // Counter stake: to equalize profit/loss
            const counterStake = (stake * backOdds - stake) / (counterOdds - 1);
            const totalInvested = stake + counterStake;

            const profitIfBack = stake * (backOdds - 1) - counterStake;
            const profitIfCounter = counterStake * (counterOdds - 1) - stake;
            const averageProfit = (profitIfBack + profitIfCounter) / 2;
            const rating = (averageProfit / stake) * 100;

            opportunities.push({
              bookmaker: group[i].bookmaker,
              exchange: `${group[j].bookmaker} (book)`,
              eventName: group[i].eventName,
              league: group[i].league,
              eventTime: group[i].eventTime,
              market: `${group[i].market} - ${outcomeA.label}/${outcomeB.label}`,
              outcome: `${outcomeA.label} vs ${outcomeB.label}`,
              backOdds,
              layOdds: counterOdds,
              rating,
              profit: averageProfit,
              backStake: stake,
              layStake: counterStake,
              liability: totalInvested,
            });
          }
        }
      }

      // For 1X2: back one outcome, counter with the single best opposite
      if (outcomes.length === 3) {
        for (const backOutcome of outcomes) {
          const opposites = outcomes.filter(o => o.key !== backOutcome.key);

          for (let i = 0; i < group.length; i++) {
            const backOdds = group[i].odds[backOutcome.key];
            if (!backOdds || backOdds <= 1) continue;
            if (!passesFilters(backOdds, group[i].eventName)) continue;

            // Find the best single opposite outcome at another bookmaker
            for (const oppOutcome of opposites) {
              let bestCounterOdds = 0;
              let bestCounterBook = '';

              for (let j = 0; j < group.length; j++) {
                if (i === j || group[i].bookmaker === group[j].bookmaker) continue;
                const cOdds = group[j].odds[oppOutcome.key];
                if (cOdds && cOdds > bestCounterOdds) {
                  bestCounterOdds = cOdds;
                  bestCounterBook = group[j].bookmaker;
                }
              }

              if (bestCounterOdds <= 1) continue;

              const counterStake = (stake * backOdds - stake) / (bestCounterOdds - 1);
              const profitIfBack = stake * (backOdds - 1) - counterStake;
              const profitIfCounter = counterStake * (bestCounterOdds - 1) - stake;
              const averageProfit = (profitIfBack + profitIfCounter) / 2;
              const rating = (averageProfit / stake) * 100;

              opportunities.push({
                bookmaker: group[i].bookmaker,
                exchange: `${bestCounterBook} (book)`,
                eventName: group[i].eventName,
                league: group[i].league,
                eventTime: group[i].eventTime,
                market: `${group[i].market} - ${backOutcome.label}/${oppOutcome.label}`,
                outcome: `${backOutcome.label} vs ${oppOutcome.label}`,
                backOdds,
                layOdds: bestCounterOdds,
                rating,
                profit: averageProfit,
                backStake: stake,
                layStake: counterStake,
                liability: stake + counterStake,
              });
            }
          }
        }
      }
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
                    <Badge variant="outline" className={opp.exchange.includes('(book)')
                      ? "bg-orange-500/10 text-orange-400 border-orange-500/30"
                      : "bg-blue-500/10 text-blue-400 border-blue-500/30"
                    }>{opp.exchange}</Badge>
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
