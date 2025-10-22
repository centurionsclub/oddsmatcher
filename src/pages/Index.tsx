import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { ArrowUp, RefreshCw, Trash2, Archive, ChevronUp, ChevronDown } from "lucide-react";

const Index = () => {
  const [activeTab, setActiveTab] = useState("singola");

  const tabs = [
    { id: "singola", label: "SINGOLA" },
    { id: "multipla", label: "MULTIPLA" },
    { id: "trevie", label: "TRE VIE" },
    { id: "bestodds", label: "BEST ODDS" },
    { id: "bestopposite", label: "BEST OPPOSITE" },
    { id: "surebet", label: "SURE BET" }
  ];

  return (
    <div className="min-h-screen bg-[#F5F5F5]">
      {/* Header */}
      <header className="bg-gradient-to-r from-[#1A7F7F] to-[#0D6B6B] py-3 shadow-md">
        <h1 className="text-[26px] font-bold text-white text-center tracking-wider">
          ODDSMATCHER
        </h1>
      </header>

      {/* Main Container */}
      <div className="max-w-[1400px] mx-auto px-6 py-4">
        {/* Top Action Buttons */}
        <div className="flex gap-2 mb-4">
          <Button 
            variant="outline" 
            size="sm" 
            className="gap-2 bg-white border-gray-300 hover:bg-gray-50 text-sm font-medium"
          >
            FILTRA <ArrowUp className="h-3.5 w-3.5" />
          </Button>
          <Button 
            variant="outline" 
            size="sm" 
            className="gap-2 bg-white border-gray-300 hover:bg-gray-50 text-sm font-medium"
          >
            AGGIORNA <RefreshCw className="h-3.5 w-3.5" />
          </Button>
          <Button 
            size="sm" 
            className="gap-2 bg-[#DC3545] hover:bg-[#C82333] text-white text-sm font-medium"
          >
            PULISCI <Trash2 className="h-3.5 w-3.5" />
          </Button>
          <Button 
            variant="outline" 
            size="sm" 
            className="gap-2 bg-white border-gray-300 hover:bg-gray-50 text-sm font-medium"
          >
            ARCHIVIO <Archive className="h-3.5 w-3.5" />
          </Button>
        </div>

        {/* Tabs */}
        <div className="flex gap-6 mb-6 border-b border-gray-300">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`pb-2 text-[13px] font-medium transition-all ${
                activeTab === tab.id
                  ? "text-gray-900 border-b-2 border-gray-900"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Filters */}
        <div className="bg-white rounded-lg border border-gray-300 p-6 space-y-4">
          {/* Row 1: Sport & Mercato */}
          <div className="grid grid-cols-2 gap-4">
            <div className="flex items-center gap-3">
              <Label className="text-sm font-normal text-gray-700 whitespace-nowrap min-w-[80px]">
                Sport
              </Label>
              <Select defaultValue="tutti">
                <SelectTrigger className="h-9 bg-white border-gray-300">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-white">
                  <SelectItem value="tutti">Tutti</SelectItem>
                  <SelectItem value="calcio">Calcio</SelectItem>
                  <SelectItem value="tennis">Tennis</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-center gap-3">
              <Label className="text-sm font-normal text-gray-700 whitespace-nowrap min-w-[80px]">
                Mercato
              </Label>
              <Select defaultValue="tutti">
                <SelectTrigger className="h-9 bg-white border-gray-300">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-white">
                  <SelectItem value="tutti">Tutti</SelectItem>
                  <SelectItem value="1x2">1X2</SelectItem>
                  <SelectItem value="over">Over/Under</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Row 2: Bookmaker & Exchange */}
          <div className="grid grid-cols-2 gap-4">
            <div className="flex items-center gap-3">
              <div className="text-sm font-normal text-gray-700 bg-[#B8D4D8] px-3 py-1 rounded whitespace-nowrap min-w-[80px] flex items-center justify-center">
                Bookmaker
              </div>
              <Select defaultValue="tutti">
                <SelectTrigger className="h-9 bg-white border-gray-300">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-white">
                  <SelectItem value="tutti">Tutti</SelectItem>
                  <SelectItem value="bet365">Bet365</SelectItem>
                  <SelectItem value="sisal">Sisal</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-center gap-3">
              <div className="text-sm font-normal text-gray-700 bg-[#EEBFBF] px-3 py-1 rounded whitespace-nowrap min-w-[80px] flex items-center justify-center">
                Exchange
              </div>
              <Select defaultValue="tutti">
                <SelectTrigger className="h-9 bg-white border-gray-300">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-white">
                  <SelectItem value="tutti">Tutti gli Exchange</SelectItem>
                  <SelectItem value="betfair">Betfair</SelectItem>
                  <SelectItem value="betflag">Betflag</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Row 3: Stake Punta */}
          <div className="flex items-center gap-3">
            <Label className="text-sm font-normal text-gray-700 whitespace-nowrap min-w-[100px]">
              Stake Punta
            </Label>
            <Input 
              type="text" 
              defaultValue="0 €" 
              className="h-9 w-32 bg-white border-gray-300"
            />
            <div className="flex items-center gap-2 ml-4">
              <Checkbox id="freebet" className="border-gray-400" />
              <label htmlFor="freebet" className="text-sm text-gray-600 cursor-pointer">
                Free Bet
              </label>
            </div>
          </div>

          {/* Row 4: Bonus */}
          <div className="flex items-center gap-3">
            <div className="text-sm font-normal text-gray-700 bg-[#F5E6A8] px-3 py-1 rounded whitespace-nowrap min-w-[100px] flex items-center justify-center">
              Bonus
            </div>
            <Input 
              type="text" 
              defaultValue="0 €" 
              className="h-9 w-32 bg-white border-gray-300"
            />
            <div className="flex items-center gap-2 ml-4">
              <Checkbox id="rimborso" className="border-gray-400" />
              <label htmlFor="rimborso" className="text-sm text-gray-600 cursor-pointer">
                Rimborso
              </label>
            </div>
          </div>

          {/* Row 5: Quota Minima & Massima */}
          <div className="grid grid-cols-2 gap-4">
            <div className="flex items-center gap-3">
              <Label className="text-sm font-normal text-gray-700 whitespace-nowrap min-w-[100px]">
                Quota Minima
              </Label>
              <div className="relative flex-1 max-w-[200px]">
                <Input
                  type="text"
                  defaultValue="0,00"
                  className="h-9 pr-8 bg-white border-gray-300"
                />
                <div className="absolute right-1 top-1/2 -translate-y-1/2 flex flex-col">
                  <button className="h-4 w-6 hover:bg-gray-100 rounded flex items-center justify-center">
                    <ChevronUp className="h-3 w-3 text-gray-600" />
                  </button>
                  <button className="h-4 w-6 hover:bg-gray-100 rounded flex items-center justify-center">
                    <ChevronDown className="h-3 w-3 text-gray-600" />
                  </button>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <Label className="text-sm font-normal text-gray-700 whitespace-nowrap min-w-[100px]">
                Quota Massima
              </Label>
              <div className="relative flex-1 max-w-[200px]">
                <Input
                  type="text"
                  defaultValue="0,00"
                  className="h-9 pr-8 bg-white border-gray-300"
                />
                <div className="absolute right-1 top-1/2 -translate-y-1/2 flex flex-col">
                  <button className="h-4 w-6 hover:bg-gray-100 rounded flex items-center justify-center">
                    <ChevronUp className="h-3 w-3 text-gray-600" />
                  </button>
                  <button className="h-4 w-6 hover:bg-gray-100 rounded flex items-center justify-center">
                    <ChevronDown className="h-3 w-3 text-gray-600" />
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Row 6: Partita */}
          <div className="flex items-center gap-3">
            <Label className="text-sm font-normal text-gray-700 whitespace-nowrap min-w-[100px]">
              Partita
            </Label>
            <Input 
              type="text" 
              placeholder="Cerca per nome..." 
              className="h-9 flex-1 bg-white border-gray-300 placeholder:text-gray-400"
            />
          </div>

          {/* Row 7: Campionato */}
          <div className="flex items-center gap-3">
            <Label className="text-sm font-normal text-gray-700 whitespace-nowrap min-w-[100px]">
              Campionato
            </Label>
            <Select>
              <SelectTrigger className="h-9 flex-1 bg-white border-gray-300">
                <SelectValue placeholder="Cerca Campionato..." />
              </SelectTrigger>
              <SelectContent className="bg-white">
                <SelectItem value="seriea">Serie A</SelectItem>
                <SelectItem value="premierleague">Premier League</SelectItem>
                <SelectItem value="laliga">La Liga</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Row 8: Date */}
          <div className="grid grid-cols-2 gap-4">
            <div className="flex items-center gap-3">
              <Label className="text-sm font-normal text-gray-700 whitespace-nowrap min-w-[80px]">
                Da data
              </Label>
              <Input 
                type="text" 
                placeholder="gg/mm/aaaa"
                className="h-9 bg-white border-gray-300 placeholder:text-gray-400"
              />
            </div>

            <div className="flex items-center gap-3">
              <Label className="text-sm font-normal text-gray-700 whitespace-nowrap min-w-[80px]">
                A data
              </Label>
              <Input 
                type="text" 
                placeholder="gg/mm/aaaa"
                className="h-9 bg-white border-gray-300 placeholder:text-gray-400"
              />
            </div>
          </div>
        </div>

        {/* Empty Results */}
        <div className="mt-6 bg-white rounded-lg border border-gray-300 p-12 text-center">
          <p className="text-gray-500">
            Nessun risultato disponibile. Utilizza i filtri per cercare opportunità.
          </p>
        </div>
      </div>
    </div>
  );
};

export default Index;
