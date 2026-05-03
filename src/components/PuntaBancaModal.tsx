import { useState, useEffect, useCallback } from "react";

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
  marketId?: string;  // Betfair market ID per link diretto
}

interface Props {
  opp: ModalOpportunity;
  commission: number;
  onClose: () => void;
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
  "lottomatica": "https://sport.lottomatica.it",
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

// Betfair Exchange deep link
// Direct market URL format: /exchange/market/?marketId=1.xxxxxxxxxx
function getBetfairUrl(_sport: string, _market: string, marketId?: string): string {
  if (!marketId) return "https://www.betfair.it/exchange/plus/";
  return `https://www.betfair.it/exchange/market/?marketId=${marketId}`;
}

function formatDt(iso: string) {
  try {
    const d = new Date(iso);
    return `${d.getDate().toString().padStart(2,"0")}/${(d.getMonth()+1).toString().padStart(2,"0")}/${d.getFullYear()}  •  ${d.getHours().toString().padStart(2,"0")}:${d.getMinutes().toString().padStart(2,"0")}`;
  } catch { return iso; }
}

function sportEmoji(s: string) {
  if (s === "calcio") return "⚽";
  if (s === "tennis") return "🎾";
  if (s === "basket") return "🏀";
  return "🏅";
}

// ─── Styled number input ────────────────────────────────────────────────────
function OddsInput({ label, value, onChange, accent, inputId }: {
  label: string; value: number; onChange: (v: number) => void; accent: string; inputId: string;
}) {
  const [raw, setRaw] = useState(value.toFixed(2));

  useEffect(() => { setRaw(value.toFixed(2)); }, [value]);

  const commit = (s: string) => {
    const v = parseFloat(s.replace(",", "."));
    if (!isNaN(v) && v > 1) { onChange(Math.round(v * 100) / 100); }
    setRaw(value.toFixed(2));
  };

  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-bold uppercase tracking-widest" style={{ color: accent }}>{label}</span>
      <div className="flex items-stretch rounded-lg overflow-hidden border" style={{ borderColor: accent + "55" }}>
        <input
          id={inputId}
          name={inputId}
          autoComplete="off"
          className="flex-1 text-center text-lg font-bold bg-[#0a1628] text-white outline-none py-2.5 w-0"
          value={raw}
          onChange={e => setRaw(e.target.value)}
          onBlur={e => commit(e.target.value)}
          onKeyDown={e => e.key === "Enter" && commit(raw)}
        />
        <div className="flex flex-col" style={{ backgroundColor: accent + "22" }}>
          <button
            className="px-2.5 flex-1 text-xs font-bold hover:opacity-80 transition-opacity"
            style={{ color: accent }}
            onClick={() => onChange(Math.round((value + 0.01) * 100) / 100)}
          >▲</button>
          <div className="h-px" style={{ backgroundColor: accent + "33" }} />
          <button
            className="px-2.5 flex-1 text-xs font-bold hover:opacity-80 transition-opacity"
            style={{ color: accent }}
            onClick={() => onChange(Math.max(1.01, Math.round((value - 0.01) * 100) / 100))}
          >▼</button>
        </div>
      </div>
    </div>
  );
}

// ─── Currency input ─────────────────────────────────────────────────────────
function EuroInput({ label, value, onChange, sub, inputId }: {
  label: string; value: number; onChange: (v: number) => void; sub?: React.ReactNode; inputId: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-bold uppercase tracking-widest text-[#8fa8c8]">{label}</span>
      <div className="flex items-stretch rounded-lg overflow-hidden border border-[#1e3a5c] bg-[#0a1628]">
        <span className="px-3 flex items-center text-[#8fa8c8] text-sm font-bold border-r border-[#1e3a5c]">€</span>
        <input
          id={inputId}
          name={inputId}
          type="number"
          min={0}
          autoComplete="off"
          className="flex-1 text-center text-lg font-bold text-white bg-transparent outline-none py-2.5"
          value={value}
          onChange={e => onChange(Math.max(0, Number(e.target.value)))}
        />
      </div>
      {sub && <div className="text-[10px] text-[#8fa8c8]">{sub}</div>}
    </div>
  );
}

// ─── Toggle chip ────────────────────────────────────────────────────────────
function Chip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="px-3 py-1 rounded-full text-[11px] font-bold transition-all border"
      style={active
        ? { backgroundColor: "#c8922d", borderColor: "#c8922d", color: "#fff" }
        : { backgroundColor: "transparent", borderColor: "#1e3a5c", color: "#8fa8c8" }
      }
    >
      {label}
    </button>
  );
}

// ─── Main modal ──────────────────────────────────────────────────────────────
export function PuntaBancaModal({ opp, commission, onClose }: Props) {
  const [stake, setStake] = useState(100);
  const [bonus, setBonus] = useState(0);
  const [freeBet, setFreeBet] = useState(false);
  const [rimborso, setRimborso] = useState(false);
  const [qPunta, setQPunta] = useState(opp.quotaBook);
  const [qBanca, setQBanca] = useState(opp.quotaExchange);

  useEffect(() => {
    setQPunta(opp.quotaBook);
    setQBanca(opp.quotaExchange);
    setFreeBet(false);
    setRimborso(false);
    setBonus(0);
  }, [opp]);

  useEffect(() => {
    const fn = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", fn);
    return () => window.removeEventListener("keydown", fn);
  }, [onClose]);

  const c = commission / 100;

  const result = useCallback(() => {
    if (qPunta <= 1 || qBanca <= 1) return null;
    const layStake = freeBet
      ? (stake * (qPunta - 1)) / (qBanca - c)
      : (stake * qPunta) / (qBanca - c);
    const rischio = layStake * (qBanca - 1);
    const win = freeBet
      ? stake * (qPunta - 1) - rischio
      : stake * (qPunta - 1) - rischio;
    const lose = rimborso
      ? layStake * (1 - c) - stake + (bonus || stake)
      : freeBet
        ? layStake * (1 - c) + bonus
        : layStake * (1 - c) - stake + bonus;
    const worst = Math.min(win, lose);
    return { layStake, rischio, win, lose, worst, rating: 100 + (worst / stake) * 100 };
  }, [stake, bonus, freeBet, rimborso, qPunta, qBanca, c])();

  const vs = opp.scommessa.split(" vs ");
  const sc1 = vs[0] ?? opp.scommessa;
  const sc2 = vs[1] ?? sc1;
  const isBackLay = !opp.isBookVsBook;

  // DEBUG temporaneo

  const fmt = (n: number) => n.toFixed(2).replace(".", ",");
  const fmtE = (n: number) => fmt(n) + " €";

  const ratingColor = !result ? "#8fa8c8"
    : result.rating >= 100 ? "#4ade80"
    : result.rating >= 98  ? "#facc15"
    : result.rating >= 95  ? "#c8922d"
    : "#f87171";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(4,9,18,0.85)", backdropFilter: "blur(6px)" }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="w-full max-w-[780px] rounded-2xl overflow-hidden shadow-2xl"
        style={{
          background: "linear-gradient(160deg, #0d1e35 0%, #081222 100%)",
          border: "1px solid #1e3a5c",
          maxHeight: "92vh",
          overflowY: "auto",
        }}
      >
        {/* ── Header ── */}
        <div
          className="flex items-center justify-between px-6 py-4"
          style={{ background: "linear-gradient(90deg, #0d4a4a 0%, #0d2035 100%)", borderBottom: "1px solid #1e3a5c" }}
        >
          <div className="flex items-center gap-3">
            <span className="text-2xl">{sportEmoji(opp.sport)}</span>
            <div>
              <div className="text-white font-black text-lg leading-tight">{opp.eventName}</div>
              <div className="text-[#87c4e8] text-xs mt-0.5">{opp.league} · {formatDt(opp.eventTime)}</div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span
              className="text-xs font-bold px-3 py-1 rounded-full"
              style={isBackLay
                ? { background: "#f4a9ba22", color: "#f4a9ba", border: "1px solid #f4a9ba44" }
                : { background: "#87c4e822", color: "#87c4e8", border: "1px solid #87c4e844" }
              }
            >
              {isBackLay ? "📘 BACK-LAY" : "📗 PUNTA-PUNTA"}
            </span>
            <button
              onClick={onClose}
              className="w-8 h-8 flex items-center justify-center rounded-full text-[#8fa8c8] hover:text-white hover:bg-white/10 transition-all text-lg"
            >✕</button>
          </div>
        </div>

        {/* ── Bookmaker vs Exchange cards ── */}
        <div className="flex items-stretch gap-0 px-6 py-5">
          {/* Bookmaker card */}
          <div className="flex-1 rounded-xl p-4" style={{ background: "#87c4e811", border: "1px solid #87c4e833" }}>
            <div className="text-[10px] font-bold uppercase tracking-widest text-[#87c4e8] mb-2">Punta su</div>
            <a
              href={getUrl(opp.bookmaker)}
              target="_blank"
              rel="noopener noreferrer"
              className="text-white font-bold text-base hover:text-[#87c4e8] transition-colors"
            >
              {opp.bookmaker} ↗
            </a>
            <div className="mt-3 flex items-center gap-2">
              <span className="text-[#8fa8c8] text-sm">Esito</span>
              <span className="px-2.5 py-0.5 rounded-full text-sm font-black text-[#0d2035] bg-[#87c4e8]">{sc1}</span>
            </div>
            <div className="mt-2 text-3xl font-black text-[#87c4e8]">{fmt(qPunta)}</div>
          </div>

          {/* Arrow */}
          <div className="flex items-center justify-center px-4 text-[#1e3a5c] text-2xl font-black select-none">→</div>

          {/* Exchange card */}
          <div className="flex-1 rounded-xl p-4" style={{ background: isBackLay ? "#f4a9ba11" : "#87c4e811", border: isBackLay ? "1px solid #f4a9ba33" : "1px solid #87c4e833" }}>
            <div className="text-[10px] font-bold uppercase tracking-widest mb-2" style={{ color: isBackLay ? "#f4a9ba" : "#87c4e8" }}>
              {isBackLay ? "Banca su" : "Punta su"}
            </div>
            <a
              href={isBackLay ? getBetfairUrl(opp.sport, opp.market, opp.marketId) : getUrl(opp.exchange)}
              target="_blank"
              rel="noopener noreferrer"
              className="text-white font-bold text-base hover:opacity-80 transition-opacity"
            >
              {opp.exchange} ↗
            </a>

            <div className="mt-3 flex items-center gap-2">
              <span className="text-[#8fa8c8] text-sm">Esito</span>
              <span className="px-2.5 py-0.5 rounded-full text-sm font-black text-[#0d2035]" style={{ backgroundColor: isBackLay ? "#f4a9ba" : "#87c4e8" }}>{sc2}</span>
            </div>
            <div className="mt-2 text-3xl font-black" style={{ color: isBackLay ? "#f4a9ba" : "#87c4e8" }}>{fmt(qBanca)}</div>
          </div>
        </div>

        {/* ── Calculator ── */}
        <div className="px-6 pb-6 space-y-5" style={{ borderTop: "1px solid #1e3a5c", paddingTop: "20px" }}>

          {/* Odds row */}
          <div className="grid grid-cols-2 gap-4">
            <OddsInput inputId="modal-quota-punta" label="Quota Punta" value={qPunta} onChange={setQPunta} accent="#87c4e8" />
            <OddsInput inputId="modal-quota-banca" label={isBackLay ? "Quota Banca" : "Quota Contro"} value={qBanca} onChange={setQBanca} accent={isBackLay ? "#f4a9ba" : "#87c4e8"} />
          </div>

          {/* Stake + bonus row */}
          <div className="grid grid-cols-2 gap-4">
            <EuroInput
              inputId="modal-stake"
              label="Stake Bookmaker"
              value={stake}
              onChange={setStake}
              sub={
                <div className="flex gap-2 mt-1">
                  <Chip label="Free Bet" active={freeBet} onClick={() => setFreeBet(v => !v)} />
                </div>
              }
            />
            <EuroInput
              inputId="modal-bonus"
              label="Bonus / Rimborso"
              value={bonus}
              onChange={setBonus}
              sub={
                <div className="flex gap-2 mt-1">
                  <Chip label="Rimborso" active={rimborso} onClick={() => setRimborso(v => !v)} />
                </div>
              }
            />
          </div>

          {/* Commission display */}
          <div className="flex items-center gap-3">
            <span className="text-[11px] font-bold uppercase tracking-widest text-[#8fa8c8]">Commissioni Exchange</span>
            <span className="ml-auto text-sm font-bold text-white bg-[#1e3a5c] px-3 py-1 rounded-lg">{commission.toFixed(2).replace(".", ",")}%</span>
          </div>

          {/* ── Result ── */}
          {result && (
            <div className="rounded-xl overflow-hidden" style={{ border: "1px solid #1e3a5c" }}>
              {/* Rating bar */}
              <div
                className="px-5 py-3 flex items-center justify-between"
                style={{ background: "linear-gradient(90deg, #0a1628 0%, #0d2035 100%)" }}
              >
                <span className="text-xs font-bold uppercase tracking-widest text-[#8fa8c8]">
                  {isBackLay ? "Bancata Standard" : "Punta-Punta"}
                </span>
                <span className="text-2xl font-black" style={{ color: ratingColor }}>
                  {fmt(result.rating)}%
                </span>
              </div>

              {/* Steps */}
              <div className="divide-y" style={{ divideColor: "#1e3a5c" }}>
                {/* Step 1: Punta */}
                <div className="flex items-center gap-4 px-5 py-3.5" style={{ background: "#87c4e808" }}>
                  <div
                    className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-black shrink-0"
                    style={{ background: "#87c4e8", color: "#0d2035" }}
                  >1</div>
                  <div className="flex-1 text-sm text-white">
                    Punta <span className="font-black text-[#87c4e8]">{fmtE(stake)}</span> su <span className="font-semibold">{opp.bookmaker}</span> a quota <span className="font-black text-[#87c4e8]">{fmt(qPunta)}</span>
                  </div>
                </div>

                {/* Step 2: Banca */}
                <div className="flex items-center gap-4 px-5 py-3.5" style={{ background: isBackLay ? "#f4a9ba08" : "#87c4e808" }}>
                  <div
                    className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-black shrink-0"
                    style={{ background: isBackLay ? "#f4a9ba" : "#87c4e8", color: "#0d2035" }}
                  >2</div>
                  <div className="flex-1 text-sm text-white">
                    {isBackLay ? "Banca" : "Punta"}{" "}
                    <span className="font-black" style={{ color: isBackLay ? "#f4a9ba" : "#87c4e8" }}>{fmtE(result.layStake)}</span>{" "}
                    su <span className="font-semibold">{opp.exchange}</span> a quota{" "}
                    <span className="font-black" style={{ color: isBackLay ? "#f4a9ba" : "#87c4e8" }}>{fmt(qBanca)}</span>
                    {isBackLay && (
                      <span className="text-[#f87171] text-xs ml-2">(Rischio: {fmtE(result.rischio)})</span>
                    )}
                  </div>
                </div>

                {/* Outcome */}
                <div
                  className="px-5 py-4 flex items-center justify-between"
                  style={{ background: result.worst >= 0 ? "#4ade8010" : "#f8717110" }}
                >
                  <span className="text-sm font-semibold" style={{ color: result.worst >= 0 ? "#4ade80" : "#f87171" }}>
                    {result.worst >= 0 ? "✓ Guadagno garantito" : "⚡ Perdita massima"}
                  </span>
                  <span
                    className="text-2xl font-black"
                    style={{ color: result.worst >= 0 ? "#4ade80" : "#f87171" }}
                  >
                    {result.worst >= 0 ? "+" : "-"}{fmtE(Math.abs(result.worst))}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Action buttons */}
          <div className="flex gap-3 pt-1">
            <button
              className="flex-1 py-3 rounded-xl text-sm font-bold transition-all"
              style={{ border: "1px solid #1e3a5c", color: "#8fa8c8", background: "transparent" }}
              onMouseEnter={e => { (e.target as HTMLElement).style.background = "#1e3a5c"; }}
              onMouseLeave={e => { (e.target as HTMLElement).style.background = "transparent"; }}
              onClick={onClose}
            >
              Chiudi
            </button>
            <button
              className="flex-1 py-3 rounded-xl text-sm font-bold text-white transition-all hover:opacity-90"
              style={{ background: "linear-gradient(90deg, #0d6e6e, #0d8080)" }}
              onClick={() => alert("Funzione in arrivo!")}
            >
              INVIA AL PT ↗
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
