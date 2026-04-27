import { useState } from "react";
import { Navbar } from "@/components/Navbar";

export default function PuntaPunta() {
  const [stakePunta1, setStakePunta1] = useState("");
  const [freeBet, setFreeBet] = useState(false);
  const [bonusPunta1, setBonusPunta1] = useState("");
  const [rimborso, setRimborso] = useState(false);
  const [quotaPunta1, setQuotaPunta1] = useState("");
  const [quotaPunta2, setQuotaPunta2] = useState("");
  const [result, setResult] = useState<{
    stakePunta2: number;
    totalInvested: number;
    profitIf1: number;
    profitIf2: number;
    rating: number;
  } | null>(null);

  const parseNum = (v: string) => parseFloat(v.replace(",", ".")) || 0;

  const handleCalcola = () => {
    const stake1 = parseNum(stakePunta1);
    const bonus = parseNum(bonusPunta1);
    const q1 = parseNum(quotaPunta1);
    const q2 = parseNum(quotaPunta2);

    if (stake1 <= 0 || q1 <= 1 || q2 <= 1) return;

    const totalStake1 = stake1 + bonus;
    const effectiveStake1 = freeBet ? 0 : stake1;

    const stake2 = totalStake1 * q1 / q2;
    const totalInvested = effectiveStake1 + stake2;

    const profitIf1 = totalStake1 * (q1 - 1) - stake2;
    const profitIf2 = stake2 * (q2 - 1) - effectiveStake1;

    const adjustedProfitIf2 = rimborso ? profitIf2 + bonus : profitIf2;

    const worstProfit = Math.min(profitIf1, adjustedProfitIf2);
    const rating = 100 + (worstProfit / totalStake1) * 100;

    setResult({
      stakePunta2: stake2,
      totalInvested,
      profitIf1,
      profitIf2: adjustedProfitIf2,
      rating,
    });
  };

  const handlePulisci = () => {
    setStakePunta1("");
    setBonusPunta1("");
    setQuotaPunta1("");
    setQuotaPunta2("");
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
          <div className="bg-[#0a0e1a] text-white text-center py-4 border-b border-[#1e3050]">
            <h1 className="text-xl font-bold tracking-wide text-[#c8922d]">PUNTA → PUNTA</h1>
          </div>

          <div className="p-6 space-y-4">
            {/* Stake Punta 1 */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-white w-[130px] text-center bg-[#1e2d42] px-2 py-1 rounded">Stake Punta 1</label>
              <input
                type="text"
                value={stakePunta1}
                onChange={(e) => setStakePunta1(e.target.value)}
                placeholder="0 €"
                className="flex-1 border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
              />
              <label className="flex items-center gap-2 text-sm text-white font-medium bg-[#1e2d42] px-3 py-1 rounded">
                <input type="checkbox" checked={freeBet} onChange={(e) => setFreeBet(e.target.checked)} className="accent-[#c8922d]" />
                Free Bet
              </label>
            </div>

            {/* Bonus Punta 1 */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-white w-[130px] text-center bg-[#c8922d] px-2 py-1 rounded">Bonus Punta 1</label>
              <input
                type="text"
                value={bonusPunta1}
                onChange={(e) => setBonusPunta1(e.target.value)}
                placeholder="0 €"
                className="flex-1 border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
              />
              <label className="flex items-center gap-2 text-sm text-white font-medium bg-[#c8922d] px-3 py-1 rounded">
                <input type="checkbox" checked={rimborso} onChange={(e) => setRimborso(e.target.checked)} className="accent-white" />
                Rimborso
              </label>
            </div>

            {/* Quota Punta 1 */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-white w-[130px] text-center bg-[#6b9db0] px-2 py-1 rounded">Quota Punta 1</label>
              <input
                type="text"
                value={quotaPunta1}
                onChange={(e) => setQuotaPunta1(e.target.value)}
                placeholder="0,00"
                className="flex-1 border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
              />
            </div>

            {/* Quota Punta 2 */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-white w-[130px] text-center bg-[#6b9db0] px-2 py-1 rounded">Quota Punta 2</label>
              <input
                type="text"
                value={quotaPunta2}
                onChange={(e) => setQuotaPunta2(e.target.value)}
                placeholder="0,00"
                className="flex-1 border border-[#253347] bg-[#1a2535] text-white placeholder-slate-500 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c8922d]/30"
              />
            </div>

            {/* Buttons */}
            <div className="flex items-center gap-3 pt-2">
              <button onClick={handleCalcola} className="px-6 py-2 border border-[#c8922d] text-[#c8922d] rounded font-semibold text-sm hover:bg-[#c8922d] hover:text-white transition-colors">
                CALCOLA →
              </button>
              <button onClick={handlePulisci} className="px-6 py-2 bg-red-600 text-white rounded font-semibold text-sm hover:bg-red-700 transition-colors">
                PULISCI
              </button>
            </div>

            {/* Results */}
            <div className="mt-4">
              <div className="bg-[#1e2d42] text-white text-center py-3 rounded-t font-bold text-sm border border-[#253347]">
                COPERTURA STANDARD
              </div>
              <div className="border border-[#253347] border-t-0 rounded-b divide-y divide-[#1e3050]">
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-white">Stake Punta 2</span>
                  <span className="text-sm font-semibold text-white">{result ? `${fmt(result.stakePunta2)} €` : ""}</span>
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-white">Investimento Totale</span>
                  <span className="text-sm font-semibold text-white">{result ? `${fmt(result.totalInvested)} €` : ""}</span>
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-white">Rating</span>
                  <span className={`text-sm font-bold ${result && result.rating >= 100 ? "text-green-400" : "text-red-400"}`}>
                    {result ? `${result.rating.toFixed(2)}%` : ""}
                  </span>
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-white">Se vince Punta 1</span>
                  <span className={`text-sm font-semibold ${result && result.profitIf1 >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {result ? `${fmt(result.profitIf1)} €` : ""}
                  </span>
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-white">Se vince Punta 2</span>
                  <span className={`text-sm font-semibold ${result && result.profitIf2 >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {result ? `${fmt(result.profitIf2)} €` : ""}
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
