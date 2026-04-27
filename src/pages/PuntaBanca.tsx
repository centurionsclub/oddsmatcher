import { useState } from "react";
import { Navbar } from "@/components/Navbar";

export default function PuntaBanca() {
  const [stakeBook, setStakeBook] = useState("");
  const [freeBet, setFreeBet] = useState(false);
  const [bonusBook, setBonusBook] = useState("");
  const [rimborso, setRimborso] = useState(false);
  const [quotaPunta, setQuotaPunta] = useState("");
  const [quotaBanca, setQuotaBanca] = useState("");
  const [commissioni, setCommissioni] = useState("4,50");
  const [result, setResult] = useState<{
    layStake: number;
    liability: number;
    profitBack: number;
    profitLay: number;
    rating: number;
  } | null>(null);

  const parseNum = (v: string) => parseFloat(v.replace(",", ".")) || 0;

  const handleCalcola = () => {
    const stake = parseNum(stakeBook);
    const bonus = parseNum(bonusBook);
    const qPunta = parseNum(quotaPunta);
    const qBanca = parseNum(quotaBanca);
    const comm = parseNum(commissioni) / 100;

    if (stake <= 0 || qPunta <= 1 || qBanca <= 1) return;

    const effectiveStake = freeBet ? 0 : stake;
    const totalBack = stake + bonus;

    let layStake: number;
    if (freeBet) {
      layStake = ((qPunta - 1) * totalBack) / (qBanca - comm);
    } else {
      layStake = (qPunta * totalBack) / (qBanca - comm);
    }

    const liability = layStake * (qBanca - 1);
    const profitBack = totalBack * (qPunta - 1) - liability;
    const profitLay = layStake * (1 - comm) - effectiveStake;

    const adjustedProfitLay = rimborso ? profitLay + bonus : profitLay;

    const rating = 100 + (Math.min(profitBack, adjustedProfitLay) / totalBack) * 100;

    setResult({
      layStake,
      liability,
      profitBack,
      profitLay: adjustedProfitLay,
      rating,
    });
  };

  const handlePulisci = () => {
    setStakeBook("");
    setBonusBook("");
    setQuotaPunta("");
    setQuotaBanca("");
    setCommissioni("4,50");
    setFreeBet(false);
    setRimborso(false);
    setResult(null);
  };

  const fmt = (n: number) => n.toFixed(2).replace(".", ",");

  return (
    <div className="min-h-screen bg-[#0d1320]">
      <Navbar />
      <div className="max-w-[700px] mx-auto mt-8 px-4">
        <div className="bg-[#152033] rounded-lg border border-[#1e3050] overflow-hidden shadow-lg">
          {/* Header */}
          <div className="bg-[#0a0e1a] text-white text-center py-4 border-b border-[#1e3050]">
            <h1 className="text-xl font-bold tracking-wide text-[#c8922d]">PUNTA → BANCA</h1>
          </div>

          <div className="p-6 space-y-4">
            {/* Stake Book */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-white w-[130px] text-center bg-[#1e2d42] px-2 py-1 rounded">Stake Book</label>
              <input
                type="text"
                value={stakeBook}
                onChange={(e) => setStakeBook(e.target.value)}
                placeholder="0 €"
                className="flex-1 border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
              />
              <label className="flex items-center gap-2 text-sm text-white">
                <input type="checkbox" checked={freeBet} onChange={(e) => setFreeBet(e.target.checked)} className="accent-[#c8922d]" />
                Free Bet
              </label>
            </div>

            {/* Bonus Book */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-white w-[130px] text-center bg-[#c8922d] px-2 py-1 rounded">Bonus Book</label>
              <input
                type="text"
                value={bonusBook}
                onChange={(e) => setBonusBook(e.target.value)}
                placeholder="0 €"
                className="flex-1 border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
              />
              <label className="flex items-center gap-2 text-sm text-white">
                <input type="checkbox" checked={rimborso} onChange={(e) => setRimborso(e.target.checked)} className="accent-[#c8922d]" />
                Rimborso
              </label>
            </div>

            {/* Quota Punta */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-white w-[130px] text-center bg-[#6b9db0] px-2 py-1 rounded">Quota Punta</label>
              <input
                type="text"
                value={quotaPunta}
                onChange={(e) => setQuotaPunta(e.target.value)}
                placeholder="0,00"
                className="flex-1 border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
              />
            </div>

            {/* Quota Banca */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-white w-[130px] text-center bg-[#c87878] px-2 py-1 rounded">Quota Banca</label>
              <input
                type="text"
                value={quotaBanca}
                onChange={(e) => setQuotaBanca(e.target.value)}
                placeholder="0,00"
                className="flex-1 border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
              />
            </div>

            {/* Commissioni */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-white w-[130px] text-center bg-[#c87878] px-2 py-1 rounded">Commissioni</label>
              <div className="flex items-center gap-1">
                <input
                  type="text"
                  value={commissioni}
                  onChange={(e) => setCommissioni(e.target.value)}
                  className="w-[80px] border border-[#253347] bg-[#1a2535] text-white rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
                />
                <span className="text-sm text-white">%</span>
              </div>
            </div>

            {/* Buttons */}
            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={handleCalcola}
                className="px-6 py-2 border border-[#c8922d] text-[#c8922d] rounded font-semibold text-sm hover:bg-[#c8922d] hover:text-white transition-colors"
              >
                CALCOLA →
              </button>
              <button
                onClick={handlePulisci}
                className="px-6 py-2 bg-red-600 text-white rounded font-semibold text-sm hover:bg-red-700 transition-colors"
              >
                PULISCI
              </button>
            </div>

            {/* Results */}
            <div className="mt-4">
              <div className="bg-[#1e2d42] text-white text-center py-3 rounded-t font-bold text-sm border border-[#253347]">
                BANCATA STANDARD
              </div>
              <div className="border border-[#253347] border-t-0 rounded-b divide-y divide-[#1e3050]">
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-white">Stake Banca</span>
                  <span className="text-sm font-semibold text-white">{result ? `${fmt(result.layStake)} €` : ""}</span>
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-white">Responsabilità</span>
                  <span className="text-sm font-semibold text-white">{result ? `${fmt(result.liability)} €` : ""}</span>
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-white">Rating</span>
                  <span className={`text-sm font-bold ${result && result.rating >= 100 ? "text-green-400" : "text-red-400"}`}>
                    {result ? `${result.rating.toFixed(2)}%` : ""}
                  </span>
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-white">Se vince Punta</span>
                  <span className={`text-sm font-semibold ${result && result.profitBack >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {result ? `${fmt(result.profitBack)} €` : ""}
                  </span>
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-white">Se vince Banca</span>
                  <span className={`text-sm font-semibold ${result && result.profitLay >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {result ? `${fmt(result.profitLay)} €` : ""}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
