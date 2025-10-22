import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { ArrowUp, RefreshCw, Trash2, Archive, ChevronUp, ChevronDown } from "lucide-react";

const Index = () => {
  const [activeTab, setActiveTab] = useState("singola");
  const [quotaMin, setQuotaMin] = useState("0,00");
  const [quotaMax, setQuotaMax] = useState("0,00");

  const tabs = [
    { id: "singola", label: "SINGOLA" },
    { id: "multipla", label: "MULTIPLA" },
    { id: "trevie", label: "TRE VIE" },
    { id: "bestodds", label: "BEST ODDS" },
    { id: "bestopposite", label: "BEST OPPOSITE" },
    { id: "surebet", label: "SURE BET" }
  ];

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="bg-primary py-4">
        <h1 className="text-2xl font-bold text-primary-foreground text-center tracking-wide">
          ODDSMATCHER
        </h1>
      </header>

      {/* Top Actions */}
      <div className="container mx-auto px-6 py-4">
        <div className="flex gap-3 mb-4">
          <Button variant="outline" size="sm" className="gap-2">
            <ArrowUp className="h-4 w-4" />
            FILTRA
          </Button>
          <Button variant="outline" size="sm" className="gap-2">
            <RefreshCw className="h-4 w-4" />
            AGGIORNA
          </Button>
          <Button variant="destructive" size="sm" className="gap-2">
            <Trash2 className="h-4 w-4" />
            PULISCI
          </Button>
          <Button variant="outline" size="sm" className="gap-2">
            <Archive className="h-4 w-4" />
            ARCHIVIO
          </Button>
        </div>

        {/* Tabs */}
        <div className="flex gap-4 mb-6 pb-2 border-b">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? "text-foreground border-b-2 border-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Filters Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {/* Sport */}
          <div className="flex items-center gap-3">
            <Label className="w-24 text-sm font-medium">Sport</Label>
            <Select defaultValue="tutti">
              <SelectTrigger className="flex-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="tutti">Tutti</SelectItem>
                <SelectItem value="calcio">Calcio</SelectItem>
                <SelectItem value="tennis">Tennis</SelectItem>
                <SelectItem value="basket">Basket</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Mercato */}
          <div className="flex items-center gap-3">
            <Label className="w-24 text-sm font-medium">Mercato</Label>
            <Select defaultValue="tutti">
              <SelectTrigger className="flex-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="tutti">Tutti</SelectItem>
                <SelectItem value="1x2">1X2</SelectItem>
                <SelectItem value="over">Over/Under</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Bookmaker */}
          <div className="flex items-center gap-3">
            <Label className="w-24 text-sm font-medium bg-[#B8D4D8] px-2 py-1 rounded">
              Bookmaker
            </Label>
            <Select defaultValue="tutti">
              <SelectTrigger className="flex-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="tutti">Tutti</SelectItem>
                <SelectItem value="bet365">Bet365</SelectItem>
                <SelectItem value="sisal">Sisal</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Exchange */}
          <div className="flex items-center gap-3">
            <Label className="w-24 text-sm font-medium bg-[#EEBFBF] px-2 py-1 rounded">
              Exchange
            </Label>
            <Select defaultValue="tutti">
              <SelectTrigger className="flex-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="tutti">Tutti gli Exchange</SelectItem>
                <SelectItem value="betfair">Betfair</SelectItem>
                <SelectItem value="betflag">Betflag</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Stake Punta */}
          <div className="flex items-center gap-3">
            <Label className="w-24 text-sm font-medium">Stake Punta</Label>
            <Input type="text" defaultValue="0 €" className="flex-1" />
            <div className="flex items-center gap-2">
              <Checkbox id="freebet" />
              <label htmlFor="freebet" className="text-sm text-muted-foreground cursor-pointer">
                Free Bet
              </label>
            </div>
          </div>

          {/* Bonus */}
          <div className="flex items-center gap-3">
            <Label className="w-24 text-sm font-medium bg-[#F5E6A8] px-2 py-1 rounded">
              Bonus
            </Label>
            <Input type="text" defaultValue="0 €" className="flex-1" />
            <div className="flex items-center gap-2">
              <Checkbox id="rimborso" />
              <label htmlFor="rimborso" className="text-sm text-muted-foreground cursor-pointer">
                Rimborso
              </label>
            </div>
          </div>

          {/* Quota Minima */}
          <div className="flex items-center gap-3">
            <Label className="w-24 text-sm font-medium">Quota Minima</Label>
            <div className="flex-1 relative">
              <Input
                type="text"
                value={quotaMin}
                onChange={(e) => setQuotaMin(e.target.value)}
                className="pr-8"
              />
              <div className="absolute right-2 top-1/2 -translate-y-1/2 flex flex-col">
                <button className="h-3 hover:bg-muted rounded">
                  <ChevronUp className="h-3 w-3" />
                </button>
                <button className="h-3 hover:bg-muted rounded">
                  <ChevronDown className="h-3 w-3" />
                </button>
              </div>
            </div>
          </div>

          {/* Quota Massima */}
          <div className="flex items-center gap-3">
            <Label className="w-24 text-sm font-medium">Quota Massima</Label>
            <div className="flex-1 relative">
              <Input
                type="text"
                value={quotaMax}
                onChange={(e) => setQuotaMax(e.target.value)}
                className="pr-8"
              />
              <div className="absolute right-2 top-1/2 -translate-y-1/2 flex flex-col">
                <button className="h-3 hover:bg-muted rounded">
                  <ChevronUp className="h-3 w-3" />
                </button>
                <button className="h-3 hover:bg-muted rounded">
                  <ChevronDown className="h-3 w-3" />
                </button>
              </div>
            </div>
          </div>

          {/* Partita */}
          <div className="flex items-center gap-3">
            <Label className="w-24 text-sm font-medium">Partita</Label>
            <Input type="text" placeholder="Cerca per nome..." className="flex-1" />
          </div>

          {/* Campionato */}
          <div className="flex items-center gap-3">
            <Label className="w-24 text-sm font-medium">Campionato</Label>
            <Select>
              <SelectTrigger className="flex-1">
                <SelectValue placeholder="Cerca Campionato..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="seriea">Serie A</SelectItem>
                <SelectItem value="premierleague">Premier League</SelectItem>
                <SelectItem value="laliga">La Liga</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Da data */}
          <div className="flex items-center gap-3">
            <Label className="w-24 text-sm font-medium">Da data</Label>
            <Input type="date" className="flex-1" />
          </div>

          {/* A data */}
          <div className="flex items-center gap-3">
            <Label className="w-24 text-sm font-medium">A data</Label>
            <Input type="date" className="flex-1" />
          </div>
        </div>

        {/* Results Area */}
        <div className="mt-8 p-8 border rounded-lg bg-card text-center text-muted-foreground">
          <p>Nessun risultato trovato. Utilizza i filtri per cercare opportunità di matched betting.</p>
        </div>
      </div>
    </div>
  );
};

export default Index;
