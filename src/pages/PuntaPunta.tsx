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

    // Equalized counter stake: same payout regardless of outcome
    // payout1 = totalStake1 * q1
    // payout2 = stake2 * q2
    // Set payout1 = payout2: stake2 = totalStake1 * q1 / q2
    const stake2 = totalStake1 * q1 / q2;
    const totalInvested = effectiveStake1 + stake2;

    // If outcome 1 wins: profit = totalStake1 * (q1 - 1) - stake2
    const profitIf1 = totalStake1 * (q1 - 1) - stake2;
    // If outcome 2 wins: profit = stake2 * (q2 - 1) - effectiveStake1
    const profitIf2 = stake2 * (q2 - 1) - effectiveStake1;

    // Adjust for rimborso
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
    <div className="min-h-screen bg-[#c8922d]">
      <Navbar />
      <div className="max-w-[700px] mx-auto mt-8 px-4">
        <div className="bg-white rounded-lg shadow-lg overflow-hidden">
          <div className="bg-[#1a6b5a] text-white text-center py-4">
            <h1 className="text-xl font-bold tracking-wide">PUNTA → PUNTA</h1>
          </div>

          <div className="p-6 space-y-4">
            {/* Stake Punta 1 */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-gray-600 w-[130px] text-right">Stake Punta 1</label>
              <input
                type="text"
                value={stakePunta1}
                onChange={(e) => setStakePunta1(e.target.value)}
                placeholder="0 &euro;"
                className="flex-1 border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a6b5a]/30"
              />
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={freeBet} onChange={(e) => setFreeBet(e.target.checked)} className="accent-[#1a6b5a]" />
                Free Bet
              </label>
            </div>

            {/* Bonus Punta 1 */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-[#c8922d] w-[130px] text-right bg-[#fdf3e0] px-2 py-1 rounded">Bonus Punta 1</label>
              <input
                type="text"
                value={bonusPunta1}
                onChange={(e) => setBonusPunta1(e.target.value)}
                placeholder="0 &euro;"
                className="flex-1 border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a6b5a]/30"
              />
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={rimborso} onChange={(e) => setRimborso(e.target.checked)} className="accent-[#1a6b5a]" />
                Rimborso
              </label>
            </div>

            {/* Quota Punta 1 */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-[#1a6b5a] w-[130px] text-right bg-[#e8f5f1] px-2 py-1 rounded">Quota Punta 1</label>
              <input
                type="text"
                value={quotaPunta1}
                onChange={(e) => setQuotaPunta1(e.target.value)}
                placeholder="0,00"
                className="flex-1 border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a6b5a]/30"
              />
            </div>

            {/* Quota Punta 2 */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-[#1a6b5a] w-[130px] text-right bg-[#e8f5f1] px-2 py-1 rounded">Quota Punta 2</label>
              <input
                type="text"
                value={quotaPunta2}
                onChange={(e) => setQuotaPunta2(e.target.value)}
                placeholder="0,00"
                className="flex-1 border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a6b5a]/30"
              />
            </div>

            {/* Buttons */}
            <div className="flex items-center gap-3 pt-2">
              <button onClick={handleCalcola} className="px-6 py-2 border-2 border-[#1a6b5a] text-[#1a6b5a] rounded font-semibold text-sm hover:bg-[#1a6b5a] hover:text-white transition-colors">
                CALCOLA →
              </button>
              <button onClick={handlePulisci} className="px-6 py-2 bg-red-500 text-white rounded font-semibold text-sm hover:bg-red-600 transition-colors">
                PULISCI
              </button>
            </div>

            {/* Results */}
            <div className="mt-4">
              <div className="bg-[#8b8b8b] text-white text-center py-3 rounded-t font-bold text-sm">
                COPERTURA STANDARD
              </div>
              <div className="border border-gray-200 rounded-b divide-y divide-gray-200">
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-gray-600">Stake Punta 2</span>
                  <span className="text-sm font-semibold">{result ? `${fmt(result.stakePunta2)} €` : ""}</span>
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-gray-600">Investimento Totale</span>
                  <span className="text-sm font-semibold">{result ? `${fmt(result.totalInvested)} €` : ""}</span>
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-gray-600">Rating</span>
                  <span className={`text-sm font-bold ${result && result.rating >= 100 ? "text-green-600" : "text-red-600"}`}>
                    {result ? `${result.rating.toFixed(2)}%` : ""}
                  </span>
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-gray-600">Se vince Punta 1</span>
                  <span className={`text-sm font-semibold ${result && result.profitIf1 >= 0 ? "text-green-600" : "text-red-600"}`}>
                    {result ? `${fmt(result.profitIf1)} €` : ""}
                  </span>
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-gray-600">Se vince Punta 2</span>
                  <span className={`text-sm font-semibold ${result && result.profitIf2 >= 0 ? "text-green-600" : "text-red-600"}`}>
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
