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

  // Calculate matched betting opportunities confrontando Sisal con Betfair
  const calculateOpportunities = (): MatchedBettingOpportunity[] => {
    const opportunities: MatchedBettingOpportunity[] = [];
    const stakeValue = parseFloat(filters.stakePunta?.toString().replace(',', '.')) || 0;
    const stake = stakeValue > 0 ? stakeValue : 100; // Default 100€
    const commissionRate = commission / 100;

    // Separa i dati di Sisal e Betfair
    const sisalOdds = data.data.filter(odd => odd.bookmaker.toLowerCase() === 'sisal');
    const betfairOdds = data.data.filter(odd => odd.bookmaker.toLowerCase() === 'betfair');

    console.log('Sisal events:', sisalOdds.length, 'Betfair events:', betfairOdds.length);

    // Normalizza il nome dell'evento per il confronto
    const normalizeEventName = (name: string): string => {
      return name.toLowerCase()
        .replace(/\s+/g, '')
        .replace(/[-–—]/g, '')
        .replace(/\./g, '');
    };

    // Per ogni evento Sisal, cerca il corrispondente su Betfair
    sisalOdds.forEach(sisalEvent => {
      const normalizedSisal = normalizeEventName(sisalEvent.eventName);
      
      // Trova l'evento corrispondente su Betfair
      const betfairEvent = betfairOdds.find(bf => {
        const normalizedBetfair = normalizeEventName(bf.eventName);
        return normalizedSisal === normalizedBetfair || 
               normalizedSisal.includes(normalizedBetfair.substring(0, 10)) ||
               normalizedBetfair.includes(normalizedSisal.substring(0, 10));
      });

      if (!betfairEvent) {
        console.log('No Betfair match for:', sisalEvent.eventName);
        return;
      }

      console.log('Matched:', sisalEvent.eventName, '<=>', betfairEvent.eventName);

      // Per ogni esito, calcola l'opportunità
      const outcomes: Array<{ key: string; label: string }> = [];
      
      if (sisalEvent.market === '1X2') {
        outcomes.push(
          { key: 'home', label: '1' },
          { key: 'draw', label: 'X' },
          { key: 'away', label: '2' }
        );
      } else {
        outcomes.push(
          { key: 'over', label: 'Over' },
          { key: 'under', label: 'Under' }
        );
      }

      outcomes.forEach(outcome => {
        const backOdds = sisalEvent.odds[outcome.key as keyof typeof sisalEvent.odds];
        const layOdds = betfairEvent.odds[outcome.key as keyof typeof betfairEvent.odds];

        if (!backOdds || !layOdds || backOdds <= 1 || layOdds <= 1) {
          return;
        }

        // Calcola lay stake e liability
        const layStake = (stake * backOdds) / layOdds;
        const liability = layStake * (layOdds - 1);

        // Calcola profitto/perdita
        // Se vince la back: +backWin - liability
        // Se perde la back: -stake + layWin
        const backWin = stake * (backOdds - 1);
        const layWin = layStake * (1 - commissionRate);
        
        const profitIfWin = backWin - liability;
        const profitIfLose = layWin - stake;
        
        // La perdita totale è la media dei due scenari (qualifying bet)
        const averageProfit = (profitIfWin + profitIfLose) / 2;
        const lossPercent = (averageProfit / stake) * 100;

        // Filtra per perdite tra -10% e -5%
        if (lossPercent > -10 && lossPercent < -5) {
          // Applica altri filtri
          if (filters.quotaMinima && backOdds < parseFloat(filters.quotaMinima.replace(',', '.'))) return;
          if (filters.quotaMassima && backOdds > parseFloat(filters.quotaMassima.replace(',', '.'))) return;
          if (filters.partita && !sisalEvent.eventName.toLowerCase().includes(filters.partita.toLowerCase())) return;
          if (filters.campionato && filters.campionato !== sisalEvent.league.toLowerCase()) return;

          opportunities.push({
            bookmaker: 'Sisal',
            eventName: sisalEvent.eventName,
            league: sisalEvent.league,
            eventTime: sisalEvent.eventTime,
            market: `${sisalEvent.market} - ${outcome.label}`,
            backOdds,
            layOdds,
            rating: lossPercent,
            profit: averageProfit,
            backStake: stake,
            layStake,
            liability,
          });
        }
      });
    });

    // Ordina per rating (perdite minori per prime)
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
              <TableHead className="text-right">Perdita %</TableHead>
              <TableHead className="text-right">Perdita €</TableHead>
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
                  <Badge variant={opp.rating > -7 ? "default" : "secondary"}>
                    {opp.rating.toFixed(2)}%
                  </Badge>
                </TableCell>
                <TableCell className="text-right font-mono text-red-600">
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
