import { useState, useRef, useEffect } from "react";
import { Navbar } from "@/components/Navbar";
import { useToast } from "@/hooks/use-toast";
import { useOddsSearch } from "@/hooks/use-odds-search";
import { OddsMatcherTable } from "@/components/OddsMatcherTable";

const BOOKMAKERS = [
  "888sport", "AdmiralBet", "Bet365", "Betfair Bookmaker", "BetFlag Bookmaker",
  "Betsson", "Bwin", "Codere", "DAZN Bet", "DomusBet", "E-Play24", "Eurobet",
  "Fastbet", "Gioco Digitale", "GoldBet", "LeoVegas", "Lottomatica", "NetBet",
  "NetWin", "Planetwin365", "Sisal", "Snai", "Stanleybet", "William Hill",
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
  { value: "tutti", label: "Tutti" },
  { value: "1", label: "1", group: "1X2" },
  { value: "X", label: "X", group: "1X2" },
  { value: "2", label: "2", group: "1X2" },
  { value: "Goal", label: "Goal", group: "BTTS" },
  { value: "No Goal", label: "No Goal", group: "BTTS" },
  { value: "Over 0.5", label: "Over 0.5", group: "O/U" },
  { value: "Under 0.5", label: "Under 0.5", group: "O/U" },
  { value: "Over 1.5", label: "Over 1.5", group: "O/U" },
  { value: "Under 1.5", label: "Under 1.5", group: "O/U" },
  { value: "Over 2.5", label: "Over 2.5", group: "O/U" },
  { value: "Under 2.5", label: "Under 2.5", group: "O/U" },
  { value: "Over 3.5", label: "Over 3.5", group: "O/U" },
  { value: "Under 3.5", label: "Under 3.5", group: "O/U" },
  { value: "Over 4.5", label: "Over 4.5", group: "O/U" },
  { value: "Under 4.5", label: "Under 4.5", group: "O/U" },
  { value: "1X", label: "1X", group: "DC" },
  { value: "X2", label: "X2", group: "DC" },
  { value: "12", label: "12", group: "DC" },
];

const Index = () => {
  const { toast } = useToast();
  const { data: oddsData, loading: oddsLoading, error: oddsError, search: searchOdds, reset: resetOdds } = useOddsSearch();

  const [filtersOpen, setFiltersOpen] = useState(true);
  const [activeSubTab, setActiveSubTab] = useState("singola");

  // Filter states
  const [selectedMarkets, setSelectedMarkets] = useState<string[]>([]);
  const [selectedBookmakers, setSelectedBookmakers] = useState<string[]>([]);
  const resultsRef = useRef<HTMLDivElement>(null);
  const [selectedExchanges, setSelectedExchanges] = useState<string[]>(["Betfair Exchange", "BetFlag Exchange"]);
  const [selectedSport, setSelectedSport] = useState("tutti");
  const [filtroLiquidita, setFiltroLiquidita] = useState(true);
  const [stakePunta, setStakePunta] = useState("");
  const [freeBet, setFreeBet] = useState(false);
  const [bonus, setBonus] = useState("");
  const [rimborso, setRimborso] = useState(false);
  const [quotaMinima, setQuotaMinima] = useState("");
  const [quotaMassima, setQuotaMassima] = useState("");
  const [partita, setPartita] = useState("");
  const [campionato, setCampionato] = useState("");
  const [commission, setCommission] = useState(4.5);

  // Dropdown states
  const [marketsOpen, setMarketsOpen] = useState(false);
  const [bookmakerOpen, setBookmakerOpen] = useState(false);
  const [exchangeOpen, setExchangeOpen] = useState(false);
  const [bookmakerSearch, setBookmakerSearch] = useState("");
  const [exchangeSearch, setExchangeSearch] = useState("");

  const handleAggiorna = () => {
    setFiltersOpen(false); // nascondi i filtri subito
    searchOdds({
      sport: selectedSport,
      mercato: "tutti",
      partita,
      campionato,
    });
  };

  // Quando le quote arrivano, porta la tabella in cima alla viewport
  useEffect(() => {
    if (!oddsLoading && oddsData && oddsData.length > 0) {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }, [oddsLoading]);

  const handlePulisci = () => {
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
    resetOdds();
  };

  const toggleMarket = (m: string) => {
    setSelectedMarkets(prev => prev.includes(m) ? prev.filter(x => x !== m) : [...prev, m]);
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
    { id: "bestopposite", label: "BEST OPPOSITE" },
  ];

  return (
    <div className="min-h-screen bg-[#0d1320]">
      <Navbar />

      {/* Title Banner */}
      <div className="bg-[#0a0e1a] text-white text-center py-3 border-b border-[#1e3050]">
        <h1 className="text-xl font-bold tracking-widest text-[#c8922d]" style={{ fontFamily: "'Roboto', sans-serif" }}>ODDSMATCHER</h1>
      </div>

      <div className="max-w-[1600px] mx-auto px-4 py-4">
        {/* Info Bar */}
        <div className="text-white text-xs py-2 leading-relaxed mb-2">
          Le quote dei bookmaker possono differire rispetto a quelle mostrate nell'oddsmatcher. Questo accade quando si registrano flussi di denaro significativi su un evento.
        </div>
        {/* Action Buttons */}
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setFiltersOpen(!filtersOpen)}
            className="px-4 py-2 border border-[#c8922d] text-[#c8922d] bg-transparent rounded font-semibold text-sm hover:bg-[#c8922d] hover:text-white transition-colors"
          >
            FILTRA {filtersOpen ? "▼" : "▲"}
          </button>
          <button
            onClick={handleAggiorna}
            disabled={oddsLoading}
            className="px-4 py-2 border border-[#c8922d] text-[#c8922d] bg-transparent rounded font-semibold text-sm hover:bg-[#c8922d] hover:text-white transition-colors disabled:opacity-50"
          >
            {oddsLoading ? "CARICAMENTO..." : "AGGIORNA ↻"}
          </button>
          <button
            onClick={handlePulisci}
            className="px-4 py-2 bg-red-600 text-white rounded font-semibold text-sm hover:bg-red-700 transition-colors"
          >
            PULISCI ✕
          </button>
        </div>

        {/* Filters Panel */}
        {filtersOpen && (
          <div className="bg-[#152033] rounded-lg border border-[#1e3050] p-5 mb-4">
            {/* Sub-tabs */}
            <div className="flex gap-0 mb-5 border-b border-[#1e3050]">
              {subTabs.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveSubTab(tab.id)}
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
            <div className="flex items-center gap-3 mb-3">
              <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded w-[110px] text-center">Sport</span>
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
            </div>

            {/* Mercati */}
            <div className="flex items-center gap-3 mb-3">
              <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded w-[110px] text-center">Mercati</span>
              <div className="relative">
                <button
                  onClick={() => { setMarketsOpen(!marketsOpen); setBookmakerOpen(false); setExchangeOpen(false); }}
                  className="border border-[#253347] rounded px-3 py-1.5 text-sm min-w-[200px] text-left flex items-center justify-between bg-[#1a2535]"
                >
                  <span className="text-white">{selectedMarkets.length === 0 ? "Tutti" : `${selectedMarkets.length} selezionati`}</span>
                  <span className="text-slate-500">▾</span>
                </button>
                {marketsOpen && (
                  <div className="absolute top-full left-0 mt-1 bg-[#1a2535] border border-[#253347] rounded shadow-lg z-50 w-[250px] max-h-[300px] overflow-y-auto">
                    <button
                      onClick={() => setSelectedMarkets([])}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-[#1e2d42] font-medium text-[#c8922d]"
                    >
                      Tutti (deseleziona)
                    </button>
                    {MARKETS.filter(m => m.value !== "tutti").map(m => (
                      <button
                        key={m.value}
                        onClick={() => toggleMarket(m.value)}
                        className={`w-full text-left px-3 py-1.5 text-sm hover:bg-[#1e2d42] ${
                          selectedMarkets.includes(m.value) ? "bg-[#1e2d42] text-[#c8922d] font-medium" : "text-white"
                        }`}
                      >
                        {m.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Bookmaker */}
            <div className="flex items-center gap-3 mb-3">
              <span className="text-sm font-semibold text-[#0d2035] bg-[#87c4e8] px-3 py-1.5 rounded w-[110px] text-center">Bookmaker</span>
              <div className="relative">
                <button
                  onClick={() => { setBookmakerOpen(!bookmakerOpen); setMarketsOpen(false); setExchangeOpen(false); setBookmakerSearch(""); }}
                  className="border border-[#253347] rounded px-3 py-1.5 text-sm min-w-[200px] text-left flex items-center justify-between bg-[#1a2535]"
                >
                  <span className="text-white">{selectedBookmakers.length === 0 ? "Tutti" : `${selectedBookmakers.length} selezionati`}</span>
                  <span className="text-slate-500">▾</span>
                </button>
                {bookmakerOpen && (
                  <div className="absolute top-full left-0 mt-1 bg-[#1a2535] border border-[#253347] rounded shadow-lg z-50 w-[250px] flex flex-col max-h-[320px]">
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
            </div>

            {/* Exchange / Bookmaker */}
            {(() => {
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
            <div className="flex items-center gap-3 mb-3">
              <span className={`text-sm font-semibold w-[110px] text-center px-3 py-1.5 rounded transition-all ${
                hasBookInExchange
                  ? "text-[#0d2035] bg-[#87c4e8]"
                  : "text-[#2d0d1a] bg-[#f4a9ba]"
              }`}>
                {hasBookInExchange ? "Bookmaker" : "Exchange"}
              </span>
              <div className="relative">
                <button
                  onClick={() => { setExchangeOpen(!exchangeOpen); setMarketsOpen(false); setBookmakerOpen(false); setExchangeSearch(""); }}
                  className="border border-[#253347] rounded px-3 py-1.5 text-sm min-w-[200px] text-left flex items-center justify-between bg-[#1a2535]"
                >
                  <span className="text-white">
                    {selectedExchanges.length === 0 ? "Nessuno" : `${selectedExchanges.length} selezionati`}
                  </span>
                  <span className="text-slate-500">▾</span>
                </button>
                {exchangeOpen && (
                  <div className="absolute top-full left-0 mt-1 bg-[#1a2535] border border-[#253347] rounded shadow-lg z-50 w-[280px] flex flex-col max-h-[360px]">
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

            {/* Stake Punta */}
            <div className="flex items-center gap-3 mb-3">
              <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded w-[110px] text-center">Stake Punta</span>
              <input
                type="text"
                value={stakePunta}
                onChange={(e) => setStakePunta(e.target.value)}
                placeholder="0 €"
                className="border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-1.5 text-sm w-[200px] focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
              />
              <label className="flex items-center gap-2 text-sm text-white font-medium bg-[#1e2d42] px-3 py-1 rounded">
                <input
                  type="checkbox"
                  checked={freeBet}
                  onChange={(e) => {
                    setFreeBet(e.target.checked);
                    if (e.target.checked) setBonus(""); // FreeBet esclude il bonus
                  }}
                  className="accent-[#c8922d]"
                />
                Free Bet
              </label>
            </div>

            {/* Bonus */}
            <div className="flex items-center gap-3 mb-3">
              <span className="text-sm font-semibold text-white bg-[#c8922d] px-3 py-1.5 rounded w-[110px] text-center">Bonus</span>
              <input
                type="text"
                value={bonus}
                onChange={(e) => setBonus(e.target.value)}
                placeholder="0 €"
                disabled={freeBet}
                className={`border border-[#253347] rounded px-3 py-1.5 text-sm w-[200px] focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30 ${freeBet ? "bg-[#0d1320] text-slate-600 cursor-not-allowed opacity-50" : "bg-[#1a2535] text-white placeholder-slate-500"}`}
              />
              <label className="flex items-center gap-2 text-sm text-white font-medium bg-[#c8922d] px-3 py-1 rounded">
                <input type="checkbox" checked={rimborso} onChange={(e) => setRimborso(e.target.checked)} className="accent-white" />
                Rimborso
              </label>
            </div>

            {/* Quota Minima / Massima */}
            <div className="flex items-center gap-3 mb-3">
              <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded w-[110px] text-center">Quota Minima</span>
              <input
                type="text"
                value={quotaMinima}
                onChange={(e) => setQuotaMinima(e.target.value)}
                placeholder="0,00"
                className="border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-1.5 text-sm w-[100px] focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
              />
              <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded">Quota Massima</span>
              <input
                type="text"
                value={quotaMassima}
                onChange={(e) => setQuotaMassima(e.target.value)}
                placeholder="0,00"
                className="border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-1.5 text-sm w-[100px] focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
              />
            </div>

            {/* Partita */}
            <div className="flex items-center gap-3 mb-3">
              <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded w-[110px] text-center">Partita</span>
              <input
                type="text"
                value={partita}
                onChange={(e) => setPartita(e.target.value)}
                placeholder="Cerca per nome..."
                className="border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-1.5 text-sm flex-1 max-w-[300px] focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
              />
            </div>

            {/* Campionato */}
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium text-white bg-[#1e2d42] px-3 py-1.5 rounded w-[110px] text-center">Campionato</span>
              <input
                type="text"
                value={campionato}
                onChange={(e) => setCampionato(e.target.value)}
                placeholder="Cerca Campionato..."
                className="border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-1.5 text-sm flex-1 max-w-[300px] focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
              />
            </div>
          </div>
        )}

        {/* Close dropdowns on outside click */}
        {(marketsOpen || bookmakerOpen || exchangeOpen) && (
          <div
            className="fixed inset-0 z-40"
            onClick={() => { setMarketsOpen(false); setBookmakerOpen(false); setExchangeOpen(false); }}
          />
        )}

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
            }}
            commission={commission}
          />
        </div>
      </div>
    </div>
  );
};

export default Index;
