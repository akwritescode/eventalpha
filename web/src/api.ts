// Typed client for the EventAlpha read API. Every response is { data, dataAsOf, generatedAt }.

export const API_URL = (process.env.REACT_APP_API_URL || '').replace(/\/$/, '');
export const TELEGRAM_URL = process.env.REACT_APP_TELEGRAM_URL || '';

export interface ApiResponse<T> {
  data: T;
  dataAsOf: string | null;
  generatedAt: string;
}

export interface Score {
  sentiment: 'bullish' | 'bearish' | 'neutral';
  sentimentScore: number;
  materiality: number;
  companySpecific: number;
  events: Record<string, number>;
  scoredAt: string;
}

export interface Article {
  id: number;
  source: string;
  formType: string | null;
  title: string;
  url: string;
  company: string | null;
  tickers: string[];
  secItems: string[];
  publishedAt: string;
  score: Score | null;
}

export interface SentimentDay {
  day: string;
  articles: number;
  scored: number;
  bullish: number;
  bearish: number;
  neutral: number;
  meanScore: number | null;
  highMateriality: number;
}

export interface SignalView {
  signalType: 'premarket' | 'spx_overnight';
  sessionDate: string;
  generatedAt: string;
  score: number | null;
  confidence: number | null;
  payload: any; // shape depends on the signal type (see src/eventalpha/signals/build.py)
  inputsAsOf: Record<string, string | null>;
}

export interface InsiderBuy {
  ticker: string;
  issuerName: string | null;
  ownerName: string;
  officerTitle: string | null;
  shares: number;
  value: number;
  lastTransaction: string;
  insiders30d: number;
}

export interface Calendar {
  economic: { eventDate: string; scheduledAt: string | null; title: string; importance: string; source: string }[];
  earnings: { ticker: string; eventDate: string; status: string; marketCap: number | null }[]; // largest first per day
}

export interface Nowcast {
  measure: string;
  targetPeriod: string;
  vintage: string;
  value: number | null;
  actual: number | null;
}

export interface FamilyDay {
  dateFiled: string;
  family: string;
  loaded: number;
  skipped: number;
  failed: number;
  rows: number;
  lastProcessedAt: string;
}

export async function getJson<T>(path: string): Promise<ApiResponse<T>> {
  const resp = await fetch(`${API_URL}${path}`, { headers: { Accept: 'application/json' } });
  if (!resp.ok) throw new Error(`${path}: HTTP ${resp.status}`);
  return resp.json();
}

/** A failed request, with the server's problem detail (RFC 9457) when it sent one. */
export class ApiError extends Error {
  constructor(public status: number, public detail?: string) {
    super(detail || `HTTP ${status}`);
  }
}

export async function postJson<T>(path: string, body: unknown): Promise<ApiResponse<T>> {
  const resp = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const problem = await resp.json().catch(() => undefined);
    throw new ApiError(resp.status, typeof problem?.detail === 'string' ? problem.detail : undefined);
  }
  return resp.json();
}

/** One new item on the feed stream (Server-Sent Events, all fields are strings). */
export interface FeedPush {
  id: string; // stream entry id (used for resume)
  kind: 'sec' | 'news' | 'macro' | 'signal';
  ref: string; // the FeedItem id it refers to, e.g. "article:154"
  title: string;
  label: string;
  tickers: string;
  sentiment: string;
  impact: 'high' | 'normal';
  url: string;
  occurred_at: string;
}

export interface ChannelPreview {
  channelName: string;
  posts: { id: string; kind: 'signal' | 'event'; postedAt: string; html: string }[];
}

// ---------- Market Intelligence Stream ----------

export type FeedType = 'sec' | 'news' | 'macro' | 'signal';

export interface FeedItem {
  id: string;
  type: FeedType;
  label: string;
  occurredAt: string;
  timeKnown: boolean;
  title: string;
  summary: string | null;
  url: string | null;
  sourceLine: string;
  tickers: string[];
  classification: {
    sentiment: 'bullish' | 'bearish' | 'neutral';
    score: number;
    confidence: number | null;
    pBullish: number;
    pBearish: number;
    pNeutral: number;
    materiality: number;
    companySpecific: number;
    events: Record<string, number>;
  } | null;
  facts: { label: string; value: string }[];
  macro: {
    release: string;
    importance: string;
    rows: { label: string; unit: string; forecast: number | null; actual: number | null; prior: number | null; surprise: number | null }[];
    verdict: string | null;
    verdictTone: 'good' | 'bad' | 'neutral';
    note: string | null;
  } | null;
  signal: {
    signalType: string;
    score: number | null;
    confidence: number | null;
    contributors: { title: string; url: string | null; tickers: string[]; sentiment: string | null; score: number | null }[];
    contributingEvents: number;
    components: Record<string, number | null>;
  } | null;
}
