import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { ArrowUp, RefreshCw, Trash2, Archive, ChevronUp, ChevronDown, Trophy, ShoppingCart, Building2, ArrowLeftRight, Coins, Gift, Wallet } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

const Index = () => {
  const [activeTab, setActiveTab] = useState("singola");
  const [betfairCommission, setBetfairCommission] = useState("4,50%");
  const [betflagCommission, setBetflagCommission] = useState("5,00%");
  const { toast } = useToast();

  // Stati per SINGOLA
  const [singolaFilters, setSingolaFilters] = useState({
    sport: "tutti",
    mercato: "tutti",
    bookmaker: "tutti",
    exchange: "tutti",
    stakePunta: "0 €",
    bonus: "0 €",
    quotaMinima: "0,00",
    quotaMassima: "0,00",
    partita: "",
    campionato: "",
    daData: "",
    aData: "",
    freebet: false,
    rimborso: false,
  });

  // Stati per MULTIPLA
  const [multiplaFilters, setMultiplaFilters] = useState({
    sport: "tutti",
    mercato: "tutti",
    bookmaker: "tutti",
    exchange: "tutti",
    stakeMultipla: "0 €",
    bonus: "0 €",
    quotaMinimaMultipla: "0,00",
    nEventi: "0",
    quotaPartitaMinima: "0,00",
    quotaPartitaMassima: "0,00",
    partita: "",
    campionato: "",
    daData: "",
    aData: "",
    freebet: false,
    rimborso: false,
    filtroLiquidita: false,
  });

  // Stati per BEST ODDS
  const [bestOddsFilters, setBestOddsFilters] = useState({
    mercato: "nessuno",
    partita: "",
  });

  const handlePulisci = () => {
    if (activeTab === "singola") {
      setSingolaFilters({
        sport: "tutti",
        mercato: "tutti",
        bookmaker: "tutti",
        exchange: "tutti",
        stakePunta: "0 €",
        bonus: "0 €",
        quotaMinima: "0,00",
        quotaMassima: "0,00",
        partita: "",
        campionato: "",
        daData: "",
        aData: "",
        freebet: false,
        rimborso: false,
      });
    } else if (activeTab === "multipla") {
      setMultiplaFilters({
        sport: "tutti",
        mercato: "tutti",
        bookmaker: "tutti",
        exchange: "tutti",
        stakeMultipla: "0 €",
        bonus: "0 €",
        quotaMinimaMultipla: "0,00",
        nEventi: "0",
        quotaPartitaMinima: "0,00",
        quotaPartitaMassima: "0,00",
        partita: "",
        campionato: "",
        daData: "",
        aData: "",
        freebet: false,
        rimborso: false,
        filtroLiquidita: false,
      });
    } else if (activeTab === "bestodds") {
      setBestOddsFilters({
        mercato: "nessuno",
        partita: "",
      });
    }
  };

  useEffect(() => {
    const savedBetfair = localStorage.getItem("betfairCommission");
    const savedBetflag = localStorage.getItem("betflagCommission");
    if (savedBetfair) setBetfairCommission(savedBetfair);
    if (savedBetflag) setBetflagCommission(savedBetflag);
  }, []);

  const handleBetfairChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setBetfairCommission(value);
    localStorage.setItem("betfairCommission", value);
    toast({
      description: "Commissione Betfair salvata",
      duration: 2000,
    });
  };

  const handleBetflagChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setBetflagCommission(value);
    localStorage.setItem("betflagCommission", value);
    toast({
      description: "Commissione BetFlag salvata",
      duration: 2000,
    });
  };

  const tabs = [
    { id: "singola", label: "SINGOLA" },
    { id: "multipla", label: "MULTIPLA" },
    { id: "trevie", label: "TRE VIE" },
    { id: "bestodds", label: "BEST ODDS" },
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
            onClick={handlePulisci}
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
        <div className="bg-white rounded-lg border border-gray-300 p-6 space-y-3">
          {activeTab === "singola" ? (
            <>
              {/* Row 1: Sport */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-[#C8E6C9] px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <Trophy className="h-4 w-4" />
                  Sport
                </div>
                <Select value={singolaFilters.sport} onValueChange={(value) => setSingolaFilters({...singolaFilters, sport: value})}>
                  <SelectTrigger className="h-9 bg-white border-gray-300 flex-1 max-w-[300px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-white">
                    <SelectItem value="tutti">Tutti</SelectItem>
                    <SelectItem value="calcio">⚽ Calcio</SelectItem>
                    <SelectItem value="tennis">🎾 Tennis</SelectItem>
                    <SelectItem value="basket">🏀 Basket</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Row 2: Mercato */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-[#FFE0B2] px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <ShoppingCart className="h-4 w-4" />
                  Mercato
                </div>
                <Select value={singolaFilters.mercato} onValueChange={(value) => setSingolaFilters({...singolaFilters, mercato: value})}>
                  <SelectTrigger className="h-9 bg-white border-gray-300 flex-1 max-w-[300px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-white max-h-[400px] overflow-y-auto">
                    <SelectItem value="tutti">Tutti</SelectItem>
                    <SelectItem value="1">⚽ 1</SelectItem>
                    <SelectItem value="2">⚽ 2</SelectItem>
                    <SelectItem value="x">⚽ X</SelectItem>
                    <SelectItem value="goal">⚽ Goal</SelectItem>
                    <SelectItem value="nogoal">⚽ No Goal</SelectItem>
                    <SelectItem value="under05">⚽ Under 0.5</SelectItem>
                    <SelectItem value="over05">⚽ Over 0.5</SelectItem>
                    <SelectItem value="under15">⚽ Under 1.5</SelectItem>
                    <SelectItem value="over15">⚽ Over 1.5</SelectItem>
                    <SelectItem value="under25">⚽ Under 2.5</SelectItem>
                    <SelectItem value="over25">⚽ Over 2.5</SelectItem>
                    <SelectItem value="under35">⚽ Under 3.5</SelectItem>
                    <SelectItem value="over35">⚽ Over 3.5</SelectItem>
                    <SelectItem value="under45">⚽ Under 4.5</SelectItem>
                    <SelectItem value="over45">⚽ Over 4.5</SelectItem>
                    <SelectItem value="1-tennis">🎾 1</SelectItem>
                    <SelectItem value="2-tennis">🎾 2</SelectItem>
                    <SelectItem value="1-basket">🏀 1</SelectItem>
                    <SelectItem value="2-basket">🏀 2</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Row 3: Bookmaker */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-[#B8D4D8] px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <Building2 className="h-4 w-4" />
                  Bookmaker
                </div>
                <Select value={singolaFilters.bookmaker} onValueChange={(value) => setSingolaFilters({...singolaFilters, bookmaker: value})}>
                  <SelectTrigger className="h-9 bg-white border-gray-300 flex-1 max-w-[300px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-white max-h-[400px] overflow-y-auto">
                    <SelectItem value="tutti">Tutti</SelectItem>
                    <SelectItem value="888sport">888sport</SelectItem>
                    <SelectItem value="admiral">Admiral</SelectItem>
                    <SelectItem value="bet365">Bet365</SelectItem>
                    <SelectItem value="betfair">Betfair</SelectItem>
                    <SelectItem value="betflag">Betflag</SelectItem>
                    <SelectItem value="betsson">Betsson</SelectItem>
                    <SelectItem value="better">Better</SelectItem>
                    <SelectItem value="betway">Betway</SelectItem>
                    <SelectItem value="eurobet">Eurobet</SelectItem>
                    <SelectItem value="goldbet">Goldbet</SelectItem>
                    <SelectItem value="lottomatica">Lottomatica</SelectItem>
                    <SelectItem value="netbet">NetBet</SelectItem>
                    <SelectItem value="sisal">Sisal</SelectItem>
                    <SelectItem value="snai">Snai</SelectItem>
                    <SelectItem value="unibet">Unibet</SelectItem>
                    <SelectItem value="williamhill">William Hill</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Row 4: Exchange */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-[#EEBFBF] px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <ArrowLeftRight className="h-4 w-4" />
                  Exchange
                </div>
                <Select value={singolaFilters.exchange} onValueChange={(value) => setSingolaFilters({...singolaFilters, exchange: value})}>
                  <SelectTrigger className="h-9 bg-white border-gray-300 flex-1 max-w-[300px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-white max-h-[400px] overflow-y-auto w-[400px]">
                    <SelectItem value="tutti">Tutti gli Exchange</SelectItem>
                    <div className="flex items-center justify-between px-2 py-1.5 hover:bg-gray-100">
                      <SelectItem value="betfair" className="flex-1 border-none">Betfair Exchange</SelectItem>
                      <Input 
                        type="text" 
                        value={betfairCommission}
                        onChange={handleBetfairChange}
                        className="h-7 w-20 text-xs"
                        onClick={(e) => e.stopPropagation()}
                      />
                    </div>
                    <div className="flex items-center justify-between px-2 py-1.5 hover:bg-gray-100">
                      <SelectItem value="betflag" className="flex-1 border-none">BetFlag Exchange</SelectItem>
                      <Input 
                        type="text" 
                        value={betflagCommission}
                        onChange={handleBetflagChange}
                        className="h-7 w-20 text-xs"
                        onClick={(e) => e.stopPropagation()}
                      />
                    </div>
                    <div className="px-2 py-1.5 text-sm font-semibold text-gray-700 bg-gray-100 border-t border-b border-gray-200 mt-1 mb-1">
                      Bookmakers
                    </div>
                    <SelectItem value="888sport">888sport</SelectItem>
                    <SelectItem value="admiral">Admiral</SelectItem>
                    <SelectItem value="bet365">Bet365</SelectItem>
                    <SelectItem value="betfair-book">Betfair</SelectItem>
                    <SelectItem value="betflag-book">Betflag</SelectItem>
                    <SelectItem value="betsson">Betsson</SelectItem>
                    <SelectItem value="better">Better</SelectItem>
                    <SelectItem value="betway">Betway</SelectItem>
                    <SelectItem value="eurobet">Eurobet</SelectItem>
                    <SelectItem value="goldbet">Goldbet</SelectItem>
                    <SelectItem value="lottomatica">Lottomatica</SelectItem>
                    <SelectItem value="netbet">NetBet</SelectItem>
                    <SelectItem value="sisal">Sisal</SelectItem>
                    <SelectItem value="snai">Snai</SelectItem>
                    <SelectItem value="unibet">Unibet</SelectItem>
                    <SelectItem value="williamhill">William Hill</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Row 5: Stake Punta */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-gray-100 px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <Coins className="h-4 w-4" />
                  Stake Punta
                </div>
                <Input 
                  type="text" 
                  value={singolaFilters.stakePunta}
                  onChange={(e) => setSingolaFilters({...singolaFilters, stakePunta: e.target.value})}
                  className="h-9 w-[100px] bg-white border-gray-300"
                />
                <div className="flex items-center gap-2 ml-4">
                  <Checkbox 
                    id="freebet" 
                    className="border-gray-400"
                    checked={singolaFilters.freebet}
                    onCheckedChange={(checked) => setSingolaFilters({...singolaFilters, freebet: !!checked})}
                  />
                  <label htmlFor="freebet" className="text-sm text-gray-600 cursor-pointer">
                    Free Bet
                  </label>
                </div>
              </div>

              {/* Row 6: Bonus */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-[#F5E6A8] px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <Gift className="h-4 w-4" />
                  Bonus
                </div>
                <Input 
                  type="text" 
                  value={singolaFilters.bonus}
                  onChange={(e) => setSingolaFilters({...singolaFilters, bonus: e.target.value})}
                  className="h-9 w-[100px] bg-white border-gray-300"
                />
                <div className="flex items-center gap-2 ml-4">
                  <Checkbox 
                    id="rimborso" 
                    className="border-gray-400"
                    checked={singolaFilters.rimborso}
                    onCheckedChange={(checked) => setSingolaFilters({...singolaFilters, rimborso: !!checked})}
                  />
                  <label htmlFor="rimborso" className="text-sm text-gray-600 cursor-pointer">
                    Rimborso
                  </label>
                </div>
              </div>

              {/* Row 7: Quota Minima & Massima */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-gray-100 px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Quota Minima
                </div>
                <div className="relative w-[100px]">
                  <Input
                    type="text"
                    value={singolaFilters.quotaMinima}
                    onChange={(e) => setSingolaFilters({...singolaFilters, quotaMinima: e.target.value})}
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
                <Label className="text-sm font-normal text-gray-700 whitespace-nowrap bg-gray-100 px-3 py-2 rounded ml-4">
                  Quota Massima
                </Label>
                <div className="relative w-[100px]">
                  <Input
                    type="text"
                    value={singolaFilters.quotaMassima}
                    onChange={(e) => setSingolaFilters({...singolaFilters, quotaMassima: e.target.value})}
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

              {/* Row 8: Partita */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-gray-100 px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Partita
                </div>
                <Input 
                  type="text" 
                  placeholder="Cerca per nome..."
                  value={singolaFilters.partita}
                  onChange={(e) => setSingolaFilters({...singolaFilters, partita: e.target.value})}
                  className="h-9 flex-1 max-w-[300px] bg-white border-gray-300 placeholder:text-gray-400"
                />
              </div>

              {/* Row 9: Campionato */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-gray-100 px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Campionato
                </div>
                <Select value={singolaFilters.campionato} onValueChange={(value) => setSingolaFilters({...singolaFilters, campionato: value})}>
                  <SelectTrigger className="h-9 flex-1 max-w-[300px] bg-white border-gray-300">
                    <SelectValue placeholder="Cerca Campionato..." />
                  </SelectTrigger>
                  <SelectContent className="bg-white">
                    <SelectItem value="seriea">Serie A</SelectItem>
                    <SelectItem value="premierleague">Premier League</SelectItem>
                    <SelectItem value="laliga">La Liga</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Row 10: Date */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-gray-100 px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Da data
                </div>
                <Input 
                  type="text" 
                  placeholder="gg/mm/aaaa"
                  value={singolaFilters.daData}
                  onChange={(e) => setSingolaFilters({...singolaFilters, daData: e.target.value})}
                  className="h-9 w-[150px] bg-white border-gray-300 placeholder:text-gray-400"
                />
                <Label className="text-sm font-normal text-gray-700 whitespace-nowrap bg-gray-100 px-3 py-2 rounded">
                  A data
                </Label>
                <Input 
                  type="text" 
                  placeholder="gg/mm/aaaa"
                  value={singolaFilters.aData}
                  onChange={(e) => setSingolaFilters({...singolaFilters, aData: e.target.value})}
                  className="h-9 w-[150px] bg-white border-gray-300 placeholder:text-gray-400"
                />
              </div>
            </>
          ) : activeTab === "multipla" ? (
            <>
              {/* Row 1: Sport */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-[#C8E6C9] px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <Trophy className="h-4 w-4" />
                  Sport
                </div>
                <Select value={multiplaFilters.sport} onValueChange={(value) => setMultiplaFilters({...multiplaFilters, sport: value})}>
                  <SelectTrigger className="h-9 bg-white border-gray-300 flex-1 max-w-[300px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-white">
                    <SelectItem value="tutti">Tutti</SelectItem>
                    <SelectItem value="calcio">⚽ Calcio</SelectItem>
                    <SelectItem value="tennis">🎾 Tennis</SelectItem>
                    <SelectItem value="basket">🏀 Basket</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Row 2: Mercato */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-[#FFE0B2] px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <ShoppingCart className="h-4 w-4" />
                  Mercato
                </div>
                <Select value={multiplaFilters.mercato} onValueChange={(value) => setMultiplaFilters({...multiplaFilters, mercato: value})}>
                  <SelectTrigger className="h-9 bg-white border-gray-300 flex-1 max-w-[300px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-white max-h-[400px] overflow-y-auto">
                    <SelectItem value="tutti">Tutti</SelectItem>
                    <SelectItem value="1">⚽ 1</SelectItem>
                    <SelectItem value="2">⚽ 2</SelectItem>
                    <SelectItem value="x">⚽ X</SelectItem>
                    <SelectItem value="goal">⚽ Goal</SelectItem>
                    <SelectItem value="nogoal">⚽ No Goal</SelectItem>
                    <SelectItem value="under05">⚽ Under 0.5</SelectItem>
                    <SelectItem value="over05">⚽ Over 0.5</SelectItem>
                    <SelectItem value="under15">⚽ Under 1.5</SelectItem>
                    <SelectItem value="over15">⚽ Over 1.5</SelectItem>
                    <SelectItem value="under25">⚽ Under 2.5</SelectItem>
                    <SelectItem value="over25">⚽ Over 2.5</SelectItem>
                    <SelectItem value="under35">⚽ Under 3.5</SelectItem>
                    <SelectItem value="over35">⚽ Over 3.5</SelectItem>
                    <SelectItem value="under45">⚽ Under 4.5</SelectItem>
                    <SelectItem value="over45">⚽ Over 4.5</SelectItem>
                    <SelectItem value="1-tennis">🎾 1</SelectItem>
                    <SelectItem value="2-tennis">🎾 2</SelectItem>
                    <SelectItem value="1-basket">🏀 1</SelectItem>
                    <SelectItem value="2-basket">🏀 2</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Row 3: Bookmaker */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-[#B8D4D8] px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <Building2 className="h-4 w-4" />
                  Bookmaker
                </div>
                <Select value={multiplaFilters.bookmaker} onValueChange={(value) => setMultiplaFilters({...multiplaFilters, bookmaker: value})}>
                  <SelectTrigger className="h-9 bg-white border-gray-300 flex-1 max-w-[300px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-white max-h-[400px] overflow-y-auto">
                    <SelectItem value="tutti">Tutti</SelectItem>
                    <SelectItem value="nessuno">Nessuno</SelectItem>
                    <SelectItem value="888sport">888sport</SelectItem>
                    <SelectItem value="admiral">Admiral</SelectItem>
                    <SelectItem value="bet365">Bet365</SelectItem>
                    <SelectItem value="betfair">Betfair</SelectItem>
                    <SelectItem value="betflag">Betflag</SelectItem>
                    <SelectItem value="betsson">Betsson</SelectItem>
                    <SelectItem value="better">Better</SelectItem>
                    <SelectItem value="betway">Betway</SelectItem>
                    <SelectItem value="eurobet">Eurobet</SelectItem>
                    <SelectItem value="goldbet">Goldbet</SelectItem>
                    <SelectItem value="lottomatica">Lottomatica</SelectItem>
                    <SelectItem value="netbet">NetBet</SelectItem>
                    <SelectItem value="sisal">Sisal</SelectItem>
                    <SelectItem value="snai">Snai</SelectItem>
                    <SelectItem value="unibet">Unibet</SelectItem>
                    <SelectItem value="williamhill">William Hill</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Row 4: Exchange with Filtro Liquidità */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-[#EEBFBF] px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <ArrowLeftRight className="h-4 w-4" />
                  Exchange
                </div>
                <Select value={multiplaFilters.exchange} onValueChange={(value) => setMultiplaFilters({...multiplaFilters, exchange: value})}>
                  <SelectTrigger className="h-9 bg-white border-gray-300 w-[200px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-white max-h-[400px] overflow-y-auto w-[400px]">
                    <SelectItem value="tutti">Tutti gli Exchange</SelectItem>
                    <div className="flex items-center justify-between px-2 py-1.5 hover:bg-gray-100">
                      <SelectItem value="betfair" className="flex-1 border-none">Betfair Exchange</SelectItem>
                      <Input 
                        type="text" 
                        value={betfairCommission}
                        onChange={handleBetfairChange}
                        className="h-7 w-20 text-xs"
                        onClick={(e) => e.stopPropagation()}
                      />
                    </div>
                    <div className="flex items-center justify-between px-2 py-1.5 hover:bg-gray-100">
                      <SelectItem value="betflag" className="flex-1 border-none">BetFlag Exchange</SelectItem>
                      <Input 
                        type="text" 
                        value={betflagCommission}
                        onChange={handleBetflagChange}
                        className="h-7 w-20 text-xs"
                        onClick={(e) => e.stopPropagation()}
                      />
                    </div>
                    <div className="px-2 py-1.5 text-sm font-semibold text-gray-700 bg-gray-100 border-t border-b border-gray-200 mt-1 mb-1">
                      Bookmakers
                    </div>
                    <SelectItem value="888sport">888sport</SelectItem>
                    <SelectItem value="admiral">Admiral</SelectItem>
                    <SelectItem value="bet365">Bet365</SelectItem>
                    <SelectItem value="betfair-book">Betfair</SelectItem>
                    <SelectItem value="betflag-book">Betflag</SelectItem>
                    <SelectItem value="betsson">Betsson</SelectItem>
                    <SelectItem value="better">Better</SelectItem>
                    <SelectItem value="betway">Betway</SelectItem>
                    <SelectItem value="eurobet">Eurobet</SelectItem>
                    <SelectItem value="goldbet">Goldbet</SelectItem>
                    <SelectItem value="lottomatica">Lottomatica</SelectItem>
                    <SelectItem value="netbet">NetBet</SelectItem>
                    <SelectItem value="sisal">Sisal</SelectItem>
                    <SelectItem value="snai">Snai</SelectItem>
                    <SelectItem value="unibet">Unibet</SelectItem>
                    <SelectItem value="williamhill">William Hill</SelectItem>
                  </SelectContent>
                </Select>
                <div className="flex items-center gap-2 ml-4">
                  <Checkbox 
                    id="filtro-liquidita" 
                    className="border-gray-400"
                    checked={multiplaFilters.filtroLiquidita}
                    onCheckedChange={(checked) => setMultiplaFilters({...multiplaFilters, filtroLiquidita: !!checked})}
                  />
                  <label htmlFor="filtro-liquidita" className="text-sm text-gray-600 cursor-pointer">
                    Filtro Liquidità
                  </label>
                </div>
              </div>

              {/* Row 5: Stake Multipla */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-gray-100 px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <Coins size={16} strokeWidth={2} className="text-gray-700 shrink-0" />
                  Stake Multipla
                </div>
                <Input 
                  type="text" 
                  value={multiplaFilters.stakeMultipla}
                  onChange={(e) => setMultiplaFilters({...multiplaFilters, stakeMultipla: e.target.value})}
                  className="h-9 w-[100px] bg-white border-gray-300"
                />
                <div className="flex items-center gap-2 ml-4">
                  <Checkbox 
                    id="freebet-multi" 
                    className="border-gray-400"
                    checked={multiplaFilters.freebet}
                    onCheckedChange={(checked) => setMultiplaFilters({...multiplaFilters, freebet: !!checked})}
                  />
                  <label htmlFor="freebet-multi" className="text-sm text-gray-600 cursor-pointer">
                    Free Bet
                  </label>
                </div>
              </div>

              {/* Row 6: Bonus */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-[#F5E6A8] px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <Gift className="h-4 w-4" />
                  Bonus
                </div>
                <Input 
                  type="text" 
                  value={multiplaFilters.bonus}
                  onChange={(e) => setMultiplaFilters({...multiplaFilters, bonus: e.target.value})}
                  className="h-9 w-[100px] bg-white border-gray-300"
                />
                <div className="flex items-center gap-2 ml-4">
                  <Checkbox 
                    id="rimborso-multi" 
                    className="border-gray-400"
                    checked={multiplaFilters.rimborso}
                    onCheckedChange={(checked) => setMultiplaFilters({...multiplaFilters, rimborso: !!checked})}
                  />
                  <label htmlFor="rimborso-multi" className="text-sm text-gray-600 cursor-pointer">
                    Rimborso
                  </label>
                </div>
              </div>

              {/* Row 7: Quota Minima Multipla & N° Eventi */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-gray-100 px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Quota Minima
                </div>
                <Label className="text-sm font-normal text-gray-700 whitespace-nowrap bg-gray-100 px-3 py-2 rounded">
                  Multipla
                </Label>
                <div className="relative w-[80px]">
                  <Input
                    type="text"
                    value={multiplaFilters.quotaMinimaMultipla}
                    onChange={(e) => setMultiplaFilters({...multiplaFilters, quotaMinimaMultipla: e.target.value})}
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
                <Label className="text-sm font-normal text-gray-700 whitespace-nowrap bg-gray-100 px-3 py-2 rounded">
                  N° Eventi
                </Label>
                <Input
                  type="text"
                  value={multiplaFilters.nEventi}
                  onChange={(e) => setMultiplaFilters({...multiplaFilters, nEventi: e.target.value})}
                  className="h-9 w-[80px] bg-white border-gray-300"
                />
              </div>

              {/* Row 8: Quota Partita */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-gray-100 px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Quota Partita
                </div>
                <Label className="text-sm font-normal text-gray-700 whitespace-nowrap bg-gray-100 px-3 py-2 rounded">
                  Minima
                </Label>
                <div className="relative w-[80px]">
                  <Input
                    type="text"
                    value={multiplaFilters.quotaPartitaMinima}
                    onChange={(e) => setMultiplaFilters({...multiplaFilters, quotaPartitaMinima: e.target.value})}
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
                <Label className="text-sm font-normal text-gray-700 whitespace-nowrap bg-gray-100 px-3 py-2 rounded">
                  Massima
                </Label>
                <div className="relative w-[80px]">
                  <Input
                    type="text"
                    value={multiplaFilters.quotaPartitaMassima}
                    onChange={(e) => setMultiplaFilters({...multiplaFilters, quotaPartitaMassima: e.target.value})}
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

              {/* Row 9: Partita */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-gray-100 px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Partita
                </div>
                <Input 
                  type="text" 
                  placeholder="Cerca per nome..."
                  value={multiplaFilters.partita}
                  onChange={(e) => setMultiplaFilters({...multiplaFilters, partita: e.target.value})}
                  className="h-9 flex-1 max-w-[300px] bg-white border-gray-300 placeholder:text-gray-400"
                />
              </div>

              {/* Row 10: Campionato */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-gray-100 px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Campionato
                </div>
                <Select value={multiplaFilters.campionato} onValueChange={(value) => setMultiplaFilters({...multiplaFilters, campionato: value})}>
                  <SelectTrigger className="h-9 flex-1 max-w-[300px] bg-white border-gray-300">
                    <SelectValue placeholder="Cerca Campionato..." />
                  </SelectTrigger>
                  <SelectContent className="bg-white">
                    <SelectItem value="seriea">Serie A</SelectItem>
                    <SelectItem value="premierleague">Premier League</SelectItem>
                    <SelectItem value="laliga">La Liga</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Row 11: Date */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-gray-100 px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Da data
                </div>
                <Input 
                  type="text" 
                  placeholder="gg/mm/aaaa"
                  value={multiplaFilters.daData}
                  onChange={(e) => setMultiplaFilters({...multiplaFilters, daData: e.target.value})}
                  className="h-9 w-[150px] bg-white border-gray-300 placeholder:text-gray-400"
                />
                <Label className="text-sm font-normal text-gray-700 whitespace-nowrap bg-gray-100 px-3 py-2 rounded">
                  A data
                </Label>
                <Input 
                  type="text" 
                  placeholder="gg/mm/aaaa"
                  value={multiplaFilters.aData}
                  onChange={(e) => setMultiplaFilters({...multiplaFilters, aData: e.target.value})}
                  className="h-9 w-[150px] bg-white border-gray-300 placeholder:text-gray-400"
                />
              </div>
            </>
          ) : activeTab === "bestodds" ? (
            <>
              {/* Row 1: Mercato */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-[#FFE0B2] px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <ShoppingCart className="h-4 w-4" />
                  Mercato
                </div>
                <Select defaultValue="nessuno">
                  <SelectTrigger className="h-9 bg-white border-gray-300 flex-1 max-w-[300px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-white max-h-[400px] overflow-y-auto">
                    <SelectItem value="nessuno">Nessuno</SelectItem>
                    <SelectItem value="1">⚽ 1</SelectItem>
                    <SelectItem value="2">⚽ 2</SelectItem>
                    <SelectItem value="x">⚽ X</SelectItem>
                    <SelectItem value="goal">⚽ Goal</SelectItem>
                    <SelectItem value="nogoal">⚽ No Goal</SelectItem>
                    <SelectItem value="under05">⚽ Under 0.5</SelectItem>
                    <SelectItem value="over05">⚽ Over 0.5</SelectItem>
                    <SelectItem value="under15">⚽ Under 1.5</SelectItem>
                    <SelectItem value="over15">⚽ Over 1.5</SelectItem>
                    <SelectItem value="under25">⚽ Under 2.5</SelectItem>
                    <SelectItem value="over25">⚽ Over 2.5</SelectItem>
                    <SelectItem value="under35">⚽ Under 3.5</SelectItem>
                    <SelectItem value="over35">⚽ Over 3.5</SelectItem>
                    <SelectItem value="under45">⚽ Under 4.5</SelectItem>
                    <SelectItem value="over45">⚽ Over 4.5</SelectItem>
                    <SelectItem value="1-tennis">🎾 1</SelectItem>
                    <SelectItem value="2-tennis">🎾 2</SelectItem>
                    <SelectItem value="1-basket">🏀 1</SelectItem>
                    <SelectItem value="2-basket">🏀 2</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Row 2: Partita */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-gray-700 bg-gray-100 px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Partita
                </div>
                <Input 
                  type="text" 
                  placeholder="Cerca per nome..." 
                  className="h-9 flex-1 max-w-[300px] bg-white border-gray-300 placeholder:text-gray-400"
                />
              </div>
            </>
          ) : null}
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
