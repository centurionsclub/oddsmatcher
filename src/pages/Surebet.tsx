import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SurebetResults } from "@/components/SurebetResults";
import { toast } from "sonner";
import { ArrowLeft, Search } from "lucide-react";
import { Link } from "react-router-dom";

export default function Surebet() {
  const [sport, setSport] = useState("calcio");
  const [market, setMarket] = useState("1X2");
  const [minProfit, setMinProfit] = useState("0.5");
  const [budget, setBudget] = useState("100");

  const handleSearch = () => {
    toast.info("Funzionalità di ricerca non attiva - solo frontend");
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-secondary/20">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <Link to="/">
            <Button variant="ghost" className="mb-4">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Torna alla Home
            </Button>
          </Link>
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 bg-gradient-to-br from-primary to-primary/60 rounded-2xl flex items-center justify-center shadow-lg">
              <span className="text-3xl font-bold text-primary-foreground">S</span>
            </div>
            <div>
              <h1 className="text-4xl font-bold text-foreground mb-2">
                SURE BET FINDER
              </h1>
              <p className="text-muted-foreground">
                Trova automaticamente opportunità di arbitraggio garantito su tutti i bookmaker
              </p>
            </div>
          </div>
        </div>

        {/* Filters Card */}
        <Card className="p-6 mb-6 border-border bg-card/80 backdrop-blur">
          <h2 className="text-xl font-semibold mb-4 text-foreground">Filtri di Ricerca</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <div className="space-y-2">
              <Label htmlFor="sport">Sport</Label>
              <Select value={sport} onValueChange={setSport}>
                <SelectTrigger id="sport">
                  <SelectValue placeholder="Seleziona sport" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="calcio">Calcio</SelectItem>
                  <SelectItem value="basket">Basket</SelectItem>
                  <SelectItem value="tennis">Tennis</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="market">Mercato</Label>
              <Select value={market} onValueChange={setMarket}>
                <SelectTrigger id="market">
                  <SelectValue placeholder="Seleziona mercato" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1X2">1X2 (Esito Finale)</SelectItem>
                  <SelectItem value="Over/Under 2.5">Over/Under 2.5</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="minProfit">Profitto Minimo (%)</Label>
              <Input
                id="minProfit"
                type="text"
                value={minProfit}
                onChange={(e) => setMinProfit(e.target.value)}
                placeholder="0.5"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="budget">Budget Totale (€)</Label>
              <Input
                id="budget"
                type="text"
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
                placeholder="100"
              />
            </div>
          </div>

          <Button 
            onClick={handleSearch} 
            className="w-full md:w-auto"
            size="lg"
          >
            <Search className="mr-2 h-5 w-5" />
            Cerca Surebet
          </Button>
        </Card>

        {/* Info Card */}
        <Card className="p-4 mb-6 bg-primary/5 border-primary/20">
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
              <span className="text-primary text-lg">ℹ️</span>
            </div>
            <div className="text-sm text-muted-foreground">
              <p className="font-medium text-foreground mb-1">Come funziona:</p>
              <p>
                Il sistema analizza automaticamente le quote di TUTTI i bookmaker disponibili e trova le combinazioni
                che garantiscono un profitto indipendentemente dall'esito dell'evento. Gli stake sono pre-calcolati
                in base al tuo budget.
              </p>
            </div>
          </div>
        </Card>

        {/* Results - empty state */}
        <SurebetResults 
          data={null}
          loading={false}
          error={null}
        />
      </div>
    </div>
  );
}
