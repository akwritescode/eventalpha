import { getJson } from './api';
import type { Explanation } from './components/MoveExplanation';

export type TickerMatch = { ticker: string; name: string };
export type MoveWindow = { start: string; end: string };
export const MINUTE_MS = 60_000;
export const DAY_MS = 86_400_000;
export const searchTickers = (query: string) =>
  getJson<TickerMatch[]>(`/api/v1/tickers/search?q=${encodeURIComponent(query)}`);

export function recentWindow(minutes: number, now = Date.now()): MoveWindow {
  const end = Math.floor(now / MINUTE_MS) * MINUTE_MS;
  return { start: new Date(end - minutes * MINUTE_MS).toISOString(), end: new Date(end).toISOString() };
}

export function windowError(start: number, end: number, demo = false): string | undefined {
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start || end - start > DAY_MS) {
    return 'Choose a stock ticker and a valid start and end time up to 24 hours apart.';
  }
  if (end > Date.now()) return 'Choose a window that has already ended.';
  if (!demo && start < Date.now() - 7 * DAY_MS) {
    return 'EventAlpha focuses on recent moves. Choose a window entirely within the past 7 days.';
  }
}

const FOLLOW_UP = /^(?:today|replay|yesterday|now|again)$/i;
// Clock times and time zones read as tickers (AM, PM, ET are all listed symbols). A user who
// means one of those companies can still name it as the subject or write $ET.
const TIME_WORDS = /\b\d{1,2}(?::\d{2})?\s*(?:AM|PM)\b|\b(?:AM|PM|ET|EST|EDT|UTC|GMT)\b/g;
// Each fallback candidate costs one search request, and the read API is rate limited per IP.
export const MAX_CANDIDATES = 5;

export function tickerQuery(text: string): string | undefined {
  if (FOLLOW_UP.test(text)) return undefined;
  const explicit = text.match(/\$([A-Za-z][A-Za-z.-]{0,9})\b/)?.[1];
  if (explicit) return explicit;
  const subject = text.match(/why\s+(?:did|has|is|was)\s+(.+?)\s+(?:drops?|dropped|dropping|falls?|fell|fallen|falling|rises?|rose|rising|moves?|moved|moving|dip|jump|rally|sell|go|up|down|surge|crash|gain|lose|decline)\b/i)?.[1];
  const object = text.match(/\b(?:move[sd]?|affect(?:s|ed)?|impact(?:s|ed)?)\s+(?!(?:after|before|on|following|in|over|during|since|today|yesterday|last|at)\b)(.+?)(?=\s+(?:in|over|during|since|today|yesterday|last|at|after|before|on|following)\b|[?!]|$)/i)?.[1];
  const named = subject || object;
  if (named) {
    return named.replace(/^the\s+/i, '').replace(/\s+(?:stock|shares?)$/i, '')
      .replace(/^(?:stock|shares?)$/i, '').trim() || undefined;
  }
  return /^[A-Za-z][A-Za-z.-]{0,9}$/.test(text) ? text : undefined;
}

export async function resolveTicker(text: string): Promise<{ query?: string; matches: TickerMatch[] }> {
  const query = tickerQuery(text);
  if (query) {
    const { data } = await searchTickers(query);
    const exact = data.find(item => item.ticker.toUpperCase() === query.toUpperCase());
    return { query, matches: exact ? [exact] : data };
  }
  if (FOLLOW_UP.test(text)) return { matches: [] };
  const words = text.replace(TIME_WORDS, ' ').match(/\b[A-Z][A-Z.-]{1,9}\b/g) || [];
  const candidates = Array.from(new Set(words)).slice(0, MAX_CANDIDATES);
  // One failed lookup must not fail the whole question: keep what the others confirmed.
  const settled = await Promise.allSettled(candidates.map(async candidate => {
    const { data } = await searchTickers(candidate);
    return data.filter(item => item.ticker.toUpperCase() === candidate);
  }));
  const confirmed = settled.flatMap(result => (result.status === 'fulfilled' ? result.value : []));
  const matches = Array.from(new Map(confirmed.map(item => [item.ticker, item])).values());
  return { matches };
}

export const isReplay = (text: string) => /\bas[ -]of\b|\bavailable\b.*\b(?:end|then)\b|\breplay\b/i.test(text);

export function fetchExplanation(ticker: string, window: MoveWindow, replay = false) {
  const params = new URLSearchParams(window);
  if (replay) params.set('asOf', window.end);
  return getJson<Explanation>(`/api/v1/tickers/${encodeURIComponent(ticker)}/move-explanation?${params}`);
}
