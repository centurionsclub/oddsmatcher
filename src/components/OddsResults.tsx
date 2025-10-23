import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ExternalLink, TrendingUp } from "lucide-react";

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

interface OddsResultsProps {
  data: {
    success?: boolean;
    data?: OddsData[];
    metadata?: {
      totalResults: number;
      bookmakers: number;
      durationMs: number;
    };
  } | null;
  loading: boolean;
  error: string | null;
}

export function OddsResults({ data, loading, error }: OddsResultsProps) {
  if (loading) {
    return (
      <div className="mt-6 bg-card rounded-xl border border-border p-12 text-center">
        <div className="flex items-center justify-center gap-3">
          <div className="h-6 w-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-foreground font-medium">Ricerca quote in corso...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mt-6 bg-destructive/10 rounded-xl border border-destructive/20 p-8 text-center">
        <p className="text-destructive font-medium">Errore: {error}</p>
      </div>
    );
  }

  if (!data || !data.data || data.data.length === 0) {
    return (
      <div className="mt-6 bg-card rounded-xl border border-border p-12 text-center">
        <p className="text-muted-foreground">
          Nessuna quota trovata. Modifica i filtri e riprova.
        </p>
      </div>
    );
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('it-IT', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    }).format(date);
  };

  const getOddsDisplay = (odds: OddsData['odds'], market: string) => {
    if (market === '1X2' && odds.home && odds.draw && odds.away) {
      return (
        <div className="flex gap-2">
          <Badge variant="outline" className="font-mono">1: {odds.home.toFixed(2)}</Badge>
          <Badge variant="outline" className="font-mono">X: {odds.draw.toFixed(2)}</Badge>
          <Badge variant="outline" className="font-mono">2: {odds.away.toFixed(2)}</Badge>
        </div>
      );
    }
    if (odds.over && odds.under) {
      return (
        <div className="flex gap-2">
          <Badge variant="outline" className="font-mono">Over: {odds.over.toFixed(2)}</Badge>
          <Badge variant="outline" className="font-mono">Under: {odds.under.toFixed(2)}</Badge>
        </div>
      );
    }
    return <span className="text-muted-foreground">N/D</span>;
  };

  return (
    <div className="mt-6 space-y-4">
      {data.metadata && (
        <div className="flex items-center justify-between bg-card rounded-lg border border-border p-4">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-primary" />
            <span className="font-semibold text-foreground">
              {data.metadata.totalResults} quote trovate da {data.metadata.bookmakers} bookmaker
            </span>
          </div>
          <span className="text-sm text-muted-foreground">
            Tempo: {(data.metadata.durationMs / 1000).toFixed(1)}s
          </span>
        </div>
      )}

      <div className="bg-card rounded-xl border border-border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Evento</TableHead>
              <TableHead>Campionato</TableHead>
              <TableHead>Data/Ora</TableHead>
              <TableHead>Bookmaker</TableHead>
              <TableHead>Mercato</TableHead>
              <TableHead>Quote</TableHead>
              <TableHead className="text-right">Azioni</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.data.map((odd, index) => (
              <TableRow key={index}>
                <TableCell className="font-medium">{odd.eventName}</TableCell>
                <TableCell>
                  <Badge variant="secondary">{odd.league}</Badge>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {formatDate(odd.eventTime)}
                </TableCell>
                <TableCell>
                  <Badge className="bg-primary/10 text-primary hover:bg-primary/20">
                    {odd.bookmaker}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{odd.market}</Badge>
                </TableCell>
                <TableCell>{getOddsDisplay(odd.odds, odd.market)}</TableCell>
                <TableCell className="text-right">
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
