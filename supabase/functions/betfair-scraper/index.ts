/**
 * betfair-scraper — Supabase Edge Function
 * Recupera quote Exchange (lay) da Betfair API e le salva in live_odds.
 * Chiamata via pg_cron ogni 5 minuti.
 */

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.7.1";

const LOGIN_URL = "https://identitysso.betfair.it/api/login";
const BETTING_URL = "https://api.betfair.com/exchange/betting/rest/v1.0/";
const EXPIRES_MINUTES = 90;
const BOOKMAKER = "Betfair Exchange";

const SPORT_IDS: Record<string, string> = { calcio: "1", tennis: "2", basket: "7" };
const BF_SPORT_NAME: Record<string, string> = { "1": "calcio", "2": "tennis", "7": "basket" };

const TARGET_COMPETITIONS: Array<[string, string]> = [
  ["ITA", "serie a"], ["ITA", "serie b"], ["ITA", "coppa italia"],
  ["GBR", "premier league"], ["GBR", "championship"],
  ["DEU", "bundesliga"],
  ["ESP", "la liga"], ["ESP", "laliga"],
  ["FRA", "ligue 1"],
  ["", "champions league"], ["", "europa league"],
  ["", "europa conference"], ["", "conference league"],
];

const MARKET_TYPES = [
  "MATCH_ODDS", "BOTH_TEAMS_TO_SCORE",
  "OVER_UNDER_25", "OVER_UNDER_35", "OVER_UNDER_45",
  "OVER_UNDER_05", "OVER_UNDER_15", "OVER_UNDER_55",
];

function bfHeaders(token: string, appKey: string) {
  return {
    "X-Application": appKey,
    "X-Authentication": token,
    "Content-Type": "application/json",
    "Accept": "application/json",
  };
}

function marketLabel(marketName: string): [string, string | null] {
  const mn = marketName.toLowerCase();
  if (mn.includes("match odds")) return ["1X2", null];
  if (mn.includes("both teams") || mn.includes("btts")) return ["BTTS", null];
  const m = mn.match(/over[/\s]under\s+([\d.]+)/);
  if (m) return ["Over/Under", m[1]];
  return [marketName, null];
}

function expiresAt(): string {
  return new Date(Date.now() + EXPIRES_MINUTES * 60 * 1000).toISOString();
}

async function betfairLogin(appKey: string, username: string, password: string): Promise<string> {
  const resp = await fetch(LOGIN_URL, {
    method: "POST",
    headers: {
      "X-Application": appKey,
      "Content-Type": "application/x-www-form-urlencoded",
      "Accept": "application/json",
    },
    body: `username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`,
  });
  const rawText = await resp.text();
  console.log(`[BF] Login HTTP ${resp.status}, content-type: ${resp.headers.get("content-type")}, body: ${rawText.slice(0, 500)}`);
  let body: Record<string, unknown>;
  try {
    body = JSON.parse(rawText);
  } catch {
    throw new Error(`Betfair login returned non-JSON (HTTP ${resp.status}): ${rawText.slice(0, 300)}`);
  }
  if (body.status !== "SUCCESS") throw new Error(`Betfair login failed: ${JSON.stringify(body)}`);
  return body.token as string;
}

async function apiPost(url: string, payload: unknown, token: string, appKey: string): Promise<unknown> {
  const resp = await fetch(url, {
    method: "POST",
    headers: bfHeaders(token, appKey),
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`Betfair API ${url} → ${resp.status}`);
  const data = await resp.json();
  if (data?.error) throw new Error(`API error: ${JSON.stringify(data)}`);
  return data;
}

async function getTargetCompIds(token: string, appKey: string): Promise<string[]> {
  const comps = await apiPost(
    BETTING_URL + "listCompetitions/",
    { filter: { eventTypeIds: ["1"] } },
    token, appKey,
  ) as Array<{ competition: { id: string; name: string }; competitionRegion: string }>;

  const ids: string[] = [];
  for (const c of comps) {
    const name = (c.competition?.name ?? "").toLowerCase();
    const region = (c.competitionRegion ?? "").toUpperCase();
    const id = c.competition?.id;
    if (!id) continue;
    for (const [reqRegion, reqKw] of TARGET_COMPETITIONS) {
      const regionOk = !reqRegion || region === reqRegion;
      if (regionOk && name.includes(reqKw)) { ids.push(id); break; }
    }
  }
  return ids;
}

async function fetchCatalogue(
  token: string, appKey: string,
  eventTypeIds: string[], marketTypes: string[],
  extra?: Record<string, unknown>,
): Promise<unknown[]> {
  const now = new Date();
  const end = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
  const filter: Record<string, unknown> = {
    eventTypeIds,
    marketTypeCodes: marketTypes,
    marketStartTime: {
      from: now.toISOString().replace(".000", ""),
      to: end.toISOString().replace(".000", ""),
    },
    ...extra,
  };
  const data = await apiPost(
    BETTING_URL + "listMarketCatalogue/",
    {
      filter,
      marketProjection: ["EVENT", "EVENT_TYPE", "COMPETITION", "MARKET_START_TIME", "RUNNER_DESCRIPTION"],
      maxResults: 1000,
    },
    token, appKey,
  ) as unknown[];
  return data ?? [];
}

async function fetchBooks(token: string, appKey: string, marketIds: string[]): Promise<unknown[]> {
  const CHUNK = 100;
  const results: unknown[] = [];
  for (let i = 0; i < marketIds.length; i += CHUNK) {
    const chunk = marketIds.slice(i, i + CHUNK);
    const books = await apiPost(
      BETTING_URL + "listMarketBook/",
      {
        marketIds: chunk,
        priceProjection: {
          priceData: ["EX_BEST_OFFERS"],
          exBestOffersOverrides: { bestPricesDepth: 1, rollupModel: "STAKE", rollupLimit: 0 },
        },
        orderProjection: "EXECUTABLE",
        matchProjection: "NO_ROLLUP",
      },
      token, appKey,
    ) as unknown[];
    results.push(...books);
  }
  return results;
}

function extractRows(catalogue: Record<string, unknown>, book: Record<string, unknown>, sportLabel: string, marketId: string): Record<string, unknown>[] {
  const rows: Record<string, unknown>[] = [];
  const marketName = (catalogue.marketName as string) ?? "";
  const [market, threshold] = marketLabel(marketName);
  const event = (catalogue.event as Record<string, unknown>) ?? {};
  const competition = (catalogue.competition as Record<string, unknown>) ?? {};
  const startTime = catalogue.marketStartTime as string ?? "";

  const eventName = (event.name as string) ?? "Unknown";
  const eventId = String(event.id ?? "");
  const league = (competition.name as string) ?? "Unknown";
  const eventTime = startTime ? new Date(startTime).toISOString() : new Date().toISOString();

  // Runner map: selectionId → {name, sortPriority}
  const runnerMap = new Map<number, { name: string; sortPriority: number }>();
  const runners = (catalogue.runners as Array<Record<string, unknown>>) ?? [];
  for (const rd of runners) {
    runnerMap.set(rd.selectionId as number, {
      name: (rd.runnerName as string) ?? "Unknown",
      sortPriority: (rd.sortPriority as number) ?? 99,
    });
  }

  const bookRunners = (book.runners as Array<Record<string, unknown>>) ?? [];
  for (const runner of bookRunners) {
    if (runner.status !== "ACTIVE") continue;
    const selId = runner.selectionId as number;
    const info = runnerMap.get(selId) ?? { name: "Unknown", sortPriority: 99 };
    const ex = (runner.ex as Record<string, unknown>) ?? {};
    const atl = (ex.availableToLay as Array<Record<string, number>>) ?? [];
    if (!atl.length) continue;
    const layPrice = atl[0].price;
    const laySize = atl[0].size ?? 0;
    if (!layPrice || layPrice <= 1.0) continue;

    // Map runner name → outcome label
    const mn = marketName.toLowerCase();
    let outcome: string;
    if (mn.includes("match odds")) {
      if (info.name === "The Draw") outcome = "X";
      else if (info.sortPriority === 1) outcome = "1";
      else if (info.sortPriority === 2) outcome = "2";
      else outcome = info.name;
    } else if (mn.includes("both teams") || mn.includes("btts")) {
      outcome = info.name === "Yes" ? "Goal" : info.name === "No" ? "No Goal" : info.name;
    } else if (mn.includes("over") && mn.includes("under")) {
      outcome = info.name.replace(/\s+goals?$/i, "");
    } else {
      outcome = info.name;
    }

    rows.push({
      bookmaker: BOOKMAKER,
      sport: sportLabel,
      league,
      event_name: eventName,
      event_time: eventTime,
      market,
      outcome,
      odds: layPrice,
      volume: laySize,
      expires_at: expiresAt(),
      market_id: marketId,
      event_id: eventId,
    });
  }
  return rows;
}

Deno.serve(async () => {
  const start = Date.now();
  const appKey = Deno.env.get("BETFAIR_APP_KEY") ?? "";
  const username = Deno.env.get("BETFAIR_USERNAME") ?? "";
  const password = Deno.env.get("BETFAIR_PASSWORD") ?? "";
  const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
  const supabaseKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";

  if (!appKey || !username || !password) {
    return new Response(JSON.stringify({ error: "Missing Betfair credentials" }), { status: 500 });
  }

  try {
    const supabase = createClient(supabaseUrl, supabaseKey);

    // Login
    const token = await betfairLogin(appKey, username, password);
    console.log("[BF] Login OK");

    // Get football competition IDs
    const compIds = await getTargetCompIds(token, appKey);
    console.log(`[BF] ${compIds.length} competition IDs`);

    // Fetch catalogue
    const COMP_BATCH = 5;
    const catalogueList: Record<string, unknown>[] = [];
    const seen = new Set<string>();

    // Football (filtered by competition)
    if (compIds.length > 0) {
      for (let i = 0; i < compIds.length; i += COMP_BATCH) {
        const batch = compIds.slice(i, i + COMP_BATCH);
        try {
          const page = await fetchCatalogue(token, appKey, ["1"], MARKET_TYPES, { competitionIds: batch });
          for (const m of page as Record<string, unknown>[]) {
            const mid = m.marketId as string;
            if (mid && !seen.has(mid)) { seen.add(mid); catalogueList.push(m); }
          }
        } catch (e) { console.error(`[BF] Catalogue batch error: ${e}`); }
      }
    }

    // Tennis + basket (global)
    try {
      const otherPage = await fetchCatalogue(token, appKey, ["2", "7"], MARKET_TYPES);
      for (const m of otherPage as Record<string, unknown>[]) {
        const mid = m.marketId as string;
        if (mid && !seen.has(mid)) { seen.add(mid); catalogueList.push(m); }
      }
    } catch (e) { console.error(`[BF] Other sports error: ${e}`); }

    console.log(`[BF] ${catalogueList.length} markets in catalogue`);

    // Map marketId → catalogue
    const catMap = new Map(catalogueList.map(c => [c.marketId as string, c]));
    const marketIds = [...catMap.keys()];

    // Fetch books
    const books = await fetchBooks(token, appKey, marketIds) as Record<string, unknown>[];
    console.log(`[BF] ${books.length} books`);

    // Extract rows
    const allRows: Record<string, unknown>[] = [];
    for (const book of books) {
      const mid = book.marketId as string;
      const cat = catMap.get(mid);
      if (!cat) continue;
      const et = (cat.eventType as Record<string, unknown>)?.id as string ?? "1";
      const sportLabel = BF_SPORT_NAME[et] ?? "calcio";
      const rows = extractRows(cat, book, sportLabel, mid);
      allRows.push(...rows);
    }

    console.log(`[BF] ${allRows.length} rows extracted`);

    // Upsert in batches of 500
    const BATCH = 500;
    let total = 0;
    for (let i = 0; i < allRows.length; i += BATCH) {
      const batch = allRows.slice(i, i + BATCH);
      const { error } = await supabase
        .from("live_odds")
        .upsert(batch, { onConflict: "bookmaker,event_name,market,outcome" });
      if (error) console.error(`[BF] Upsert error: ${error.message}`);
      else total += batch.length;
    }

    const ms = Date.now() - start;
    console.log(`[BF] Done — ${total} rows upserted in ${ms}ms`);

    return new Response(JSON.stringify({ rows: total, ms }), {
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error(`[BF] Fatal: ${msg}`);
    return new Response(JSON.stringify({ error: msg }), { status: 500 });
  }
});
