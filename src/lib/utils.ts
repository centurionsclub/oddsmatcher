import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// ── Betfair URL helpers ────────────────────────────────────────────────────────

function slugify(s: string): string {
  return s
    .toLowerCase()
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/\s+v\s+|\s+vs\.?\s+|\s+-\s+/g, "-")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

const BF_SPORT_IT: Record<string, string> = {
  calcio: "calcio",
  tennis: "tennis",
  basket: "basket",
};

export function getBetfairUrl(
  sport: string,
  marketId?: string,
  eventId?: string,
  eventName?: string,
  league?: string,
): string {
  if (!eventId && !marketId) return "https://www.betfair.it/exchange/plus/";
  const sportSlug = BF_SPORT_IT[sport] ?? "calcio";
  if (eventId) {
    const leagueSlug = slugify(league ?? "");
    const teamsSlug = slugify(eventName ?? "");
    return `https://www.betfair.it/exchange/plus/it/${sportSlug}/${leagueSlug}/${teamsSlug}-scommesse-${eventId}`;
  }
  // fallback: market URL
  return `https://www.betfair.it/exchange/plus/it/${sportSlug}/market/${marketId}`;
}
