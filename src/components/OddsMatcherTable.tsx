import { useMemo } from "react";

interface OddsData {
  bookmaker: string;
  eventName: string;
  league: string;
  eventTime: string;
  market: string;
  sport: string;
  odds: Record<string, number>;
}

interface Opportunity {
  eventTime: string;
  sport: string;
  eventName: string;
  league: string;
  scommessa: string;
  rating: number;
  bookmaker: string;
  quotaBook: number;
  exchange: string;
  quotaExchange: number;
  isBookVsBook: boolean;
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

function normalizeEventName(name: string): string {
  return name.toLowerCase().replace(/\s+/g, "").replace(/[-–—]/g, "").replace(/\./g, "").replace(/'/g, "");
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
  const outcomes: Array<{ key: string; label: string }> = [];
  if (event.market === "1X2" || event.market === "h2h") {
    if (event.odds.home) outcomes.push({ key: "home", label: "1" });
    if (event.odds.draw) outcomes.push({ key: "draw", label: "X" });
    if (event.odds.away) outcomes.push({ key: "away", label: "2" });
  } else if (event.market === "12") {
    if (event.odds.home) outcomes.push({ key: "home", label: "1" });
    if (event.odds.away) outcomes.push({ key: "away", label: "2" });
  } else if (event.market === "BTTS") {
    if (event.odds.yes) outcomes.push({ key: "yes", label: "Goal" });
    if (event.odds.no) outcomes.push({ key: "no", label: "No Goal" });
  } else if (event.market === "Double Chance") {
    if (event.odds["1X"]) outcomes.push({ key: "1X", label: "1X" });
    if (event.odds["X2"]) outcomes.push({ key: "X2", label: "X2" });
    if (event.odds["12"]) outcomes.push({ key: "12", label: "12" });
  } else {
    if (event.odds.over) outcomes.push({ key: "over", label: "Over" });
    if (event.odds.under) outcomes.push({ key: "under", label: "Under" });
  }
  return outcomes;
}

function findMatchingEvents(sourceEvent: OddsData, pool: OddsData[]): OddsData[] {
  const normalized = normalizeEventName(sourceEvent.eventName);
  return pool.filter(ev => {
    const norm = normalizeEventName(ev.eventName);
    return normalized === norm ||
      (normalized.length > 10 && norm.length > 10 && (
        normalized.includes(norm.substring(0, 10)) ||
        norm.includes(normalized.substring(0, 10))
      ));
  });
}

export function OddsMatcherTable({ data, loading, activeTab, filters, commission }: Props) {

  // ═══ SINGOLA: Book vs Exchange ═══
  const singolaOpps = useMemo(() => {
    if (!data?.data || data.data.length === 0) return [];
    const opps: Opportunity[] = [];
    const commissionRate = commission / 100;
    const bookmakerOdds = data.data.filter(odd => !isExchange(odd.bookmaker));
    const exchangeOdds = data.data.filter(odd => isExchange(odd.bookmaker));

    if (exchangeOdds.length === 0) return [];

    bookmakerOdds.forEach(bmEvent => {
      const matchingExchanges = findMatchingEvents(bmEvent, exchangeOdds);
      if (matchingExchanges.length === 0) return;
      const outcomes = getOutcomes(bmEvent);

      outcomes.forEach(outcome => {
        const backOdds = bmEvent.odds[outcome.key];
        if (!backOdds || backOdds <= 1) return;

        let bestLayOdds = Infinity;
        let bestExchange = "";
        matchingExchanges.forEach(exEvent => {
          const layOdds = exEvent.odds[outcome.key];
          if (layOdds && layOdds > 1 && layOdds < bestLayOdds) {
            bestLayOdds = layOdds;
            bestExchange = exEvent.bookmaker;
          }
        });
        if (bestLayOdds === Infinity) return;

        const layStake = backOdds / (bestLayOdds - commissionRate);
        const profitIfWin = (backOdds - 1) - layStake * (bestLayOdds - 1);
        const profitIfLose = layStake * (1 - commissionRate) - 1;
        const worstProfit = Math.min(profitIfWin, profitIfLose);
        const rating = 100 + worstProfit * 100;

        if (rating > 70 && rating < 105) {
          opps.push({
            eventTime: bmEvent.eventTime,
            sport: bmEvent.sport || "calcio",
            eventName: cleanEventName(bmEvent.eventName),
            league: bmEvent.league,
            scommessa: outcome.label,
            rating,
            bookmaker: bmEvent.bookmaker,
            quotaBook: backOdds,
            exchange: bestExchange,
            quotaExchange: bestLayOdds,
            isBookVsBook: false,
          });
        }
      });
    });

    return opps.sort((a, b) => b.rating - a.rating);
  }, [data, commission]);

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
    if (!hasExchangeData) {
      return (
        <div className="text-center py-12">
          <div className="text-white mb-2">Nessun dato Exchange disponibile (Betfair/BetFlag Exchange).</div>
          <div className="text-white text-sm">La modalit&agrave; SINGOLA richiede quote exchange per il calcolo back/lay.</div>
          <div className="text-white text-sm mt-1">Usa la tab <strong className="text-white">TRE VIE</strong> per le opportunit&agrave; book vs book, o <strong className="text-white">BEST ODDS</strong> per le migliori quote.</div>
        </div>
      );
    }
    const filtered = applyFilters(singolaOpps).slice(0, 200);
    return renderOpportunityTable(filtered, false);
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
                <th className="text-center py-2.5 px-2 font-semibold w-10">Sport</th>
                <th className="text-left py-2.5 px-3 font-semibold">Partita</th>
                <th className="text-center py-2.5 px-3 font-semibold">Mercato</th>
                <th className="text-center py-2.5 px-3 font-semibold">Esito</th>
                <th className="text-center py-2.5 px-3 font-semibold">Miglior Book</th>
                <th className="text-center py-2.5 px-3 font-semibold text-green-400">Quota Max</th>
                <th className="text-center py-2.5 px-3 font-semibold">Peggior Book</th>
                <th className="text-center py-2.5 px-3 font-semibold text-red-400">Quota Min</th>
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
                    <td className="py-2 px-3 text-center text-xs text-white">{row.market}</td>
                    <td className="py-2 px-3 text-center text-sm font-medium text-white">{row.outcome}</td>
                    <td className="py-2 px-3 text-center">
                      <span className="inline-block px-2 py-0.5 rounded text-[11px] font-bold" style={{ backgroundColor: bestColor.bg, color: bestColor.text }}>{row.bestBookmaker}</span>
                    </td>
                    <td className="py-2 px-3 text-center font-mono text-sm font-bold text-green-400 bg-green-900/20">{row.bestOdds.toFixed(2).replace(".", ",")}</td>
                    <td className="py-2 px-3 text-center">
                      <span className="inline-block px-2 py-0.5 rounded text-[11px] font-bold" style={{ backgroundColor: worstColor.bg, color: worstColor.text }}>{row.worstBookmaker}</span>
                    </td>
                    <td className="py-2 px-3 text-center font-mono text-sm text-red-400 bg-red-900/20">{row.worstOdds.toFixed(2).replace(".", ",")}</td>
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
                <th className="text-center py-2.5 px-2 font-semibold w-10">Sport</th>
                <th className="text-left py-2.5 px-3 font-semibold">Partita</th>
                <th className="text-center py-2.5 px-3 font-semibold">Esito 1</th>
                <th className="text-center py-2.5 px-3 font-semibold">Book 1</th>
                <th className="text-center py-2.5 px-3 font-semibold text-green-400">Quota</th>
                <th className="text-center py-2.5 px-3 font-semibold">Esito 2</th>
                <th className="text-center py-2.5 px-3 font-semibold">Book 2</th>
                <th className="text-center py-2.5 px-3 font-semibold text-red-400">Quota</th>
                <th className="text-center py-2.5 px-3 font-semibold">Margine</th>
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
                    <td className="py-2 px-3 text-center text-sm font-medium text-white">{row.outcome1}</td>
                    <td className="py-2 px-3 text-center">
                      <span className="inline-block px-2 py-0.5 rounded text-[11px] font-bold" style={{ backgroundColor: c1.bg, color: c1.text }}>{row.book1}</span>
                    </td>
                    <td className="py-2 px-3 text-center font-mono text-sm text-green-400 bg-green-900/20">{row.odds1.toFixed(2).replace(".", ",")}</td>
                    <td className="py-2 px-3 text-center text-sm font-medium text-white">{row.outcome2}</td>
                    <td className="py-2 px-3 text-center">
                      <span className="inline-block px-2 py-0.5 rounded text-[11px] font-bold" style={{ backgroundColor: c2.bg, color: c2.text }}>{row.book2}</span>
                    </td>
                    <td className="py-2 px-3 text-center font-mono text-sm text-red-400 bg-red-900/20">{row.odds2.toFixed(2).replace(".", ",")}</td>
                    <td className="py-2 px-3 text-center">
                      <span className={`text-sm font-bold ${row.margin < 100 ? "text-green-400" : "text-red-400"}`}>
                        {row.margin.toFixed(1)}%
                      </span>
                    </td>
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

  // ═══ Helper: render opportunity table ═══
  function renderOpportunityTable(opps: Opportunity[], isBookVsBook: boolean) {
    return (
      <div>
        <div className="text-right text-xs text-white px-4 py-2">
          {opps.length} opportunit&agrave;
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[#0a0e1a] text-white text-[12px] uppercase tracking-wide border-b border-[#1e3050]">
                <th className="text-left py-2.5 px-3 font-semibold">Data/Ora</th>
                <th className="text-center py-2.5 px-2 font-semibold w-10">Sport</th>
                <th className="text-left py-2.5 px-3 font-semibold">Partita</th>
                <th className="text-center py-2.5 px-3 font-semibold">Scommessa</th>
                <th className="text-center py-2.5 px-3 font-semibold">Rating</th>
                <th className="text-center py-2.5 px-3 font-semibold">Bookmaker</th>
                <th className="text-center py-2.5 px-3 font-semibold text-green-400">Quota</th>
                <th className="text-center py-2.5 px-3 font-semibold">{isBookVsBook ? "Controparte" : "Exchange"}</th>
                {!isBookVsBook && <th className="text-center py-2.5 px-3 font-semibold text-red-400">Quota</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1e3050]">
              {opps.map((opp, i) => {
                const bookColor = getBookColor(opp.bookmaker);
                const exchColor = getBookColor(opp.exchange);
                return (
                  <tr key={i} className="hover:bg-[#1e2d42] transition-colors">
                    <td className="py-2 px-3 text-xs text-white whitespace-nowrap">{formatDate(opp.eventTime)}</td>
                    <td className="py-2 px-2 text-center text-base">{getSportIcon(opp.sport)}</td>
                    <td className="py-2 px-3 text-sm text-white font-medium max-w-[250px] truncate">{opp.eventName}</td>
                    <td className="py-2 px-3 text-center text-sm font-medium text-white">{opp.scommessa}</td>
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
                    <td className="py-2 px-3 text-center font-mono text-sm text-green-400 bg-green-900/20">{opp.quotaBook.toFixed(2).replace(".", ",")}</td>
                    <td className="py-2 px-3 text-center">
                      <span className="inline-block px-2 py-0.5 rounded text-[11px] font-bold whitespace-nowrap" style={{ backgroundColor: exchColor.bg, color: exchColor.text }}>
                        {opp.exchange}
                      </span>
                    </td>
                    {!isBookVsBook && (
                      <td className="py-2 px-3 text-center font-mono text-sm text-red-400 bg-red-900/20">{opp.quotaExchange.toFixed(2).replace(".", ",")}</td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  }
}
