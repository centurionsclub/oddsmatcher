import { useState, useEffect } from "react";
import type { SingolaBPData } from "./PuntaBancaModal";
import {
  loginBetProfit,
  fetchBPAccounts,
  fetchBPTags,
  createSingolaBet,
  createLayBet,
  type BPAccount,
} from "@/lib/betprofit-api";

interface Props {
  data: SingolaBPData;
  onClose: () => void;
}

// Sessione in memoria — persiste per la sessione del browser (non su refresh)
let _bpToken: string | null = null;
let _bpUserId: string = "";
let _bpAccounts: BPAccount[] = [];
let _bpTags: string[] = [];

export function SingolaBPModal({ data, onClose }: Props) {
  const [step, setStep] = useState<"login" | "form">(_bpToken ? "form" : "login");

  // Login state
  const [bpEmail, setBpEmail] = useState("");
  const [bpPassword, setBpPassword] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState("");

  // Form state
  const [accounts, setAccounts] = useState<BPAccount[]>(_bpAccounts);
  const [tags, setTags] = useState<string[]>(_bpTags);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [contoPunta, setContoPunta] = useState("");
  const [contoBanca, setContoBanca] = useState("");
  const [competizione, setCompetizione] = useState(data.competizione);
  const [tag, setTag] = useState("none");
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [done, setDone] = useState(false);

  // Se già autenticato, carica account
  useEffect(() => {
    if (_bpToken && accounts.length === 0) {
      loadAccounts(_bpToken);
    }
    // Pre-seleziona se c'è un solo account per tipo
    if (accounts.length === 1) {
      setContoPunta(accounts[0].conto);
      setContoBanca(accounts[0].conto);
    }
  }, []);

  useEffect(() => {
    if (accounts.length > 0 && !contoPunta) {
      // Pre-seleziona: bookmaker per punta (non exchange), exchange per banca
      const exchangeKeywords = ["exchange", "betfair", "betdaq", "smarkets", "matchbook"];
      const banca = accounts.find(a =>
        exchangeKeywords.some(k => a.conto.toLowerCase().includes(k))
      );
      const punta = accounts.find(a =>
        !exchangeKeywords.some(k => a.conto.toLowerCase().includes(k))
      );
      // Try to match by our bookmaker name
      const bookmakerName = data.bookmakerPunta.toLowerCase();
      const matched = accounts.find(a => a.conto.toLowerCase().includes(bookmakerName) || bookmakerName.includes(a.conto.toLowerCase()));
      setContoPunta(matched?.conto || punta?.conto || accounts[0]?.conto || "");
      setContoBanca(banca?.conto || accounts[0]?.conto || "");
    }
  }, [accounts]);

  const loadAccounts = async (token: string) => {
    setAccountsLoading(true);
    try {
      const [accs, tgs] = await Promise.all([
        fetchBPAccounts(token, _bpUserId),
        fetchBPTags(token, _bpUserId),
      ]);
      _bpAccounts = accs;
      _bpTags = tgs;
      setAccounts(accs);
      setTags(tgs);
    } catch {
      setLoginError("Errore nel caricamento account. Effettua nuovamente il login.");
      _bpToken = null;
      setStep("login");
    } finally {
      setAccountsLoading(false);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError("");
    setLoginLoading(true);
    try {
      const { token, userId } = await loginBetProfit(bpEmail, bpPassword);
      _bpToken = token;
      _bpUserId = userId;
      setStep("form");
      await loadAccounts(token);
    } catch (err: any) {
      setLoginError(err.message || "Errore di login");
    } finally {
      setLoginLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!_bpToken || !contoPunta || !contoBanca) return;
    setSubmitError("");
    setSubmitLoading(true);

    const intestatarioPunta = accounts.find(a => a.conto === contoPunta)?.intestatario || "";
    const tagValue = tag !== "none" ? tag : "";

    try {
      const betId = await createSingolaBet(_bpToken, _bpUserId, {
        conto: contoPunta,
        intestatario: intestatarioPunta,
        stake: data.stake || 0,
        quota: data.quota,
        evento: data.evento,
        dataEvento: data.dataEvento,
        metodo: "Punta",
        tipoBonus: data.tipoBonus,
        bonus: data.bonus || 0,
        rimborso: data.rimborsoAmount || 0,
        mercato: data.mercato,
        urlEvento: data.bookmakerUrl || "",
        competizione: competizione || data.competizione,
        tag: tagValue,
      });

      await createLayBet(_bpToken, _bpUserId, betId, {
        conto: contoBanca,
        stake: data.layStake,
        quotaBanca: data.quotaBanca,
        quotaPunta: data.quota,
        tassePercentuale: data.commissionRate,
        evento: data.evento,
        dataEvento: data.dataEvento,
        mercato: data.mercato,
      });

      setDone(true);
      setTimeout(onClose, 1800);
    } catch (err: any) {
      // Se token scaduto, forza re-login
      if (err.message?.includes("401") || err.message?.includes("JWT")) {
        _bpToken = null;
        setStep("login");
        setSubmitError("Sessione scaduta. Effettua nuovamente il login.");
      } else {
        setSubmitError(err.message || "Errore nell'invio");
      }
    } finally {
      setSubmitLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center"
      style={{ backgroundColor: "rgba(0,0,0,0.75)" }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-[#152033] border border-[#1e3050] rounded-xl shadow-2xl p-6 w-[90vw] max-w-[420px]">

        {done ? (
          <div className="py-8 text-center">
            <div className="text-4xl mb-3">✅</div>
            <p className="text-white font-bold text-lg">Singola salvata in BetProfit!</p>
            <p className="text-slate-400 text-sm mt-1">{data.evento}</p>
          </div>
        ) : step === "login" ? (
          <>
            <h2 className="text-white font-bold text-lg mb-1">Accedi a BetProfit</h2>
            <p className="text-slate-400 text-xs mb-4">Le credenziali vengono usate solo per questa sessione e non vengono salvate.</p>
            <form onSubmit={handleLogin}>
              <div className="mb-3">
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">Email BetProfit</label>
                <input
                  type="email"
                  value={bpEmail}
                  onChange={e => setBpEmail(e.target.value)}
                  required
                  autoFocus
                  placeholder="email@esempio.com"
                  className="w-full bg-[#1a2535] border border-[#253347] text-white rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c8922d]/40 placeholder-slate-500"
                />
              </div>
              <div className="mb-4">
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">Password BetProfit</label>
                <input
                  type="password"
                  value={bpPassword}
                  onChange={e => setBpPassword(e.target.value)}
                  required
                  placeholder="••••••••"
                  className="w-full bg-[#1a2535] border border-[#253347] text-white rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c8922d]/40 placeholder-slate-500"
                />
              </div>
              {loginError && <p className="text-red-400 text-xs mb-3">{loginError}</p>}
              <div className="flex gap-2 justify-end">
                <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-400 hover:text-white border border-[#253347] rounded transition-colors">
                  Annulla
                </button>
                <button type="submit" disabled={loginLoading} className="px-5 py-2 text-sm font-bold rounded bg-[#c8922d] text-white hover:bg-[#b07a24] disabled:opacity-50 transition-colors">
                  {loginLoading ? "Accesso…" : "Accedi"}
                </button>
              </div>
            </form>
          </>
        ) : (
          <>
            <h2 className="text-white font-bold text-lg mb-1">Invia Singola a BetProfit</h2>
            <p className="text-slate-400 text-xs mb-4 truncate">{data.evento} · {data.mercato}</p>

            {accountsLoading ? (
              <div className="text-slate-400 text-sm py-6 text-center">Caricamento account…</div>
            ) : accounts.length === 0 ? (
              <div className="text-red-400 text-sm py-4 text-center">Nessun account BetProfit trovato</div>
            ) : (
              <>
                <div className="mb-3">
                  <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">Competizione</label>
                  <input
                    type="text"
                    value={competizione}
                    onChange={e => setCompetizione(e.target.value)}
                    className="w-full bg-[#1a2535] border border-slate-600 text-white rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500/40 placeholder-slate-500"
                  />
                </div>

                <div className="mb-3">
                  <label className="block text-xs font-semibold text-[#87c4e8] uppercase tracking-wide mb-1">Conto Punta (Bookmaker)</label>
                  <select
                    autoFocus
                    value={contoPunta}
                    onChange={e => setContoPunta(e.target.value)}
                    className="w-full bg-[#1a2535] border border-[#87c4e8]/40 text-white rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#87c4e8]/40"
                  >
                    <option value="">— Seleziona —</option>
                    {accounts.map(a => (
                      <option key={a.conto} value={a.conto}>
                        {a.conto} ({a.intestatario}) — €{a.saldoAttuale.toFixed(2)}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="mb-3">
                  <label className="block text-xs font-semibold text-[#f4a9ba] uppercase tracking-wide mb-1">Conto Banca (Exchange)</label>
                  <select
                    value={contoBanca}
                    onChange={e => setContoBanca(e.target.value)}
                    className="w-full bg-[#1a2535] border border-[#f4a9ba]/40 text-white rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#f4a9ba]/40"
                  >
                    <option value="">— Seleziona —</option>
                    {accounts.map(a => (
                      <option key={a.conto} value={a.conto}>
                        {a.conto} ({a.intestatario})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="mb-4">
                  <label className="block text-xs font-semibold text-[#c8922d] uppercase tracking-wide mb-1">Tag</label>
                  <select
                    value={tag}
                    onChange={e => setTag(e.target.value)}
                    className="w-full bg-[#1a2535] border border-[#c8922d]/40 text-white rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#c8922d]/40"
                  >
                    <option value="none">— Nessun tag —</option>
                    {tags.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>

                {/* Riepilogo */}
                <div className="mb-4 bg-[#0f1a2e] rounded-lg px-3 py-2 text-xs text-slate-400 space-y-0.5">
                  <div className="flex justify-between"><span>Stake punta</span><span className="text-white">€{(data.stake || 0).toFixed(2)}</span></div>
                  <div className="flex justify-between"><span>Quota punta</span><span className="text-white">{data.quota.toFixed(2)}</span></div>
                  <div className="flex justify-between"><span>Lay stake</span><span className="text-white">€{data.layStake.toFixed(2)}</span></div>
                  <div className="flex justify-between"><span>Quota banca</span><span className="text-white">{data.quotaBanca.toFixed(2)}</span></div>
                  <div className="flex justify-between"><span>Commissione</span><span className="text-white">{data.commissionRate}%</span></div>
                </div>

                {submitError && <p className="text-red-400 text-xs mb-3">{submitError}</p>}

                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => { _bpToken = null; setStep("login"); }}
                    className="px-3 py-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors"
                  >
                    Cambia account
                  </button>
                  <button onClick={onClose} className="px-4 py-2 text-sm text-slate-400 hover:text-white border border-[#253347] rounded transition-colors">
                    Annulla
                  </button>
                  <button
                    onClick={handleSubmit}
                    disabled={submitLoading || !contoPunta || !contoBanca}
                    className="px-5 py-2 text-sm font-bold rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    {submitLoading ? "Invio…" : "Salva in BP ↗"}
                  </button>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
