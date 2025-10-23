import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Loader2 } from "lucide-react";

interface Surebet {
  id: string;
  sport: string;
  event: string;
  time: string;
  profit: number;
  bookmaker1: string;
  bookmaker2: string;
  odds1: number;
  odds2: number;
  market1: string;
  market2: string;
}

interface SurebetResultsProps {
  data: any;
  loading: boolean;
  error: string | null;
}

export function SurebetResults({ data, loading, error }: SurebetResultsProps) {
  if (loading) {
    return (
      <div className="mt-6 bg-card rounded-xl border border-border p-12 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <span className="ml-3 text-muted-foreground">Caricamento dati...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mt-6 bg-card rounded-xl border border-destructive p-6">
        <p className="text-destructive font-medium">Errore: {error}</p>
      </div>
    );
  }

  if (!data || !data.arbs || data.arbs.length === 0) {
    return (
      <div className="mt-6 bg-card rounded-xl border border-border p-12 text-center">
        <p className="text-muted-foreground">
          Nessun risultato disponibile. Utilizza i filtri per cercare opportunità.
        </p>
      </div>
    );
  }

  return (
    <div className="mt-6 bg-card rounded-xl border border-border overflow-hidden">
      <div className="p-4 border-b border-border bg-secondary/50">
        <h3 className="font-semibold text-foreground">
          {data.arbs.length} Surebet trovate
        </h3>
      </div>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Sport</TableHead>
              <TableHead>Evento</TableHead>
              <TableHead>Orario</TableHead>
              <TableHead>Profitto %</TableHead>
              <TableHead>Bookmaker 1</TableHead>
              <TableHead>Quota 1</TableHead>
              <TableHead>Mercato 1</TableHead>
              <TableHead>Bookmaker 2</TableHead>
              <TableHead>Quota 2</TableHead>
              <TableHead>Mercato 2</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.arbs.map((arb: any, index: number) => (
              <TableRow key={arb.id || index}>
                <TableCell className="font-medium">{arb.sport?.name || 'N/A'}</TableCell>
                <TableCell>{arb.event?.name || 'N/A'}</TableCell>
                <TableCell>
                  {arb.started_at ? new Date(arb.started_at).toLocaleString('it-IT') : 'N/A'}
                </TableCell>
                <TableCell className="font-semibold text-green-600">
                  {arb.profit ? `${arb.profit.toFixed(2)}%` : 'N/A'}
                </TableCell>
                <TableCell>{arb.bookmaker1?.name || 'N/A'}</TableCell>
                <TableCell className="font-medium">{arb.odds1 || 'N/A'}</TableCell>
                <TableCell>{arb.market1?.name || 'N/A'}</TableCell>
                <TableCell>{arb.bookmaker2?.name || 'N/A'}</TableCell>
                <TableCell className="font-medium">{arb.odds2 || 'N/A'}</TableCell>
                <TableCell>{arb.market2?.name || 'N/A'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
