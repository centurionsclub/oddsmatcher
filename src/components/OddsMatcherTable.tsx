import { useMemo, useState } from "react";
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
}

interface Opportunity {
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
  };
  commission: number;
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
  ["eintracht francoforte", "eintracht"], ["eintracht frankfurt", "eintracht"],
  ["bayer leverkusen", "leverkusen"],
  ["stoccarda vfb", "stuttgart"], ["stoccarda", "stuttgart"],
  ["rb lipsia", "leipzig"], ["lipsia", "leipzig"],
  ["siviglia", "sevilla"],
  ["royal antwerp", "antwerp"], ["anversa", "antwerp"],
  ["club bruges", "brugge"], ["bruges", "brugge"],
  ["sporting lisbona", "sporting"], ["sporting cp", "sporting"],
  ["sl benfica", "benfica"],
  ["psv eindhoven", "psv"],
  ["ajax amsterdam", "ajax"],
  ["feyenoord rotterdam", "feyenoord"],
  ["girona fc", "girona"],
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

export function OddsMatcherTable({ data, loading, activeTab, selectedExchanges, filters, commission }: Props) {
  const [selectedOpp, setSelectedOpp] = useState<Opportunity | null>(null);

  const REAL_EXCHANGE_NAMES = ["betfair exchange", "betflag exchange", "smarkets", "betdaq", "matchbook"];

  // Check if a bookmaker name is a real exchange
  const isRealExchange = (name: string) =>
    REAL_EXCHANGE_NAMES.some(ex => name.toLowerCase().includes(ex.toLowerCase()));

  // Check if a bookmaker is selected as exchange side
  const isOnExchangeSide = (name: string): boolean => {
    if (!selectedExchanges || selectedExchanges.length === 0)
      return isRealExchange(name);
    return selectedExchanges.some(ex =>
      name.toLowerCase().includes(ex.toLowerCase()) ||
      ex.toLowerCase().includes(name.toLowerCase())
    );
  };

  // Is punta-punta mode (no real exchanges selected, only bookmakers)
  const isPuntaPuntaMode = !!selectedExchanges && selectedExchanges.length > 0 &&
    !selectedExchanges.some(ex => isRealExchange(ex));

  // ═══ SINGOLA: Book vs Exchange (back-lay) OR Book vs Book (punta-punta) ═══
  const singolaOpps = useMemo(() => {
    if (!data?.data || data.data.length === 0) return [];
    const opps: Opportunity[] = [];
    const commissionRate = commission / 100;
    const isFB = filters.freebet;

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
              if (rating > 75 && rating < 105) {
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
                if (rating > 75 && rating < 105) {
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
            const profitIfWin = (backOdds - 1) - layStake * (bestLayOdds - 1);
            const profitIfLose = isFB
              ? layStake * (1 - commissionRate)          // FreeBet: stake gratis, no -1
              : layStake * (1 - commissionRate) - 1;
            const worstProfit = Math.min(profitIfWin, profitIfLose);
            const rating = 100 + worstProfit * 100;

            if (rating > 70 && rating < 105) {
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
  }, [data, commission, selectedExchanges, isPuntaPuntaMode, filters.freebet]);

  // ═══ TRE VIE: Book vs Book 3-way dutching ═══
  const trevieOpps = useMemo(() => {
    if (!data?.data || data.data.length === 0) return [];
    const opps: Opportunity[] = [];
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

      if (outcomes.length === 2) {
        const [oA, oB] = outcomes;
        let bestA = { odds: 0, book: "" };
        let bestB = { odds: 0, book: "" };
        for (const bm of group) {
          const a = bm.odds[oA.key];
          const b = bm.odds[oB.key];
          if (a && a > bestA.odds) { bestA = { odds: a, book: bm.bookmaker }; }
          if (b && b > bestB.odds) { bestB = { odds: b, book: bm.bookmaker }; }
        }
        if (bestA.odds <= 1 || bestB.odds <= 1) return;

        const margin = 1 / bestA.odds + 1 / bestB.odds;
        const rating = (1 / margin) * 100;

        if (rating > 85 && rating < 105) {
          opps.push({
            eventTime: group[0].eventTime,
            sport: group[0].sport || "calcio",
            eventName: cleanEventName(group[0].eventName),
            league: group[0].league,
            market: group[0].market,
            scommessa: `${oA.label}/${oB.label}`,
            rating,
            bookmaker: bestA.book,
            quotaBook: bestA.odds,
            exchange: bestB.book,
            quotaExchange: bestB.odds,
            isBookVsBook: true,
          });
        }
      }

      if (outcomes.length === 3) {
        const bestForOutcome: Record<string, { odds: number; bookmaker: string }> = {};
        for (const outcome of outcomes) {
          bestForOutcome[outcome.key] = { odds: 0, bookmaker: "" };
          for (const bm of group) {
            const o = bm.odds[outcome.key];
            if (o && o > bestForOutcome[outcome.key].odds) {
              bestForOutcome[outcome.key] = { odds: o, bookmaker: bm.bookmaker };
            }
          }
        }
        if (outcomes.some(o => bestForOutcome[o.key].odds <= 1)) return;

        const margin = outcomes.reduce((sum, o) => sum + 1 / bestForOutcome[o.key].odds, 0);
        const rating = (1 / margin) * 100;

        if (rating > 85 && rating < 105) {
          for (const mainOutcome of outcomes) {
            const mainOdds = bestForOutcome[mainOutcome.key].odds;
            const mainBook = bestForOutcome[mainOutcome.key].bookmaker;
            const otherBooks = outcomes
              .filter(o => o.key !== mainOutcome.key)
              .map(o => bestForOutcome[o.key].bookmaker);
            const uniqueOtherBooks = [...new Set(otherBooks)];

            opps.push({
              eventTime: group[0].eventTime,
              sport: group[0].sport || "calcio",
              eventName: cleanEventName(group[0].eventName),
              league: group[0].league,
              market: group[0].market,
              scommessa: mainOutcome.label,
              rating,
              bookmaker: mainBook,
              quotaBook: mainOdds,
              exchange: uniqueOtherBooks.join(" + "),
              quotaExchange: 0,
              isBookVsBook: true,
            });
          }
        }
      }
    });

    return opps.sort((a, b) => b.rating - a.rating);
  }, [data]);

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
    if (filters.bookmaker.length > 0) {
      result = result.filter(opp => {
        const book = (opp as any).bookmaker || (opp as any).bestBookmaker || "";
        return filters.bookmaker.some(bm =>
          book.toLowerCase().includes(bm.toLowerCase()) ||
          bm.toLowerCase().includes(book.toLowerCase())
        );
      });
    }
    const qMin = parseFloat((filters.quotaMinima || "0").replace(",", "."));
    const qMax = parseFloat((filters.quotaMassima || "0").replace(",", "."));
    const qField = (item: any) => item.quotaBook || item.bestOdds || item.odds1 || 0;
    if (qMin > 0) result = result.filter(o => qField(o) >= qMin);
    if (qMax > 0) result = result.filter(o => qField(o) <= qMax);
    if (filters.partita) {
      const search = filters.partita.toLowerCase();
      result = result.filter(o => o.eventName.toLowerCase().includes(search));
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
    const filtered = applyFilters(singolaOpps).slice(0, 200);
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
    const filtered = applyFilters(trevieOpps).slice(0, 200);
    if (filtered.length === 0) {
      return (
        <div className="text-center py-12 text-white">
          Nessuna opportunit&agrave; tre vie trovata con rating tra 85% e 105%. I dati potrebbero essere non aggiornati.
        </div>
      );
    }
    return renderOpportunityTable(filtered, true);
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
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[#0a0e1a] text-white text-[12px] uppercase tracking-wide border-b border-[#1e3050]">
                <th className="text-left py-2.5 px-3 font-semibold">Data/Ora</th>
                <th className="text-center py-2.5 px-2 font-semibold">Sport</th>
                <th className="text-left py-2.5 px-3 font-semibold">Partita</th>
                <th className="text-center py-2.5 px-2 font-semibold">Nazione</th>
                <th className="text-center py-2.5 px-3 font-semibold">Mercato</th>
                <th className="text-center py-2.5 px-3 font-semibold">Esito</th>
                <th className="text-center py-2.5 px-3 font-semibold">Miglior Book</th>
                <th className="text-center py-2.5 px-3 font-semibold text-[#87c4e8]">Quota Max</th>
                <th className="text-center py-2.5 px-3 font-semibold">Peggior Book</th>
                <th className="text-center py-2.5 px-3 font-semibold text-[#f4a9ba]">Quota Min</th>
                <th className="text-center py-2.5 px-3 font-semibold">Diff</th>
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
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[#0a0e1a] text-white text-[12px] uppercase tracking-wide border-b border-[#1e3050]">
                <th className="text-left py-2.5 px-3 font-semibold">Data/Ora</th>
                <th className="text-center py-2.5 px-2 font-semibold">Sport</th>
                <th className="text-left py-2.5 px-3 font-semibold">Partita</th>
                <th className="text-center py-2.5 px-2 font-semibold">Nazione</th>
                <th className="text-center py-2.5 px-3 font-semibold">Scommessa 1</th>
                <th className="text-center py-2.5 px-3 font-semibold">Scommessa 2</th>
                <th className="text-center py-2.5 px-3 font-semibold">Margine</th>
                <th className="text-center py-2.5 px-3 font-semibold">Bookmaker 1</th>
                <th className="text-center py-2.5 px-3 font-semibold text-[#87c4e8]">Quota 1</th>
                <th className="text-center py-2.5 px-3 font-semibold">Bookmaker 2</th>
                <th className="text-center py-2.5 px-3 font-semibold text-[#f4a9ba]">Quota 2</th>
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

  // ═══ RENDER: MULTIPLA (placeholder) ═══
  if (activeTab === "multipla") {
    return (
      <div className="text-center py-12 text-white">
        <div>La sezione MULTIPLA &egrave; in fase di sviluppo.</div>
        <div className="text-sm mt-1 text-white">Usa le altre tab per trovare opportunit&agrave;.</div>
      </div>
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
      <div>
        <div className="flex items-center justify-between px-4 py-2">
          <span className="text-xs font-medium px-2 py-0.5 rounded" style={{ backgroundColor: isBookVsBook ? "#87c4e820" : "#f4a9ba20", color: isBookVsBook ? "#87c4e8" : "#f4a9ba" }}>
            {isBookVsBook ? "📗 Modalità Punta-Punta" : "📘 Modalità Back-Lay"}
          </span>
          <span className="text-xs text-white">{opps.length} opportunit&agrave;</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[#0a0e1a] text-white text-[12px] uppercase tracking-wide border-b border-[#1e3050]">
                <th className="text-left py-2.5 px-3 font-semibold">Data/Ora</th>
                <th className="text-center py-2.5 px-2 font-semibold">Sport</th>
                <th className="text-left py-2.5 px-3 font-semibold">Partita</th>
                <th className="text-center py-2.5 px-2 font-semibold">Nazione</th>
                <th className="text-center py-2.5 px-3 font-semibold">Scommessa 1</th>
                <th className="text-center py-2.5 px-3 font-semibold">Scommessa 2</th>
                <th className="text-center py-2.5 px-3 font-semibold">Rating</th>
                <th className="text-center py-2.5 px-3 font-semibold">Bookmaker 1</th>
                <th className="text-center py-2.5 px-3 font-semibold text-[#87c4e8]">Quota 1</th>
                <th className="text-center py-2.5 px-3 font-semibold">Bookmaker 2</th>
                <th className={`text-center py-2.5 px-3 font-semibold ${isBookVsBook ? "text-[#87c4e8]" : "text-[#f4a9ba]"}`}>Quota 2</th>
                {showVolume && <th className="text-center py-2.5 px-3 font-semibold text-[#f4a9ba]">Volume</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e3050]">
              {opps.map((opp, i) => {
                const bookColor = getBookColor(opp.bookmaker);
                const exchColor = getBookColor(opp.exchange);
                // Split "1 vs X+2" → sc1="1", sc2="X+2"
                const vsSplit = opp.scommessa.split(" vs ");
                const sc1 = vsSplit[0] ?? opp.scommessa;
                const sc2 = vsSplit[1] ?? opp.scommessa;
                // Counter quota display for Quota 2
                const counterQuota = opp.quotaExchange > 0 ? opp.quotaExchange.toFixed(2).replace(".", ",") : "—";
                return (
                  <tr key={i} className="hover:bg-[#1e2d42] transition-colors cursor-pointer" onClick={() => setSelectedOpp(opp)}>
                    <td className="py-2 px-3 text-xs text-white whitespace-nowrap">{formatDate(opp.eventTime)}</td>
                    <td className="py-2 px-2 text-center text-base">{getSportIcon(opp.sport)}</td>
                    <td className="py-2 px-3 text-sm text-white font-medium max-w-[220px] truncate">{opp.eventName}</td>
                    <td className="py-2 px-2 text-center text-lg">{getLeagueFlag(opp.league)}</td>
                    <td className="py-2 px-3 text-center text-sm font-bold text-white">{sc1}</td>
                    <td className="py-2 px-3 text-center text-sm font-bold text-white">{sc2}</td>
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
                      <span className="inline-block px-2 py-0.5 rounded text-[11px] font-bold whitespace-nowrap" style={{ backgroundColor: bookColor.bg, color: bookColor.text }}>
                        {opp.bookmaker}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-center font-mono text-sm font-bold text-[#0d2035] bg-[#87c4e8]">{opp.quotaBook.toFixed(2).replace(".", ",")}</td>
                    <td className="py-2 px-3 text-center">
                      <span className="inline-block px-2 py-0.5 rounded text-[11px] font-bold whitespace-nowrap" style={{ backgroundColor: exchColor.bg, color: exchColor.text }}>
                        {opp.exchange}
                      </span>
                    </td>
                    <td className={`py-2 px-3 text-center font-mono text-sm ${isBookVsBook ? "text-[#0d2035] bg-[#87c4e8]" : "text-[#2d0d1a] bg-[#f4a9ba]"}`}>
                      {counterQuota}
                    </td>
                    {showVolume && (
                      <td className="py-2 px-3 text-center text-xs font-mono text-[#f4a9ba]">
                        {opp.volumeExchange != null ? formatVolume(opp.volumeExchange) : <span className="text-white opacity-30">—</span>}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
      </>
    );
  }
}
