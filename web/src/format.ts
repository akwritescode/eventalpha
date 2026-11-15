export function timeAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return '—';
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

const NY = 'America/New_York';

export const etTime = (iso: string) =>
  new Date(iso).toLocaleTimeString('en-US', { timeZone: NY, hour: '2-digit', minute: '2-digit', hour12: false });

export const etDate = (isoOrDate: string, opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' }) =>
  new Date(isoOrDate.length === 10 ? `${isoOrDate}T12:00:00Z` : isoOrDate).toLocaleDateString('en-US', { timeZone: NY, ...opts });

export const signed = (n: number | null | undefined, digits = 2) =>
  n == null || Number.isNaN(n) ? '—' : `${n > 0 ? '+' : ''}${n.toFixed(digits)}`;

export const money = (n: number) =>
  n >= 1e9 ? `$${(n / 1e9).toFixed(1)}B` : n >= 1e6 ? `$${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `$${(n / 1e3).toFixed(0)}K` : `$${n.toFixed(0)}`;

export const compact = (n: number) => new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(n);

export const humanize = (key: string) => key.replace(/_/g, ' ').replace(/\bm and a\b/i, 'M&A');
