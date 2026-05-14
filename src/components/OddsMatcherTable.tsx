import { useMemo, useState, useEffect } from "react";
import { PuntaBancaModal } from "./PuntaBancaModal";

interface OddsData {
  bookmaker: string;
  eventName: string;
  league: string;
  eventTime: string;
  market: string;
  sport: string;
  odds: Record<string, number>;
  volume?: Record<string, number>;  // lay volume per outcome (Betfair Exchange only)
  marketId?: string;                // Betfair market ID
  eventId?: string;                 // Betfair event ID for direct URL
  centroquoteUrl?: string;          // centroquote.it comparison page URL
}

export interface Opportunity {
  eventTime: string;
  sport: string;
  eventName: string;
  league: string;
  market: string;           // e.g. "1X2", "Over/Under", "DC", "BTTS"
  scommessa: string;
  rating: number;
  bookmaker: string;
  quotaBook: number;
  exchange: string;
  quotaExchange: number;
  isBookVsBook: boolean;
  volumeExchange?: number;  // Betfair lay volume (€) — only in back-lay mode
  marketId?: string;        // Betfair market ID
  eventId?: string;         // Betfair event ID for direct URL
  bookmakerUrl?: string;    // centroquote.it comparison page (direct link to match)
}

interface TreVieGroup {
  eventTime: string;
  sport: string;
  eventName: string;
  league: string;
  market: string;
  rating: number;
  legs: Array<{
    outcome: string;    // "1", "X", "2"
    bookmaker: string;
    odds: number;
  }>;
}

interface BestOddsRow {
  eventTime: string;
  sport: string;
  eventName: string;
  league: string;
  outcome: string;
  market: string;
  bestBookmaker: string;
  bestOdds: number;
  worstBookmaker: string;
  worstOdds: number;
  allOdds: Array<{ bookmaker: string; odds: number }>;
}

interface Props {
  data: {
    data: OddsData[];
    metadata?: any;
  } | null;
  loading: boolean;
  activeTab: string;
  selectedExchanges?: string[];
  filters: {
    bookmaker: string[];
    stakePunta: string;
    quotaMinima: string;
    quotaMassima: string;
    partita: string;
    campionato: string;
    freebet: boolean;
    rimborso: boolean;
    bonus: string;
    filtroLiquidita: boolean;
    // Multipla-specific
    stakeMultipla?: string;
    quotaMinimaMultipla?: string;
    numEventi?: string;
    quotaPartitaMinima?: string;
    quotaPartitaMassima?: string;
    daData?: string;
    aData?: string;
    // Tre Vie specific
    trevieMain?: string;
    trevieSecondary?: string[];
  };
  commission: number;
  multiplaResetKey?: number;
  onMultiplaSelectedChange?: (selected: Opportunity[]) => void;
}

const EXCHANGE_NAMES = [
  "betfair exchange", "betfair", "betflag exchange",
  "smarkets", "betdaq", "matchbook",
];

function isExchange(bookmaker: string): boolean {
  return EXCHANGE_NAMES.some(ex => bookmaker.toLowerCase().includes(ex.toLowerCase()));
}

// Alias: varianti inglesi/italiane/abbreviate → forma canonica
// ORDINATI per lunghezza decrescente — le frasi più lunghe hanno precedenza
const TEAM_ALIASES: [string, string][] = [
  // frasi multi-parola prima
  ["fc bayern munich", "bayern"], ["fc bayern", "bayern"], ["bayern munich", "bayern"],
  ["paris saint-germain", "psg"], ["paris saint germain", "psg"],
  ["paris st-germain", "psg"], ["paris st germain", "psg"], ["paris st g", "psg"],
  ["paris sg", "psg"],
  ["nottingham forest", "nottmforest"], ["nottm forest", "nottmforest"],
  ["internazionale", "inter"], ["inter milan", "inter"],
  ["ac milan", "milan"],
  ["atletico de madrid", "atletico"], ["atletico madrid", "atletico"],
  ["manchester united", "manutd"], ["man united", "manutd"], ["man utd", "manutd"],
  ["manchester city", "mancity"], ["man city", "mancity"],
  ["tottenham hotspur", "tottenham"], ["tottenham h", "tottenham"],
  ["newcastle united", "newcastle"], ["newcastle utd", "newcastle"],
  ["west ham united", "westham"], ["west ham", "westham"],
  ["rayo vallecano", "vallecano"],
  ["real sociedad", "sociedad"],
  ["real betis", "betis"],
  ["deportivo alaves", "alaves"],
  ["borussia dortmund", "dortmund"], ["bvb dortmund", "dortmund"],
  ["borussia monchengladbach", "gladbach"], ["b monchengladbach", "gladbach"],
  ["monchengladbach", "gladbach"], ["mgladbach", "gladbach"],
  ["eintracht francoforte", "eintracht"], ["eintracht frankfurt", "eintracht"],
  ["bayer leverkusen", "leverkusen"],
  ["stoccarda vfb", "stuttgart"], ["stoccarda", "stuttgart"],
  ["rb lipsia", "leipzig"], ["lipsia", "leipzig"],
  ["union berlino", "union berlin"], ["berlino", "berlin"],
  ["fc colonia", "koln"], ["colonia", "koln"],
  ["hamburger sv", "hamburg"], ["amburgo", "hamburg"], ["hamburger", "hamburg"],
  ["fc augsburg", "augsburg"], ["augusta", "augsburg"],
  ["werder bremen", "bremen"], ["werder brema", "bremen"], ["brema", "bremen"],
  ["rb salisburgo", "salzburg"], ["salisburgo", "salzburg"],
  // Francoforte (centroquote) = Eintracht Frankfurt (betfair)
  ["francoforte", "eintracht"],
  // Mainz italian name
  ["magonza", "mainz"],
  // St Pauli variants
  ["san paolo", "stpauli"], ["st pauli", "stpauli"], ["st. pauli", "stpauli"],
  ["siviglia", "sevilla"],
  ["royal antwerp", "antwerp"], ["anversa", "antwerp"],
  ["club bruges", "brugge"], ["bruges", "brugge"],
  ["sporting lisbona", "sporting"], ["sporting cp", "sporting"],
  ["sl benfica", "benfica"],
  ["psv eindhoven", "psv"],
  ["ajax amsterdam", "ajax"],
  ["feyenoord rotterdam", "feyenoord"],
  ["girona fc", "girona"],
  // Ligue 1 names
  ["paris fc", "parisfc"],
  ["olympique lione", "lyon"], ["olympique lyon", "lyon"],
  ["olympique marsiglia", "marseille"], ["olympique de marseille", "marseille"],
  ["st etienne", "saintetienne"], ["saint etienne", "saintetienne"],
  ["nizza", "nice"],
  ["angers sco", "angers"],
  ["le havre", "havre"],
  ["stade rennais", "rennes"],
  // singole parole (frasi più corte, applicate dopo)
  ["nottingham", "nottmforest"], ["nottm", "nottmforest"],
  ["friburgo", "freiburg"],
  ["strasburgo", "strasbourg"],
  ["maiorca", "mallorca"],
  ["villareal", "villarreal"],
];

function applyTeamAliases(text: string): string {
  let result = text;
  for (const [alias, canonical] of TEAM_ALIASES) {
    if (result.includes(alias)) {
      result = result.split(alias).join(canonical); // replace all occurrences
    }
  }
  return result;
}

function normalizeEventName(name: string): string {
  // Base cleanup: lowercase, remove accents, strip punctuation & separators
  let base = name
    .toLowerCase()
    .normalize("NFD").replace(/[̀-ͯ]/g, "")   // remove accents
    .replace(/[.\-–—']/g, " ")
    .replace(/\b(v|vs|versus|fc|ac|sc|rc|cf|afc|bfc|vfb|rb|sl|sv)\b/g, " ")  // remove separators & suffixes
    .replace(/\s+/g, " ")
    .trim();

  // Applica alias team (prima di splittare in parole)
  base = applyTeamAliases(base);

  // Keep only words longer than 2 chars, sort alphabetically
  const words = base.split(" ").filter(w => w.length > 2);
  return words.sort().join("");
}

function eventNamesMatch(a: string, b: string): boolean {
  const na = normalizeEventName(a);
  const nb = normalizeEventName(b);
  if (na === nb) return true;
  // Partial match: one is a subset of the other (handles truncated names)
  if (na.length >= 6 && nb.length >= 6 && (na.includes(nb) || nb.includes(na))) return true;
  return false;
}

function cleanEventName(name: string): string {
  return name
    .replace(/ v Quote.*$/i, "")
    .replace(/ vs /, " v ")
    .trim();
}

// Bookmaker badge colors
const BOOK_COLORS: Record<string, { bg: string; text: string }> = {
  "888sport": { bg: "#1a1a2e", text: "#fff" },
  "bet365": { bg: "#027b5b", text: "#ffd700" },
  "betfair": { bg: "#ffb80c", text: "#1e1e1e" },
  "betflag": { bg: "#e31e24", text: "#fff" },
  "betsson": { bg: "#1a3a5c", text: "#fff" },
  "bwin": { bg: "#f0c800", text: "#1e1e1e" },
  "codere": { bg: "#1a1a1a", text: "#c8a000" },
  "eurobet": { bg: "#e30613", text: "#fff" },
  "fastbet": { bg: "#1a1a2e", text: "#ff6600" },
  "goldbet": { bg: "#003d7a", text: "#ffd700" },
  "lottomatica": { bg: "#c8102e", text: "#fff" },
  "planetwin365": { bg: "#00a651", text: "#fff" },
  "sisal": { bg: "#003366", text: "#fff" },
  "snai": { bg: "#003087", text: "#ffd700" },
  "william": { bg: "#1a3a5c", text: "#fff" },
  "gioco digitale": { bg: "#00a850", text: "#fff" },
  "netbet": { bg: "#1a8a1a", text: "#fff" },
  "netwin": { bg: "#333", text: "#fff" },
  "dazn": { bg: "#0d0f14", text: "#f8f8f5" },
  "domusbet": { bg: "#1a1a1a", text: "#e88a00" },
  "admiral": { bg: "#003366", text: "#fff" },
  "stanleybet": { bg: "#c8102e", text: "#fff" },
  "leovegas": { bg: "#ff6600", text: "#fff" },
  "e-play24": { bg: "#1a5276", text: "#fff" },
};

function getBookColor(name: string): { bg: string; text: string } {
  const lower = name.toLowerCase();
  for (const [key, colors] of Object.entries(BOOK_COLORS)) {
    if (lower.includes(key)) return colors;
  }
  return { bg: "#2a3a50", text: "#fff" };
}

function getOutcomes(event: OddsData): Array<{ key: string; label: string }> {
  const o = event.odds;
  if (event.market === "1X2" || event.market === "h2h") {
    const outcomes: Array<{ key: string; label: string }> = [];
    // Scraper stores "1"/"X"/"2"; legacy may use "home"/"draw"/"away"
    if (o["1"]) outcomes.push({ key: "1", label: "1" });
    if (o["X"]) outcomes.push({ key: "X", label: "X" });
    if (o["2"]) outcomes.push({ key: "2", label: "2" });
    if (!outcomes.length) {
      if (o["home"]) outcomes.push({ key: "home", label: "1" });
      if (o["draw"]) outcomes.push({ key: "draw", label: "X" });
      if (o["away"]) outcomes.push({ key: "away", label: "2" });
    }
    return outcomes;
  }
  if (event.market === "DC" || event.market === "Double Chance") {
    const outcomes: Array<{ key: string; label: string }> = [];
    if (o["1X"]) outcomes.push({ key: "1X", label: "1X" });
    if (o["X2"]) outcomes.push({ key: "X2", label: "X2" });
    if (o["12"]) outcomes.push({ key: "12", label: "12" });
    return outcomes;
  }
  if (event.market === "BTTS") {
    const outcomes: Array<{ key: string; label: string }> = [];
    if (o["Goal"]) outcomes.push({ key: "Goal", label: "Goal" });
    if (o["No Goal"]) outcomes.push({ key: "No Goal", label: "No Goal" });
    if (!outcomes.length) {
      if (o["yes"]) outcomes.push({ key: "yes", label: "Goal" });
      if (o["no"]) outcomes.push({ key: "no", label: "No Goal" });
    }
    return outcomes;
  }
  // Over/Under and any other market: return all available outcome keys
  return Object.entries(o)
    .filter(([, v]) => v > 1)
    .map(([k]) => ({ key: k, label: k }));
}

function findMatchingEvents(sourceEvent: OddsData, pool: OddsData[]): OddsData[] {
  return pool.filter(ev => eventNamesMatch(sourceEvent.eventName, ev.eventName));
}

export function OddsMatcherTable({ data, loading, activeTab, selectedExchanges, filters, commission, multiplaResetKey, onMultiplaSelectedChange }: Props) {
  const [selectedOpp, setSelectedOpp] = useState<Opportunity | null>(null);
  const [multiplaSelected, setMultiplaSelected] = useState<Opportunity[]>([]);

  // Reset selezione multipla quando l'utente clicca Aggiorna o Pulisci
  useEffect(() => {
    setMultiplaSelected([]);
  }, [multiplaResetKey]);

  // Notifica il parent ogni volta che cambia la selezione multipla
  useEffect(() => {
    onMultiplaSelectedChange?.(multiplaSelected);
  }, [multiplaSelected, onMultiplaSelectedChange]);

  // ── Snapshot "committed" filters ──────────────────────────────────────────
  // selectedExchanges e filters vengono aggiornati in tempo reale dalla UI,
  // ma i calcoli pesanti (singolaOpps ecc.) devono girare SOLO quando arrivano
  // nuovi dati (= l'utente ha cliccato Aggiorna). Usiamo uno snapshot che si
  // congela fino alla prossima fetch.
  const [committedExchanges, setCommittedExchanges] = useState<string[]>(selectedExchanges ?? []);
  const [committedFilters, setCommittedFilters] = useState(filters);

  useEffect(() => {
    // data cambia solo quando Aggiorna viene cliccato → aggiorna snapshot
    setCommittedExchanges(selectedExchanges ?? []);
    setCommittedFilters(filters);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);
  // ─────────────────────────────────────────────────────────────────────────

  const REAL_EXCHANGE_NAMES = ["betfair exchange", "betflag exchange", "smarkets", "betdaq", "matchbook"];

  // Check if a bookmaker name is a real exchange
  const isRealExchange = (name: string) =>
    REAL_EXCHANGE_NAMES.some(ex => name.toLowerCase().includes(ex.toLowerCase()));

  // Check if a bookmaker is selected as exchange side — usa snapshot committato
  const isOnExchangeSide = (name: string): boolean => {
    if (!committedExchanges || committedExchanges.length === 0)
      return isRealExchange(name);
    return committedExchanges.some(ex =>
      name.toLowerCase().includes(ex.toLowerCase()) ||
      ex.toLowerCase().includes(name.toLowerCase())
    );
  };

  // Is punta-punta mode — usa snapshot committato
  const isPuntaPuntaMode = committedExchanges.length > 0 &&
    !committedExchanges.some(ex => isRealExchange(ex));

  // ═══ SINGOLA: Book vs Exchange (back-lay) OR Book vs Book (punta-punta) ═══
  const singolaOpps = useMemo(() => {
    if (!data?.data || data.data.length === 0) return [];
    const opps: Opportunity[] = [];
    const commissionRate = commission / 100;
    const isFB = committedFilters.freebet;

    const bookmakerSide = data.data.filter(odd => !isOnExchangeSide(odd.bookmaker));
    const rawExchangeSide = data.data.filter(odd => isOnExchangeSide(odd.bookmaker));

    // Punta-punta only when the user explicitly selects bookmakers as counter side.
    // In punta-punta mode use ALL data for both sides so no bookmaker is accidentally
    // excluded — the inner loop already prevents same-bookmaker comparisons.
    const effectivePuntaPunta = isPuntaPuntaMode;
    const allPool = data.data;
    const exchangeSide = effectivePuntaPunta ? allPool : rawExchangeSide;

    if (exchangeSide.length === 0) return [];

    if (effectivePuntaPunta) {
      // ── PUNTA-PUNTA ──
      allPool.forEach(bmEvent => {
        const matchingCounters = findMatchingEvents(bmEvent, exchangeSide);
        if (matchingCounters.length === 0) return;
        const outcomes = getOutcomes(bmEvent);
        const hasDrawKey = "X" in bmEvent.odds || "draw" in bmEvent.odds;

        // ── 3-way 1X2 (football): punta-punta ──
        // Primary: DC counter (real Double Chance quote from centroquote.it)
        //   "1 vs X2", "2 vs 1X", "X vs 12"
        // Fallback: Dutch on 1X2 if DC data not yet in DB
        const DC_COUNTER: Record<string, string> = { "1": "X2", "2": "1X", "X": "12" };

        if (hasDrawKey && outcomes.length === 3) {
          if (bmEvent.market !== "1X2") return;

          const dcCounters = findMatchingEvents(bmEvent, allPool).filter(e => e.market === "DC");
          const sameMarket1x2 = matchingCounters.filter(e => e.market === "1X2");

          outcomes.forEach(outcome => {
            const backOdds = bmEvent.odds[outcome.key];
            if (!backOdds || backOdds <= 1) return;
            const dcKey = DC_COUNTER[outcome.key];
            if (!dcKey) return;

            // ── Primary: DC counter ──
            dcCounters.forEach(dcEvent => {
              if (dcEvent.bookmaker === bmEvent.bookmaker) return;
              const counterOdds = dcEvent.odds[dcKey];
              if (!counterOdds || counterOdds <= 1) return;
              const stake2 = backOdds / counterOdds;
              const profitIf1 = (backOdds - 1) - stake2;
              const profitIf2 = stake2 * (counterOdds - 1) - 1;
              const rating = 100 + Math.min(profitIf1, profitIf2) * 100;
              if (rating > 75 && rating < 120) {
                opps.push({
                  eventTime: bmEvent.eventTime, sport: bmEvent.sport || "calcio",
                  eventName: cleanEventName(bmEvent.eventName), league: bmEvent.league,
                  market: bmEvent.market,
                  scommessa: `${outcome.label} vs ${dcKey}`,
                  rating, bookmaker: bmEvent.bookmaker, quotaBook: backOdds,
                  exchange: dcEvent.bookmaker, quotaExchange: counterOdds,
                  isBookVsBook: true,
                });
              }
            });

            // ── Fallback: Dutch on 1X2 when no DC data available ──
            if (dcCounters.length === 0) {
              const compOutcomes = outcomes.filter(o => o.key !== outcome.key);
              sameMarket1x2.forEach(exEvent => {
                if (exEvent.bookmaker === bmEvent.bookmaker) return;
                const compOdds = compOutcomes.map(o => ({ key: o.key, label: o.label, odds: exEvent.odds[o.key] }));
                if (compOdds.some(o => !o.odds || o.odds <= 1)) return;
                const dutchMargin = compOdds.reduce((sum, o) => sum + 1 / o.odds!, 0);
                const effectiveCounterOdds = 1 / dutchMargin;
                if (effectiveCounterOdds <= 1) return;
                const stake2 = backOdds / effectiveCounterOdds;
                const profitIf1 = (backOdds - 1) - stake2;
                const profitIf2 = stake2 * (effectiveCounterOdds - 1) - 1;
                const rating = 100 + Math.min(profitIf1, profitIf2) * 100;
                if (rating > 75 && rating < 120) {
                  const compLabel = compOutcomes.map(o => o.label).join("+");
                  opps.push({
                    eventTime: bmEvent.eventTime, sport: bmEvent.sport || "calcio",
                    eventName: cleanEventName(bmEvent.eventName), league: bmEvent.league,
                    market: bmEvent.market,
                    scommessa: `${outcome.label} vs ${compLabel}`,
                    rating, bookmaker: bmEvent.bookmaker, quotaBook: backOdds,
                    exchange: exEvent.bookmaker, quotaExchange: effectiveCounterOdds,
                    isBookVsBook: true,
                  });
                }
              });
            }
          });
          return;
        }

        // ── 2-way markets only: tennis/NBA 1X2, BTTS, Over/Under ──
        // (3-way football 1X2 is already handled above via Dutch coverage)
        // No DC cross-market entries — DC scraping removed (unreliable data).
        const OPPOSITE: Record<string, string> = {
          "1": "2", "2": "1",           // tennis/NBA (no draw)
          "Goal": "No Goal", "No Goal": "Goal",
          "yes": "no", "no": "yes",
          "home": "away", "away": "home",
        };
        outcomes.forEach(({ key }) => {
          if (key.startsWith("Over ")) OPPOSITE[key] = key.replace("Over ", "Under ");
          if (key.startsWith("Under ")) OPPOSITE[key] = key.replace("Under ", "Over ");
        });

        // Skip if this is still a 3-way market that slipped through (safety guard)
        if (hasDrawKey && outcomes.length === 3) return;

        outcomes.forEach(outcome => {
          const backOdds = bmEvent.odds[outcome.key];
          if (!backOdds || backOdds <= 1) return;
          const oppositeKey = OPPOSITE[outcome.key];
          if (!oppositeKey) return;

          matchingCounters.forEach(exEvent => {
            if (exEvent.market !== bmEvent.market) return; // same market only
            const counterOdds = exEvent.odds[oppositeKey];
            if (!counterOdds || counterOdds <= 1) return;
            if (bmEvent.bookmaker === exEvent.bookmaker) return;

            const stake2 = backOdds / counterOdds;
            const profitIf1 = (backOdds - 1) - stake2;
            const profitIf2 = stake2 * (counterOdds - 1) - 1;
            const worstProfit = Math.min(profitIf1, profitIf2);
            const rating = 100 + worstProfit * 100;

            if (rating > 75 && rating < 105) {
              opps.push({
                eventTime: bmEvent.eventTime,
                sport: bmEvent.sport || "calcio",
                eventName: cleanEventName(bmEvent.eventName),
                league: bmEvent.league,
                market: bmEvent.market,
                scommessa: `${outcome.label} vs ${oppositeKey}`,
                rating,
                bookmaker: bmEvent.bookmaker,
                quotaBook: backOdds,
                exchange: exEvent.bookmaker,
                quotaExchange: counterOdds,
                isBookVsBook: true,
              });
            }
          });
        });
      });
    } else {
      // ── BACK-LAY: standard book vs exchange ──
      // For events with no exchange match, fall back to punta-punta (book vs book)
      const OPPOSITE: Record<string, string> = {
        "1": "2", "2": "1",
        "Goal": "No Goal", "No Goal": "Goal",
        "yes": "no", "no": "yes",
        "home": "away", "away": "home",
      };

      bookmakerSide.forEach(bmEvent => {
        const matchingExchanges = findMatchingEvents(bmEvent, exchangeSide);
        const outcomes = getOutcomes(bmEvent);
        const hasDrawKey = "X" in bmEvent.odds || "draw" in bmEvent.odds;
        const is3Way = hasDrawKey && outcomes.length === 3;

        // ── Try back-lay first ──
        if (matchingExchanges.length > 0) {
          outcomes.forEach(outcome => {
            const backOdds = bmEvent.odds[outcome.key];
            if (!backOdds || backOdds <= 1) return;

            let bestLayOdds = Infinity;
            let bestExchange = "";
            let bestVolume: number | undefined;
            let bestMarketId: string | undefined;
            let bestEventId: string | undefined;
            matchingExchanges.forEach(exEvent => {
              const layOdds = exEvent.odds[outcome.key];
              if (layOdds && layOdds > 1 && layOdds < bestLayOdds) {
                bestLayOdds = layOdds;
                bestExchange = exEvent.bookmaker;
                bestVolume = exEvent.volume?.[outcome.key];
                bestMarketId = exEvent.marketId;
                bestEventId = exEvent.eventId;
              }
            });
            if (bestLayOdds === Infinity) return;

            const layStake = isFB
              ? (backOdds - 1) / (bestLayOdds - commissionRate)   // FreeBet: copri solo profitto
              : backOdds / (bestLayOdds - commissionRate);
            // FreeBet: stake non torna indietro se vinci → sottraiamo 1 (face value) dal profitIfWin
            const profitIfWin = isFB
              ? (backOdds - 1) - layStake * (bestLayOdds - 1) - 1
              : (backOdds - 1) - layStake * (bestLayOdds - 1);
            const profitIfLose = layStake * (1 - commissionRate) - 1;
            const worstProfit = Math.min(profitIfWin, profitIfLose);
            const rating = 100 + worstProfit * 100;

            if (rating > 70 && rating < 120) {
              opps.push({
                eventTime: bmEvent.eventTime,
                sport: bmEvent.sport || "calcio",
                eventName: cleanEventName(bmEvent.eventName),
                league: bmEvent.league,
                market: bmEvent.market,
                scommessa: outcome.label,
                rating,
                bookmaker: bmEvent.bookmaker,
                quotaBook: backOdds,
                exchange: bestExchange,
                quotaExchange: bestLayOdds,
                isBookVsBook: false,
                volumeExchange: bestVolume,
                marketId: bestMarketId,
                eventId: bestEventId,
                bookmakerUrl: bmEvent.centroquoteUrl,
              });
            }
          });
          return; // back-lay handled
        }
        // No exchange found for this event → skip (stay in back-lay mode, no punta-punta mixing)
      });
    }

    // Deduplicate: keep best rating per (eventName, scommessa, bookmaker)
    const dedupMap = new Map<string, Opportunity>();
    for (const opp of opps) {
      const key = `${normalizeEventName(opp.eventName)}|${opp.scommessa}|${opp.bookmaker}`;
      const existing = dedupMap.get(key);
      if (!existing || opp.rating > existing.rating) dedupMap.set(key, opp);
    }
    return Array.from(dedupMap.values()).sort((a, b) => b.rating - a.rating);
  }, [data, commission, committedExchanges, isPuntaPuntaMode, committedFilters.freebet]);

  // ═══ TRE VIE: Dutch 3-way — Bookmaker Principale + Secondari ═══
  const trevieOpps = useMemo((): TreVieGroup[] => {
    if (!data?.data || data.data.length === 0) return [];

    const tvMain = committedFilters.trevieMain || "";
    const tvSecondary = committedFilters.trevieSecondary ?? [];

    // Only non-exchange bookmakers; only calcio; only 1X2 market
    let pool = data.data.filter(odd =>
      !isExchange(odd.bookmaker) &&
      odd.sport === "calcio" &&
      odd.market === "1X2"
    );

    // If secondari are selected, restrict pool to them (+ always include principale)
    if (tvSecondary.length > 0) {
      pool = pool.filter(bm => {
        const lower = bm.bookmaker.toLowerCase();
        const inSecondary = tvSecondary.some(s => lower.includes(s.toLowerCase()) || s.toLowerCase().includes(lower));
        const isMain = tvMain && (lower.includes(tvMain.toLowerCase()) || tvMain.toLowerCase().includes(lower));
        return inSecondary || isMain;
      });
    }

    // Group by event
    const eventGroups = new Map<string, OddsData[]>();
    pool.forEach(bm => {
      const key = normalizeEventName(bm.eventName);
      if (!eventGroups.has(key)) eventGroups.set(key, []);
      eventGroups.get(key)!.push(bm);
    });

    const groups: TreVieGroup[] = [];
    const OUTCOMES_3WAY = ["1", "X", "2"];

    eventGroups.forEach(group => {
      if (group.length < 2) return;

      // Ensure this event actually has 3-way odds
      const sampleOdds = group[0].odds;
      if (!("1" in sampleOdds) || !("X" in sampleOdds) || !("2" in sampleOdds)) return;

      // Find best odds per outcome
      const bestForOutcome: Record<string, { odds: number; bookmaker: string } | null> = {
        "1": null, "X": null, "2": null,
      };
      for (const outcome of OUTCOMES_3WAY) {
        for (const bm of group) {
          const o = bm.odds[outcome];
          if (o && o > 1) {
            if (!bestForOutcome[outcome] || o > bestForOutcome[outcome]!.odds) {
              bestForOutcome[outcome] = { odds: o, bookmaker: bm.bookmaker };
            }
          }
        }
      }

      // All three outcomes must have valid odds
      if (OUTCOMES_3WAY.some(o => !bestForOutcome[o])) return;

      // If principale is specified, it must appear in at least one leg
      if (tvMain) {
        const mainLower = tvMain.toLowerCase();
        const appearsInLeg = OUTCOMES_3WAY.some(o => {
          const bm = bestForOutcome[o]!.bookmaker.toLowerCase();
          return bm.includes(mainLower) || mainLower.includes(bm);
        });
        if (!appearsInLeg) return;
      }

      const margin = OUTCOMES_3WAY.reduce((sum, o) => sum + 1 / bestForOutcome[o]!.odds, 0);
      const rating = (1 / margin) * 100;

      if (rating > 85 && rating < 120) {
        groups.push({
          eventTime: group[0].eventTime,
          sport: "calcio",
          eventName: cleanEventName(group[0].eventName),
          league: group[0].league,
          market: "1X2",
          rating,
          legs: OUTCOMES_3WAY.map(o => ({
            outcome: o,
            bookmaker: bestForOutcome[o]!.bookmaker,
            odds: bestForOutcome[o]!.odds,
          })),
        });
      }
    });

    return groups.sort((a, b) => b.rating - a.rating);
  }, [data, committedFilters.trevieMain, committedFilters.trevieSecondary]);

  // ═══ BEST ODDS ═══
  const bestOddsRows = useMemo(() => {
    if (!data?.data || data.data.length === 0) return [];
    const rows: BestOddsRow[] = [];
    const bookmakerOdds = data.data.filter(odd => !isExchange(odd.bookmaker));

    const eventGroups = new Map<string, OddsData[]>();
    bookmakerOdds.forEach(bm => {
      const key = normalizeEventName(bm.eventName) + "|" + bm.market;
      if (!eventGroups.has(key)) eventGroups.set(key, []);
      eventGroups.get(key)!.push(bm);
    });

    eventGroups.forEach(group => {
      const outcomes = getOutcomes(group[0]);
      for (const outcome of outcomes) {
        const oddsForOutcome: Array<{ bookmaker: string; odds: number }> = [];
        for (const bm of group) {
          const o = bm.odds[outcome.key];
          if (o && o > 1) oddsForOutcome.push({ bookmaker: bm.bookmaker, odds: o });
        }
        if (oddsForOutcome.length === 0) continue;
        oddsForOutcome.sort((a, b) => b.odds - a.odds);

        rows.push({
          eventTime: group[0].eventTime,
          sport: group[0].sport || "calcio",
          eventName: cleanEventName(group[0].eventName),
          league: group[0].league,
          outcome: outcome.label,
          market: group[0].market,
          bestBookmaker: oddsForOutcome[0].bookmaker,
          bestOdds: oddsForOutcome[0].odds,
          worstBookmaker: oddsForOutcome[oddsForOutcome.length - 1].bookmaker,
          worstOdds: oddsForOutcome[oddsForOutcome.length - 1].odds,
          allOdds: oddsForOutcome,
        });
      }
    });

    return rows.sort((a, b) => b.bestOdds - a.bestOdds);
  }, [data]);

  // ═══ BEST OPPOSITE ═══
  const bestOppositeRows = useMemo(() => {
    if (!data?.data || data.data.length === 0) return [];
    const rows: Array<{
      eventTime: string; sport: string; eventName: string; league: string;
      outcome1: string; book1: string; odds1: number;
      outcome2: string; book2: string; odds2: number;
      margin: number;
    }> = [];

    const bookmakerOdds = data.data.filter(odd => !isExchange(odd.bookmaker));
    const eventGroups = new Map<string, OddsData[]>();
    bookmakerOdds.forEach(bm => {
      const key = normalizeEventName(bm.eventName) + "|" + bm.market;
      if (!eventGroups.has(key)) eventGroups.set(key, []);
      eventGroups.get(key)!.push(bm);
    });

    eventGroups.forEach(group => {
      if (group.length < 2) return;
      const outcomes = getOutcomes(group[0]);
      if (outcomes.length < 2) return;

      for (let a = 0; a < outcomes.length; a++) {
        for (let b = a + 1; b < outcomes.length; b++) {
          let bestA = { odds: 0, book: "" };
          let bestB = { odds: 0, book: "" };
          for (const bm of group) {
            const oA = bm.odds[outcomes[a].key];
            const oB = bm.odds[outcomes[b].key];
            if (oA && oA > bestA.odds) bestA = { odds: oA, book: bm.bookmaker };
            if (oB && oB > bestB.odds) bestB = { odds: oB, book: bm.bookmaker };
          }
          if (bestA.odds <= 1 || bestB.odds <= 1) continue;

          const margin = (1 / bestA.odds + 1 / bestB.odds) * 100;

          rows.push({
            eventTime: group[0].eventTime,
            sport: group[0].sport || "calcio",
            eventName: cleanEventName(group[0].eventName),
            league: group[0].league,
            outcome1: outcomes[a].label,
            book1: bestA.book,
            odds1: bestA.odds,
            outcome2: outcomes[b].label,
            book2: bestB.book,
            odds2: bestB.odds,
            margin,
          });
        }
      }
    });

    return rows.sort((a, b) => a.margin - b.margin).slice(0, 200);
  }, [data]);

  const applyFilters = <T extends { eventName: string; bookmaker?: string; quotaBook?: number }>(items: T[]): T[] => {
    let result = items;
    // Usa committedFilters (snapshot al momento dell'ultimo Aggiorna)
    if (committedFilters.bookmaker.length > 0) {
      result = result.filter(opp => {
        const book = (opp as any).bookmaker || (opp as any).bestBookmaker || "";
        return committedFilters.bookmaker.some(bm =>
          book.toLowerCase().includes(bm.toLowerCase()) ||
          bm.toLowerCase().includes(book.toLowerCase())
        );
      });
    }
    const qMin = parseFloat((committedFilters.quotaMinima || "0").replace(",", "."));
    const qMax = parseFloat((committedFilters.quotaMassima || "0").replace(",", "."));
    const qField = (item: any) => item.quotaBook || item.bestOdds || item.odds1 || 0;
    if (qMin > 0) result = result.filter(o => qField(o) >= qMin);
    if (qMax > 0) result = result.filter(o => qField(o) <= qMax);
    if (committedFilters.partita) {
      const search = committedFilters.partita.toLowerCase();
      result = result.filter(o => o.eventName.toLowerCase().includes(search));
    }
    // Filtro liquidità: mostra solo opportunità con volume exchange >= lay stake calcolato
    if (committedFilters.filtroLiquidita) {
      const stake = parseFloat((committedFilters.stakePunta || "0").replace(",", ".")) || 0;
      const bonus = parseFloat((committedFilters.bonus || "0").replace(",", ".")) || 0;
      const totalStake = stake + bonus;
      const c = commission / 100;
      result = result.filter(o => {
        const opp = o as any;
        // Applica solo in modalità back-lay (non punta-punta) e se c'è il volume
        if (opp.isBookVsBook || opp.volumeExchange == null) return true;
        const backOdds: number = opp.quotaBook;
        const layOdds: number = opp.quotaExchange;
        if (!backOdds || !layOdds || layOdds <= c) return true;
        // Se lo stake è 0, filtra almeno per volume minimo di 10€
        const effectiveStake = totalStake > 0 ? totalStake : 10;
        const isFB = committedFilters.freebet;
        const layStake = isFB
          ? (effectiveStake * (backOdds - 1)) / (layOdds - c)
          : (effectiveStake * backOdds) / (layOdds - c);
        return opp.volumeExchange >= layStake;
      });
    }
    return result;
  };

  const formatDate = (dateString: string) => {
    try {
      const d = new Date(dateString);
      return `${d.getDate().toString().padStart(2, "0")}/${(d.getMonth() + 1).toString().padStart(2, "0")}/${d.getFullYear()} ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
    } catch { return dateString; }
  };

  const getSportIcon = (sport: string) => {
    switch (sport.toLowerCase()) {
      case "calcio": case "soccer": case "football": return "⚽";
      case "tennis": return "🎾";
      case "basket": case "basketball": return "🏀";
      default: return "⚽";
    }
  };

  const getLeagueFlag = (league: string): string => {
    const l = league.toLowerCase();
    if (l.includes("serie a") || l.includes("serie b") || l.includes("coppa italia")) return "🇮🇹";
    if (l.includes("premier") || l.includes("championship") || l.includes("fa cup") || l.includes("league one") || l.includes("league two")) return "🏴󠁧󠁢󠁥󠁮󠁧󠁿";
    if (l.includes("laliga") || l.includes("la liga") || l.includes("segunda")) return "🇪🇸";
    if (l.includes("bundesliga") || l.includes("bundesliga 2")) return "🇩🇪";
    if (l.includes("ligue 1") || l.includes("ligue 2")) return "🇫🇷";
    if (l.includes("champions") || l.includes("europa league") || l.includes("conference")) return "🇪🇺";
    if (l.includes("nba")) return "🇺🇸";
    if (l.includes("atp") || l.includes("wta")) return "🌍";
    if (l.includes("eredivisie") || l.includes("olanda")) return "🇳🇱";
    if (l.includes("primeira") || l.includes("portogallo")) return "🇵🇹";
    if (l.includes("super lig") || l.includes("turchia")) return "🇹🇷";
    return "🏳";
  };

  if (loading) {
    return (
      <div className="text-center py-12 text-white">
        <div className="animate-spin inline-block w-6 h-6 border-2 border-[#c8922d] border-t-transparent rounded-full mb-2"></div>
        <div>Caricamento quote...</div>
      </div>
    );
  }

  if (!data?.data || data.data.length === 0) {
    return (
      <div className="text-center py-12 text-white">
        {data === null ? "Clicca AGGIORNA per caricare le quote." : "Nessuna quota trovata nel database."}
      </div>
    );
  }

  const hasExchangeData = data.data.some(d => isExchange(d.bookmaker));

  // ═══ RENDER: SINGOLA ═══
  if (activeTab === "singola") {
    const filtered = applyFilters(singolaOpps).slice(0, 1000);
    if (filtered.length === 0) {
      return (
        <div className="text-center py-12 text-white">
          {isPuntaPuntaMode
            ? "Nessuna opportunità punta-punta trovata con rating tra 85% e 105%."
            : "Nessuna opportunità trovata. Seleziona i Bookmaker come counter per la modalità Punta-Punta."}
        </div>
      );
    }
    return renderOpportunityTable(filtered, isPuntaPuntaMode);
  }

  // ═══ RENDER: TRE VIE ═══
  if (activeTab === "trevie") {
    // Apply filters
    let tvFiltered = trevieOpps;
    if (committedFilters.partita) {
      const search = committedFilters.partita.toLowerCase();
      tvFiltered = tvFiltered.filter(g => g.eventName.toLowerCase().includes(search));
    }
    if (committedFilters.daData) {
      const from = new Date(committedFilters.daData).getTime();
      tvFiltered = tvFiltered.filter(g => new Date(g.eventTime).getTime() >= from);
    }
    if (committedFilters.aData) {
      const to = new Date(committedFilters.aData + "T23:59:59").getTime();
      tvFiltered = tvFiltered.filter(g => new Date(g.eventTime).getTime() <= to);
    }
    tvFiltered = tvFiltered.slice(0, 200);

    if (tvFiltered.length === 0) {
      return (
        <div className="text-center py-12 text-white">
          Nessuna opportunit&agrave; tre vie trovata. Prova a cambiare i filtri o clicca Aggiorna.
        </div>
      );
    }

    // Stake totale per calcolo Dutch
    const tvStake = parseFloat((committedFilters.stakePunta || "0").replace(",", "."))
                  + parseFloat((committedFilters.bonus || "0").replace(",", "."));
    const tvHasStake = tvStake > 0;

    // Sort by day ASC then rating DESC
    const tvSorted = [...tvFiltered].sort((a, b) => {
      const da = a.eventTime.slice(0, 10);
      const db = b.eventTime.slice(0, 10);
      if (da !== db) return da < db ? -1 : 1;
      return b.rating - a.rating;
    });

    // Group by day
    const tvDayGroups: { date: string; groups: TreVieGroup[] }[] = [];
    for (const g of tvSorted) {
      const date = g.eventTime.slice(0, 10);
      const last = tvDayGroups[tvDayGroups.length - 1];
      if (!last || last.date !== date) tvDayGroups.push({ date, groups: [g] });
      else last.groups.push(g);
    }

    const formatDayLabel = (dateStr: string) => {
      const d = new Date(dateStr + "T12:00:00");
      return d.toLocaleDateString("it-IT", { weekday: "short", day: "numeric", month: "short" });
    };

    const colCount = tvHasStake ? 9 : 8;

    return (
      <>
        {/* Day selector strip */}
        {tvDayGroups.length > 1 && (
          <div className="flex flex-wrap gap-1.5 px-3 py-2 bg-[#080c17] border-b border-[#1e3050]">
            {tvDayGroups.map(({ date, groups: dg }) => (
              <button
                key={date}
                onClick={() => {
                  const el = document.getElementById(`tvday-${date}`);
                  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
                }}
                className="px-3 py-1 rounded text-xs font-semibold bg-[#1e2d42] text-white hover:bg-[#2a4060] transition-colors whitespace-nowrap border border-[#2a3f5c]"
              >
                {formatDayLabel(date)}
                <span className="ml-1.5 text-[10px] opacity-60">({dg.length})</span>
              </button>
            ))}
          </div>
        )}

        {/* Back-to-top */}
        <button
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          className="fixed bottom-6 right-6 z-50 w-10 h-10 rounded-full bg-[#87c4e8] text-[#0d2035] flex items-center justify-center shadow-xl hover:bg-[#6ab0d8] transition-colors text-lg font-bold select-none"
          title="Torna in cima"
        >↑</button>

        <div className="text-right text-xs text-white px-4 py-2">{tvFiltered.length} eventi</div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[600px] text-sm border-collapse">
            <thead>
              <tr className="bg-[#0a0e1a] text-white text-[12px] uppercase tracking-wide border-b border-[#1e3050]">
                <th className="text-left py-2 px-2 md:px-3 font-semibold">Data/Ora</th>
                <th className="text-center py-2 px-2 font-semibold">Sport</th>
                <th className="text-left py-2 px-2 md:px-3 font-semibold">Partita</th>
                <th className="text-center py-2 px-2 font-semibold">Nazione</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Rating</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">#</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Bookmaker</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold text-[#87c4e8]">Quota</th>
                {tvHasStake && <th className="text-center py-2 px-2 md:px-3 font-semibold text-[#c8922d]">Stake</th>}
              </tr>
            </thead>
            <tbody>
              {tvDayGroups.map(({ date, groups: dg }) => (
                <>
                  {/* Day divider */}
                  <tr key={`tvdiv-${date}`} id={`tvday-${date}`}>
                    <td colSpan={colCount} className="bg-[#0d1829] border-t-2 border-[#87c4e8] py-2 px-4">
                      <span className="text-[#87c4e8] font-semibold text-xs uppercase tracking-wider">
                        📅 {formatDayLabel(date)}
                      </span>
                      <span className="ml-2 text-[#4a6a8a] text-xs">
                        {dg.length} {dg.length === 1 ? "evento" : "eventi"}
                      </span>
                    </td>
                  </tr>
                  {dg.map((grp, gi) => {
                    const margin = grp.legs.reduce((s, l) => s + 1 / l.odds, 0);
                    const guaranteed = tvHasStake ? tvStake / margin : 0;
                    const profit = tvHasStake ? guaranteed - tvStake : 0;

                    return grp.legs.map((leg, li) => {
                      const isFirst = li === 0;
                      const isLast = li === grp.legs.length - 1;
                      const bookColor = getBookColor(leg.bookmaker);
                      const legStake = tvHasStake ? guaranteed / leg.odds : 0;
                      const ratingColor = grp.rating >= 100
                        ? "text-green-400" : grp.rating >= 98
                        ? "text-white" : grp.rating >= 95
                        ? "text-[#c8922d]" : "text-red-400";

                      return (
                        <tr
                          key={`tv-${date}-${gi}-${li}`}
                          className={`transition-colors hover:bg-[#1a2535] ${isLast ? "border-b border-[#1e3050]" : "border-b border-[#0d1829]"}`}
                        >
                          {isFirst && (
                            <>
                              <td rowSpan={3} className="py-2 px-3 text-xs text-white whitespace-nowrap align-middle border-r border-[#1e3050]">
                                {formatDate(grp.eventTime)}
                              </td>
                              <td rowSpan={3} className="py-2 px-2 text-center text-base align-middle border-r border-[#1e3050]">
                                {getSportIcon(grp.sport)}
                              </td>
                              <td rowSpan={3} className="py-2 px-3 text-sm text-white font-medium align-middle max-w-[200px] truncate border-r border-[#1e3050]">
                                {grp.eventName}
                              </td>
                              <td rowSpan={3} className="py-2 px-2 text-center text-lg align-middle border-r border-[#1e3050]">
                                {getLeagueFlag(grp.league)}
                              </td>
                              <td rowSpan={3} className="py-2 px-3 text-center align-middle border-r border-[#1e3050]">
                                <span className={`text-sm font-bold ${ratingColor}`}>
                                  {grp.rating.toFixed(2)}%
                                </span>
                                {tvHasStake && (
                                  <div className={`text-xs mt-1 font-semibold ${profit >= 0 ? "text-green-400" : "text-red-400"}`}>
                                    {profit >= 0 ? "+" : ""}{profit.toFixed(2)}€
                                  </div>
                                )}
                              </td>
                            </>
                          )}
                          <td className="py-1.5 px-3 text-center font-bold text-white text-sm">
                            <span className="inline-block px-2 py-0.5 rounded bg-[#1e3050] text-white text-[10px] font-bold whitespace-nowrap">
                              Book {li + 1}
                            </span>
                          </td>
                          <td className="py-1.5 px-3 text-center">
                            <span
                              className="inline-block px-2 py-0.5 rounded text-[11px] font-bold whitespace-nowrap"
                              style={{ backgroundColor: bookColor.bg, color: bookColor.text }}
                            >
                              {leg.bookmaker}
                            </span>
                          </td>
                          <td className="py-1.5 px-3 text-center font-mono text-sm font-bold text-[#0d2035] bg-[#87c4e8]">
                            {leg.odds.toFixed(2).replace(".", ",")}
                          </td>
                          {tvHasStake && (
                            <td className="py-1.5 px-3 text-center text-xs font-mono text-[#c8922d] font-semibold">
                              {legStake.toFixed(2).replace(".", ",")}€
                            </td>
                          )}
                        </tr>
                      );
                    });
                  })}
                </>
              ))}
            </tbody>
          </table>
        </div>
      </>
    );
  }

  // ═══ RENDER: BEST ODDS ═══
  if (activeTab === "bestodds") {
    const filtered = applyFilters(bestOddsRows).slice(0, 200);
    return (
      <div>
        <div className="text-right text-xs text-white px-4 py-2">
          {filtered.length} risultati
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] text-sm">
            <thead>
              <tr className="bg-[#0a0e1a] text-white text-[12px] uppercase tracking-wide border-b border-[#1e3050]">
                <th className="text-left py-2 px-2 md:px-3 font-semibold">Data/Ora</th>
                <th className="text-center py-2 px-2 font-semibold">Sport</th>
                <th className="text-left py-2 px-2 md:px-3 font-semibold">Partita</th>
                <th className="text-center py-2 px-2 font-semibold">Nazione</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Mercato</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Esito</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Miglior Book</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold text-[#87c4e8]">Quota Max</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Peggior Book</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold text-[#f4a9ba]">Quota Min</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Diff</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e3050]">
              {filtered.map((row, i) => {
                const bestColor = getBookColor(row.bestBookmaker);
                const worstColor = getBookColor(row.worstBookmaker);
                const diff = ((row.bestOdds - row.worstOdds) / row.worstOdds * 100).toFixed(1);
                return (
                  <tr key={i} className="hover:bg-[#1e2d42] transition-colors">
                    <td className="py-2 px-3 text-xs text-white whitespace-nowrap">{formatDate(row.eventTime)}</td>
                    <td className="py-2 px-2 text-center text-base">{getSportIcon(row.sport)}</td>
                    <td className="py-2 px-3 text-sm text-white font-medium max-w-[220px] truncate">{row.eventName}</td>
                    <td className="py-2 px-2 text-center text-lg">{getLeagueFlag(row.league)}</td>
                    <td className="py-2 px-3 text-center text-xs text-white">{row.market}</td>
                    <td className="py-2 px-3 text-center text-sm font-medium text-white">{row.outcome}</td>
                    <td className="py-2 px-3 text-center">
                      <span className="inline-block px-2 py-0.5 rounded text-[11px] font-bold" style={{ backgroundColor: bestColor.bg, color: bestColor.text }}>{row.bestBookmaker}</span>
                    </td>
                    <td className="py-2 px-3 text-center font-mono text-sm font-bold text-[#0d2035] bg-[#87c4e8]">{row.bestOdds.toFixed(2).replace(".", ",")}</td>
                    <td className="py-2 px-3 text-center">
                      <span className="inline-block px-2 py-0.5 rounded text-[11px] font-bold" style={{ backgroundColor: worstColor.bg, color: worstColor.text }}>{row.worstBookmaker}</span>
                    </td>
                    <td className="py-2 px-3 text-center font-mono text-sm text-[#2d0d1a] bg-[#f4a9ba]">{row.worstOdds.toFixed(2).replace(".", ",")}</td>
                    <td className="py-2 px-3 text-center text-xs font-medium text-[#c8922d]">+{diff}%</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // ═══ RENDER: BEST OPPOSITE ═══
  if (activeTab === "bestopposite") {
    const filtered = applyFilters(bestOppositeRows as any).slice(0, 200);
    return (
      <div>
        <div className="text-right text-xs text-white px-4 py-2">
          {filtered.length} risultati &middot; Margine pi&ugrave; basso = migliore opportunit&agrave;
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] text-sm">
            <thead>
              <tr className="bg-[#0a0e1a] text-white text-[12px] uppercase tracking-wide border-b border-[#1e3050]">
                <th className="text-left py-2 px-2 md:px-3 font-semibold">Data/Ora</th>
                <th className="text-center py-2 px-2 font-semibold">Sport</th>
                <th className="text-left py-2 px-2 md:px-3 font-semibold">Partita</th>
                <th className="text-center py-2 px-2 font-semibold">Nazione</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Scommessa 1</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Scommessa 2</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Margine</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Bookmaker 1</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold text-[#87c4e8]">Quota 1</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Bookmaker 2</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold text-[#f4a9ba]">Quota 2</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e3050]">
              {(filtered as typeof bestOppositeRows).map((row, i) => {
                const c1 = getBookColor(row.book1);
                const c2 = getBookColor(row.book2);
                return (
                  <tr key={i} className="hover:bg-[#1e2d42] transition-colors">
                    <td className="py-2 px-3 text-xs text-white whitespace-nowrap">{formatDate(row.eventTime)}</td>
                    <td className="py-2 px-2 text-center text-base">{getSportIcon(row.sport)}</td>
                    <td className="py-2 px-3 text-sm text-white font-medium max-w-[200px] truncate">{row.eventName}</td>
                    <td className="py-2 px-2 text-center text-lg">{getLeagueFlag(row.league)}</td>
                    <td className="py-2 px-3 text-center text-sm font-medium text-white">{row.outcome1}</td>
                    <td className="py-2 px-3 text-center text-sm font-medium text-white">{row.outcome2}</td>
                    <td className="py-2 px-3 text-center">
                      <span className={`text-sm font-bold ${row.margin < 100 ? "text-green-400" : "text-red-400"}`}>
                        {row.margin.toFixed(1)}%
                      </span>
                    </td>
                    <td className="py-2 px-3 text-center">
                      <span className="inline-block px-2 py-0.5 rounded text-[11px] font-bold whitespace-nowrap" style={{ backgroundColor: c1.bg, color: c1.text }}>{row.book1}</span>
                    </td>
                    <td className="py-2 px-3 text-center font-mono text-sm font-bold text-[#0d2035] bg-[#87c4e8]">{row.odds1.toFixed(2).replace(".", ",")}</td>
                    <td className="py-2 px-3 text-center">
                      <span className="inline-block px-2 py-0.5 rounded text-[11px] font-bold whitespace-nowrap" style={{ backgroundColor: c2.bg, color: c2.text }}>{row.book2}</span>
                    </td>
                    <td className="py-2 px-3 text-center font-mono text-sm font-bold text-[#2d0d1a] bg-[#f4a9ba]">{row.odds2.toFixed(2).replace(".", ",")}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // ═══ RENDER: MULTIPLA ═══
  if (activeTab === "multipla") {
    let multiplaOpps = singolaOpps.filter(o => o.sport === "calcio");
    const numEventiTarget = parseInt(filters.numEventi || "0") || 0;

    const qpMin = parseFloat((filters.quotaPartitaMinima || "0").replace(",", "."));
    const qpMax = parseFloat((filters.quotaPartitaMassima || "0").replace(",", "."));
    if (qpMin > 0) multiplaOpps = multiplaOpps.filter(o => o.quotaBook >= qpMin);
    if (qpMax > 0) multiplaOpps = multiplaOpps.filter(o => o.quotaBook <= qpMax);

    if (filters.daData) {
      const from = new Date(filters.daData).getTime();
      multiplaOpps = multiplaOpps.filter(o => new Date(o.eventTime).getTime() >= from);
    }
    if (filters.aData) {
      const to = new Date(filters.aData + "T23:59:59").getTime();
      multiplaOpps = multiplaOpps.filter(o => new Date(o.eventTime).getTime() <= to);
    }

    // Per multipla: applica solo filtro bookmaker, partita e liquidità — NO quota min/max
    // (multipla ha i propri filtri quotaPartitaMinima/Massima già applicati sopra)
    const filtered = (() => {
      let r = multiplaOpps;
      // Bookmaker filter
      if (committedFilters.bookmaker.length > 0) {
        r = r.filter(opp =>
          committedFilters.bookmaker.some(bm =>
            opp.bookmaker.toLowerCase().includes(bm.toLowerCase()) ||
            bm.toLowerCase().includes(opp.bookmaker.toLowerCase())
          )
        );
      }
      // Partita filter
      if (committedFilters.partita) {
        const search = committedFilters.partita.toLowerCase();
        r = r.filter(o => o.eventName.toLowerCase().includes(search));
      }
      // Liquidità: usa stakeMultipla se disponibile, altrimenti stakePunta
      if (committedFilters.filtroLiquidita) {
        const stakeRaw = committedFilters.stakeMultipla || committedFilters.stakePunta || "0";
        const stake = parseFloat(stakeRaw.replace(",", ".")) || 0;
        const bonus = parseFloat((committedFilters.bonus || "0").replace(",", ".")) || 0;
        const totalStake = stake + bonus;
        const effectiveStake = totalStake > 0 ? totalStake : 10;
        const c = commission / 100;
        r = r.filter(opp => {
          if (opp.isBookVsBook || opp.volumeExchange == null) return true;
          if (!opp.quotaBook || !opp.quotaExchange || opp.quotaExchange <= c) return true;
          const isFB = committedFilters.freebet;
          const layStake = isFB
            ? (effectiveStake * (opp.quotaBook - 1)) / (opp.quotaExchange - c)
            : (effectiveStake * opp.quotaBook) / (opp.quotaExchange - c);
          return opp.volumeExchange >= layStake;
        });
      }
      return r;
    })().slice(0, 200);

    if (filtered.length === 0) {
      return (
        <div className="text-center py-12 text-white">
          Nessuna opportunità trovata. Clicca <strong>Aggiorna</strong> per caricare i dati.
        </div>
      );
    }

    const oppKey = (o: Opportunity) => `${o.eventName}|${o.scommessa}|${o.bookmaker}`;

    // Solo gli eventi selezionati che sono ancora visibili nella lista filtrata corrente.
    // Se l'utente cambia filtri o aggiorna, gli eventi spariti dalla tabella non vengono
    // contati anche se erano in stato "selezionato".
    const effectiveSelected = multiplaSelected.filter(o =>
      filtered.some(f => oppKey(f) === oppKey(o))
    );

    const toggleMultipla = (opp: Opportunity) => {
      setMultiplaSelected(prev => {
        const key = oppKey(opp);
        const exists = prev.some(o => oppKey(o) === key);
        if (exists) return prev.filter(o => oppKey(o) !== key);
        // Conta solo le selezioni visibili nella lista corrente (ignora i "fantasma")
        const visibleCount = prev.filter(o => filtered.some(f => oppKey(f) === oppKey(o))).length;
        if (numEventiTarget > 0 && visibleCount >= numEventiTarget) return prev;
        return [...prev, opp];
      });
    };

    // ── Calcoli sommario ──
    const stakeBase = parseFloat(filters.stakeMultipla || filters.stakePunta || "0") || 0;
    const bonusVal  = parseFloat(filters.bonus || "0") || 0;
    const stake     = stakeBase + bonusVal;   // stake totale = puntata + eventuale bonus
    const hasStake  = stake > 0;              // mostra calcoli solo se c'è uno stake
    const isFB      = filters.freebet;        // free bet: non si recupera lo stake
    const c = commission / 100;
    const n = effectiveSelected.length;
    const quotaTotale = effectiveSelected.reduce((acc, o) => acc * o.quotaBook, 1);
    const ratingMultipla = n > 0 ? effectiveSelected.reduce((acc, o) => acc + o.rating, 0) / n : 0;

    // Per ogni gamba: lay stake, liability, ritorno lay garantito
    // stake = stakeBase + bonusVal (totale da coprire)
    const perLeg = effectiveSelected.map(o => {
      const layStake  = isFB
        ? (stake * (o.quotaBook - 1)) / (o.quotaExchange - c)
        : (stake * o.quotaBook)       / (o.quotaExchange - c);
      const liability = layStake * (o.quotaExchange - 1);
      const layReturn = layStake * (1 - c);
      return { layStake, liability, layReturn };
    });
    const responsabilitaTotale = perLeg.reduce((acc, l) => acc + l.liability, 0);

    // ── Risultato GARANTITO per gamba ──
    // In una multipla hai UNA sola scommessa da <stake>.
    // Quando una gamba fallisce (la multipla muore), incassi il layReturn di QUELLA gamba
    // e perdi la posta. Le altre gambe si cancellano a vicenda (una copre l'altra).
    // Risultato garantito ≈ layReturn_medio_per_gamba − stakeBase
    //   • soldi propri:  layReturn − stake   → piccola perdita (commissione+margine)
    //   • solo bonus:    layReturn − 0       → vincita garantita (non hai speso niente)
    //   • free bet:      layReturn_FB − 0    → vincita ridotta (~40-60% del bonus)
    const avgLayReturn = n > 0 ? perLeg.reduce((acc, l) => acc + l.layReturn, 0) / n : 0;
    const risultatoFinale = avgLayReturn - stakeBase;

    const ready = numEventiTarget > 0 && n === numEventiTarget;

    const fmtEur = (v: number) => {
      const sign = v >= 0 ? "+" : "-";
      return `${sign}${Math.abs(v).toFixed(2).replace(".", ",")}€`;
    };

    return (
      <>
        {/* ── Barra riepilogo ── */}
        {n > 0 && hasStake && (
          <div className="bg-[#0a0e1a] border-b border-[#1e3050] px-6 py-3 flex flex-wrap items-center gap-6 text-sm">
            <span className="text-white">
              Rating Multipla →{" "}
              <span className={`font-bold ${ratingMultipla >= 100 ? "text-green-400" : ratingMultipla >= 95 ? "text-[#c8922d]" : "text-red-400"}`}>
                {ratingMultipla.toFixed(2).replace(".", ",")}%
              </span>
            </span>
            <span className="text-white">
              Quota Totale →{" "}
              <span className="font-bold text-white">{quotaTotale.toFixed(2).replace(".", ",")}</span>
            </span>
            <span className="text-white">
              Responsabilità →{" "}
              <span className="font-bold text-white">{responsabilitaTotale.toFixed(2).replace(".", ",")}€</span>
            </span>
            <span className="text-white">
              Risultato garantito →{" "}
              <span className={`font-bold text-base ${risultatoFinale >= 0 ? "text-green-400" : "text-red-400"}`}>
                {fmtEur(risultatoFinale)}
              </span>
            </span>
            {bonusVal > 0 && (
              <span className="text-xs text-[#c8922d]">
                {stakeBase.toFixed(2)}€ stake + {bonusVal.toFixed(2)}€ bonus{isFB ? " (Free Bet)" : ""}
              </span>
            )}
            <button
              onClick={() => setMultiplaSelected([])}
              className="ml-auto text-xs text-slate-400 hover:text-white border border-[#253347] px-2 py-1 rounded"
            >
              Azzera ✕
            </button>
          </div>
        )}

        {/* ── Contatore selezione ── */}
        <div className={`px-4 py-2 text-xs border-b border-[#1e3050] flex items-center gap-3 ${ready ? "bg-green-900/30" : "bg-[#0d1829]"}`}>
          <span className="text-slate-400">👆 Clicca una riga per aggiungerla alla multipla</span>
          {numEventiTarget > 0 && (
            <span className="text-white font-semibold">
              Selezionati:{" "}
              <span className={`font-bold ${ready ? "text-green-400" : "text-[#c8922d]"}`}>
                {n}/{numEventiTarget}
              </span>
            </span>
          )}
          {numEventiTarget === 0 && n > 0 && (
            <span className="text-[#c8922d] font-semibold">{n} selezionati</span>
          )}
          {n > 0 && (
            <button
              onClick={() => setMultiplaSelected([])}
              className="ml-auto text-xs text-slate-400 hover:text-white border border-[#253347] px-2 py-0.5 rounded"
            >
              Azzera ✕
            </button>
          )}
        </div>

        {/* ── Tabella ── */}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] text-sm">
            <thead>
              <tr className="bg-[#0a0e1a] text-white text-[12px] uppercase tracking-wide border-b border-[#1e3050]">
                <th className="text-left py-2 px-2 md:px-3 font-semibold">Data/Ora</th>
                <th className="text-center py-2 px-2 font-semibold">Sport</th>
                <th className="text-left py-2 px-2 md:px-3 font-semibold">Partita</th>
                <th className="text-center py-2 px-2 font-semibold">Nazione</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Competizione</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Scommessa</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Rating</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Bookmaker</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold text-[#87c4e8]">Quota</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Exchange</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold text-[#f4a9ba]">Quota</th>
                <th className="hidden md:table-cell text-center py-2 px-2 md:px-3 font-semibold text-[#f4a9ba]">Liquidità</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e3050]">
              {filtered.map((opp, i) => {
                const key = oppKey(opp);
                const isSelected = effectiveSelected.some(o => oppKey(o) === key);
                const isFull = numEventiTarget > 0 && n >= numEventiTarget && !isSelected;
                const bookColor = getBookColor(opp.bookmaker);
                const exchColor = getBookColor(opp.exchange);
                const sc = opp.scommessa.split(" vs ")[0] ?? opp.scommessa;
                const ratingColor = opp.rating >= 100
                  ? "text-green-400" : opp.rating >= 95 ? "text-[#c8922d]" : "text-slate-300";

                return (
                  <tr
                    key={i}
                    onClick={() => !isFull && toggleMultipla(opp)}
                    className={`transition-colors ${
                      isSelected
                        ? "bg-[#193d1c] border-l-4 border-green-500 cursor-pointer"
                        : isFull
                          ? "opacity-40 cursor-not-allowed"
                          : "hover:bg-[#1a2535] cursor-pointer border-l-4 border-transparent"
                    }`}
                  >
                    <td className="py-2 px-3 text-white text-xs whitespace-nowrap">
                      <span className="mr-1">{isSelected ? "✅" : ""}</span>
                      {formatDate(opp.eventTime)}
                    </td>
                    <td className="py-2 px-2 text-center text-base">{getSportIcon(opp.sport)}</td>
                    <td className="py-2 px-3 text-white font-medium max-w-[180px] truncate">{opp.eventName}</td>
                    <td className="py-2 px-2 text-center text-lg">{getLeagueFlag(opp.league)}</td>
                    <td className="py-2 px-3 text-center text-xs text-slate-300">{opp.league}</td>
                    <td className="py-2 px-3 text-center">
                      <span className="inline-block bg-[#87c4e8] text-[#0d2035] text-xs font-bold px-2 py-0.5 rounded">{sc}</span>
                    </td>
                    <td className="py-2 px-3 text-center">
                      <span className={`text-sm font-bold ${ratingColor}`}>{opp.rating.toFixed(2)}%</span>
                    </td>
                    <td className="py-2 px-3 text-center">
                      <span className="inline-block px-2 py-0.5 rounded text-[11px] font-bold whitespace-nowrap" style={{ backgroundColor: bookColor.bg, color: bookColor.text }}>
                        {opp.bookmaker}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-center font-mono text-sm font-bold text-[#0d2035] bg-[#87c4e8]">
                      {opp.quotaBook.toFixed(2).replace(".", ",")}
                    </td>
                    <td className="py-2 px-3 text-center">
                      <span className="inline-block px-2 py-0.5 rounded text-[11px] font-bold whitespace-nowrap" style={{ backgroundColor: exchColor.bg, color: exchColor.text }}>
                        {opp.exchange}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-center font-mono text-sm text-[#2d0d1a] bg-[#f4a9ba]">
                      {opp.quotaExchange.toFixed(2).replace(".", ",")}
                    </td>
                    <td className="hidden md:table-cell py-2 px-3 text-center text-xs font-mono text-[#f4a9ba]">
                      {opp.volumeExchange != null ? formatVolume(opp.volumeExchange) : <span className="opacity-30">—</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </>
    );
  }

  return null;

  // Format volume: €1.234 / €12.3K / €1.2M
  function formatVolume(v: number | undefined): string {
    if (v == null) return "";
    if (v >= 1_000_000) return `€${(v / 1_000_000).toFixed(1)}M`;
    if (v >= 1_000) return `€${(v / 1_000).toFixed(1)}K`;
    return `€${Math.round(v)}`;
  }

  // ═══ Helper: render opportunity table ═══
  function renderOpportunityTable(opps: Opportunity[], isBookVsBook: boolean) {
    const showVolume = !isBookVsBook; // volume only in back-lay mode
    const colSpan = showVolume ? 11 : 10;

    // Sort: date ASC → rating DESC
    const sorted = [...opps].sort((a, b) => {
      const da = a.eventTime.slice(0, 10);
      const db = b.eventTime.slice(0, 10);
      if (da !== db) return da < db ? -1 : 1;
      return b.rating - a.rating;
    });

    // Group by date
    const dayGroups: { date: string; opps: Opportunity[] }[] = [];
    for (const opp of sorted) {
      const date = opp.eventTime.slice(0, 10);
      const last = dayGroups[dayGroups.length - 1];
      if (!last || last.date !== date) {
        dayGroups.push({ date, opps: [opp] });
      } else {
        last.opps.push(opp);
      }
    }

    // Italian day label: "Mer 14 Mag"
    const formatDayLabel = (dateStr: string) => {
      const d = new Date(dateStr + "T12:00:00");
      return d.toLocaleDateString("it-IT", { weekday: "short", day: "numeric", month: "short" });
    };

    return (
      <>
      {selectedOpp && (
        <PuntaBancaModal
          opp={selectedOpp}
          commission={commission}
          onClose={() => setSelectedOpp(null)}
          initialBonus={parseFloat(filters.bonus) || 0}
          initialStake={filters.stakePunta === "" ? 0 : (parseFloat(filters.stakePunta) || 0)}
          initialFreeBet={filters.freebet}
          initialRimborso={filters.rimborso}
        />
      )}

      {/* ── Day selector strip ── */}
      {dayGroups.length > 1 && (
        <div className="flex flex-wrap gap-1.5 px-3 py-2 bg-[#080c17] border-b border-[#1e3050]">
          {dayGroups.map(({ date, opps: dayOpps }) => (
            <button
              key={date}
              onClick={() => {
                const el = document.getElementById(`day-${date}`);
                if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
              className="px-3 py-1 rounded text-xs font-semibold bg-[#1e2d42] text-white hover:bg-[#2a4060] transition-colors whitespace-nowrap border border-[#2a3f5c]"
            >
              {formatDayLabel(date)}
              <span className="ml-1.5 text-[10px] opacity-60">({dayOpps.length})</span>
            </button>
          ))}
        </div>
      )}

      {/* ── Back-to-top floating button ── */}
      <button
        onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
        className="fixed bottom-6 right-6 z-50 w-10 h-10 rounded-full bg-[#87c4e8] text-[#0d2035] flex items-center justify-center shadow-xl hover:bg-[#6ab0d8] transition-colors text-lg font-bold select-none"
        title="Torna in cima"
      >
        ↑
      </button>

      <div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] text-sm">
            <thead>
              <tr className="bg-[#0a0e1a] text-white text-[12px] uppercase tracking-wide border-b border-[#1e3050]">
                <th className="text-left py-2 px-2 md:px-3 font-semibold">Data/Ora</th>
                <th className="text-center py-2 px-2 font-semibold">Sport</th>
                <th className="text-left py-2 px-2 md:px-3 font-semibold">Partita</th>
                <th className="text-center py-2 px-2 font-semibold">Nazione</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Scommessa</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Rating</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Bookmaker</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold text-[#87c4e8]">Quota</th>
                <th className="text-center py-2 px-2 md:px-3 font-semibold">Exchange</th>
                <th className={`text-center py-2 px-2 md:px-3 font-semibold ${isBookVsBook ? "text-[#87c4e8]" : "text-[#f4a9ba]"}`}>Quota</th>
                {showVolume && <th className="hidden md:table-cell text-center py-2 px-2 md:px-3 font-semibold text-[#f4a9ba]">Liquidità</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e3050]">
              {dayGroups.map(({ date, opps: dayOpps }) => (
                <>
                  {/* Day divider row */}
                  <tr key={`divider-${date}`} id={`day-${date}`}>
                    <td colSpan={colSpan} className="bg-[#0d1829] border-t-2 border-[#87c4e8] py-2 px-4">
                      <span className="text-[#87c4e8] font-semibold text-xs uppercase tracking-wider">
                        📅 {formatDayLabel(date)}
                      </span>
                      <span className="ml-2 text-[#4a6a8a] text-xs">
                        {dayOpps.length} {dayOpps.length === 1 ? "opportunità" : "opportunità"}
                      </span>
                    </td>
                  </tr>
                  {dayOpps.map((opp, i) => {
                    const bookColor = getBookColor(opp.bookmaker);
                    const exchColor = getBookColor(opp.exchange);
                    const counterQuota = opp.quotaExchange > 0 ? opp.quotaExchange.toFixed(2).replace(".", ",") : "—";
                    return (
                      <tr key={`${date}-${i}`} className="hover:bg-[#1e2d42] transition-colors cursor-pointer" onClick={() => setSelectedOpp(opp)}>
                        <td className="py-2 px-3 text-xs text-white whitespace-nowrap">{formatDate(opp.eventTime)}</td>
                        <td className="py-2 px-2 text-center text-base">{getSportIcon(opp.sport)}</td>
                        <td className="py-2 px-3 text-sm text-white font-medium max-w-[220px] truncate">{opp.eventName}</td>
                        <td className="py-2 px-2 text-center text-lg">{getLeagueFlag(opp.league)}</td>
                        <td className="py-2 px-3 text-center text-sm font-bold text-white">{opp.scommessa}</td>
                        <td className="py-2 px-3 text-center">
                          <span className={`text-sm font-bold ${
                            opp.rating >= 100 ? "text-green-400" :
                            opp.rating >= 98 ? "text-white" :
                            opp.rating >= 95 ? "text-[#c8922d]" :
                            "text-red-400"
                          }`}>
                            {opp.rating.toFixed(2)}%
                          </span>
                        </td>
                        <td className="py-2 px-3 text-center">
                          {opp.bookmakerUrl ? (
                            <a
                              href={opp.bookmakerUrl}
                              target="_blank" rel="noopener noreferrer"
                              onClick={e => e.stopPropagation()}
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold whitespace-nowrap hover:opacity-80 transition-opacity"
                              style={{ backgroundColor: bookColor.bg, color: bookColor.text }}
                            >
                              {opp.bookmaker} <span className="text-[9px] opacity-70">↗</span>
                            </a>
                          ) : (
                            <span className="inline-block px-2 py-0.5 rounded text-[11px] font-bold whitespace-nowrap" style={{ backgroundColor: bookColor.bg, color: bookColor.text }}>
                              {opp.bookmaker}
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-3 text-center font-mono text-sm font-bold text-[#0d2035] bg-[#87c4e8]">{opp.quotaBook.toFixed(2).replace(".", ",")}</td>
                        <td className="py-2 px-3 text-center">
                          {opp.eventId ? (
                            <a
                              href={`https://www.betfair.it/exchange/plus/it/${opp.sport ?? "calcio"}/${opp.eventId}`}
                              target="_blank" rel="noopener noreferrer"
                              onClick={e => e.stopPropagation()}
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold whitespace-nowrap hover:opacity-80 transition-opacity"
                              style={{ backgroundColor: exchColor.bg, color: exchColor.text }}
                            >
                              {opp.exchange} <span className="text-[9px] opacity-70">↗</span>
                            </a>
                          ) : (
                            <span className="inline-block px-2 py-0.5 rounded text-[11px] font-bold whitespace-nowrap" style={{ backgroundColor: exchColor.bg, color: exchColor.text }}>
                              {opp.exchange}
                            </span>
                          )}
                        </td>
                        <td className={`py-2 px-3 text-center font-mono text-sm ${isBookVsBook ? "text-[#0d2035] bg-[#87c4e8]" : "text-[#2d0d1a] bg-[#f4a9ba]"}`}>
                          {counterQuota}
                        </td>
                        {showVolume && (
                          <td className="hidden md:table-cell py-2 px-3 text-center text-xs font-mono text-[#f4a9ba]">
                            {opp.volumeExchange != null ? formatVolume(opp.volumeExchange) : <span className="text-white opacity-30">—</span>}
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      </>
    );
  }
}
