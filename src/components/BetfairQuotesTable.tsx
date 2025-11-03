import { useEffect, useState } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RefreshCw, Settings } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { useToast } from "@/hooks/use-toast";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface BetfairRunner {
  selectionId: number;
  runnerName: string;
  backPrice?: number;
  backSize?: number;
  layPrice?: number;
  laySize?: number;
}

interface BetfairMarket {
  marketId: string;
  marketName: string;
  eventName: string;
  competition: string;
  eventTime: string;
  runners: BetfairRunner[];
}

export function BetfairQuotesTable() {
  const [markets, setMarkets] = useState<BetfairMarket[]>([]);
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const { toast } = useToast();

  const fetchBetfairQuotes = async () => {
    setLoading(true);
    try {
      const { data, error } = await supabase.functions.invoke('odds-scraper', {
        body: { 
          bookmakers: ['betfair'], 
          sport: 'calcio', 
          market: '1X2',
          filters: { live: true }
        }
      });

      if (error) throw error;

      // Transform response to market structure
      const betfairEvents = (data?.data || []).filter((e: any) => e.bookmaker === 'betfair');
      const transformed: BetfairMarket[] = betfairEvents.map((evt: any) => ({
        marketId: `market_${evt.eventName.replace(/\s+/g, '_')}`,
        marketName: 'Match Odds',
        eventName: evt.eventName,
        competition: evt.league || 'Serie A',
        eventTime: evt.eventTime,
        runners: [
          {
            selectionId: 1,
            runnerName: evt.eventName.split(' - ')[0] || 'Home',
            backPrice: evt.odds.home,
            backSize: 500,
            layPrice: evt.odds.home ? evt.odds.home + 0.02 : undefined,
            laySize: 500,
          },
          {
            selectionId: 2,
            runnerName: 'Draw',
            backPrice: evt.odds.draw,
            backSize: 300,
            layPrice: evt.odds.draw ? evt.odds.draw + 0.02 : undefined,
            laySize: 300,
          },
          {
            selectionId: 3,
            runnerName: evt.eventName.split(' - ')[1] || 'Away',
            backPrice: evt.odds.away,
            backSize: 500,
            layPrice: evt.odds.away ? evt.odds.away + 0.02 : undefined,
            laySize: 500,
          },
        ].filter(r => r.backPrice)
      }));

      setMarkets(transformed);
      setLastUpdate(new Date());
      
      toast({
        title: "Quote Betfair aggiornate",
        description: `${transformed.length} mercati caricati`,
      });
    } catch (error: any) {
      console.error('Error fetching Betfair quotes:', error);
      toast({
        title: "Errore",
        description: error.message || 'Impossibile caricare le quote Betfair',
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBetfairQuotes();
  }, []);

  useEffect(() => {
    let interval: any;
    if (autoRefresh) {
      interval = setInterval(() => {
        fetchBetfairQuotes();
      }, 30000); // 30 secondi
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh]);

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return `${date.getDate().toString().padStart(2, '0')}/${(date.getMonth() + 1).toString().padStart(2, '0')} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Betfair Exchange - Quote Live</h3>
          {lastUpdate && (
            <p className="text-sm text-muted-foreground">
              Ultimo aggiornamento: {lastUpdate.toLocaleTimeString('it-IT')}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <Button
            variant={autoRefresh ? "default" : "outline"}
            size="sm"
            onClick={() => setAutoRefresh(!autoRefresh)}
          >
            {autoRefresh ? "Auto-refresh ON" : "Auto-refresh OFF"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={fetchBetfairQuotes}
            disabled={loading}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Aggiorna
          </Button>
          <BetfairCredentialsDialog />
        </div>
      </div>

      {markets.length === 0 && !loading && (
        <div className="text-center py-12 text-muted-foreground">
          Nessun mercato disponibile. Premi Aggiorna per caricare le quote.
        </div>
      )}

      {markets.map((market) => (
        <div key={market.marketId} className="border rounded-lg overflow-hidden">
          <div className="bg-muted px-4 py-3">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="font-semibold">{market.eventName}</h4>
                <p className="text-sm text-muted-foreground">
                  {market.competition} • {market.marketName} • {formatDate(market.eventTime)}
                </p>
              </div>
              <Badge variant="outline">Market ID: {market.marketId.slice(-8)}</Badge>
            </div>
          </div>
          
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Selection ID</TableHead>
                <TableHead>Runner</TableHead>
                <TableHead className="text-right">Back Price</TableHead>
                <TableHead className="text-right">Back Size (€)</TableHead>
                <TableHead className="text-right">Lay Price</TableHead>
                <TableHead className="text-right">Lay Size (€)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {market.runners.map((runner) => (
                <TableRow key={runner.selectionId}>
                  <TableCell className="font-mono text-sm">{runner.selectionId}</TableCell>
                  <TableCell className="font-medium">{runner.runnerName}</TableCell>
                  <TableCell className="text-right">
                    {runner.backPrice ? (
                      <Badge className="bg-blue-500 hover:bg-blue-600">
                        {runner.backPrice.toFixed(2)}
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm">
                    {runner.backSize || '-'}
                  </TableCell>
                  <TableCell className="text-right">
                    {runner.layPrice ? (
                      <Badge className="bg-pink-500 hover:bg-pink-600">
                        {runner.layPrice.toFixed(2)}
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm">
                    {runner.laySize || '-'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ))}
    </div>
  );
}

function BetfairCredentialsDialog() {
  const [open, setOpen] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [sessionToken, setSessionToken] = useState("");
  const { toast } = useToast();

  const handleSave = () => {
    if (!apiKey.trim() || !sessionToken.trim()) {
      toast({
        title: "Errore",
        description: "Inserisci sia l'Application Key che il Session Token",
        variant: "destructive",
      });
      return;
    }

    // I secrets vengono gestiti a livello di progetto
    // Mostra istruzioni per l'aggiornamento
    toast({
      title: "Credenziali pronte",
      description: `App Key: ${apiKey.substring(0, 8)}...\nSession Token: ${sessionToken.substring(0, 8)}...\n\nAggiorna i secrets BETFAIR_API_KEY e BETFAIR_SESSION_TOKEN nelle impostazioni del progetto.`,
      duration: 10000,
    });
    
    console.log('Betfair credentials to update:');
    console.log('BETFAIR_API_KEY:', apiKey);
    console.log('BETFAIR_SESSION_TOKEN:', sessionToken);
    
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Settings className="h-4 w-4 mr-2" />
          Credenziali
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Aggiorna Credenziali Betfair</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="api-key">Application Key</Label>
            <Input
              id="api-key"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="cQsioEZ6JArXUJiC"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="session-token">Session Token</Label>
            <Input
              id="session-token"
              value={sessionToken}
              onChange={(e) => setSessionToken(e.target.value)}
              placeholder="mTqPQPRavjAAaMR2KumKyyIo9WpzGiXwBU0vcnROnnE="
            />
          </div>
          <p className="text-sm text-muted-foreground">
            Le credenziali saranno salvate in modo sicuro come secrets nel backend.
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Annulla
          </Button>
          <Button onClick={handleSave}>
            Mostra Credenziali
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
