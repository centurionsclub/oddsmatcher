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

    // Lay stake formula
    let layStake: number;
    if (freeBet) {
      // Free bet SNR: layStake = (backOdds - 1) * stake / (layOdds - commission)
      layStake = ((qPunta - 1) * totalBack) / (qBanca - comm);
    } else {
      // Normal: layStake = backOdds * stake / (layOdds - commission)
      layStake = (qPunta * totalBack) / (qBanca - comm);
    }

    const liability = layStake * (qBanca - 1);
    const profitBack = totalBack * (qPunta - 1) - liability;
    const profitLay = layStake * (1 - comm) - effectiveStake;

    // If rimborso, add bonus back on loss
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
    <div className="min-h-screen bg-[#c8922d]">
      <Navbar />
      <div className="max-w-[700px] mx-auto mt-8 px-4">
        {/* Card */}
        <div className="bg-white rounded-lg shadow-lg overflow-hidden">
          {/* Header */}
          <div className="bg-[#1a6b5a] text-white text-center py-4">
            <h1 className="text-xl font-bold tracking-wide">PUNTA → BANCA</h1>
          </div>

          <div className="p-6 space-y-4">
            {/* Stake Book */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-gray-600 w-[130px] text-right">Stake Book</label>
              <input
                type="text"
                value={stakeBook}
                onChange={(e) => setStakeBook(e.target.value)}
                placeholder="0 &euro;"
                className="flex-1 border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a6b5a]/30"
              />
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={freeBet}
                  onChange={(e) => setFreeBet(e.target.checked)}
                  className="accent-[#1a6b5a]"
                />
                Free Bet
              </label>
            </div>

            {/* Bonus Book */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-[#c8922d] w-[130px] text-right bg-[#fdf3e0] px-2 py-1 rounded">Bonus Book</label>
              <input
                type="text"
                value={bonusBook}
                onChange={(e) => setBonusBook(e.target.value)}
                placeholder="0 &euro;"
                className="flex-1 border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a6b5a]/30"
              />
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={rimborso}
                  onChange={(e) => setRimborso(e.target.checked)}
                  className="accent-[#1a6b5a]"
                />
                Rimborso
              </label>
            </div>

            {/* Quota Punta */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-[#1a6b5a] w-[130px] text-right bg-[#e8f5f1] px-2 py-1 rounded">Quota Punta</label>
              <input
                type="text"
                value={quotaPunta}
                onChange={(e) => setQuotaPunta(e.target.value)}
                placeholder="0,00"
                className="flex-1 border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a6b5a]/30"
              />
            </div>

            {/* Quota Banca */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-red-500 w-[130px] text-right bg-red-50 px-2 py-1 rounded">Quota Banca</label>
              <input
                type="text"
                value={quotaBanca}
                onChange={(e) => setQuotaBanca(e.target.value)}
                placeholder="0,00"
                className="flex-1 border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a6b5a]/30"
              />
            </div>

            {/* Commissioni */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-medium text-[#c8922d] w-[130px] text-right bg-[#fdf3e0] px-2 py-1 rounded">Commissioni</label>
              <div className="flex items-center gap-1">
                <input
                  type="text"
                  value={commissioni}
                  onChange={(e) => setCommissioni(e.target.value)}
                  className="w-[80px] border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a6b5a]/30"
                />
                <span className="text-sm text-gray-500">%</span>
              </div>
            </div>

            {/* Buttons */}
            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={handleCalcola}
                className="px-6 py-2 border-2 border-[#1a6b5a] text-[#1a6b5a] rounded font-semibold text-sm hover:bg-[#1a6b5a] hover:text-white transition-colors"
              >
                CALCOLA →
              </button>
              <button
                onClick={handlePulisci}
                className="px-6 py-2 bg-red-500 text-white rounded font-semibold text-sm hover:bg-red-600 transition-colors"
              >
                PULISCI
              </button>
            </div>

            {/* Results */}
            <div className="mt-4">
              <div className="bg-[#8b8b8b] text-white text-center py-3 rounded-t font-bold text-sm">
                BANCATA STANDARD
              </div>
              <div className="border border-gray-200 rounded-b divide-y divide-gray-200">
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-gray-600">Stake Banca</span>
                  <span className="text-sm font-semibold">{result ? `${fmt(result.layStake)} €` : ""}</span>
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-gray-600">Responsabilità</span>
                  <span className="text-sm font-semibold">{result ? `${fmt(result.liability)} €` : ""}</span>
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-gray-600">Rating</span>
                  <span className={`text-sm font-bold ${result && result.rating >= 100 ? "text-green-600" : "text-red-600"}`}>
                    {result ? `${result.rating.toFixed(2)}%` : ""}
                  </span>
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-gray-600">Se vince Punta</span>
                  <span className={`text-sm font-semibold ${result && result.profitBack >= 0 ? "text-green-600" : "text-red-600"}`}>
                    {result ? `${fmt(result.profitBack)} €` : ""}
                  </span>
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-sm text-gray-600">Se vince Banca</span>
                  <span className={`text-sm font-semibold ${result && result.profitLay >= 0 ? "text-green-600" : "text-red-600"}`}>
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
