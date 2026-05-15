const BP_URL = "https://olmkgsvzpvyherlvokmz.supabase.co";
const BP_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9sbWtnc3Z6cHZ5aGVybHZva216Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI3MDkxNzUsImV4cCI6MjA4ODI4NTE3NX0.MwS8rO67QvQGJr5221FbGgLRbEVWzusYzpEwlqJ5Cew";
const BP_SESSION_KEY = "bp_session";

export interface BPAccount {
  conto: string;
  intestatario: string;
  saldoAttuale: number;
}

interface BPSession {
  token: string;
  refreshToken: string;
  userId: string;
  expiresAt: number; // unix ms
}

function decodeJwtPayload(token: string): any {
  try {
    return JSON.parse(atob(token.split(".")[1]));
  } catch {
    return null;
  }
}

function decodeJwtUserId(token: string): string {
  return decodeJwtPayload(token)?.sub ?? "";
}

// ── Session persistence ────────────────────────────────────────────────────

export function saveBPSession(token: string, refreshToken: string): void {
  const payload = decodeJwtPayload(token);
  const expiresAt = payload?.exp ? payload.exp * 1000 : Date.now() + 3600_000;
  const session: BPSession = { token, refreshToken, userId: payload?.sub ?? "", expiresAt };
  localStorage.setItem(BP_SESSION_KEY, JSON.stringify(session));
}

export function loadBPSession(): BPSession | null {
  try {
    const raw = localStorage.getItem(BP_SESSION_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as BPSession;
  } catch {
    return null;
  }
}

export function clearBPSession(): void {
  localStorage.removeItem(BP_SESSION_KEY);
}

export async function restoreBPSession(): Promise<{ token: string; userId: string } | null> {
  const session = loadBPSession();
  if (!session) return null;

  // Token still valid (with 60s margin)
  if (session.expiresAt - Date.now() > 60_000) {
    return { token: session.token, userId: session.userId };
  }

  // Try to refresh
  try {
    const res = await fetch(`${BP_URL}/auth/v1/token?grant_type=refresh_token`, {
      method: "POST",
      headers: { "Content-Type": "application/json", apikey: BP_KEY },
      body: JSON.stringify({ refresh_token: session.refreshToken }),
    });
    if (!res.ok) { clearBPSession(); return null; }
    const data = await res.json();
    const token = data.access_token as string;
    const refreshToken = data.refresh_token as string;
    saveBPSession(token, refreshToken);
    return { token, userId: decodeJwtUserId(token) };
  } catch {
    clearBPSession();
    return null;
  }
}

// ── Auth ───────────────────────────────────────────────────────────────────

export async function loginBetProfit(email: string, password: string): Promise<{ token: string; userId: string }> {
  const res = await fetch(`${BP_URL}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: { "Content-Type": "application/json", apikey: BP_KEY },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error("Email o password BetProfit errati.");
  const data = await res.json();
  const token = data.access_token as string;
  const refreshToken = data.refresh_token as string;
  saveBPSession(token, refreshToken);
  return { token, userId: decodeJwtUserId(token) };
}

// ── Data ───────────────────────────────────────────────────────────────────

export async function fetchBPAccounts(token: string, userId: string): Promise<BPAccount[]> {
  const res = await fetch(
    `${BP_URL}/rest/v1/accounts?select=conto,intestatario,saldo_attuale&stato=eq.Abilitato&user_id=eq.${userId}&order=conto.asc`,
    { headers: { apikey: BP_KEY, Authorization: `Bearer ${token}` } }
  );
  if (!res.ok) throw new Error("Errore nel caricamento account BetProfit.");
  const data = await res.json();
  return (data as any[]).map((a) => ({
    conto: a.conto,
    intestatario: a.intestatario,
    saldoAttuale: Number(a.saldo_attuale),
  }));
}

export async function fetchBPTags(token: string, userId: string): Promise<string[]> {
  // Try with user_id filter first (matches BetProfit's own query)
  const res = await fetch(
    `${BP_URL}/rest/v1/tags?select=nome&user_id=eq.${userId}&order=nome.asc`,
    { headers: { apikey: BP_KEY, Authorization: `Bearer ${token}` } }
  );
  if (res.ok) {
    const data = await res.json() as any[];
    if (data.length > 0) return data.map((t: any) => t.nome).filter(Boolean);
  }
  // Fallback: rely on RLS via Bearer token only
  const res2 = await fetch(
    `${BP_URL}/rest/v1/tags?select=nome&order=nome.asc`,
    { headers: { apikey: BP_KEY, Authorization: `Bearer ${token}` } }
  );
  if (!res2.ok) return [];
  const data2 = await res2.json() as any[];
  return data2.map((t: any) => t.nome).filter(Boolean);
}

export async function createSingolaBet(
  token: string,
  userId: string,
  bet: {
    conto: string;
    intestatario: string;
    stake: number;
    quota: number;
    evento: string;
    dataEvento: string;
    metodo: "Punta" | "Banca";
    tipoBonus: string;
    bonus: number;
    rimborso: number;
    mercato: string;
    urlEvento: string;
    competizione: string;
    tag: string;
  }
): Promise<string> {
  const res = await fetch(`${BP_URL}/rest/v1/bets`, {
    method: "POST",
    headers: {
      apikey: BP_KEY,
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      Prefer: "return=representation",
    },
    body: JSON.stringify({
      tipo: "Singola",
      conto: bet.conto,
      intestatario: bet.intestatario,
      stake: bet.stake,
      quota: bet.quota,
      quota_punta: bet.quota,
      evento: bet.evento,
      data_evento: bet.dataEvento,
      metodo: bet.metodo,
      tipo_bonus: bet.tipoBonus !== "Nessuno" ? bet.tipoBonus : null,
      bonus: bet.bonus > 0 ? bet.bonus : null,
      rimborso: bet.rimborso > 0 ? bet.rimborso : null,
      stato: "In Corso",
      mercato: bet.mercato,
      url_evento: bet.urlEvento || null,
      competizione: bet.competizione || null,
      tag: bet.tag || null,
      wallet_id: null,
      note: null,
      nome_gioco: null,
      percentuale_bonus: null,
      numero_minimo_selezioni: null,
      quota_combinata: null,
      vincita_potenziale: Math.round(bet.stake * bet.quota * 100) / 100,
      user_id: userId,
    }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Errore creazione scommessa: ${err}`);
  }
  const rows = await res.json();
  return rows[0].id as string;
}

export async function createLayBet(
  token: string,
  userId: string,
  parentBetId: string,
  lay: {
    conto: string;
    stake: number;
    quotaBanca: number;
    quotaPunta: number;
    tassePercentuale: number;
    evento: string;
    dataEvento: string;
    mercato: string;
    competizione: string;
  }
): Promise<void> {
  const res = await fetch(`${BP_URL}/rest/v1/lay_bets`, {
    method: "POST",
    headers: {
      apikey: BP_KEY,
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      Prefer: "return=representation",
    },
    body: JSON.stringify({
      parent_bet_id: parentBetId,
      metodo: "Banca",
      evento: lay.evento,
      data_evento: lay.dataEvento,
      mercato: lay.mercato,
      competizione: lay.competizione || null,
      conto: lay.conto,
      stake: lay.stake,
      quota_banca: lay.quotaBanca,
      quota_punta: lay.quotaPunta,
      tasse_percentuale: lay.tassePercentuale,
      attiva: true,
      stato: "In Corso",
      url_evento: null,
      user_id: userId,
    }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Errore creazione lay bet: ${err}`);
  }
}
