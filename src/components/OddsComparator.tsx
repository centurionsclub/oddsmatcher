import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { format } from "date-fns";

interface ComparatorData {
  event: string;
  eventTime: string;
  league: string;
  market: string;
  bestOdds: {
    home: { bookmaker: string; odds: number };
    draw?: { bookmaker: string; odds: number };
    away: { bookmaker: string; odds: number };
  };
  allBookmakers: {
    bookmaker: string;
    home: number;
    draw?: number;
    away: number;
  }[];
}

interface OddsComparatorProps {
  data: ComparatorData[];
}

export function OddsComparator({ data }: OddsComparatorProps) {
  if (!data || data.length === 0) {
    return (
      <Card>
        <CardContent className="pt-6">
          <p className="text-center text-muted-foreground">Nessun dato disponibile</p>
        </CardContent>
      </Card>
    );
  }

  const formatDate = (dateString: string) => {
    try {
      return format(new Date(dateString), "dd/MM/yyyy HH:mm");
    } catch {
      return dateString;
    }
  };

  return (
    <div className="space-y-4">
      {data.map((event, idx) => (
        <Card key={idx} className="border-primary/20">
          <CardHeader className="pb-3">
            <h3 className="font-bold text-lg">{event.event}</h3>
            <p className="text-sm text-muted-foreground">
              {event.league} • {formatDate(event.eventTime)} • {event.market}
            </p>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[150px]">Bookmaker</TableHead>
                  <TableHead className="text-center">1</TableHead>
                  {event.bestOdds.draw && <TableHead className="text-center">X</TableHead>}
                  <TableHead className="text-center">2</TableHead>
                  <TableHead className="text-center">Migliore</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {event.allBookmakers.map((bm) => (
                  <TableRow key={bm.bookmaker}>
                    <TableCell className="font-medium capitalize">
                      {bm.bookmaker}
                    </TableCell>
                    <TableCell
                      className={`text-center ${
                        bm.home === event.bestOdds.home.odds
                          ? "bg-green-100 dark:bg-green-900/30 font-bold text-green-700 dark:text-green-400"
                          : ""
                      }`}
                    >
                      {bm.home > 0 ? bm.home.toFixed(2) : "-"}
                    </TableCell>
                    {event.bestOdds.draw && (
                      <TableCell
                        className={`text-center ${
                          bm.draw === event.bestOdds.draw.odds
                            ? "bg-green-100 dark:bg-green-900/30 font-bold text-green-700 dark:text-green-400"
                            : ""
                        }`}
                      >
                        {bm.draw && bm.draw > 0 ? bm.draw.toFixed(2) : "-"}
                      </TableCell>
                    )}
                    <TableCell
                      className={`text-center ${
                        bm.away === event.bestOdds.away.odds
                          ? "bg-green-100 dark:bg-green-900/30 font-bold text-green-700 dark:text-green-400"
                          : ""
                      }`}
                    >
                      {bm.away > 0 ? bm.away.toFixed(2) : "-"}
                    </TableCell>
                    <TableCell className="text-center">
                      {(bm.home === event.bestOdds.home.odds ||
                        bm.draw === event.bestOdds.draw?.odds ||
                        bm.away === event.bestOdds.away.odds) && (
                        <Badge className="bg-green-500 hover:bg-green-600">★</Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            <div className="mt-4 p-4 bg-secondary/20 rounded-lg border border-secondary">
              <p className="text-sm font-semibold mb-2">Migliori Quote per Questo Evento:</p>
              <div className="flex flex-wrap gap-4">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground font-medium">1:</span>
                  <span className="font-bold text-green-600 dark:text-green-400 text-lg">
                    {event.bestOdds.home.odds.toFixed(2)}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    ({event.bestOdds.home.bookmaker})
                  </span>
                </div>
                {event.bestOdds.draw && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground font-medium">X:</span>
                    <span className="font-bold text-green-600 dark:text-green-400 text-lg">
                      {event.bestOdds.draw.odds.toFixed(2)}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      ({event.bestOdds.draw.bookmaker})
                    </span>
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground font-medium">2:</span>
                  <span className="font-bold text-green-600 dark:text-green-400 text-lg">
                    {event.bestOdds.away.odds.toFixed(2)}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    ({event.bestOdds.away.bookmaker})
                  </span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
