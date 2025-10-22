import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ExternalLink, TrendingUp, Shield } from "lucide-react";

interface MatchTableProps {
  type: "singola" | "multipla" | "surebet" | "bestodds";
}

// Mock data
const mockMatches = [
  {
    id: 1,
    event: "Inter - Juventus",
    league: "Serie A",
    market: "1X2",
    selection: "1",
    bookmaker: "Bet365",
    bookmakerOdds: 2.15,
    exchange: "Betfair",
    exchangeOdds: 2.20,
    yield: 95.2,
    profit: 2.35,
    liability: 47.65,
    isSureBet: false,
    time: "Oggi 20:45"
  },
  {
    id: 2,
    event: "Milan - Napoli",
    league: "Serie A",
    market: "Over 2.5",
    selection: "Over",
    bookmaker: "Sisal",
    bookmakerOdds: 1.85,
    exchange: "Betflag",
    exchangeOdds: 1.92,
    yield: 96.8,
    profit: 1.85,
    liability: 42.50,
    isSureBet: true,
    time: "Domani 18:00"
  },
  {
    id: 3,
    event: "Roma - Lazio",
    league: "Serie A",
    market: "1X2",
    selection: "X",
    bookmaker: "Snai",
    bookmakerOdds: 3.40,
    exchange: "Betfair",
    exchangeOdds: 3.50,
    yield: 97.1,
    profit: 3.85,
    liability: 75.20,
    isSureBet: false,
    time: "Domani 20:45"
  },
  {
    id: 4,
    event: "Atalanta - Fiorentina",
    league: "Serie A",
    market: "Gol",
    selection: "Gol",
    bookmaker: "Eurobet",
    bookmakerOdds: 1.65,
    exchange: "Betfair",
    exchangeOdds: 1.70,
    yield: 97.0,
    profit: 1.25,
    liability: 32.50,
    isSureBet: false,
    time: "Sab 15:00"
  }
];

export const MatchTable = ({ type }: MatchTableProps) => {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Opportunità Trovate</h3>
          <p className="text-sm text-muted-foreground">{mockMatches.length} match disponibili</p>
        </div>
      </div>

      <div className="rounded-lg border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50">
              <TableHead className="font-semibold">Evento</TableHead>
              <TableHead className="font-semibold">Mercato</TableHead>
              <TableHead className="font-semibold">Bookmaker</TableHead>
              <TableHead className="font-semibold text-center">Quota BK</TableHead>
              <TableHead className="font-semibold">Exchange</TableHead>
              <TableHead className="font-semibold text-center">Quota EX</TableHead>
              <TableHead className="font-semibold text-center">Yield %</TableHead>
              <TableHead className="font-semibold text-right">Profitto €</TableHead>
              <TableHead className="font-semibold text-right">Responsabilità €</TableHead>
              <TableHead className="font-semibold text-center">Azioni</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {mockMatches.map((match) => (
              <TableRow key={match.id} className="hover:bg-muted/30 transition-colors">
                <TableCell>
                  <div className="space-y-1">
                    <div className="font-medium">{match.event}</div>
                    <div className="text-xs text-muted-foreground flex items-center gap-2">
                      <span>{match.league}</span>
                      <span>•</span>
                      <span>{match.time}</span>
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  <div className="space-y-1">
                    <Badge variant="outline" className="font-normal">
                      {match.market}
                    </Badge>
                    <div className="text-xs text-muted-foreground">{match.selection}</div>
                  </div>
                </TableCell>
                <TableCell>
                  <span className="font-medium">{match.bookmaker}</span>
                </TableCell>
                <TableCell className="text-center">
                  <Badge variant="secondary" className="font-mono font-semibold">
                    {match.bookmakerOdds.toFixed(2)}
                  </Badge>
                </TableCell>
                <TableCell>
                  <span className="font-medium">{match.exchange}</span>
                </TableCell>
                <TableCell className="text-center">
                  <Badge variant="secondary" className="font-mono font-semibold">
                    {match.exchangeOdds.toFixed(2)}
                  </Badge>
                </TableCell>
                <TableCell className="text-center">
                  <div className="flex items-center justify-center gap-2">
                    {match.isSureBet && <Shield className="h-4 w-4 text-accent" />}
                    <span 
                      className={`font-semibold ${
                        match.yield >= 97 
                          ? "text-accent" 
                          : match.yield >= 95 
                          ? "text-warning" 
                          : "text-muted-foreground"
                      }`}
                    >
                      {match.yield.toFixed(1)}%
                    </span>
                  </div>
                </TableCell>
                <TableCell className="text-right">
                  <span className="font-semibold text-accent">
                    +€{match.profit.toFixed(2)}
                  </span>
                </TableCell>
                <TableCell className="text-right">
                  <span className="text-muted-foreground font-mono">
                    €{match.liability.toFixed(2)}
                  </span>
                </TableCell>
                <TableCell className="text-center">
                  <Button size="sm" variant="outline">
                    <ExternalLink className="h-4 w-4 mr-1" />
                    Apri
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {mockMatches.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          <TrendingUp className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>Nessuna opportunità trovata con i filtri selezionati</p>
        </div>
      )}
    </div>
  );
};
