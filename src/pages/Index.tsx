import { useState, useRef, useEffect, useMemo } from "react";
import { Navbar } from "@/components/Navbar";
import { useToast } from "@/hooks/use-toast";
import { useOddsSearch } from "@/hooks/use-odds-search";
import { OddsMatcherTable, type Opportunity } from "@/components/OddsMatcherTable";
import { supabase } from "@/integrations/supabase/client";
import { useAuth } from "@/contexts/AuthContext";

const BOOKMAKERS = [
  "888sport", "Bet365", "BetFlag Bookmaker", "Betsson", "Bwin",
  "Eurobet", "GoldBet", "Lottomatica", "NetWin",
  "Planetwin365", "Sisal", "Snai", "William Hill",
];

const EXCHANGES = [
  "Betfair Exchange", "BetFlag Exchange",
];

// Exchange dropdown includes real exchanges + all bookmakers (for punta-punta)
const EXCHANGE_OPTIONS = [
  ...EXCHANGES,
  ...BOOKMAKERS,
];

const MARKETS = [
  // Calcio 1X2
  { value: "1",        label: "1",        group: "⚽ Calcio 1X2" },
  { value: "X",        label: "X",        group: "⚽ Calcio 1X2" },
  { value: "2",        label: "2",        group: "⚽ Calcio 1X2" },
  // Calcio BTTS
  { value: "Goal",     label: "Goal",     group: "⚽ Calcio BTTS" },
  { value: "No Goal",  label: "No Goal",  group: "⚽ Calcio BTTS" },
  // Calcio O/U
  { value: "Over 0.5",  label: "Over 0.5",  group: "⚽ Calcio O/U" },
  { value: "Under 0.5", label: "Under 0.5", group: "⚽ Calcio O/U" },
  { value: "Over 1.5",  label: "Over 1.5",  group: "⚽ Calcio O/U" },
  { value: "Under 1.5", label: "Under 1.5", group: "⚽ Calcio O/U" },
  { value: "Over 2.5",  label: "Over 2.5",  group: "⚽ Calcio O/U" },
  { value: "Under 2.5", label: "Under 2.5", group: "⚽ Calcio O/U" },
  { value: "Over 3.5",  label: "Over 3.5",  group: "⚽ Calcio O/U" },
  { value: "Under 3.5", label: "Under 3.5", group: "⚽ Calcio O/U" },
  { value: "Over 4.5",  label: "Over 4.5",  group: "⚽ Calcio O/U" },
  { value: "Under 4.5", label: "Under 4.5", group: "⚽ Calcio O/U" },
  // Calcio DC
  { value: "1X", label: "1X", group: "⚽ Calcio DC" },
  { value: "X2", label: "X2", group: "⚽ Calcio DC" },
  { value: "12", label: "12", group: "⚽ Calcio DC" },
  // Tennis
  { value: "Tennis 1", label: "1", group: "🎾 Tennis" },
  { value: "Tennis 2", label: "2", group: "🎾 Tennis" },
  // Basket
  { value: "Basket 1", label: "1", group: "🏀 Basket" },
  { value: "Basket 2", label: "2", group: "🏀 Basket" },
];

const Index = () => {
  const { toast } = useToast();
  const { data: oddsData, loading: oddsLoading, error: oddsError, search: searchOdds, reset: resetOdds } = useOddsSearch();

  const [filtersOpen, setFiltersOpen] = useState(true);
  const [multiplaResetKey, setMultiplaResetKey] = useState(0);
  const [activeSubTab, setActiveSubTab] = useState("singola");
  const [multiplaSelected, setMultiplaSelected] = useState<Opportunity[]>([]);
  const { session } = useAuth();
  const [showInviaModal, setShowInviaModal] = useState(false);
  const [inviaIntestatario, setInviaIntestatario] = useState("");
  const [inviaIntestatarioBanca, setInviaIntestatarioBanca] = useState("");
  const [intestatariList, setIntestatariList] = useState<string[]>([]);
  const [intestatariLoading, setIntestatariLoading] = useState(false);
  const [inviaTag, setInviaTag] = useState("none");
  const [tagList, setTagList] = useState<string[]>([]);

  // Filter states
  const [selectedMarkets, setSelectedMarkets] = useState<string[]>([]);
  const [selectedBookmakers, setSelectedBookmakers] = useState<string[]>([]);
  const resultsRef = useRef<HTMLDivElement>(null);
  const [selectedExchanges, setSelectedExchanges] = useState<string[]>(["Betfair Exchange", "BetFlag Exchange"]);
  const [selectedSport, setSelectedSport] = useState("tutti");
  const [filtroLiquidita, setFiltroLiquidita] = useState(true);
  const [stakePunta, setStakePunta] = useState("");
  const [stakeError, setStakeError] = useState<string | null>(null);
  const [freeBet, setFreeBet] = useState(false);
  const [bonus, setBonus] = useState("");
  const [rimborso, setRimborso] = useState(false);
  const [quotaMinima, setQuotaMinima] = useState("");
  const [quotaMassima, setQuotaMassima] = useState("");
  const [partita, setPartita] = useState("");
  const [campionato, setCampionato] = useState("");
  const [commission, setCommission] = useState(4.5);

  // Multipla-specific states
  const [multiplaOpposta, setMultiplaOpposta] = useState(false);
  const [stakeMultipla, setStakeMultipla] = useState("");
  const [quotaMinimaMultipla, setQuotaMinimaMultipla] = useState("");
  const [numEventi, setNumEventi] = useState("");
  const [quotaPartitaMinima, setQuotaPartitaMinima] = useState("");
  const [quotaPartitaMassima, setQuotaPartitaMassima] = useState("");
  const [daData, setDaData] = useState("");
  const [aData, setAData] = useState("");

  // Tre Vie specific states
  const [trevieMain, setTrevieMain] = useState("");
  const [trevieSecondary, setTrevieSecondary] = useState<string[]>([]);
  const [trevieMainOpen, setTrevieMainOpen] = useState(false);
  const [trevieSecondaryOpen, setTrevieSecondaryOpen] = useState(false);
  const [trevieSecondarySearch, setTrevieSecondarySearch] = useState("");

  // Dropdown states
  const [marketsOpen, setMarketsOpen] = useState(false);
  const [bookmakerOpen, setBookmakerOpen] = useState(false);
  const [exchangeOpen, setExchangeOpen] = useState(false);
  const [bookmakerSearch, setBookmakerSearch] = useState("");
  const [exchangeSearch, setExchangeSearch] = useState("");
  const [partitaOpen, setPartitaOpen] = useState(false);
  const [campionatoOpen, setCampionatoOpen] = useState(false);

  const [allEvents, setAllEvents] = useState<string[]>([]);
  const [allLeagues, setAllLeagues] = useState<string[]>([]);

  useEffect(() => {
    const loadSuggestions = async () => {
      const cutoff = new Date(Date.now() + 20 * 60 * 1000).toISOString();
      const { data } = await supabase
        .from("live_odds")
        .select("event_name, league")
        .gt("event_time", cutoff);
      if (data) {
        setAllEvents([...new Set(data.map((r: any) => r.event_name as string).filter(Boolean))].sort());
        setAllLeagues([...new Set(data.map((r: any) => r.league as string).filter(Boolean))].sort());
      }
    };
    loadSuggestions();
  }, []);

  const partitaSuggestions = useMemo(() =>
    partita.trim().length < 3 ? [] :
    allEvents.filter(e => e.toLowerCase().includes(partita.toLowerCase())).slice(0, 8),
  [partita, allEvents]);

  const campionatoSuggestions = useMemo(() =>
    campionato.trim().length < 3 ? [] :
    allLeagues.filter(l => l.toLowerCase().includes(campionato.toLowerCase())).slice(0, 8),
  [campionato, allLeagues]);

  const handleAggiorna = () => {
    // Singola: richiede stake punta o bonus
    if (activeSubTab === "singola") {
      const stakeVal = parseFloat(stakePunta.replace(",", ".") || "0");
      const bonusVal = parseFloat(bonus.replace(",", ".") || "0");
      if (!stakeVal && !bonusVal) {
        setStakeError(`Inserisci un importo in "Stake Punta" oppure in "Bonus" per continuare.`);
        return;
      }
    }
    // Multipla: richiede stake E N° eventi >= 2
    if (activeSubTab === "multipla") {
      const stakeVal = parseFloat((stakeMultipla || "0").replace(",", "."));
      const bonusVal = parseFloat((bonus || "0").replace(",", "."));
      const nEventi = parseInt(numEventi || "0");
      if ((!stakeVal && !bonusVal) || nEventi < 2) {
        const msgs = [];
        if (!stakeVal && !bonusVal) msgs.push('"Stake Multipla" o "Bonus"');
        if (nEventi < 2) msgs.push('"N° Eventi" (minimo 2)');
        setStakeError(`Compila: ${msgs.join(" e ")}.`);
        return;
      }
    }
    // Tre Vie: richiede stake punta o bonus
    if (activeSubTab === "trevie") {
      const stakeVal = parseFloat(stakePunta.replace(",", ".") || "0");
      const bonusVal = parseFloat(bonus.replace(",", ".") || "0");
      if (!stakeVal && !bonusVal) {
        setStakeError(`Inserisci un importo in "Stake Punta" oppure in "Bonus" per continuare.`);
        return;
      }
    }
    // Best Odds: richiede almeno Partita o Mercato
    if (activeSubTab === "bestodds") {
      if (!partita.trim() && selectedMarkets.length === 0) {
        setStakeError(`Compila almeno "Partita" o "Mercato" per vedere i risultati.`);
        return;
      }
    }
    setStakeError(null);
    setFiltersOpen(false); // nascondi i filtri subito
    setMultiplaResetKey(k => k + 1); // reset selezione multipla
    searchOdds({
      sport: selectedSport,
      mercato: "tutti",
      partita,
      campionato,
    });
    setPartita(""); // resetta il campo partita dopo la ricerca
  };

  // Quando le quote arrivano, porta la tabella in cima alla viewport
  useEffect(() => {
    if (!oddsLoading && oddsData && oddsData.length > 0) {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }, [oddsLoading]);

  // Carica intestatari e tag quando si apre il modal
  useEffect(() => {
    if (!showInviaModal || !session) return;
    setIntestatariList([]);
    setInviaIntestatario("");
    setInviaIntestatarioBanca("");
    setInviaTag("none");
    setTagList([]);
    setIntestatariLoading(true);

    const PREDEFINED_TAGS = [
      "Bonus benvenuto", "Bonus personale", "Bonus ricorrente",
      "Dividi Payout", "Scommessa personale", "Surebet a 2 vie", "Surebet a 3 vie",
    ];

    Promise.all([
      supabase.functions.invoke("get-intestatari"),
      supabase.from("tags").select("nome").order("nome"),
    ]).then(([intRes, tagRes]) => {
      if (!intRes.error && Array.isArray(intRes.data)) {
        setIntestatariList(intRes.data);
        if (intRes.data.length === 1) {
          setInviaIntestatario(intRes.data[0]);
          setInviaIntestatarioBanca(intRes.data[0]);
        }
      }
      const customTags: string[] = (tagRes.data ?? []).map((t: { nome: string }) => t.nome);
      const allTags = [...new Set([...PREDEFINED_TAGS, ...customTags])];
      setTagList(allTags);
      setIntestatariLoading(false);
    });
  }, [showInviaModal, session]);

  const handlePulisci = () => {
    setStakeError(null);
    setSelectedMarkets([]);
    setSelectedBookmakers([]);
    setSelectedExchanges(["Betfair Exchange", "BetFlag Exchange"]);
    setStakePunta("");
    setBonus("");
    setQuotaMinima("");
    setQuotaMassima("");
    setPartita("");
    setCampionato("");
    setFreeBet(false);
    setRimborso(false);
    setSelectedSport("tutti");
    setMultiplaOpposta(false);
    setStakeMultipla("");
    setQuotaMinimaMultipla("");
    setNumEventi("0");
    setQuotaPartitaMinima("");
    setQuotaPartitaMassima("");
    setDaData("");
    setAData("");
    setTrevieMain("");
    setTrevieSecondary([]);
    resetOdds();
    setMultiplaResetKey(k => k + 1); // reset selezione multipla
  };

  const toggleMarket = (m: string) => {
    setSelectedMarkets(prev => prev.includes(m) ? [] : [m]);
  };

  const toggleBookmaker = (b: string) => {
    setSelectedBookmakers(prev => prev.includes(b) ? prev.filter(x => x !== b) : [...prev, b]);
  };

  const toggleExchange = (e: string) => {
    const isExchange = EXCHANGES.includes(e);
    setSelectedExchanges(prev => {
      if (prev.includes(e)) return prev.filter(x => x !== e);
      // Selezionando un exchange → rimuovi tutti i bookmaker
      // Selezionando un bookmaker → rimuovi tutti gli exchange
      const filtered = isExchange
        ? prev.filter(x => !BOOKMAKERS.includes(x))
        : prev.filter(x => !EXCHANGES.includes(x));
      return [...filtered, e];
    });
  };

  const subTabs = [
    { id: "singola", label: "SINGOLA" },
    { id: "multipla", label: "MULTIPLA" },
    { id: "trevie", label: "TRE VIE" },
    { id: "bestodds", label: "BEST ODDS" },
  ];

  return (
    <div className="min-h-screen bg-[#0d1320]">
      <Navbar />

      {/* Title Banner */}
      <div className="bg-[#0a0e1a] text-white text-center py-3 border-b border-[#1e3050]">
        <h1 className="text-3xl font-bold text-[#c8922d]" style={{ fontFamily: "'Cinzel', serif", letterSpacing: "0.15em" }}>ODDSMATCHER</h1>
      </div>

      <div className="max-w-[1600px] mx-auto px-4 py-4">
        {/* Info Bar */}
        <div className="text-white text-xs py-2 leading-relaxed mb-2">
          Le quote dei bookmaker possono differire rispetto a quelle mostrate nell'oddsmatcher. Questo accade quando si registrano flussi di denaro significativi su un evento.
        </div>
        {/* Action Buttons */}
        <div className="flex flex-wrap gap-2 mb-4">
          <button
            onClick={() => setFiltersOpen(!filtersOpen)}
            className="px-4 py-2 border border-[#c8922d] text-[#c8922d] bg-transparent rounded font-semibold text-xs sm:text-sm hover:bg-[#c8922d] hover:text-white transition-colors"
          >
            FILTRA {filtersOpen ? "▼" : "▲"}
          </button>
          <button
            onClick={handleAggiorna}
            disabled={oddsLoading}
            className="px-4 py-2 border border-[#c8922d] text-[#c8922d] bg-transparent rounded font-semibold text-xs sm:text-sm hover:bg-[#c8922d] hover:text-white transition-colors disabled:opacity-50"
          >
            {oddsLoading ? "CARICAMENTO..." : "AGGIORNA ↻"}
          </button>
          <button
            onClick={handlePulisci}
            className="px-4 py-2 bg-red-600 text-white rounded font-semibold text-xs sm:text-sm hover:bg-red-700 transition-colors"
          >
            PULISCI ✕
          </button>
          {activeSubTab === "multipla" && (() => {
            const nTarget = parseInt(numEventi || "0");
            const isReady = nTarget >= 2 && multiplaSelected.length >= nTarget;
            return (
              <button
                disabled={!isReady}
                onClick={() => setShowInviaModal(true)}
                className={`px-4 py-2 rounded font-semibold text-xs sm:text-sm transition-colors ${
                  isReady
                    ? "bg-green-600 text-white hover:bg-green-700 cursor-pointer"
                    : "bg-[#1a2535] text-slate-500 border border-[#253347] cursor-not-allowed"
                }`}
              >
                INVIA MULTIPLA ↗
              </button>
            );
          })()}
        </div>

        {/* Filters Panel */}
        {filtersOpen && (
          <div className="bg-[#152033] rounded-lg border border-[#1e3050] p-5 mb-4">
            {/* Sub-tabs */}
            <div className="flex gap-0 mb-5 border-b border-[#1e3050]">
              {subTabs.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => { setActiveSubTab(tab.id); setPartita(""); }}
                  className={`px-4 py-2 text-[13px] font-medium border-b-2 transition-colors ${
                    activeSubTab === tab.id
                      ? "border-[#c8922d] text-[#c8922d]"
                      : "border-transparent text-white hover:text-white"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Sport */}
            {activeSubTab !== "multipla" && activeSubTab !== "bestodds" && <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-3 mb-3">
              <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded w-full sm:w-[110px] text-center">Sport</span>
              <div className="flex gap-1">
                {[
                  { value: "tutti", label: "Tutti" },
                  { value: "calcio", label: "⚽ Calcio" },
                  { value: "tennis", label: "🎾 Tennis" },
                  { value: "basket", label: "🏀 Basket" },
                ].map(s => (
                  <button
                    key={s.value}
                    onClick={() => setSelectedSport(s.value)}
                    className={`px-3 py-1.5 text-sm rounded font-medium transition-colors ${
                      selectedSport === s.value
                        ? "bg-[#c8922d] text-white"
                        : "bg-[#1a2535] border border-[#253347] text-white hover:bg-[#1e2d42]"
                    }`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>}

            {/* Mercati - nascosto per tre vie (sempre 1X2) */}
            {activeSubTab !== "trevie" && <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-3 mb-3">
              <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded w-full sm:w-[110px] text-center">{activeSubTab === "bestodds" ? "Mercato" : "Mercati"}</span>
              <div className="relative w-full sm:w-auto">
                <button
                  onClick={() => { setMarketsOpen(!marketsOpen); setBookmakerOpen(false); setExchangeOpen(false); }}
                  className="border border-[#253347] rounded px-3 py-1.5 text-sm w-full sm:min-w-[200px] text-left flex items-center justify-between bg-[#1a2535]"
                >
                  <span className="text-white">
                    {selectedMarkets.length === 0
                      ? "Tutti"
                      : (() => {
                          const m = MARKETS.find(x => x.value === selectedMarkets[0]);
                          return m ? `${m.group} – ${m.label}` : selectedMarkets[0];
                        })()}
                  </span>
                  <span className="text-slate-500">▾</span>
                </button>
                {marketsOpen && (
                  <div className="absolute top-full left-0 mt-1 bg-[#1a2535] border border-[#253347] rounded shadow-lg z-50 w-full sm:w-[260px] max-h-[350px] overflow-y-auto">
                    <button
                      onClick={() => { setSelectedMarkets([]); setMarketsOpen(false); }}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-[#1e2d42] font-medium text-[#c8922d] border-b border-[#253347]"
                    >
                      Tutti (deseleziona)
                    </button>
                    {(() => {
                      const groups = Array.from(new Set(MARKETS.map(m => m.group)));
                      return groups.map(group => (
                        <div key={group}>
                          <div className="px-3 py-1 text-[11px] font-bold text-slate-400 uppercase tracking-wider bg-[#0d1320] border-b border-[#253347]">
                            {group}
                          </div>
                          {MARKETS.filter(m => m.group === group).map(m => (
                            <button
                              key={m.value}
                              onClick={() => { toggleMarket(m.value); setMarketsOpen(false); }}
                              className={`w-full text-left px-4 py-1.5 text-sm hover:bg-[#1e2d42] ${
                                selectedMarkets.includes(m.value) ? "bg-[#1e2d42] text-[#c8922d] font-medium" : "text-white"
                              }`}
                            >
                              {selectedMarkets.includes(m.value) ? "✓ " : ""}{m.label}
                            </button>
                          ))}
                        </div>
                      ));
                    })()}
                  </div>
                )}
              </div>
            </div>}

            {/* Bookmaker — nascosto per tre vie (coperto da Book 1 / Book 2/3) */}
            {activeSubTab !== "trevie" && activeSubTab !== "bestodds" && <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-3 mb-3">
              <span className="text-sm font-semibold text-[#0d2035] bg-[#87c4e8] px-3 py-1.5 rounded w-full sm:w-[110px] text-center">Bookmaker</span>
              <div className="relative w-full sm:w-auto">
                <button
                  onClick={() => { setBookmakerOpen(!bookmakerOpen); setMarketsOpen(false); setExchangeOpen(false); setBookmakerSearch(""); }}
                  className="border border-[#253347] rounded px-3 py-1.5 text-sm w-full sm:min-w-[200px] text-left flex items-center justify-between bg-[#1a2535]"
                >
                  <span className="text-white">{selectedBookmakers.length === 0 ? "Tutti" : `${selectedBookmakers.length} selezionati`}</span>
                  <span className="text-slate-500">▾</span>
                </button>
                {bookmakerOpen && (
                  <div className="absolute top-full left-0 mt-1 bg-[#1a2535] border border-[#253347] rounded shadow-lg z-50 w-full sm:w-[250px] flex flex-col max-h-[320px]">
                    {/* Search input sticky */}
                    <div className="p-2 border-b border-[#253347] shrink-0">
                      <input
                        type="text"
                        value={bookmakerSearch}
                        onChange={e => setBookmakerSearch(e.target.value)}
                        placeholder="Cerca bookmaker..."
                        autoFocus
                        className="w-full bg-[#0d1320] text-white text-sm px-2 py-1.5 rounded border border-[#253347] placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-[#87c4e8]"
                      />
                    </div>
                    <div className="overflow-y-auto">
                      <button
                        onClick={() => setSelectedBookmakers([])}
                        className="w-full text-left px-3 py-2 text-sm hover:bg-[#1e2d42] font-medium text-[#c8922d]"
                      >
                        Tutti (deseleziona)
                      </button>
                      {BOOKMAKERS.filter(b => b.toLowerCase().includes(bookmakerSearch.toLowerCase())).map(b => (
                        <button
                          key={b}
                          onClick={() => toggleBookmaker(b)}
                          className={`w-full text-left px-3 py-1.5 text-sm hover:bg-[#1e2d42] ${
                            selectedBookmakers.includes(b) ? "bg-[#1e2d42] text-[#c8922d] font-medium" : "text-white"
                          }`}
                        >
                          {b}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>}

            {/* Exchange / Bookmaker — nascosto per tre vie */}
            {activeSubTab !== "trevie" && activeSubTab !== "bestodds" && (() => {
              const hasBookInExchange = selectedExchanges.some(e => BOOKMAKERS.includes(e));
              const allExchangesSelected = EXCHANGES.every(e => selectedExchanges.includes(e));
              const allBookmakersSelected = BOOKMAKERS.every(b => selectedExchanges.includes(b));
              const toggleAllExchanges = () => {
                if (allExchangesSelected) {
                  setSelectedExchanges(prev => prev.filter(e => !EXCHANGES.includes(e)));
                } else {
                  // Seleziona tutti gli exchange → rimuovi tutti i bookmaker
                  setSelectedExchanges(prev => [...new Set([...prev.filter(x => !BOOKMAKERS.includes(x)), ...EXCHANGES])]);
                }
              };
              const toggleAllBookmakers = () => {
                if (allBookmakersSelected) {
                  setSelectedExchanges(prev => prev.filter(e => !BOOKMAKERS.includes(e)));
                } else {
                  // Seleziona tutti i bookmaker → rimuovi tutti gli exchange
                  setSelectedExchanges(prev => [...new Set([...prev.filter(x => !EXCHANGES.includes(x)), ...BOOKMAKERS])]);
                }
              };
              return (
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-3 mb-3">
              <span className={`text-sm font-semibold w-full sm:w-[110px] text-center px-3 py-1.5 rounded transition-all ${
                hasBookInExchange
                  ? "text-[#0d2035] bg-[#87c4e8]"
                  : "text-[#2d0d1a] bg-[#f4a9ba]"
              }`}>
                {hasBookInExchange ? "Bookmaker" : "Exchange"}
              </span>
              <div className="relative w-full sm:w-auto">
                <button
                  onClick={() => { setExchangeOpen(!exchangeOpen); setMarketsOpen(false); setBookmakerOpen(false); setExchangeSearch(""); }}
                  className="border border-[#253347] rounded px-3 py-1.5 text-sm w-full sm:min-w-[200px] text-left flex items-center justify-between bg-[#1a2535]"
                >
                  <span className="text-white">
                    {selectedExchanges.length === 0 ? "Nessuno" : `${selectedExchanges.length} selezionati`}
                  </span>
                  <span className="text-slate-500">▾</span>
                </button>
                {exchangeOpen && (
                  <div className="absolute top-full left-0 mt-1 bg-[#1a2535] border border-[#253347] rounded shadow-lg z-50 w-full sm:w-[280px] flex flex-col max-h-[360px]">
                    {/* Search input sticky */}
                    <div className="p-2 border-b border-[#253347] shrink-0">
                      <input
                        type="text"
                        value={exchangeSearch}
                        onChange={e => setExchangeSearch(e.target.value)}
                        placeholder="Cerca exchange / bookmaker..."
                        autoFocus
                        className="w-full bg-[#0d1320] text-white text-sm px-2 py-1.5 rounded border border-[#253347] placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-[#f4a9ba]"
                      />
                    </div>
                    <div className="overflow-y-auto">
                      <button
                        onClick={() => setSelectedExchanges([])}
                        className="w-full text-left px-3 py-2 text-sm hover:bg-[#1e2d42] font-medium text-white border-b border-[#253347]"
                      >
                        ✕ Deseleziona tutti
                      </button>
                      {/* Exchange group */}
                      {EXCHANGES.some(e => e.toLowerCase().includes(exchangeSearch.toLowerCase())) && (
                        <>
                          <div className="flex items-center justify-between px-3 py-1.5 border-b border-[#253347] bg-[#1e2d42]">
                            <span className="text-xs text-[#f4a9ba] font-semibold uppercase tracking-wide">Exchange</span>
                            <label className="flex items-center gap-1.5 text-xs text-[#f4a9ba] cursor-pointer">
                              <input type="checkbox" checked={allExchangesSelected} onChange={toggleAllExchanges} className="accent-[#f4a9ba]" />
                              Tutti
                            </label>
                          </div>
                          {EXCHANGES.filter(e => e.toLowerCase().includes(exchangeSearch.toLowerCase())).map(e => (
                            <button
                              key={e}
                              onClick={() => toggleExchange(e)}
                              className={`w-full text-left px-3 py-2 text-sm hover:bg-[#1e2d42] ${
                                selectedExchanges.includes(e) ? "bg-[#1e2d42] text-[#c8922d] font-medium" : "text-white"
                              }`}
                            >
                              {selectedExchanges.includes(e) ? "✓ " : ""}{e}
                            </button>
                          ))}
                        </>
                      )}
                      {/* Bookmaker group */}
                      {BOOKMAKERS.some(b => b.toLowerCase().includes(exchangeSearch.toLowerCase())) && (
                        <>
                          <div className="flex items-center justify-between px-3 py-1.5 border-b border-[#253347] border-t border-[#253347] bg-[#1e2d42]">
                            <span className="text-xs text-[#87c4e8] font-semibold uppercase tracking-wide">Bookmaker</span>
                            <label className="flex items-center gap-1.5 text-xs text-[#87c4e8] cursor-pointer">
                              <input type="checkbox" checked={allBookmakersSelected} onChange={toggleAllBookmakers} className="accent-[#87c4e8]" />
                              Tutti
                            </label>
                          </div>
                          {BOOKMAKERS.filter(b => b.toLowerCase().includes(exchangeSearch.toLowerCase())).map(b => (
                            <button
                              key={b}
                              onClick={() => toggleExchange(b)}
                              className={`w-full text-left px-3 py-2 text-sm hover:bg-[#1e2d42] ${
                                selectedExchanges.includes(b) ? "bg-[#1e2d42] text-[#c8922d] font-medium" : "text-white"
                              }`}
                            >
                              {selectedExchanges.includes(b) ? "✓ " : ""}{b}
                            </button>
                          ))}
                        </>
                      )}
                    </div>
                  </div>
                )}
              </div>
              {!hasBookInExchange && (
                <label className="flex items-center gap-2 text-sm text-[#2d0d1a] font-medium bg-[#f4a9ba] px-3 py-1 rounded ml-2">
                  <input
                    type="checkbox"
                    checked={filtroLiquidita}
                    onChange={(e) => setFiltroLiquidita(e.target.checked)}
                    className="accent-[#2d0d1a]"
                  />
                  Filtro Liquidit&agrave;
                </label>
              )}
            </div>
              );
            })()}

            {/* Tre Vie: Bookmaker Principale */}
            {activeSubTab === "trevie" && (
              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-3 mb-3">
                <span className="text-sm font-semibold text-[#0d2035] bg-[#87c4e8] px-3 py-1.5 rounded w-full sm:w-[110px] text-center">Book 1</span>
                <div className="relative w-full sm:w-auto">
                  <button
                    onClick={() => { setTrevieMainOpen(!trevieMainOpen); setTrevieSecondaryOpen(false); }}
                    className="border border-[#253347] rounded px-3 py-1.5 text-sm w-full sm:min-w-[200px] text-left flex items-center justify-between bg-[#1a2535]"
                  >
                    <span className="text-white">{trevieMain || "Tutti"}</span>
                    <span className="text-slate-500">▾</span>
                  </button>
                  {trevieMainOpen && (
                    <div className="absolute top-full left-0 mt-1 bg-[#1a2535] border border-[#253347] rounded shadow-lg z-50 w-full sm:w-[250px] max-h-[300px] overflow-y-auto">
                      <button
                        onClick={() => { setTrevieMain(""); setTrevieMainOpen(false); }}
                        className="w-full text-left px-3 py-2 text-sm hover:bg-[#1e2d42] font-medium text-[#c8922d]"
                      >
                        Tutti (nessun filtro)
                      </button>
                      {BOOKMAKERS.map(b => (
                        <button
                          key={b}
                          onClick={() => { setTrevieMain(b); setTrevieMainOpen(false); }}
                          className={`w-full text-left px-3 py-1.5 text-sm hover:bg-[#1e2d42] ${
                            trevieMain === b ? "bg-[#1e2d42] text-[#c8922d] font-medium" : "text-white"
                          }`}
                        >
                          {trevieMain === b ? "✓ " : ""}{b}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                {trevieMain && (
                  <button
                    onClick={() => setTrevieMain("")}
                    className="text-xs text-slate-400 hover:text-white border border-[#253347] px-2 py-1 rounded"
                  >
                    ✕
                  </button>
                )}
              </div>
            )}

            {/* Tre Vie: Bookmakers Secondari */}
            {activeSubTab === "trevie" && (
              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-3 mb-3">
                <span className="text-sm font-semibold text-[#0d2035] bg-[#87c4e8] px-3 py-1.5 rounded w-full sm:w-[110px] text-center">Book 2/3</span>
                <div className="relative w-full sm:w-auto">
                  <button
                    onClick={() => { setTrevieSecondaryOpen(!trevieSecondaryOpen); setTrevieMainOpen(false); setTrevieSecondarySearch(""); }}
                    className="border border-[#253347] rounded px-3 py-1.5 text-sm w-full sm:min-w-[200px] text-left flex items-center justify-between bg-[#1a2535]"
                  >
                    <span className="text-white">
                      {trevieSecondary.length === 0 ? "Tutti" : `${trevieSecondary.length} selezionati`}
                    </span>
                    <span className="text-slate-500">▾</span>
                  </button>
                  {trevieSecondaryOpen && (
                    <div className="absolute top-full left-0 mt-1 bg-[#1a2535] border border-[#253347] rounded shadow-lg z-50 w-full sm:w-[280px] flex flex-col max-h-[360px]">
                      <div className="p-2 border-b border-[#253347] shrink-0">
                        <input
                          type="text"
                          value={trevieSecondarySearch}
                          onChange={e => setTrevieSecondarySearch(e.target.value)}
                          placeholder="Cerca bookmaker..."
                          autoFocus
                          className="w-full bg-[#0d1320] text-white text-sm px-2 py-1.5 rounded border border-[#253347] placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-[#87c4e8]"
                        />
                      </div>
                      <div className="overflow-y-auto">
                        <button
                          onClick={() => setTrevieSecondary([])}
                          className="w-full text-left px-3 py-2 text-sm hover:bg-[#1e2d42] font-medium text-[#c8922d] border-b border-[#253347]"
                        >
                          Tutti (deseleziona)
                        </button>
                        <button
                          onClick={() => setTrevieSecondary(
                            BOOKMAKERS.filter(b => [
                              "lottomatica","goldbet","bet365","planetwin365",
                              "snai","sisal","william hill","eurobet",
                            ].some(t => b.toLowerCase().includes(t)))
                          )}
                          className="w-full text-left px-3 py-2 text-sm hover:bg-[#1e2d42] font-medium text-white border-b border-[#253347] bg-[#1e2d42]"
                        >
                          ★ Seleziona Top
                        </button>
                        {BOOKMAKERS.filter(b => b.toLowerCase().includes(trevieSecondarySearch.toLowerCase())).map(b => (
                          <button
                            key={b}
                            onClick={() => setTrevieSecondary(prev =>
                              prev.includes(b) ? prev.filter(x => x !== b) : [...prev, b]
                            )}
                            className={`w-full text-left px-3 py-1.5 text-sm hover:bg-[#1e2d42] ${
                              trevieSecondary.includes(b) ? "bg-[#1e2d42] text-[#c8922d] font-medium" : "text-white"
                            }`}
                          >
                            {trevieSecondary.includes(b) ? "✓ " : ""}{b}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Stake */}
            {activeSubTab !== "bestodds" && <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-3 mb-3">
              <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded w-full sm:w-[110px] text-center">
                {activeSubTab === "multipla" ? "Stake Multipla" : "Stake Punta"}
              </span>
              <input
                type="text"
                value={activeSubTab === "multipla" ? stakeMultipla : stakePunta}
                onChange={(e) => { activeSubTab === "multipla" ? setStakeMultipla(e.target.value) : setStakePunta(e.target.value); setStakeError(null); }}
                placeholder="0 €"
                className={`border rounded px-3 py-1.5 text-sm w-full sm:w-[200px] focus:outline-none focus:ring-2 bg-[#1a2535] text-white placeholder-slate-500 ${stakeError ? "border-red-500 focus:ring-red-500/30" : "border-[#253347] focus:ring-[#c8922d]/30"}`}
              />
              <label className="flex items-center gap-2 text-sm text-white font-medium bg-[#1e2d42] px-3 py-1 rounded cursor-pointer">
                <input
                  type="checkbox"
                  checked={freeBet}
                  onChange={(e) => { setFreeBet(e.target.checked); if (e.target.checked) setBonus(""); }}
                  className="accent-[#c8922d]"
                />
                Free Bet
              </label>
            </div>}

            {/* Bonus */}
            {activeSubTab !== "bestodds" && <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-3 mb-3">
              <span className="text-sm font-semibold text-white bg-[#c8922d] px-3 py-1.5 rounded w-full sm:w-[110px] text-center">Bonus</span>
              <input
                type="text"
                value={bonus}
                onChange={(e) => { setBonus(e.target.value); setStakeError(null); }}
                placeholder="0 €"
                disabled={freeBet}
                className={`border rounded px-3 py-1.5 text-sm w-full sm:w-[200px] focus:outline-none focus:ring-2 ${freeBet ? "border-[#253347] bg-[#0d1320] text-slate-600 cursor-not-allowed opacity-50" : stakeError ? "border-red-500 bg-[#1a2535] text-white placeholder-slate-500 focus:ring-red-500/30" : "border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 focus:ring-[#c8922d]/30"}`}
              />
              <label className="flex items-center gap-2 text-sm text-white font-medium bg-[#c8922d] px-3 py-1 rounded cursor-pointer">
                <input type="checkbox" checked={rimborso} onChange={(e) => setRimborso(e.target.checked)} className="accent-white" />
                Rimborso
              </label>
            </div>}

            {/* Errore stake vuoto */}
            {stakeError && (
              <div className="flex items-center gap-2 mb-3 px-3 py-2 bg-red-900/40 border border-red-500/60 rounded text-red-300 text-sm">
                <span className="text-base">⚠️</span>
                {stakeError}
              </div>
            )}

            {/* Quota rows - condizionali per tab */}
            {activeSubTab !== "bestodds" && (activeSubTab === "multipla" ? (
              <>
                {/* Quota Minima Multipla + N° Eventi */}
                <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-3 mb-3">
                  <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded whitespace-nowrap text-center">Quota Minima Multipla</span>
                  <input
                    type="number"
                    value={quotaMinimaMultipla}
                    onChange={(e) => setQuotaMinimaMultipla(e.target.value)}
                    step="0.01"
                    min="0"
                    placeholder="0,00"
                    className="border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-1.5 text-sm w-full sm:w-[100px] focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
                  />
                  <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded text-center">N° Eventi</span>
                  <input
                    type="number"
                    value={numEventi}
                    onChange={(e) => setNumEventi(e.target.value)}
                    min="0"
                    step="1"
                    placeholder="0"
                    className="border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-1.5 text-sm w-full sm:w-20 focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
                  />
                </div>

                {/* Quota Partita Minima / Massima */}
                <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-3 mb-3">
                  <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded w-full sm:w-[110px] text-center">Quota Partita</span>
                  <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded">Minima</span>
                  <input
                    type="number"
                    value={quotaPartitaMinima}
                    onChange={(e) => setQuotaPartitaMinima(e.target.value)}
                    step="0.01"
                    min="0"
                    placeholder="0,00"
                    className="border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-1.5 text-sm w-full sm:w-[100px] focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
                  />
                  <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded">Massima</span>
                  <input
                    type="number"
                    value={quotaPartitaMassima}
                    onChange={(e) => setQuotaPartitaMassima(e.target.value)}
                    step="0.01"
                    min="0"
                    placeholder="0,00"
                    className="border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-1.5 text-sm w-full sm:w-[100px] focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
                  />
                </div>
              </>
            ) : (
              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-3 mb-3">
                <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded w-full sm:w-[110px] text-center">Quota Minima</span>
                <input
                  type="text"
                  value={quotaMinima}
                  onChange={(e) => setQuotaMinima(e.target.value)}
                  placeholder="0,00"
                  className="border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-1.5 text-sm w-full sm:w-[100px] focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
                />
                <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded">Quota Massima</span>
                <input
                  type="text"
                  value={quotaMassima}
                  onChange={(e) => setQuotaMassima(e.target.value)}
                  placeholder="0,00"
                  className="border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-1.5 text-sm w-full sm:w-[100px] focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
                />
              </div>
            ))}

            {/* Partita */}
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-3 mb-3">
              <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded w-full sm:w-[110px] text-center">Partita</span>
              <div className="relative w-full sm:flex-1 sm:max-w-[300px]">
                <input
                  type="text"
                  value={partita}
                  onChange={(e) => { setPartita(e.target.value); setPartitaOpen(true); }}
                  onBlur={() => setTimeout(() => setPartitaOpen(false), 150)}
                  placeholder="Cerca per nome..."
                  className="w-full border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
                />
                {partitaOpen && partitaSuggestions.length > 0 && (
                  <div className="absolute top-full left-0 mt-1 w-full bg-[#1a2535] border border-[#253347] rounded shadow-lg z-50 max-h-[200px] overflow-y-auto">
                    {partitaSuggestions.map(s => (
                      <button
                        key={s}
                        onMouseDown={() => { setPartita(s); setPartitaOpen(false); }}
                        className="w-full text-left px-3 py-2 text-sm text-white hover:bg-[#1e2d42] truncate"
                      >{s}</button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Campionato */}
            {activeSubTab !== "bestodds" && <div className={`flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-3 ${activeSubTab === "multipla" ? "mb-3" : ""}`}>
              <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded w-full sm:w-[110px] text-center">Campionato</span>
              <div className="relative w-full sm:flex-1 sm:max-w-[300px]">
                <input
                  type="text"
                  value={campionato}
                  onChange={(e) => { setCampionato(e.target.value); setCampionatoOpen(true); }}
                  onBlur={() => setTimeout(() => setCampionatoOpen(false), 150)}
                  placeholder="Cerca Campionato..."
                  className="w-full border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
                />
                {campionatoOpen && campionatoSuggestions.length > 0 && (
                  <div className="absolute top-full left-0 mt-1 w-full bg-[#1a2535] border border-[#253347] rounded shadow-lg z-50 max-h-[200px] overflow-y-auto">
                    {campionatoSuggestions.map(s => (
                      <button
                        key={s}
                        onMouseDown={() => { setCampionato(s); setCampionatoOpen(false); }}
                        className="w-full text-left px-3 py-2 text-sm text-white hover:bg-[#1e2d42] truncate"
                      >{s}</button>
                    ))}
                  </div>
                )}
              </div>
            </div>}

            {/* Da data / A data - multipla e tre vie */}
            {(activeSubTab === "multipla" || activeSubTab === "trevie") && (
              <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-3">
                <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded w-full sm:w-[110px] text-center">Da data</span>
                <input
                  type="date"
                  value={daData}
                  onChange={(e) => setDaData(e.target.value)}
                  className="border border-[#253347] bg-[#1a2535] text-white rounded px-3 py-1.5 text-sm w-full sm:w-auto focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
                />
                <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded text-center">A data</span>
                <input
                  type="date"
                  value={aData}
                  onChange={(e) => setAData(e.target.value)}
                  className="border border-[#253347] bg-[#1a2535] text-white rounded px-3 py-1.5 text-sm w-full sm:w-auto focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
                />
              </div>
            )}
          </div>
        )}

        {/* Close dropdowns on outside click */}
        {(marketsOpen || bookmakerOpen || exchangeOpen || trevieMainOpen || trevieSecondaryOpen) && (
          <div
            className="fixed inset-0 z-40"
            onClick={() => { setMarketsOpen(false); setBookmakerOpen(false); setExchangeOpen(false); setTrevieMainOpen(false); setTrevieSecondaryOpen(false); }}
          />
        )}

        {/* Modale intestatario per invio multipla a betprofit */}
        {showInviaModal && (() => {
          const nTarget = parseInt(numEventi || "0");
          const bonusVal = parseFloat(bonus || "0");
          const stakeVal = parseFloat(stakeMultipla || "0");

          const toBetprofitMercato = (scommessa: string, sport: string): string => {
            const sc = scommessa.split(" vs ")[0].trim();
            if (sport === "tennis") return sc === "1" ? "Tennis 1" : sc === "2" ? "Tennis 2" : "Altro Tennis";
            if (sport === "basket") return sc === "1" ? "Basket 1" : sc === "2" ? "Basket 2" : "Altro Basket";
            const map: Record<string, string> = {
              "1": "1 Calcio", "X": "X Calcio", "2": "2 Calcio",
              "1X": "1X Calcio", "X2": "X2 Calcio", "12": "12 Calcio",
              "Goal": "Goal Calcio", "No Goal": "No Goal Calcio",
              "Over 0.5": "Over 0.5 Calcio", "Over 1.5": "Over 1.5 Calcio",
              "Over 2.5": "Over 2.5 Calcio", "Over 3.5": "Over 3.5 Calcio", "Over 4.5": "Over 4.5 Calcio",
              "Under 0.5": "Under 0.5 Calcio", "Under 1.5": "Under 1.5 Calcio",
              "Under 2.5": "Under 2.5 Calcio", "Under 3.5": "Under 3.5 Calcio", "Under 4.5": "Under 4.5 Calcio",
            };
            return map[sc] ?? "Altro Calcio";
          };

          const BETPROFIT_COMPETITIONS = [
            "Serie A (Italia)", "Premier League (Inghilterra)", "La Liga (Spagna)",
            "Bundesliga (Germania)", "Ligue 1 (Francia)", "UEFA Champions League",
            "UEFA Europa League", "UEFA Conference League", "Coppa Italia",
            "FA Cup (Inghilterra)", "Copa del Rey (Spagna)", "DFB-Pokal (Germania)",
            "Coupe de France", "Eredivisie (Olanda)", "Primeira Liga (Portogallo)",
            "Brasileirão", "Liga MX (Messico)", "MLS (USA)", "FIFA World Cup",
            "Africa Cup of Nations", "Amichevoli internazionali", "Supercoppe nazionali",
            "Qualificazioni Mondiali 2026", "Play-off Mondiali",
          ];
          const toBetprofitCompetizione = (league: string): string => {
            const lower = league.toLowerCase();
            for (const comp of BETPROFIT_COMPETITIONS) {
              const key = comp.toLowerCase().replace(/\s*\(.*\)/, "").trim();
              if (lower.includes(key) || key.includes(lower)) return comp;
            }
            return league; // fallback: nome reale della lega
          };

          const handleInvia = () => {
            if (!inviaIntestatario.trim() || !inviaIntestatarioBanca.trim()) return;

            // Calcolo lay stake per ogni selezione
            const effectiveStake = bonusVal > 0 ? bonusVal : stakeVal;
            const quotaCombinata = multiplaSelected.reduce((acc, opp) => acc * opp.quotaBook, 1);
            const potentialWin = effectiveStake * quotaCombinata;
            const commRate = commission / 100;

            const savedState = {
              autoSave: true,
              selections: multiplaSelected.map(opp => ({
                evento: opp.eventName,
                competizione: toBetprofitCompetizione(opp.league),
                mercato: toBetprofitMercato(opp.scommessa, opp.sport),
                quota: opp.quotaBook,
                dataEvento: opp.eventTime,
              })),
              quotaInputs: multiplaSelected.map(opp => opp.quotaBook.toFixed(2).replace(".", ",")),
              formValues: {
                intestatario: inviaIntestatario.trim(),
                conto: "",
                stake: stakeVal || 0,
                tipoBonus: bonusVal > 0 ? "Bonus" : "Nessuno",
                bonus: bonusVal > 0 ? bonusVal : 0,
                rimborso: 0,
                percentualeBonus: 0,
                numeroMinimoSelezioni: nTarget,
                urlEvento: "",
                note: "",
                tag: inviaTag,
              },
              selectedIntestatario: inviaIntestatario.trim(),
              selectedConto: "",
              tipoBonus: bonusVal > 0 ? "Bonus" : "Nessuno",
              bookmakerPunta: multiplaSelected[0]?.bookmaker ?? "",
              intestatarioBanca: inviaIntestatarioBanca.trim(),
              bancate: [...multiplaSelected].sort((a, b) => new Date(a.eventTime).getTime() - new Date(b.eventTime).getTime()).map(opp => ({
                evento: opp.eventName,
                dataEvento: opp.eventTime,
                mercato: toBetprofitMercato(opp.scommessa, opp.sport),
                stake: potentialWin > 0
                  ? Math.round((potentialWin / (opp.quotaExchange * (1 - commRate))) * 100) / 100
                  : 0,
                quotaBanca: opp.quotaExchange,
                quotaPunta: opp.quotaBook,
                tassePercentuale: commission,
              })),
            };
            const encoded = btoa(unescape(encodeURIComponent(JSON.stringify(savedState))));
            window.open(`https://betprofit.app/puntate?import=${encoded}`, "_blank");
            setShowInviaModal(false);
            setInviaIntestatario("");
            setInviaIntestatarioBanca("");
            setInviaTag("none");
          };

          return (
            <div
              className="fixed inset-0 z-50 flex items-center justify-center"
              style={{ backgroundColor: "rgba(0,0,0,0.7)" }}
              onClick={e => { if (e.target === e.currentTarget) { setShowInviaModal(false); setInviaIntestatario(""); } }}
            >
              <div className="bg-[#152033] border border-[#1e3050] rounded-xl shadow-2xl p-6 w-[90vw] max-w-[400px]">
                <h2 className="text-white font-bold text-lg mb-4">Invia Multipla</h2>

                {intestatariLoading ? (
                  <div className="text-slate-400 text-sm py-4 text-center">Caricamento intestatari…</div>
                ) : intestatariList.length === 0 ? (
                  <div className="text-red-400 text-sm py-4 text-center">Nessun intestatario abilitato trovato</div>
                ) : (
                  <>
                    {/* Intestatario Punta */}
                    <div className="mb-4">
                      <label className="block text-xs font-semibold text-[#87c4e8] uppercase tracking-wide mb-1">
                        Intestatario Punta
                      </label>
                      <select
                        autoFocus
                        value={inviaIntestatario}
                        onChange={e => setInviaIntestatario(e.target.value)}
                        className="w-full bg-[#1a2535] border border-[#87c4e8]/40 text-white rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#87c4e8]/40"
                      >
                        {intestatariList.length > 1 && <option value="">— Seleziona —</option>}
                        {intestatariList.map(nome => (
                          <option key={nome} value={nome}>{nome}</option>
                        ))}
                      </select>
                    </div>

                    {/* Intestatario Banca */}
                    <div className="mb-4">
                      <label className="block text-xs font-semibold text-[#f4a9ba] uppercase tracking-wide mb-1">
                        Intestatario Banca
                      </label>
                      <select
                        value={inviaIntestatarioBanca}
                        onChange={e => setInviaIntestatarioBanca(e.target.value)}
                        className="w-full bg-[#1a2535] border border-[#f4a9ba]/40 text-white rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#f4a9ba]/40"
                      >
                        {intestatariList.length > 1 && <option value="">— Seleziona —</option>}
                        {intestatariList.map(nome => (
                          <option key={nome} value={nome}>{nome}</option>
                        ))}
                      </select>
                    </div>

                    {/* Tag */}
                    <div className="mb-6">
                      <label className="block text-xs font-semibold text-[#c8922d] uppercase tracking-wide mb-1">
                        Tag
                      </label>
                      <select
                        value={inviaTag}
                        onChange={e => setInviaTag(e.target.value)}
                        className="w-full bg-[#1a2535] border border-[#c8922d]/40 text-white rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c8922d]/40"
                      >
                        <option value="none">— Nessun tag —</option>
                        {tagList.map(tag => (
                          <option key={tag} value={tag}>{tag}</option>
                        ))}
                      </select>
                    </div>
                  </>
                )}

                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => { setShowInviaModal(false); setInviaIntestatario(""); setInviaIntestatarioBanca(""); setInviaTag("none"); }}
                    className="px-4 py-2 text-sm text-slate-400 hover:text-white border border-[#253347] rounded transition-colors"
                  >
                    Annulla
                  </button>
                  <button
                    onClick={handleInvia}
                    disabled={!inviaIntestatario.trim() || !inviaIntestatarioBanca.trim()}
                    className="px-5 py-2 text-sm font-bold rounded transition-colors bg-green-600 text-white hover:bg-green-700 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Invia ↗
                  </button>
                </div>
              </div>
            </div>
          );
        })()}

        {/* Results Table */}
        <div ref={resultsRef} className="bg-[#152033] rounded-lg border border-[#1e3050] overflow-hidden">
          {oddsError && (
            <div className="text-red-400 text-sm p-4">Errore: {oddsError}</div>
          )}

          <OddsMatcherTable
            data={oddsData}
            loading={oddsLoading}
            activeTab={activeSubTab}
            selectedExchanges={selectedExchanges}
            filters={{
              bookmaker: selectedBookmakers,
              stakePunta,
              quotaMinima,
              quotaMassima,
              partita,
              campionato,
              freebet: freeBet,
              rimborso,
              bonus,
              filtroLiquidita,
              stakeMultipla,
              quotaMinimaMultipla,
              numEventi,
              quotaPartitaMinima,
              quotaPartitaMassima,
              daData,
              aData,
              trevieMain,
              trevieSecondary,
              selectedMarkets,
            }}
            commission={commission}
            multiplaResetKey={multiplaResetKey}
            onMultiplaSelectedChange={setMultiplaSelected}
          />
        </div>
      </div>
    </div>
  );
};

export default Index;
