import { useState, useEffect, useCallback } from "react";
import { getBetfairUrl } from "@/lib/utils";

interface ModalOpportunity {
  eventTime: string;
  sport: string;
  eventName: string;
  league: string;
  market: string;
  scommessa: string;
  bookmaker: string;
  quotaBook: number;
  exchange: string;
  quotaExchange: number;
  isBookVsBook: boolean;
  volumeExchange?: number;
  marketId?: string;
  eventId?: string;
  bookmakerUrl?: string;
}

export interface SingolaBPData {
  mercato: string;
  competizione: string;
  evento: string;
  dataEvento: string;
  quota: number;
  quotaBanca: number;
  layStake: number;
  totalStake: number;
  stake: number;
  commissionRate: number;
  tipoBonus: string;
  bonus: number;
  rimborsoAmount: number;
  bookmakerPunta: string;
  bookmakerUrl: string;
  exchangeUrl: string;
  exchange: string;
}

interface Props {
  opp: ModalOpportunity;
  commission: number;
  onClose: () => void;
  onInviaBP?: (data: SingolaBPData) => void;
  initialBonus?: number;
  initialStake?: number;
  initialFreeBet?: boolean;
  initialRimborso?: boolean;
}

const BOOKMAKER_URLS: Record<string, string> = {
  "bet365": "https://www.bet365.it",
  "betfair": "https://www.betfair.it",
  "betflag": "https://www.betflag.it",
  "betsson": "https://www.betsson.it",
  "bwin": "https://sports.bwin.it",
  "888sport": "https://www.888sport.it",
  "eurobet": "https://www.eurobet.it",
  "goldbet": "https://www.goldbet.it",
  "lottomatica": "https://www.lottomatica.it/scommesse/sport/",
  "netwin": "https://www.netwin.it",
  "planetwin365": "https://www.planetwin365.it",
  "sisal": "https://www.sisal.it",
  "snai": "https://www.snai.it",
  "william": "https://sports.williamhill.it",
  "admiral": "https://www.admiralbet.it",
  "leovegas": "https://www.leovegas.it",
  "stanleybet": "https://www.stanleybet.it",
  "gioco digitale": "https://www.giocodigitale.it",
  "dazn": "https://bet.dazn.com",
  "domusbet": "https://www.domusbet.it",
  "netbet": "https://www.netbet.it",
};

function getUrl(name: string) {
  const l = name.toLowerCase();
  for (const [k, v] of Object.entries(BOOKMAKER_URLS)) if (l.includes(k)) return v;
  return "#";
}

function getDisplayDomain(name: string): string {
  const url = getUrl(name);
  if (url === "#") return name;
  const domain = url.replace("https://www.", "").replace("https://", "").replace("http://", "");
  return domain.charAt(0).toUpperCase() + domain.slice(1);
}


function formatDt(iso: string) {
  try {
    const d = new Date(iso);
    const dd = d.getDate().toString().padStart(2, "0");
    const mm = (d.getMonth() + 1).toString().padStart(2, "0");
    const yyyy = d.getFullYear();
    const hh = d.getHours().toString().padStart(2, "0");
    const min = d.getMinutes().toString().padStart(2, "0");
    return `${dd}/${mm}/${yyyy} ${hh}:${min}`;
  } catch { return iso; }
}

function sportEmoji(s: string) {
  if (s === "calcio") return "⚽";
  if (s === "tennis") return "🎾";
  if (s === "basket") return "🏀";
  return "🏅";
}

function fmtIt(n: number, decimals = 2): string {
  return n.toLocaleString("it-IT", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

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

function matchCompetizione(league: string): string {
  const lower = league.toLowerCase();
  for (const comp of BETPROFIT_COMPETITIONS) {
    const key = comp.toLowerCase().replace(/\s*\(.*\)/, "").trim();
    if (lower.includes(key) || key.includes(lower)) return comp;
  }
  return league; // fallback: nome reale della lega
}

export function PuntaBancaModal({
  opp, commission, onClose, onInviaBP,
  initialBonus = 0, initialStake = 0, initialFreeBet = false, initialRimborso = false,
}: Props) {
  const [stake, setStake] = useState(initialStake);
  const [bonus, setBonus] = useState(initialBonus);
  const [commissionRate, setCommissionRate] = useState(commission);
  const [freeBet, setFreeBet] = useState(initialFreeBet);
  const [rimborso, setRimborso] = useState(initialRimborso);
  const [qPunta, setQPunta] = useState(opp.quotaBook);
  const [qBanca, setQBanca] = useState(opp.quotaExchange);
  const [rawQPunta, setRawQPunta] = useState(opp.quotaBook.toFixed(2));
  const [rawQBanca, setRawQBanca] = useState(opp.quotaExchange.toFixed(2));

  useEffect(() => {
    setQPunta(opp.quotaBook);
    setQBanca(opp.quotaExchange);
    setRawQPunta(opp.quotaBook.toFixed(2));
    setRawQBanca(opp.quotaExchange.toFixed(2));
    setFreeBet(initialFreeBet);
    setRimborso(initialRimborso);
    setBonus(initialBonus);
    setStake(initialStake);
    setCommissionRate(commission);
  }, [opp, initialBonus, initialStake, initialFreeBet, initialRimborso, commission]);

  useEffect(() => { setRawQPunta(qPunta.toFixed(2)); }, [qPunta]);
  useEffect(() => { setRawQBanca(qBanca.toFixed(2)); }, [qBanca]);

  useEffect(() => {
    const fn = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", fn);
    return () => window.removeEventListener("keydown", fn);
  }, [onClose]);


  const c = opp.isBookVsBook ? 0 : commissionRate / 100;

  const result = useCallback(() => {
    const totalStake = stake + bonus;
    if (qPunta <= 1 || qBanca <= 1 || totalStake <= 0) return null;

    const isPP = opp.isBookVsBook; // punta-punta mode

    const layStake = isPP
      ? (totalStake * qPunta) / qBanca                          // punta-punta: copri con seconda puntata
      : freeBet
        ? (totalStake * (qPunta - 1)) / (qBanca - c)
        : (totalStake * qPunta) / (qBanca - c);

    const rischio = isPP
      ? layStake                                                // punta-punta: perdi l'intera seconda puntata
      : layStake * (qBanca - 1);                               // back-lay: perdi solo il rischio lay

    const win = isPP
      ? totalStake * (qPunta - 1) - layStake                   // bet1 vince: profitto bet1 - costo bet2
      : freeBet
        ? totalStake * (qPunta - 1) - rischio
        : totalStake * qPunta - stake - rischio;

    const lose = isPP
      ? layStake * (qBanca - 1) - stake                        // bet2 vince: profitto bet2 - costo bet1
      : rimborso
        ? layStake * (1 - c)
        : freeBet
          ? layStake * (1 - c)
          : layStake * (1 - c) - stake;

    const worst = Math.min(win, lose);
    const rating = isPP
      ? 100 + (worst / totalStake) * 100                       // punta-punta: % sul primo stake
      : (layStake * (1 - c) / totalStake) * 100;              // back-lay: recovery %

    return { totalStake, layStake, rischio, win, lose, worst, rating };
  }, [stake, bonus, freeBet, rimborso, qPunta, qBanca, c, opp.isBookVsBook])();

  const vs = opp.scommessa.split(" vs ");
  const sc1 = vs[0] ?? opp.scommessa;
  const sc2 = vs[1] ?? sc1;
  const isBackLay = !opp.isBookVsBook;

  const exchangeUrl = isBackLay
    ? getBetfairUrl(opp.sport, opp.marketId, opp.eventId, opp.eventName, opp.league)
    : getUrl(opp.exchange);

  const minutesUntilMatch = (new Date(opp.eventTime).getTime() - Date.now()) / 60000;
  const isNearMatch = minutesUntilMatch > 0 && minutesUntilMatch < 60;

  const betTypeLabel = isBackLay ? "BANCATA" : "PUNTA-PUNTA";
  const flagLabels = [bonus > 0 && "BONUS", rimborso && "RIMBORSO", freeBet && "FREE BET"].filter(Boolean).join(" ");
  const headerLabel = betTypeLabel + (flagLabels ? ` ${flagLabels}` : "");

  const commitQPunta = () => {
    const v = parseFloat(rawQPunta.replace(",", "."));
    if (!isNaN(v) && v > 1) setQPunta(Math.round(v * 100) / 100);
    else setRawQPunta(qPunta.toFixed(2));
  };
  const commitQBanca = () => {
    const v = parseFloat(rawQBanca.replace(",", "."));
    if (!isNaN(v) && v > 1) setQBanca(Math.round(v * 100) / 100);
    else setRawQBanca(qBanca.toFixed(2));
  };

  const fmt2 = (n: number) => n.toFixed(2).replace(".", ",");

  // ── BetProfit helpers ──────────────────────────────────────────────────────
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

  const handleInviaBPClick = () => {
    if (!result || !onInviaBP) return;
    const tipoBonus = rimborso ? "Rimborso" : freeBet ? "FreeBet" : bonus > 0 ? "Bonus" : "Nessuno";
    onInviaBP({
      mercato: toBetprofitMercato(opp.scommessa, opp.sport),
      competizione: matchCompetizione(opp.league),
      evento: opp.eventName,
      dataEvento: opp.eventTime,
      quota: qPunta,
      quotaBanca: qBanca,
      layStake: Math.round(result.layStake * 100) / 100,
      totalStake: result.totalStake,
      stake: stake || 0,
      commissionRate,
      tipoBonus,
      bonus: bonus > 0 ? bonus : 0,
      rimborsoAmount: rimborso ? result.totalStake : 0,
      bookmakerPunta: opp.bookmaker,
      bookmakerUrl: opp.bookmakerUrl || getUrl(opp.bookmaker),
      exchangeUrl,
      exchange: opp.exchange,
    });
    onClose(); // chiude il modal di calcolo, lascia visibile solo il popup intestatario
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(0,0,0,0.75)" }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white rounded-lg shadow-2xl w-[95vw] max-w-[950px] max-h-[90vh] overflow-y-auto relative">

        {/* Title bar */}
        <div className="flex items-center justify-between px-5 py-3 rounded-t-lg" style={{ backgroundColor: "#87c4e8" }}>
          <span className="font-black text-base tracking-widest uppercase" style={{ color: "#0d2035" }}>
            {isBackLay ? "Punta Banca" : "Punta Punta"}
          </span>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-full hover:bg-black/10 text-base transition-all" style={{ color: "#0d2035" }}
          >✕</button>
        </div>

        <div className="flex flex-col md:flex-row">

          {/* ── LEFT: Event Info ── */}
          <div className="md:w-[360px] shrink-0 p-6">
            <div className="border border-gray-300 rounded-lg overflow-hidden text-center text-gray-800">

              <div className="border-b border-gray-200 px-4 py-3 text-sm text-gray-500">
                Sport - {opp.sport.charAt(0).toUpperCase() + opp.sport.slice(1)} {sportEmoji(opp.sport)}
              </div>

              <div className="border-b border-gray-200 px-4 py-3 font-bold">
                {formatDt(opp.eventTime)}
              </div>

              <div className="border-b border-gray-200 px-4 py-4 font-bold text-base leading-snug">
                {opp.eventName}
              </div>

              <div className="border-b border-gray-200 px-4 py-3 text-sm text-gray-500">
                {opp.league}
              </div>

              <div className="border-b border-gray-200 px-4 py-3 text-sm">
                Bookmaker -{" "}
                <a href={opp.bookmakerUrl || getUrl(opp.bookmaker)} target="_blank" rel="noopener noreferrer" className="text-blue-600 underline">
                  {getDisplayDomain(opp.bookmaker)} ↗
                </a>{" "}→ {sc1}
              </div>

              <div className="px-4 py-3 text-sm">
                {isBackLay ? "Exchange" : "Bookmaker 2"} -{" "}
                <a href={exchangeUrl} target="_blank" rel="noopener noreferrer" className="text-blue-600 underline">
                  {getDisplayDomain(opp.exchange)}
                </a>{" "}→ {sc2}
              </div>
            </div>

            {isNearMatch && (
              <div className="mt-4 bg-amber-50 border border-amber-300 rounded-lg p-4 text-sm font-bold text-amber-800 text-center leading-relaxed">
                La partita inizia tra meno di 60 minuti, le quote potrebbero non essere allineate.
              </div>
            )}
          </div>

          {/* ── RIGHT: Calculator ── */}
          <div className="flex-1 px-6 py-6 border-t md:border-t-0 md:border-l border-gray-200 space-y-3">

            {/* Stake Book */}
            <div className="flex items-center gap-2">
              <span className="px-3 py-2 text-sm font-medium rounded w-32 text-center shrink-0 text-white" style={{ backgroundColor: "#1e2d42" }}>
                Stake Book
              </span>
              <div className="flex-1 flex items-stretch border border-blue-300 rounded overflow-hidden min-w-0 focus-within:ring-2 focus-within:ring-blue-200">
                <input
                  type="number"
                  min={0}
                  value={stake}
                  onChange={e => setStake(Math.max(0, Number(e.target.value)))}
                  onFocus={e => e.target.select()}
                  onClick={e => (e.target as HTMLInputElement).select()}
                  className="flex-1 px-3 py-2 text-sm text-gray-800 focus:outline-none min-w-0"
                />
                <span className="px-2 flex items-center text-gray-500 text-sm border-l border-blue-300">€</span>
              </div>
              <label className="flex items-center justify-center gap-1.5 text-sm font-medium shrink-0 cursor-pointer select-none px-3 py-2 rounded text-white w-32" style={{ backgroundColor: "#1e2d42" }}>
                <input
                  type="checkbox"
                  checked={freeBet}
                  onChange={e => setFreeBet(e.target.checked)}
                  className="w-4 h-4 accent-white"
                />
                Free Bet
              </label>
            </div>

            {/* Bonus Book */}
            <div className="flex items-center gap-2">
              <span className="px-3 py-2 text-sm font-medium rounded w-32 text-center shrink-0 text-white" style={{ backgroundColor: "#c8922d" }}>
                Bonus Book
              </span>
              <div className="flex-1 flex items-stretch border border-gray-300 rounded overflow-hidden min-w-0 focus-within:ring-2 focus-within:ring-amber-200">
                <input
                  type="number"
                  min={0}
                  value={bonus}
                  onChange={e => setBonus(Math.max(0, Number(e.target.value)))}
                  onFocus={e => e.target.select()}
                  onClick={e => (e.target as HTMLInputElement).select()}
                  className="flex-1 px-3 py-2 text-sm text-gray-800 focus:outline-none min-w-0"
                />
                <span className="px-2 flex items-center text-gray-500 text-sm border-l border-gray-300">€</span>
              </div>
              <label className="flex items-center justify-center gap-1.5 text-sm font-medium shrink-0 cursor-pointer select-none px-3 py-2 rounded text-white w-32" style={{ backgroundColor: "#c8922d" }}>
                <input
                  type="checkbox"
                  checked={rimborso}
                  onChange={e => setRimborso(e.target.checked)}
                  className="w-4 h-4 accent-white"
                />
                Rimborso
              </label>
            </div>

            {/* Quota Punta */}
            <div className="flex items-center gap-2">
              <span className="px-3 py-2 text-sm font-semibold rounded w-32 text-center shrink-0 whitespace-nowrap" style={{ backgroundColor: "#87c4e8", color: "#0d2035" }}>
                {isBackLay ? "Quota Punta" : "Quota Punta 1"}
              </span>
              <div className="flex-1 flex items-stretch border border-gray-300 rounded overflow-hidden min-w-0">
                <input
                  type="text"
                  value={rawQPunta}
                  onChange={e => setRawQPunta(e.target.value)}
                  onBlur={commitQPunta}
                  onKeyDown={e => { if (e.key === "Enter") commitQPunta(); }}
                  className="flex-1 px-3 py-2 text-sm text-center text-gray-800 focus:outline-none min-w-0"
                />
                <div className="flex flex-col border-l border-gray-300 shrink-0">
                  <button
                    onClick={() => setQPunta(v => Math.round((v + 0.01) * 100) / 100)}
                    className="px-2 text-[10px] hover:bg-gray-100 flex-1 leading-none py-1"
                  >▲</button>
                  <div className="h-px bg-gray-300" />
                  <button
                    onClick={() => setQPunta(v => Math.max(1.01, Math.round((v - 0.01) * 100) / 100))}
                    className="px-2 text-[10px] hover:bg-gray-100 flex-1 leading-none py-1"
                  >▼</button>
                </div>
              </div>
            </div>

            {/* Quota Banca / Quota 2 */}
            <div className="flex items-center gap-2">
              <span className="px-3 py-2 text-sm font-semibold rounded w-32 text-center shrink-0 whitespace-nowrap" style={isBackLay ? { backgroundColor: "#f4a9ba", color: "#2d0d1a" } : { backgroundColor: "#87c4e8", color: "#0d2035" }}>
                {isBackLay ? "Quota Banca" : "Quota Punta 2"}
              </span>
              <div className="flex-1 flex items-stretch border border-gray-300 rounded overflow-hidden min-w-0">
                <input
                  type="text"
                  value={rawQBanca}
                  onChange={e => setRawQBanca(e.target.value)}
                  onBlur={commitQBanca}
                  onKeyDown={e => { if (e.key === "Enter") commitQBanca(); }}
                  className="flex-1 px-3 py-2 text-sm text-center text-gray-800 focus:outline-none min-w-0"
                />
                <div className="flex flex-col border-l border-gray-300 shrink-0">
                  <button
                    onClick={() => setQBanca(v => Math.round((v + 0.01) * 100) / 100)}
                    className="px-2 text-[10px] hover:bg-gray-100 flex-1 leading-none py-1"
                  >▲</button>
                  <div className="h-px bg-gray-300" />
                  <button
                    onClick={() => setQBanca(v => Math.max(1.01, Math.round((v - 0.01) * 100) / 100))}
                    className="px-2 text-[10px] hover:bg-gray-100 flex-1 leading-none py-1"
                  >▼</button>
                </div>
              </div>
            </div>

            {/* Commissioni + INVIA AL BP — solo in back-lay */}
            {isBackLay && <div className="flex items-center gap-2">
              <span className="px-3 py-2 text-sm font-semibold rounded w-32 text-center shrink-0" style={{ backgroundColor: "#f4a9ba", color: "#2d0d1a" }}>
                Commissioni
              </span>
              <div className="flex items-stretch border border-gray-300 rounded overflow-hidden">
                <input
                  type="number"
                  min={0}
                  max={100}
                  step={0.5}
                  value={commissionRate}
                  onChange={e => setCommissionRate(Math.max(0, Math.min(100, Number(e.target.value))))}
                  onFocus={e => e.target.select()}
                  onClick={e => (e.target as HTMLInputElement).select()}
                  className="w-20 text-center px-2 py-2 text-sm text-gray-800 focus:outline-none"
                />
                <span className="px-2 flex items-center text-gray-500 text-sm border-l border-gray-300">%</span>
              </div>
              <button
                className="flex-1 py-2 text-sm font-bold rounded transition-colors text-white hover:opacity-90"
                style={{ backgroundColor: "#1e2d42" }}
                onClick={handleInviaBPClick}
              >
                INVIA AL BP
              </button>
            </div>}

            {/* INVIA AL BP — solo in punta-punta (nessuna riga commissioni) */}
            {!isBackLay && <div className="flex gap-2 pt-1">
              <button
                className="flex-1 py-2 text-sm font-bold rounded transition-colors text-white hover:opacity-90"
                style={{ backgroundColor: "#1e2d42" }}
                onClick={handleInviaBPClick}
              >
                INVIA AL BP
              </button>
            </div>}

            {/* ── Results ── */}
            <div className="rounded overflow-hidden border border-gray-200 mt-1">

              {/* Header */}
              <div className="px-4 py-2.5 text-sm font-bold tracking-wide text-center" style={{ backgroundColor: "#87c4e8", color: "#0d2035" }}>
                {result ? `${headerLabel} • RATING ${fmt2(result.rating)}%` : `${headerLabel} • RATING —`}
              </div>

              {/* Body */}
              <div className="bg-white divide-y divide-gray-100">

                {result ? (
                  <>
                    {/* Punta row */}
                    <div className="px-4 py-3 text-sm text-gray-800 text-center">
                      <span className="font-bold">Punta</span> su {getDisplayDomain(opp.bookmaker)}{" "}
                      <a
                        href={opp.bookmakerUrl || getUrl(opp.bookmaker)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 underline font-medium"
                      >
                        {fmtIt(result.totalStake)}€
                      </a>{" "}
                      a quota {fmt2(qPunta)}
                    </div>

                    {/* Banca row */}
                    <div className="px-4 py-3 text-center">
                      <a
                        href={exchangeUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={() => {
                          const amount = (Math.round(result.layStake * 100) / 100).toFixed(2);
                          navigator.clipboard.writeText(amount).catch(() => {});
                        }}
                        className="inline-block px-3 py-2 text-sm font-medium text-gray-800 underline decoration-dotted hover:text-blue-600 cursor-pointer transition-colors"
                        title={isBackLay ? "Clicca per aprire Betfair e copiare l'importo" : "Clicca per aprire il bookmaker e copiare l'importo"}
                      >
                        <span className="font-bold">{isBackLay ? "Banca" : "Punta"}</span> su {getDisplayDomain(opp.exchange)}{" "}
                        {fmtIt(result.layStake)}€ a quota {fmt2(qBanca)}{" "}
                        {isBackLay && <>(<span className="font-bold">Rischio</span>{" "}
                        {fmtIt(Math.ceil(result.rischio * 100) / 100)}€)</>}
                      </a>
                      <p className="mt-1 text-xs text-gray-400 italic">
                        📋 Cliccando il link si aprirà direttamente la scommessa e l'importo verrà copiato automaticamente negli appunti.
                      </p>
                    </div>

                    {/* Outcome */}
                    <div className={`px-4 py-3 text-center font-bold text-sm ${result.worst >= 0 ? "text-green-400" : "text-red-600"}`}>
                      {result.worst >= 0
                        ? `Guadagnerai ${fmtIt(Math.floor(result.worst * 100) / 100)}€`
                        : `Perderai ${fmtIt(Math.floor(Math.abs(result.worst) * 100) / 100)}€`
                      }
                    </div>
                  </>
                ) : (
                  <div className="px-4 py-5 text-center text-sm text-gray-400">
                    Inserisci lo stake per vedere i conteggi
                  </div>
                )}

              </div>
            </div>
          </div>
        </div>
      </div>

    </div>
  );
}
