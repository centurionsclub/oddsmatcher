import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

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
      // Equalized formula: counterStake = stake * backOdds / counterOdds
      // guarantees same profit regardless of outcome
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

            // Equalized counter stake: same payout regardless of outcome
            const counterStake = stake * backOdds / counterOdds;
            const totalInvested = stake + counterStake;

            // Both profits are equal with this formula
            const profit = stake * backOdds - totalInvested;
            const rating = (profit / stake) * 100;

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
              profit,
              backStake: stake,
              layStake: counterStake,
              liability: totalInvested,
            });
          }
        }
      }

      // For 1X2: 3-way dutching — cover ALL 3 outcomes using best odds
      // from different bookmakers. Guarantees same payout regardless of result.
      if (outcomes.length === 3) {
        // Find best odds for each outcome across all bookmakers
        const bestForOutcome: Record<string, { odds: number; bookmaker: string }> = {};
        for (const outcome of outcomes) {
          bestForOutcome[outcome.key] = { odds: 0, bookmaker: '' };
          for (const bm of group) {
            const o = bm.odds[outcome.key];
            if (o && o > bestForOutcome[outcome.key].odds) {
              bestForOutcome[outcome.key] = { odds: o, bookmaker: bm.bookmaker };
            }
          }
        }

        // Check all outcomes have valid odds
        if (outcomes.some(o => bestForOutcome[o.key].odds <= 1)) return;

        // For each outcome as the "main" back bet
        for (const mainOutcome of outcomes) {
          const mainOdds = bestForOutcome[mainOutcome.key].odds;
          const mainBook = bestForOutcome[mainOutcome.key].bookmaker;

          if (!passesFilters(mainOdds, group[0].eventName)) continue;

          const otherOutcomes = outcomes.filter(o => o.key !== mainOutcome.key);

          // Equalized payout: if main wins, payout = stake * mainOdds
          // Counter stakes set so each counter also returns same payout
          const payout = stake * mainOdds;
          let totalCounterStake = 0;
          const counterBooks: string[] = [];

          for (const other of otherOutcomes) {
            const counterOdds = bestForOutcome[other.key].odds;
            const cs = payout / counterOdds;
            totalCounterStake += cs;
            if (!counterBooks.includes(bestForOutcome[other.key].bookmaker)) {
              counterBooks.push(bestForOutcome[other.key].bookmaker);
            }
          }

          const totalInvested = stake + totalCounterStake;
          // Guaranteed profit (same for any outcome)
          const profit = payout - totalInvested;
          const rating = (profit / stake) * 100;

          // Show effective counter-odds (what the combined counter is worth)
          const effectiveCounterOdds = payout / totalCounterStake;

          opportunities.push({
            bookmaker: mainBook,
            exchange: counterBooks.join(' + ') + ' (book)',
            eventName: group[0].eventName,
            league: group[0].league,
            eventTime: group[0].eventTime,
            market: `${group[0].market} - ${mainOutcome.label}`,
            outcome: mainOutcome.label,
            backOdds: mainOdds,
            layOdds: effectiveCounterOdds,
            rating,
            profit,
            backStake: stake,
            layStake: totalCounterStake,
            liability: totalInvested,
          });
        }
      }
    });

    // Sort by rating (closest to 0 = best)
    let sorted = opportunities.sort((a, b) => b.rating - a.rating);

    // If specific bookmakers are selected, show only opportunities
    // where the "back" bookmaker is one of the selected ones
    const selectedBookmakers: string[] = filters.bookmaker || [];
    if (selectedBookmakers.length > 0) {
      sorted = sorted.filter(opp =>
        selectedBookmakers.some(bm =>
          opp.bookmaker.toLowerCase().includes(bm.toLowerCase()) ||
          bm.toLowerCase().includes(opp.bookmaker.toLowerCase())
        )
      );
    }

    return sorted;
  };

  const opportunities = calculateOpportunities();

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return `${date.getDate().toString().padStart(2, '0')}/${(date.getMonth() + 1).toString().padStart(2, '0')}/${date.getFullYear().toString().slice(-2)} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
  };

  return (
    <div className="mt-4">
      {opportunities.length === 0 ? (
        <div className="flex items-center justify-center py-8">
          <div className="text-muted-foreground">
            Nessuna opportunità di matched betting trovata con i filtri attuali.
          </div>
        </div>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <Table className="text-xs">
            <TableHeader>
              <TableRow>
                <TableHead className="py-2 px-2">Evento</TableHead>
                <TableHead className="py-2 px-2">Lega</TableHead>
                <TableHead className="py-2 px-2">Data/Ora</TableHead>
                <TableHead className="py-2 px-2">Bookmaker</TableHead>
                <TableHead className="py-2 px-2">Controparte</TableHead>
                <TableHead className="py-2 px-2">Mercato</TableHead>
                <TableHead className="py-2 px-2 text-right">Back</TableHead>
                <TableHead className="py-2 px-2 text-right">Lay</TableHead>
                <TableHead className="py-2 px-2 text-right">Rating</TableHead>
                <TableHead className="py-2 px-2 text-right">Perdita</TableHead>
                <TableHead className="py-2 px-2 text-right">Punta</TableHead>
                <TableHead className="py-2 px-2 text-right">Banca</TableHead>
                <TableHead className="py-2 px-2 text-right">Passivo</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {opportunities.slice(0, 100).map((opp, index) => (
                <TableRow key={index} className="h-8">
                  <TableCell className="py-1 px-2 font-medium max-w-[150px] truncate">{opp.eventName}</TableCell>
                  <TableCell className="py-1 px-2">
                    <Badge variant="secondary" className="text-[10px] px-1.5 py-0">{opp.league}</Badge>
                  </TableCell>
                  <TableCell className="py-1 px-2 whitespace-nowrap">{formatDate(opp.eventTime)}</TableCell>
                  <TableCell className="py-1 px-2">
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0">{opp.bookmaker}</Badge>
                  </TableCell>
                  <TableCell className="py-1 px-2">
                    <Badge variant="outline" className={cn(
                      "text-[10px] px-1.5 py-0",
                      opp.exchange.includes('(book)')
                        ? "bg-orange-500/10 text-orange-400 border-orange-500/30"
                        : "bg-blue-500/10 text-blue-400 border-blue-500/30"
                    )}>{opp.exchange}</Badge>
                  </TableCell>
                  <TableCell className="py-1 px-2">{opp.market}</TableCell>
                  <TableCell className="py-1 px-2 text-right font-mono">{opp.backOdds.toFixed(2)}</TableCell>
                  <TableCell className="py-1 px-2 text-right font-mono">{opp.layOdds.toFixed(2)}</TableCell>
                  <TableCell className="py-1 px-2 text-right">
                    <Badge variant={opp.rating > -5 ? "default" : opp.rating > -8 ? "secondary" : "destructive"} className="text-[10px] px-1.5 py-0">
                      {opp.rating.toFixed(2)}%
                    </Badge>
                  </TableCell>
                  <TableCell className="py-1 px-2 text-right font-mono text-red-400">
                    €{opp.profit.toFixed(2)}
                  </TableCell>
                  <TableCell className="py-1 px-2 text-right font-mono">€{opp.backStake.toFixed(2)}</TableCell>
                  <TableCell className="py-1 px-2 text-right font-mono">€{opp.layStake.toFixed(2)}</TableCell>
                  <TableCell className="py-1 px-2 text-right font-mono text-red-400">
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
