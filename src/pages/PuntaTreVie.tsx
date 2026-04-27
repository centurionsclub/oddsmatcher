import { useState } from "react";
import { Navbar } from "@/components/Navbar";

export default function PuntaTreVie() {
  const [stake1, setStake1] = useState("");
  const [bonus1, setBonus1] = useState("");
  const [rimborso1, setRimborso1] = useState(false);
  const [stakeX, setStakeX] = useState("");
  const [bonusX, setBonusX] = useState("");
  const [rimborsoX, setRimborsoX] = useState(false);
  const [stake2, setStake2] = useState("");
  const [bonus2, setBonus2] = useState("");
  const [rimborso2, setRimborso2] = useState(false);
  const [quota1, setQuota1] = useState("");
  const [quotaX, setQuotaX] = useState("");
  const [quota2, setQuota2] = useState("");
  const [result, setResult] = useState<{
    rating: number;
    result1: number;
    resultX: number;
    result2: number;
    calcStakeX: number;
    calcStake2: number;
  } | null>(null);

  const parseNum = (v: string) => parseFloat(v.replace(",", ".")) || 0;

  const handleCalcola = () => {
    const s1 = parseNum(stake1);
    const b1 = parseNum(bonus1);
    const sX = parseNum(stakeX);
    const bX = parseNum(bonusX);
    const s2 = parseNum(stake2);
    const b2 = parseNum(bonus2);
    const q1 = parseNum(quota1);
    const qX = parseNum(quotaX);
    const q2 = parseNum(quota2);

    if (q1 <= 1 || qX <= 1 || q2 <= 1) return;

    // If user provides stake1, calculate stakeX and stake2 to equalize payouts
    const mainStake = s1 > 0 ? s1 : 100;
    const totalMain = mainStake + b1;

    // Equalized payout
    const payout = totalMain * q1;
    const calcStakeX = sX > 0 ? sX : payout / qX;
    const calcStake2 = s2 > 0 ? s2 : payout / q2;

    const totalInvested = mainStake + calcStakeX + calcStake2;

    // Results for each outcome
    const result1 = (totalMain * q1) - totalInvested;
    const resultXVal = ((calcStakeX + bX) * qX) - totalInvested;
    const result2Val = ((calcStake2 + b2) * q2) - totalInvested;

    const worstCase = Math.min(result1, resultXVal, result2Val);
    const rating = 100 + (worstCase / totalInvested) * 100;

    setResult({
      rating,
      result1,
      resultX: resultXVal,
      result2: result2Val,
      calcStakeX,
      calcStake2,
    });
  };

  const handlePulisci = () => {
    setStake1(""); setBonus1(""); setRimborso1(false);
    setStakeX(""); setBonusX(""); setRimborsoX(false);
    setStake2(""); setBonus2(""); setRimborso2(false);
    setQuota1(""); setQuotaX(""); setQuota2("");
    setResult(null);
  };

  const fmt = (n: number) => n.toFixed(2).replace(".", ",");

  return (
    <div className="min-h-screen bg-[#c8922d]">
      <Navbar />
      <div className="max-w-[700px] mx-auto mt-8 px-4">
        <div className="bg-white rounded-lg shadow-lg overflow-hidden">
          <div className="bg-[#1a6b5a] text-white text-center py-4">
            <h1 className="text-xl font-bold tracking-wide">PUNTA → 3 VIE</h1>
          </div>

          <div className="p-6 space-y-4">
            {/* Stake 1 */}
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-gray-600 w-[80px] text-right">Stake 1</label>
              <input
                type="text"
                value={stake1}
                onChange={(e) => setStake1(e.target.value)}
                placeholder="0 &euro;"
                className="w-[140px] border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a6b5a]/30"
              />
              <label className="text-sm font-medium text-[#c8922d] bg-[#fdf3e0] px-2 py-1 rounded">Bonus 1</label>
              <input
                type="text"
                value={bonus1}
                onChange={(e) => setBonus1(e.target.value)}
                placeholder="0 &euro;"
                className="w-[100px] border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a6b5a]/30"
              />
              <label className="flex items-center gap-1 text-sm">
                <input type="checkbox" checked={rimborso1} onChange={(e) => setRimborso1(e.target.checked)} className="accent-[#1a6b5a]" />
                R
              </label>
            </div>

            {/* Stake X */}
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-gray-600 w-[80px] text-right">Stake X</label>
              <input
                type="text"
                value={stakeX}
                onChange={(e) => setStakeX(e.target.value)}
                placeholder="0 &euro;"
                className="w-[140px] border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a6b5a]/30"
              />
              <label className="text-sm font-medium text-[#c8922d] bg-[#fdf3e0] px-2 py-1 rounded">Bonus X</label>
              <input
                type="text"
                value={bonusX}
                onChange={(e) => setBonusX(e.target.value)}
                placeholder="0 &euro;"
                className="w-[100px] border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a6b5a]/30"
              />
              <label className="flex items-center gap-1 text-sm">
                <input type="checkbox" checked={rimborsoX} onChange={(e) => setRimborsoX(e.target.checked)} className="accent-[#1a6b5a]" />
                R
              </label>
            </div>

            {/* Stake 2 */}
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-gray-600 w-[80px] text-right">Stake 2</label>
              <input
                type="text"
                value={stake2}
                onChange={(e) => setStake2(e.target.value)}
                placeholder="0 &euro;"
                className="w-[140px] border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a6b5a]/30"
              />
              <label className="text-sm font-medium text-[#c8922d] bg-[#fdf3e0] px-2 py-1 rounded">Bonus 2</label>
              <input
                type="text"
                value={bonus2}
                onChange={(e) => setBonus2(e.target.value)}
                placeholder="0 &euro;"
                className="w-[100px] border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a6b5a]/30"
              />
              <label className="flex items-center gap-1 text-sm">
                <input type="checkbox" checked={rimborso2} onChange={(e) => setRimborso2(e.target.checked)} className="accent-[#1a6b5a]" />
                R
              </label>
            </div>

            {/* Quote */}
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-gray-600 w-[80px] text-right">Quote</label>
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">1</span>
                <input
                  type="text"
                  value={quota1}
                  onChange={(e) => setQuota1(e.target.value)}
                  placeholder="0,00"
                  className="w-[80px] border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a6b5a]/30"
                />
                <span className="text-sm font-medium">X</span>
                <input
                  type="text"
                  value={quotaX}
                  onChange={(e) => setQuotaX(e.target.value)}
                  placeholder="0,00"
                  className="w-[80px] border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a6b5a]/30"
                />
                <span className="text-sm font-medium">2</span>
                <input
                  type="text"
                  value={quota2}
                  onChange={(e) => setQuota2(e.target.value)}
                  placeholder="0,00"
                  className="w-[80px] border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a6b5a]/30"
                />
              </div>
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
            <div className="mt-4 space-y-3">
              <div className="flex items-center gap-3 border border-gray-200 rounded px-4 py-3">
                <span className="text-sm text-gray-600 w-[80px]">Rating</span>
                <span className={`text-sm font-bold ${result && result.rating >= 100 ? "text-green-600" : "text-red-600"}`}>
                  {result ? `${result.rating.toFixed(2)}%` : "0%"}
                </span>
              </div>

              <div className="flex items-center gap-3 border border-gray-200 rounded px-4 py-3">
                <span className="text-sm text-gray-600 w-[80px]">Risultato</span>
                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-1">
                    <span className="text-xs font-medium text-gray-500">1</span>
                    <span className={`text-sm font-semibold ${result && result.result1 >= 0 ? "text-green-600" : "text-red-600"}`}>
                      {result ? `${fmt(result.result1)} €` : "0,00 €"}
                    </span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="text-xs font-medium text-gray-500">X</span>
                    <span className={`text-sm font-semibold ${result && result.resultX >= 0 ? "text-green-600" : "text-red-600"}`}>
                      {result ? `${fmt(result.resultX)} €` : "0,00 €"}
                    </span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="text-xs font-medium text-gray-500">2</span>
                    <span className={`text-sm font-semibold ${result && result.result2 >= 0 ? "text-green-600" : "text-red-600"}`}>
                      {result ? `${fmt(result.result2)} €` : "0,00 €"}
                    </span>
                  </div>
                </div>
              </div>

              {result && (
                <div className="text-xs text-gray-500 mt-2">
                  Stake X calcolato: {fmt(result.calcStakeX)} € · Stake 2 calcolato: {fmt(result.calcStake2)} €
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
