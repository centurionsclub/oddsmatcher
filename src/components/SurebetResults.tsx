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
              <TableHead>Evento</TableHead>
              <TableHead>Orario</TableHead>
              <TableHead>Mercato</TableHead>
              <TableHead className="bg-primary/5">Book 1</TableHead>
              <TableHead className="bg-primary/5">Esito 1</TableHead>
              <TableHead className="bg-primary/5">Quota 1</TableHead>
              <TableHead className="bg-primary/5">Stake 1</TableHead>
              <TableHead className="bg-secondary/30">Book 2</TableHead>
              <TableHead className="bg-secondary/30">Esito 2</TableHead>
              <TableHead className="bg-secondary/30">Quota 2</TableHead>
              <TableHead className="bg-secondary/30">Stake 2</TableHead>
              <TableHead className="bg-accent/10">Book 3</TableHead>
              <TableHead className="bg-accent/10">Esito 3</TableHead>
              <TableHead className="bg-accent/10">Quota 3</TableHead>
              <TableHead className="bg-accent/10">Stake 3</TableHead>
              <TableHead className="font-semibold">Profitto %</TableHead>
              <TableHead className="font-semibold">Profitto €</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.arbs.map((arb: any, index: number) => {
              const profitClass = arb.profitPercentage >= 2 
                ? 'text-green-600 font-bold' 
                : arb.profitPercentage >= 1 
                ? 'text-green-500 font-semibold' 
                : 'text-green-400';
              
              const leg1 = arb.legs?.[0];
              const leg2 = arb.legs?.[1];
              const leg3 = arb.legs?.[2];

              return (
                <TableRow key={arb.id || index} className="hover:bg-muted/50">
                  <TableCell className="font-medium">
                    <div className="min-w-[180px]">
                      <div className="font-semibold">{arb.event?.home || 'N/A'}</div>
                      <div className="text-muted-foreground text-sm">vs {arb.event?.away || 'N/A'}</div>
                      <div className="text-xs text-muted-foreground mt-1">{arb.sport || 'N/A'}</div>
                    </div>
                  </TableCell>
                  <TableCell>
                    {arb.event?.startTime 
                      ? new Date(arb.event.startTime).toLocaleString('it-IT', {
                          day: '2-digit',
                          month: '2-digit',
                          hour: '2-digit',
                          minute: '2-digit'
                        })
                      : 'N/A'}
                  </TableCell>
                  <TableCell className="font-medium">{arb.market || 'N/A'}</TableCell>
                  
                  {/* Leg 1 */}
                  <TableCell className="bg-primary/5">{leg1?.bookmaker || 'N/A'}</TableCell>
                  <TableCell className="bg-primary/5 font-medium">{leg1?.outcome || 'N/A'}</TableCell>
                  <TableCell className="bg-primary/5 font-semibold">{leg1?.odds?.toFixed(2) || 'N/A'}</TableCell>
                  <TableCell className="bg-primary/5">
                    {leg1?.stake ? `€${leg1.stake.toFixed(2)}` : 'N/A'}
                  </TableCell>
                  
                  {/* Leg 2 */}
                  <TableCell className="bg-secondary/30">{leg2?.bookmaker || 'N/A'}</TableCell>
                  <TableCell className="bg-secondary/30 font-medium">{leg2?.outcome || 'N/A'}</TableCell>
                  <TableCell className="bg-secondary/30 font-semibold">{leg2?.odds?.toFixed(2) || 'N/A'}</TableCell>
                  <TableCell className="bg-secondary/30">
                    {leg2?.stake ? `€${leg2.stake.toFixed(2)}` : 'N/A'}
                  </TableCell>
                  
                  {/* Leg 3 (optional - only for 3-way markets) */}
                  <TableCell className="bg-accent/10">{leg3?.bookmaker || '-'}</TableCell>
                  <TableCell className="bg-accent/10 font-medium">{leg3?.outcome || '-'}</TableCell>
                  <TableCell className="bg-accent/10 font-semibold">{leg3?.odds?.toFixed(2) || '-'}</TableCell>
                  <TableCell className="bg-accent/10">
                    {leg3?.stake ? `€${leg3.stake.toFixed(2)}` : '-'}
                  </TableCell>
                  
                  {/* Profit */}
                  <TableCell className={profitClass}>
                    {arb.profitPercentage ? `${arb.profitPercentage.toFixed(2)}%` : 'N/A'}
                  </TableCell>
                  <TableCell className={`${profitClass} font-bold`}>
                    {arb.guaranteedProfit ? `€${arb.guaranteedProfit.toFixed(2)}` : 'N/A'}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
