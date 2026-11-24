import { getJson, postJson } from './api';
import type { Explanation } from './components/MoveResult';

export type MoveWindow = { start: string; end: string };
export type TickerOption = { ticker: string; name: string };
export const MINUTE_MS = 60_000;
export const DAY_MS = 86_400_000;

/** What POST /api/v1/move-query resolved a chat question to (see MoveQueryController). */
export type MoveQuery = {
  ticker: string | null;
  tickerName: string | null;
  tickerOptions: TickerOption[];
  start: string | null;
  end: string | null;
  replay: boolean;
  message: string | null;
};

export type QueryContext = { ticker?: string; window?: MoveWindow };

export const askMoveQuery = (question: string, context: QueryContext) =>
  postJson<MoveQuery>('/api/v1/move-query', {
    question,
    contextTicker: context.ticker,
    contextStart: context.window?.start,
    contextEnd: context.window?.end,
  });

export function recentWindow(minutes: number, now = Date.now()): MoveWindow {
  const end = Math.floor(now / MINUTE_MS) * MINUTE_MS;
  return { start: new Date(end - minutes * MINUTE_MS).toISOString(), end: new Date(end).toISOString() };
}

export function windowError(start: number, end: number, demo = false): string | undefined {
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start || end - start > DAY_MS) {
    return 'Choose a start and end time up to 24 hours apart.';
  }
  if (end > Date.now()) return 'Choose a window that has already ended.';
  if (!demo && start < Date.now() - 7 * DAY_MS) {
    return 'EventAlpha focuses on recent moves. Choose a window entirely within the past 7 days.';
  }
}

/** The time-frame chips shown once a ticker is picked. */
export type TimeFrame =
  | { label: string; kind: 'recent'; minutes: number }
  | { label: string; kind: 'today' }
  | { label: string; kind: 'since'; anchor: 'open' | 'close' };

export const TIME_FRAMES: TimeFrame[] = [
  { label: 'Last 30 min', kind: 'recent', minutes: 30 },
  { label: 'Last hour', kind: 'recent', minutes: 60 },
  { label: 'Last 2 hours', kind: 'recent', minutes: 120 },
  { label: 'Today', kind: 'today' },
  { label: 'Since yesterday’s close', kind: 'since', anchor: 'close' },
];

/** A concrete window for a chip, or the reason there isn't one (market closed, calendar missing). */
export async function frameWindow(frame: TimeFrame): Promise<MoveWindow | string> {
  if (frame.kind === 'recent') return recentWindow(frame.minutes);
  const route = frame.kind === 'today' ? '/api/v1/move-window/today' : `/api/v1/move-window/since-yesterday?anchor=${frame.anchor}`;
  const { data } = await getJson<{ start: string | null; end: string | null; message?: string | null }>(route);
  return data.start && data.end ? { start: data.start, end: data.end } : data.message || 'That window isn’t available right now.';
}

export function fetchExplanation(ticker: string, window: MoveWindow, replay = false) {
  const params = new URLSearchParams(window);
  if (replay) params.set('asOf', window.end);
  return getJson<Explanation>(`/api/v1/tickers/${encodeURIComponent(ticker)}/move-explanation?${params}`);
}
