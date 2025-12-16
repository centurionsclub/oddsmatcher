import { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DecimalInput } from "@/components/ui/decimal-input";
import { CurrencyInput } from "@/components/ui/currency-input";
import { MultiSelect } from "@/components/ui/multi-select";
import { ExchangeMultiSelect } from "@/components/ui/exchange-multi-select";
import { DatePicker } from "@/components/ui/date-picker";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog";
import { ArrowUp, RefreshCw, Trash2, Archive, ChevronUp, ChevronDown, Trophy, ShoppingCart, Building2, ArrowLeftRight, Coins, Gift, Save, X, Search } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { OddsResults } from "@/components/OddsResults";
import { MatchedBettingResults } from "@/components/MatchedBettingResults";
import { MultipleMatchedBettingResults } from "@/components/MultipleMatchedBettingResults";
import { ThreeWayArbitrageResults } from "@/components/ThreeWayArbitrageResults";
import { BetfairQuotesTable } from "@/components/BetfairQuotesTable";
import { OddsComparator } from "@/components/OddsComparator";
import { OddsAlerts } from "@/components/OddsAlerts";
import logoCenturion from "@/assets/logo_centurion_new.png";

const Index = () => {
  const [activeTab, setActiveTab] = useState("singola");
  const [betfairCommission, setBetfairCommission] = useState("4,50%");
  const [betflagCommission, setBetflagCommission] = useState("5,00%");
  const { toast } = useToast();
  
  // Stati per salvare filtri (solo locale, nessun database)
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [filterName, setFilterName] = useState("");
  const [savedFilters, setSavedFilters] = useState<any[]>([]);
  const [archiveOpen, setArchiveOpen] = useState(false);

  // Stati per SINGOLA
  const [singolaFilters, setSingolaFilters] = useState({
    sport: "tutti",
    mercato: "tutti",
    bookmaker: [] as string[],
    exchange: [] as string[],
    stakePunta: "0",
    bonus: "0",
    quotaMinima: "0,00",
    quotaMassima: "0,00",
    partita: "",
    campionato: "",
    daData: undefined as Date | undefined,
    aData: undefined as Date | undefined,
    freebet: false,
    rimborso: false,
  });

  // Stati per MULTIPLA
  const [multiplaFilters, setMultiplaFilters] = useState({
    sport: "tutti",
    mercato: "tutti",
    bookmaker: [] as string[],
    exchange: [] as string[],
    stakeMultipla: "0",
    bonus: "0",
    quotaMinimaMultipla: "0,00",
    nEventi: "0",
    quotaPartitaMinima: "0,00",
    quotaPartitaMassima: "0,00",
    partita: "",
    campionato: "",
    daData: undefined as Date | undefined,
    aData: undefined as Date | undefined,
    freebet: false,
    rimborso: false,
    filtroLiquidita: false,
  });

  // Stati per TRE VIE
  const [trevieFilters, setTrevieFilters] = useState({
    bookmakerPrincipale: "nessuno",
    bookmakersSecondari: [] as string[],
    stakePunta: "0",
    bonus: "0",
    quotaMinima: "0,00",
    quotaMassima: "0,00",
    partita: "",
    campionato: "",
    daData: undefined as Date | undefined,
    aData: undefined as Date | undefined,
    rimborso: false,
  });

  // Stati per BEST ODDS
  const [bestOddsFilters, setBestOddsFilters] = useState({
    mercato: "nessuno",
    partita: "",
  });

  // Stati per COMPARATORE
  const [comparatoreFilters, setComparatoreFilters] = useState({
    sport: "calcio",
    mercato: "1X2",
    campionato: "",
  });

  const handlePulisci = () => {
    if (activeTab === "singola") {
      setSingolaFilters({
        sport: "tutti",
        mercato: "tutti",
        bookmaker: [],
        exchange: [],
        stakePunta: "0",
        bonus: "0",
        quotaMinima: "0,00",
        quotaMassima: "0,00",
        partita: "",
        campionato: "",
        daData: undefined,
        aData: undefined,
        freebet: false,
        rimborso: false,
      });
    } else if (activeTab === "multipla") {
      setMultiplaFilters({
        sport: "tutti",
        mercato: "tutti",
        bookmaker: [],
        exchange: [],
        stakeMultipla: "0",
        bonus: "0",
        quotaMinimaMultipla: "0,00",
        nEventi: "0",
        quotaPartitaMinima: "0,00",
        quotaPartitaMassima: "0,00",
        partita: "",
        campionato: "",
        daData: undefined,
        aData: undefined,
        freebet: false,
        rimborso: false,
        filtroLiquidita: false,
      });
    } else if (activeTab === "trevie") {
      setTrevieFilters({
        bookmakerPrincipale: "nessuno",
        bookmakersSecondari: [],
        stakePunta: "0",
        bonus: "0",
        quotaMinima: "0,00",
        quotaMassima: "0,00",
        partita: "",
        campionato: "",
        daData: undefined,
        aData: undefined,
        rimborso: false,
      });
    } else if (activeTab === "bestodds") {
      setBestOddsFilters({
        mercato: "nessuno",
        partita: "",
      });
    } else if (activeTab === "comparatore") {
      setComparatoreFilters({
        sport: "calcio",
        mercato: "1X2",
        campionato: "",
      });
    }
    toast({
      title: "Filtri puliti",
      description: "Tutti i filtri sono stati resettati",
    });
  };

  const handleBetfairChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setBetfairCommission(e.target.value);
  };

  const handleBetflagChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setBetflagCommission(e.target.value);
  };

  const handleSaveFilter = () => {
    if (!filterName.trim()) {
      toast({
        title: "Errore",
        description: "Inserisci un nome per il filtro",
        variant: "destructive",
      });
      return;
    }

    let filterData;
    if (activeTab === "singola") {
      filterData = singolaFilters;
    } else if (activeTab === "multipla") {
      filterData = multiplaFilters;
    } else if (activeTab === "trevie") {
      filterData = trevieFilters;
    } else if (activeTab === "bestodds") {
      filterData = bestOddsFilters;
    }

    // Salva solo localmente
    const newFilter = {
      id: Date.now().toString(),
      name: filterName,
      tab_type: activeTab,
      filter_data: filterData,
    };
    
    setSavedFilters([newFilter, ...savedFilters]);

    toast({
      title: "Filtro salvato",
      description: `Il filtro "${filterName}" è stato salvato localmente`,
    });

    setFilterName("");
    setSaveDialogOpen(false);
  };

  const handleLoadFilter = (filterData: any) => {
    if (activeTab === "singola") {
      setSingolaFilters(filterData);
    } else if (activeTab === "multipla") {
      setMultiplaFilters(filterData);
    } else if (activeTab === "trevie") {
      setTrevieFilters(filterData);
    } else if (activeTab === "bestodds") {
      setBestOddsFilters(filterData);
    }
    setArchiveOpen(false);
    toast({
      title: "Filtro caricato",
      description: "Il filtro è stato applicato",
    });
  };

  const handleDeleteFilter = (id: string) => {
    setSavedFilters(savedFilters.filter(f => f.id !== id));
    toast({
      title: "Filtro eliminato",
      description: "Il filtro è stato rimosso",
    });
  };

  const handleSearch = () => {
    toast({
      title: "Ricerca",
      description: "Funzionalità di ricerca non attiva - solo frontend",
    });
  };

  const tabs = [
    { id: "singola", label: "SINGOLA" },
    { id: "multipla", label: "MULTIPLA" },
    { id: "trevie", label: "TRE VIE" },
    { id: "bestodds", label: "BEST ODDS" },
    { id: "betfairlive", label: "BETFAIR LIVE" },
    { id: "comparatore", label: "COMPARATORE" },
    { id: "alert", label: "ALERT" },
  ];

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="bg-[hsl(208,40%,16%)] py-3 shadow-md">
        <div className="max-w-[1400px] mx-auto px-6 relative flex items-center">
          <img src={logoCenturion} alt="Centurion Club" className="h-12 w-auto" />
          <h1 className="text-[26px] font-bold text-foreground tracking-wider absolute left-1/2 -translate-x-1/2">
            ODDSMATCHER
          </h1>
        </div>
      </header>

      {/* Main Container */}
      <div className="max-w-[1400px] mx-auto px-6 py-4">
        {/* Top Action Buttons */}
        <div className="flex gap-2 mb-4">
          <Button 
            variant="outline" 
            size="sm" 
            className="gap-2 text-sm font-medium"
          >
            FILTRA <ArrowUp className="h-3.5 w-3.5" />
          </Button>
          <Button 
            variant="outline" 
            size="sm" 
            className="gap-2 text-sm font-medium"
            onClick={handleSearch}
          >
            CERCA <Search className="h-3.5 w-3.5" />
          </Button>
          <Button 
            size="sm" 
            className="gap-2 text-sm font-medium"
            onClick={handlePulisci}
          >
            PULISCI <Trash2 className="h-3.5 w-3.5" />
          </Button>
          
          <Popover open={archiveOpen} onOpenChange={setArchiveOpen}>
            <PopoverTrigger asChild>
              <Button 
                variant="outline" 
                size="sm" 
                className="gap-2 text-sm font-medium"
              >
                ARCHIVIO <Archive className="h-3.5 w-3.5" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[300px] p-4" align="start">
              <div className="space-y-2">
                <h4 className="font-medium text-sm mb-3">Filtri salvati</h4>
                {savedFilters.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Nessun filtro salvato</p>
                ) : (
                  <div className="space-y-2 max-h-[300px] overflow-y-auto">
                    {savedFilters.map((filter) => (
                      <div 
                        key={filter.id} 
                        className="flex items-center justify-between p-2 hover:bg-secondary/50 rounded border border-border"
                      >
                        <button
                          onClick={() => handleLoadFilter(filter.filter_data)}
                          className="flex-1 text-left text-sm"
                        >
                          {filter.name}
                        </button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDeleteFilter(filter.id)}
                          className="h-7 w-7 p-0"
                        >
                          <X className="h-4 w-4 text-muted-foreground" />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </PopoverContent>
          </Popover>

          <Dialog open={saveDialogOpen} onOpenChange={setSaveDialogOpen}>
            <DialogTrigger asChild>
              <Button 
                variant="outline" 
                size="sm" 
                className="gap-2 text-sm font-medium"
              >
                SALVA FILTRO <Save className="h-3.5 w-3.5" />
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Salva filtro</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="filter-name">Nome filtro</Label>
                  <Input
                    id="filter-name"
                    value={filterName}
                    onChange={(e) => setFilterName(e.target.value)}
                    placeholder="Es. Calcio Serie A Multipla"
                  />
                </div>
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => setSaveDialogOpen(false)}
                >
                  Annulla
                </Button>
                <Button onClick={handleSaveFilter}>
                  Salva
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
          
          {/* Link to dedicated Surebet page */}
          <Link to="/surebet">
            <Button 
              variant="default"
              size="sm" 
              className="gap-2 text-sm font-medium bg-primary hover:bg-primary-hover"
            >
              <Trophy className="h-3.5 w-3.5" />
              SUREBET FINDER
            </Button>
          </Link>
        </div>

        {/* Tabs */}
        <div className="flex gap-6 mb-6 border-b border-border">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`pb-2 text-[13px] font-medium transition-all ${
                activeTab === tab.id
                  ? "text-foreground border-b-2 border-primary"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Filters */}
        <div className="bg-card rounded-xl border border-border p-6 space-y-3">
          {activeTab === "singola" ? (
            <>
              {/* Row 1: Sport */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <Trophy className="h-4 w-4" />
                  Sport
                </div>
                <Select value={singolaFilters.sport} onValueChange={(value) => setSingolaFilters({...singolaFilters, sport: value})}>
                  <SelectTrigger className="h-9 flex-1 max-w-[300px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="tutti">Tutti gli sport</SelectItem>
                    <SelectItem value="calcio">⚽ Calcio</SelectItem>
                    <SelectItem value="tennis">🎾 Tennis</SelectItem>
                    <SelectItem value="basket">🏀 Basket</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Row 2: Mercato */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <ShoppingCart className="h-4 w-4" />
                  Mercato
                </div>
                <Select value={singolaFilters.mercato} onValueChange={(value) => setSingolaFilters({...singolaFilters, mercato: value})}>
                  <SelectTrigger className="h-9 flex-1 max-w-[300px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="max-h-[400px] overflow-y-auto">
                    <SelectItem value="tutti">Tutti i mercati</SelectItem>
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
                <div className="text-sm font-semibold text-white bg-[#29B6F6] px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <Building2 className="h-4 w-4" />
                  Bookmaker
                </div>
                <MultiSelect
                  options={[
                    { value: "888sport", label: "888sport" },
                    { value: "admiral", label: "Admiral" },
                    { value: "bet365", label: "Bet365" },
                    { value: "betfair", label: "Betfair" },
                    { value: "betflag", label: "Betflag" },
                    { value: "betsson", label: "Betsson" },
                    { value: "better", label: "Better" },
                    { value: "betway", label: "Betway" },
                    { value: "eurobet", label: "Eurobet" },
                    { value: "goldbet", label: "Goldbet" },
                    { value: "lottomatica", label: "Lottomatica" },
                    { value: "netbet", label: "NetBet" },
                    { value: "sisal", label: "Sisal" },
                    { value: "snai", label: "Snai" },
                    { value: "unibet", label: "Unibet" },
                    { value: "williamhill", label: "William Hill" },
                  ]}
                  selected={singolaFilters.bookmaker}
                  onChange={(selected) => setSingolaFilters({...singolaFilters, bookmaker: selected})}
                  className="flex-1 max-w-[300px]"
                />
              </div>

              {/* Row 4: Exchange */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-semibold text-white bg-[#e89fad] px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <ArrowLeftRight className="h-4 w-4" />
                  Exchange
                </div>
                <ExchangeMultiSelect
                  selected={singolaFilters.exchange}
                  onChange={(selected) => setSingolaFilters({...singolaFilters, exchange: selected})}
                  betfairCommission={betfairCommission}
                  betflagCommission={betflagCommission}
                  onBetfairChange={handleBetfairChange}
                  onBetflagChange={handleBetflagChange}
                  className="flex-1 max-w-[300px]"
                />
              </div>

              {/* Row 5: Stake Punta */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <Coins className="h-4 w-4" />
                  Stake Punta
                </div>
                <CurrencyInput 
                  value={singolaFilters.stakePunta}
                  onChange={(value) => setSingolaFilters({...singolaFilters, stakePunta: value})}
                  className="h-9 w-[120px]"
                />
                <div className="flex items-center gap-2 ml-4">
                  <Checkbox 
                    id="freebet" 
                    className="border-border"
                    checked={singolaFilters.freebet}
                    onCheckedChange={(checked) => setSingolaFilters({...singolaFilters, freebet: !!checked})}
                  />
                  <label htmlFor="freebet" className="text-sm text-foreground cursor-pointer">
                    Free Bet
                  </label>
                </div>
              </div>

              {/* Row 6: Bonus */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <Gift className="h-4 w-4" />
                  Bonus
                </div>
                <CurrencyInput 
                  value={singolaFilters.bonus}
                  onChange={(value) => setSingolaFilters({...singolaFilters, bonus: value})}
                  className="h-9 w-[120px]"
                />
                <div className="flex items-center gap-2 ml-4">
                  <Checkbox 
                    id="rimborso" 
                    className="border-border"
                    checked={singolaFilters.rimborso}
                    onCheckedChange={(checked) => setSingolaFilters({...singolaFilters, rimborso: !!checked})}
                  />
                  <label htmlFor="rimborso" className="text-sm text-foreground cursor-pointer">
                    Rimborso
                  </label>
                </div>
              </div>

              {/* Row 7: Quota Minima & Massima */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Quota Minima
                </div>
                <div className="relative w-[100px]">
                  <DecimalInput
                    value={singolaFilters.quotaMinima}
                    onChange={(value) => setSingolaFilters({...singolaFilters, quotaMinima: value})}
                    className="h-9 pr-8"
                  />
                  <div className="absolute right-1 top-1/2 -translate-y-1/2 flex flex-col">
                    <button className="h-4 w-6 hover:bg-secondary rounded flex items-center justify-center">
                      <ChevronUp className="h-3 w-3 text-muted-foreground" />
                    </button>
                    <button className="h-4 w-6 hover:bg-secondary rounded flex items-center justify-center">
                      <ChevronDown className="h-3 w-3 text-muted-foreground" />
                    </button>
                  </div>
                </div>
                <Label className="text-sm font-normal text-foreground whitespace-nowrap bg-secondary px-3 py-2 rounded ml-4">
                  Quota Massima
                </Label>
                <div className="relative w-[100px]">
                  <DecimalInput
                    value={singolaFilters.quotaMassima}
                    onChange={(value) => setSingolaFilters({...singolaFilters, quotaMassima: value})}
                    className="h-9 pr-8"
                  />
                  <div className="absolute right-1 top-1/2 -translate-y-1/2 flex flex-col">
                    <button className="h-4 w-6 hover:bg-secondary rounded flex items-center justify-center">
                      <ChevronUp className="h-3 w-3 text-muted-foreground" />
                    </button>
                    <button className="h-4 w-6 hover:bg-secondary rounded flex items-center justify-center">
                      <ChevronDown className="h-3 w-3 text-muted-foreground" />
                    </button>
                  </div>
                </div>
              </div>

              {/* Row 8: Partita */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Partita
                </div>
                <Input 
                  type="text" 
                  placeholder="Cerca per nome..."
                  value={singolaFilters.partita}
                  onChange={(e) => setSingolaFilters({...singolaFilters, partita: e.target.value})}
                  className="h-9 flex-1 max-w-[300px] placeholder:text-muted-foreground/60"
                />
              </div>

              {/* Row 9: Campionato */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Campionato
                </div>
                <Select value={singolaFilters.campionato} onValueChange={(value) => setSingolaFilters({...singolaFilters, campionato: value})}>
                  <SelectTrigger className="h-9 flex-1 max-w-[300px]">
                    <SelectValue placeholder="Cerca Campionato..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="seriea">Serie A</SelectItem>
                    <SelectItem value="premierleague">Premier League</SelectItem>
                    <SelectItem value="laliga">La Liga</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Row 10: Date */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Da data
                </div>
                <DatePicker
                  date={singolaFilters.daData}
                  onSelect={(date) => setSingolaFilters({...singolaFilters, daData: date})}
                  placeholder="gg/mm/aaaa"
                  className="w-[180px]"
                />
                <Label className="text-sm font-normal text-foreground whitespace-nowrap bg-secondary px-3 py-2 rounded">
                  A data
                </Label>
                <DatePicker
                  date={singolaFilters.aData}
                  onSelect={(date) => setSingolaFilters({...singolaFilters, aData: date})}
                  placeholder="gg/mm/aaaa"
                  className="w-[180px]"
                />
              </div>
            </>
          ) : activeTab === "multipla" ? (
            <>
              {/* Row 1: Sport */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <Trophy className="h-4 w-4" />
                  Sport
                </div>
                <Select value={multiplaFilters.sport} onValueChange={(value) => setMultiplaFilters({...multiplaFilters, sport: value})}>
                  <SelectTrigger className="h-9 flex-1 max-w-[300px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="tutti">Tutti gli sport</SelectItem>
                    <SelectItem value="calcio">⚽ Calcio</SelectItem>
                    <SelectItem value="tennis">🎾 Tennis</SelectItem>
                    <SelectItem value="basket">🏀 Basket</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Row 2: Mercato */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <ShoppingCart className="h-4 w-4" />
                  Mercato
                </div>
                <Select value={multiplaFilters.mercato} onValueChange={(value) => setMultiplaFilters({...multiplaFilters, mercato: value})}>
                  <SelectTrigger className="h-9 flex-1 max-w-[300px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="max-h-[400px] overflow-y-auto">
                    <SelectItem value="tutti">Tutti i mercati</SelectItem>
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
                <div className="text-sm font-semibold text-white bg-[#29B6F6] px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <Building2 className="h-4 w-4" />
                  Bookmaker
                </div>
                <MultiSelect
                  options={[
                    { value: "888sport", label: "888sport" },
                    { value: "admiral", label: "Admiral" },
                    { value: "bet365", label: "Bet365" },
                    { value: "betfair", label: "Betfair" },
                    { value: "betflag", label: "Betflag" },
                    { value: "betsson", label: "Betsson" },
                    { value: "better", label: "Better" },
                    { value: "betway", label: "Betway" },
                    { value: "eurobet", label: "Eurobet" },
                    { value: "goldbet", label: "Goldbet" },
                    { value: "lottomatica", label: "Lottomatica" },
                    { value: "netbet", label: "NetBet" },
                    { value: "sisal", label: "Sisal" },
                    { value: "snai", label: "Snai" },
                    { value: "unibet", label: "Unibet" },
                    { value: "williamhill", label: "William Hill" },
                  ]}
                  selected={multiplaFilters.bookmaker}
                  onChange={(selected) => setMultiplaFilters({...multiplaFilters, bookmaker: selected})}
                  className="flex-1 max-w-[300px]"
                />
              </div>

              {/* Row 4: Exchange with Filtro Liquidità */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-semibold text-white bg-[#e89fad] px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <ArrowLeftRight className="h-4 w-4" />
                  Exchange
                </div>
                <ExchangeMultiSelect
                  selected={multiplaFilters.exchange}
                  onChange={(selected) => setMultiplaFilters({...multiplaFilters, exchange: selected})}
                  betfairCommission={betfairCommission}
                  betflagCommission={betflagCommission}
                  onBetfairChange={handleBetfairChange}
                  onBetflagChange={handleBetflagChange}
                  className="w-[200px]"
                />
                <div className="flex items-center gap-2 ml-4">
                  <Checkbox 
                    id="filtro-liquidita" 
                    className="border-border"
                    checked={multiplaFilters.filtroLiquidita}
                    onCheckedChange={(checked) => setMultiplaFilters({...multiplaFilters, filtroLiquidita: !!checked})}
                  />
                  <label htmlFor="filtro-liquidita" className="text-sm text-foreground cursor-pointer">
                    Filtro Liquidità
                  </label>
                </div>
              </div>

              {/* Row 5: Stake Multipla */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <Coins className="h-4 w-4" />
                  Stake Multipla
                </div>
                <CurrencyInput 
                  value={multiplaFilters.stakeMultipla}
                  onChange={(value) => setMultiplaFilters({...multiplaFilters, stakeMultipla: value})}
                  className="h-9 w-[120px]"
                />
                <div className="flex items-center gap-2 ml-4">
                  <Checkbox 
                    id="freebet-multi" 
                    className="border-border"
                    checked={multiplaFilters.freebet}
                    onCheckedChange={(checked) => setMultiplaFilters({...multiplaFilters, freebet: !!checked})}
                  />
                  <label htmlFor="freebet-multi" className="text-sm text-foreground cursor-pointer">
                    Free Bet
                  </label>
                </div>
              </div>

              {/* Row 6: Bonus */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <Gift className="h-4 w-4" />
                  Bonus
                </div>
                <CurrencyInput 
                  value={multiplaFilters.bonus}
                  onChange={(value) => setMultiplaFilters({...multiplaFilters, bonus: value})}
                  className="h-9 w-[120px]"
                />
                <div className="flex items-center gap-2 ml-4">
                  <Checkbox 
                    id="rimborso-multi" 
                    className="border-border"
                    checked={multiplaFilters.rimborso}
                    onCheckedChange={(checked) => setMultiplaFilters({...multiplaFilters, rimborso: !!checked})}
                  />
                  <label htmlFor="rimborso-multi" className="text-sm text-foreground cursor-pointer">
                    Rimborso
                  </label>
                </div>
              </div>

              {/* Row 7: Quota Minima Multipla & N° Eventi */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Quota Minima
                </div>
                <Label className="text-sm font-normal text-foreground whitespace-nowrap bg-secondary px-3 py-2 rounded">
                  Multipla
                </Label>
                <div className="relative w-[80px]">
                  <DecimalInput
                    value={multiplaFilters.quotaMinimaMultipla}
                    onChange={(value) => setMultiplaFilters({...multiplaFilters, quotaMinimaMultipla: value})}
                    className="h-9 pr-8"
                  />
                  <div className="absolute right-1 top-1/2 -translate-y-1/2 flex flex-col">
                    <button className="h-4 w-6 hover:bg-secondary rounded flex items-center justify-center">
                      <ChevronUp className="h-3 w-3 text-muted-foreground" />
                    </button>
                    <button className="h-4 w-6 hover:bg-secondary rounded flex items-center justify-center">
                      <ChevronDown className="h-3 w-3 text-muted-foreground" />
                    </button>
                  </div>
                </div>
                <Label className="text-sm font-normal text-foreground whitespace-nowrap bg-secondary px-3 py-2 rounded">
                  N° Eventi
                </Label>
                <Input
                  type="text"
                  value={multiplaFilters.nEventi}
                  onChange={(e) => setMultiplaFilters({...multiplaFilters, nEventi: e.target.value})}
                  className="h-9 w-[80px]"
                />
              </div>

              {/* Row 8: Quota Partita */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Quota Partita
                </div>
                <Label className="text-sm font-normal text-foreground whitespace-nowrap bg-secondary px-3 py-2 rounded">
                  Minima
                </Label>
                <div className="relative w-[80px]">
                  <DecimalInput
                    value={multiplaFilters.quotaPartitaMinima}
                    onChange={(value) => setMultiplaFilters({...multiplaFilters, quotaPartitaMinima: value})}
                    className="h-9 pr-8"
                  />
                  <div className="absolute right-1 top-1/2 -translate-y-1/2 flex flex-col">
                    <button className="h-4 w-6 hover:bg-secondary rounded flex items-center justify-center">
                      <ChevronUp className="h-3 w-3 text-muted-foreground" />
                    </button>
                    <button className="h-4 w-6 hover:bg-secondary rounded flex items-center justify-center">
                      <ChevronDown className="h-3 w-3 text-muted-foreground" />
                    </button>
                  </div>
                </div>
                <Label className="text-sm font-normal text-foreground whitespace-nowrap bg-secondary px-3 py-2 rounded">
                  Massima
                </Label>
                <div className="relative w-[80px]">
                  <DecimalInput
                    value={multiplaFilters.quotaPartitaMassima}
                    onChange={(value) => setMultiplaFilters({...multiplaFilters, quotaPartitaMassima: value})}
                    className="h-9 pr-8"
                  />
                  <div className="absolute right-1 top-1/2 -translate-y-1/2 flex flex-col">
                    <button className="h-4 w-6 hover:bg-secondary rounded flex items-center justify-center">
                      <ChevronUp className="h-3 w-3 text-muted-foreground" />
                    </button>
                    <button className="h-4 w-6 hover:bg-secondary rounded flex items-center justify-center">
                      <ChevronDown className="h-3 w-3 text-muted-foreground" />
                    </button>
                  </div>
                </div>
              </div>

              {/* Row 9: Partita */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Partita
                </div>
                <Input 
                  type="text" 
                  placeholder="Cerca per nome..."
                  value={multiplaFilters.partita}
                  onChange={(e) => setMultiplaFilters({...multiplaFilters, partita: e.target.value})}
                  className="h-9 flex-1 max-w-[300px] placeholder:text-muted-foreground/60"
                />
              </div>

              {/* Row 10: Campionato */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Campionato
                </div>
                <Select value={multiplaFilters.campionato} onValueChange={(value) => setMultiplaFilters({...multiplaFilters, campionato: value})}>
                  <SelectTrigger className="h-9 flex-1 max-w-[300px]">
                    <SelectValue placeholder="Cerca Campionato..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="seriea">Serie A</SelectItem>
                    <SelectItem value="premierleague">Premier League</SelectItem>
                    <SelectItem value="laliga">La Liga</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Row 11: Date */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Da data
                </div>
                <DatePicker
                  date={multiplaFilters.daData}
                  onSelect={(date) => setMultiplaFilters({...multiplaFilters, daData: date})}
                  placeholder="gg/mm/aaaa"
                  className="w-[180px]"
                />
                <Label className="text-sm font-normal text-foreground whitespace-nowrap bg-secondary px-3 py-2 rounded">
                  A data
                </Label>
                <DatePicker
                  date={multiplaFilters.aData}
                  onSelect={(date) => setMultiplaFilters({...multiplaFilters, aData: date})}
                  placeholder="gg/mm/aaaa"
                  className="w-[180px]"
                />
              </div>
            </>
          ) : activeTab === "trevie" ? (
            <>
              {/* Row 1: Bookmaker Principale */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-semibold text-white bg-[#29B6F6] px-3 py-1 rounded whitespace-nowrap w-[170px] flex items-center justify-center">
                  Bookmaker Principale
                </div>
                <Select value={trevieFilters.bookmakerPrincipale} onValueChange={(value) => setTrevieFilters({...trevieFilters, bookmakerPrincipale: value})}>
                  <SelectTrigger className="h-9 flex-1 max-w-[300px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="nessuno">Nessuno</SelectItem>
                    <SelectItem value="bet365">Bet365</SelectItem>
                    <SelectItem value="snai">Snai</SelectItem>
                    <SelectItem value="sisal">Sisal</SelectItem>
                    <SelectItem value="lottomatica">Lottomatica</SelectItem>
                    <SelectItem value="goldbet">Goldbet</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Row 2: Bookmaker Secondari */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-semibold text-white bg-[#e89fad] px-3 py-1 rounded whitespace-nowrap w-[170px] flex items-center justify-center">
                  Bookmaker Secondari
                </div>
                <MultiSelect
                  options={[
                    { value: "sisal", label: "Sisal" },
                    { value: "bet365", label: "Bet365" },
                    { value: "lottomatica", label: "Lottomatica" },
                    { value: "goldbet", label: "Goldbet" },
                    { value: "planetwin365", label: "Planetwin365" },
                    { value: "snai", label: "Snai" },
                    { value: "eurobet", label: "Eurobet" },
                    { value: "betfair", label: "Betfair" },
                  ]}
                  selected={trevieFilters.bookmakersSecondari}
                  onChange={(selected) => setTrevieFilters({...trevieFilters, bookmakersSecondari: selected})}
                  className="flex-1 max-w-[300px]"
                />
                <Button 
                  variant="outline" 
                  size="sm" 
                  className="text-sm font-medium"
                  onClick={() => {
                    setTrevieFilters({
                      ...trevieFilters,
                      bookmakersSecondari: ["sisal", "bet365", "lottomatica", "goldbet", "planetwin365", "snai", "eurobet", "betfair"]
                    });
                  }}
                >
                  Seleziona Top
                </Button>
              </div>

              {/* Row 3: Stake Punta */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[170px] flex items-center justify-center gap-2">
                  <Coins className="h-4 w-4" />
                  Stake Punta
                </div>
                <CurrencyInput 
                  value={trevieFilters.stakePunta}
                  onChange={(value) => setTrevieFilters({...trevieFilters, stakePunta: value})}
                  className="h-9 w-[120px]"
                />
              </div>

              {/* Row 4: Bonus */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[170px] flex items-center justify-center gap-2">
                  <Gift className="h-4 w-4" />
                  Bonus
                </div>
                <CurrencyInput 
                  value={trevieFilters.bonus}
                  onChange={(value) => setTrevieFilters({...trevieFilters, bonus: value})}
                  className="h-9 w-[120px]"
                />
                <div className="flex items-center gap-2 ml-4">
                  <Checkbox 
                    id="rimborso-trevie" 
                    className="border-border"
                    checked={trevieFilters.rimborso}
                    onCheckedChange={(checked) => setTrevieFilters({...trevieFilters, rimborso: !!checked})}
                  />
                  <label htmlFor="rimborso-trevie" className="text-sm text-foreground cursor-pointer">
                    Rimborso
                  </label>
                </div>
              </div>

              {/* Row 5: Quota Minima & Massima */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[170px] flex items-center justify-center">
                  Quota
                </div>
                <Label className="text-sm font-normal text-foreground whitespace-nowrap bg-secondary px-3 py-2 rounded">
                  Minima
                </Label>
                <div className="relative w-[100px]">
                  <DecimalInput
                    value={trevieFilters.quotaMinima}
                    onChange={(value) => setTrevieFilters({...trevieFilters, quotaMinima: value})}
                    className="h-9 pr-8"
                  />
                  <div className="absolute right-1 top-1/2 -translate-y-1/2 flex flex-col">
                    <button className="h-4 w-6 hover:bg-secondary rounded flex items-center justify-center">
                      <ChevronUp className="h-3 w-3 text-muted-foreground" />
                    </button>
                    <button className="h-4 w-6 hover:bg-secondary rounded flex items-center justify-center">
                      <ChevronDown className="h-3 w-3 text-muted-foreground" />
                    </button>
                  </div>
                </div>
                <Label className="text-sm font-normal text-foreground whitespace-nowrap bg-secondary px-3 py-2 rounded">
                  Massima
                </Label>
                <div className="relative w-[100px]">
                  <DecimalInput
                    value={trevieFilters.quotaMassima}
                    onChange={(value) => setTrevieFilters({...trevieFilters, quotaMassima: value})}
                    className="h-9 pr-8"
                  />
                  <div className="absolute right-1 top-1/2 -translate-y-1/2 flex flex-col">
                    <button className="h-4 w-6 hover:bg-secondary rounded flex items-center justify-center">
                      <ChevronUp className="h-3 w-3 text-muted-foreground" />
                    </button>
                    <button className="h-4 w-6 hover:bg-secondary rounded flex items-center justify-center">
                      <ChevronDown className="h-3 w-3 text-muted-foreground" />
                    </button>
                  </div>
                </div>
              </div>

              {/* Row 6: Partita */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[170px] flex items-center justify-center">
                  Partita
                </div>
                <Input 
                  type="text" 
                  placeholder="Cerca per nome..."
                  value={trevieFilters.partita}
                  onChange={(e) => setTrevieFilters({...trevieFilters, partita: e.target.value})}
                  className="h-9 flex-1 max-w-[300px] placeholder:text-muted-foreground/60"
                />
              </div>

              {/* Row 7: Campionato */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[170px] flex items-center justify-center">
                  Campionato
                </div>
                <Select value={trevieFilters.campionato} onValueChange={(value) => setTrevieFilters({...trevieFilters, campionato: value})}>
                  <SelectTrigger className="h-9 flex-1 max-w-[300px]">
                    <SelectValue placeholder="Cerca Campionato..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="seriea">Serie A</SelectItem>
                    <SelectItem value="premierleague">Premier League</SelectItem>
                    <SelectItem value="laliga">La Liga</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Row 8: Date */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[170px] flex items-center justify-center">
                  Da data
                </div>
                <DatePicker
                  date={trevieFilters.daData}
                  onSelect={(date) => setTrevieFilters({...trevieFilters, daData: date})}
                  placeholder="gg/mm/aaaa"
                  className="w-[180px]"
                />
                <Label className="text-sm font-normal text-foreground whitespace-nowrap bg-secondary px-3 py-2 rounded">
                  A data
                </Label>
                <DatePicker
                  date={trevieFilters.aData}
                  onSelect={(date) => setTrevieFilters({...trevieFilters, aData: date})}
                  placeholder="gg/mm/aaaa"
                  className="w-[180px]"
                />
              </div>
            </>
          ) : activeTab === "bestodds" ? (
            <>
              {/* Row 1: Mercato */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <ShoppingCart className="h-4 w-4" />
                  Mercato
                </div>
                <Select value={bestOddsFilters.mercato} onValueChange={(value) => setBestOddsFilters({...bestOddsFilters, mercato: value})}>
                  <SelectTrigger className="h-9 flex-1 max-w-[300px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="max-h-[400px] overflow-y-auto">
                    <SelectItem value="nessuno">Tutti i mercati</SelectItem>
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
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Partita
                </div>
                <Input 
                  type="text" 
                  placeholder="Cerca per nome..."
                  value={bestOddsFilters.partita}
                  onChange={(e) => setBestOddsFilters({...bestOddsFilters, partita: e.target.value})}
                  className="h-9 flex-1 max-w-[300px] placeholder:text-muted-foreground/60"
                />
              </div>
            </>
          ) : activeTab === "comparatore" ? (
            <>
              {/* Row 1: Sport */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <Trophy className="h-4 w-4" />
                  Sport
                </div>
                <Select value={comparatoreFilters.sport} onValueChange={(value) => setComparatoreFilters({...comparatoreFilters, sport: value})}>
                  <SelectTrigger className="h-9 flex-1 max-w-[300px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="calcio">⚽ Calcio</SelectItem>
                    <SelectItem value="tennis">🎾 Tennis</SelectItem>
                    <SelectItem value="basket">🏀 Basket</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Row 2: Mercato */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center gap-2">
                  <ShoppingCart className="h-4 w-4" />
                  Mercato
                </div>
                <Select value={comparatoreFilters.mercato} onValueChange={(value) => setComparatoreFilters({...comparatoreFilters, mercato: value})}>
                  <SelectTrigger className="h-9 flex-1 max-w-[300px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1X2">⚽ 1X2</SelectItem>
                    <SelectItem value="under25">⚽ Under 2.5</SelectItem>
                    <SelectItem value="over25">⚽ Over 2.5</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Row 3: Campionato */}
              <div className="flex items-center gap-3">
                <div className="text-sm font-normal text-foreground bg-secondary px-3 py-1 rounded whitespace-nowrap w-[120px] flex items-center justify-center">
                  Campionato
                </div>
                <Input 
                  type="text" 
                  placeholder="Es: Serie A, Premier League..."
                  value={comparatoreFilters.campionato}
                  onChange={(e) => setComparatoreFilters({...comparatoreFilters, campionato: e.target.value})}
                  className="h-9 flex-1 max-w-[300px] placeholder:text-muted-foreground/60"
                />
              </div>
            </>
          ) : null}
        </div>

        {/* Results placeholder for different tabs */}
        {activeTab === "singola" && (
          <div className="mt-6">
            <MatchedBettingResults 
              data={null} 
              filters={singolaFilters}
              commission={parseFloat(betfairCommission.replace('%', '').replace(',', '.'))}
              loading={false} 
              error={null} 
            />
            <div className="mt-6">
              <OddsResults data={null} loading={false} error={null} />
            </div>
          </div>
        )}

        {activeTab === "multipla" && (
          <MultipleMatchedBettingResults 
            data={null} 
            filters={multiplaFilters}
            commission={parseFloat(betfairCommission.replace('%', '').replace(',', '.'))}
            loading={false} 
            error={null} 
          />
        )}

        {activeTab === "trevie" && (
          <ThreeWayArbitrageResults 
            data={null} 
            filters={trevieFilters}
            loading={false} 
            error={null} 
          />
        )}

        {activeTab === "bestodds" && (
          <OddsResults data={null} loading={false} error={null} />
        )}

        {activeTab === "betfairlive" && (
          <BetfairQuotesTable />
        )}

        {activeTab === "comparatore" && (
          <div className="mt-6">
            <p className="text-center text-muted-foreground mt-8">Seleziona i filtri e clicca su CERCA per visualizzare il comparatore quote</p>
          </div>
        )}

        {activeTab === "alert" && (
          <div className="mt-6">
            <div className="bg-card rounded-xl border border-border p-6">
              <h2 className="text-xl font-semibold mb-4">Alert Quote Anomale</h2>
              <p className="text-muted-foreground mb-6">
                Gli alert vengono generati automaticamente quando vengono rilevate quote significativamente più alte della media. 
                Riceverai notifiche in tempo reale quando nuovi alert vengono creati.
              </p>
            </div>
            <OddsAlerts />
          </div>
        )}
      </div>
    </div>
  );
};

export default Index;
