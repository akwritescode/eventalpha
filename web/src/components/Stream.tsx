import React, { useMemo, useState } from 'react';
import { Box, Button, CircularProgress, Paper, Stack, Typography } from '@mui/material';
import { FeedItem, FeedType } from '../api';
import { useFeed } from '../hooks/useFeed';
import { etDate } from '../format';
import { T } from '../theme';
import { FeedCard, Related } from './FeedCard';
import { Empty } from './ui';

const TABS: { key: string; label: string; types: FeedType[] }[] = [
  { key: 'all', label: 'All events', types: ['sec', 'news', 'macro', 'signal'] },
  { key: 'sec', label: 'SEC filings', types: ['sec'] },
  { key: 'news', label: 'News', types: ['news'] },
  { key: 'macro', label: 'Macro', types: ['macro'] },
  { key: 'signal', label: 'Signals', types: ['signal'] },
];
const RELATED_WINDOW_MS = 3 * 24 * 3600 * 1000;

const dayKey = (iso: string) => new Date(iso).toLocaleDateString('en-CA', { timeZone: 'America/New_York' });

/** Events sharing a ticker within 3 days; for signals, the loaded events that fed them. */
function relationships(items: FeedItem[]): Map<string, Related> {
  const byTicker = new Map<string, FeedItem[]>();
  items.forEach((i) => i.tickers.forEach((t) => byTicker.set(t, [...(byTicker.get(t) ?? []), i])));
  const byUrl = new Map(items.filter((i) => i.url).map((i) => [i.url as string, i]));
  const out = new Map<string, Related>();
  for (const item of items) {
    const at = new Date(item.occurredAt).getTime();
    const events = new Map<string, FeedItem>();
    item.tickers.forEach((t) =>
      (byTicker.get(t) ?? []).forEach((o) => {
        if (o.id !== item.id && Math.abs(new Date(o.occurredAt).getTime() - at) <= RELATED_WINDOW_MS) events.set(o.id, o);
      })
    );
    item.signal?.contributors.forEach((c) => {
      const o = c.url ? byUrl.get(c.url) : undefined;
      if (o) events.set(o.id, o);
    });
    out.set(item.id, { companies: item.tickers, events: Array.from(events.values()) });
  }
  return out;
}

export const Stream: React.FC<{ live: boolean; pushVersion: number }> = ({ live, pushVersion }) => {
  const [tab, setTab] = useState(TABS[0]);
  const feed = useFeed(tab.types, pushVersion);
  const related = useMemo(() => relationships(feed.items), [feed.items]);
  const [loadingMore, setLoadingMore] = useState(false);

  const jump = (id: string) => {
    const el = document.getElementById(id);
    if (el) {
      window.history.replaceState(null, '', `#${encodeURIComponent(id)}`);
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  const groups: { day: string; items: FeedItem[] }[] = [];
  feed.items.forEach((i) => {
    const d = dayKey(i.occurredAt);
    if (groups.length && groups[groups.length - 1].day === d) groups[groups.length - 1].items.push(i);
    else groups.push({ day: d, items: [i] });
  });

  return (
    <Paper id="stream" sx={{ overflow: 'hidden' }}>
      <Box sx={{ px: { xs: 2, sm: 2.5 }, pt: 2.5, pb: 2 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="h1" sx={{ fontSize: { xs: '1.1rem', sm: '1.3rem' } }}>Market Intelligence Stream</Typography>
          <Box
            title={live ? 'Receiving live events' : 'Reconnecting to the live stream'}
            sx={{
              px: 1.25, height: 26, display: 'inline-flex', alignItems: 'center', borderRadius: 999, fontSize: '0.8rem',
              fontWeight: 600, letterSpacing: '0.04em',
              color: live ? T.tone.bullish.fg : T.fgMuted, bgcolor: live ? T.tone.bullish.bg : T.pill,
            }}
          >
            {live ? 'LIVE' : 'OFFLINE'}
          </Box>
        </Stack>
        <Stack direction="row" spacing={1} sx={{ mt: 1.5, flexWrap: 'wrap', rowGap: 1 }}>
          {TABS.map((t) => {
            const active = t.key === tab.key;
            return (
              <Box key={t.key} component="button" onClick={() => setTab(t)}
                sx={{
                  border: `1px solid ${active ? 'rgba(245,158,11,0.45)' : 'transparent'}`, cursor: 'pointer', height: 30, px: 1.5,
                  borderRadius: 999, fontSize: '0.86rem', fontFamily: 'inherit', fontWeight: 500,
                  color: active ? T.amberHover : T.fg, bgcolor: active ? 'rgba(245,158,11,0.12)' : T.pill,
                  '&:hover': { bgcolor: active ? 'rgba(245,158,11,0.16)' : 'rgba(148,163,184,0.2)' },
                }}>
                {t.label}
              </Box>
            );
          })}
        </Stack>
      </Box>

      {feed.loading && <Box sx={{ py: 6, textAlign: 'center' }}><CircularProgress size={22} /></Box>}
      {feed.error && !feed.items.length && <Empty>Can't reach the EventAlpha API ({feed.error}).</Empty>}
      {!feed.loading && !feed.error && !feed.items.length && <Empty>No events of this type in the last 30 days.</Empty>}

      {groups.map((g, gi) => (
        <Box key={g.day}>
          <Stack direction="row" justifyContent="space-between" sx={{ px: { xs: 2, sm: 2.5 }, py: 1.25, borderTop: `1px solid ${T.border}`, bgcolor: T.bg }}>
            <Typography sx={{ fontSize: '0.86rem', color: T.fgSecondary, letterSpacing: '0.04em' }}>
              {etDate(g.day, { month: 'short', day: 'numeric' }).toUpperCase()} · {g.day.slice(0, 4)}
            </Typography>
            {gi === 0 && <Typography sx={{ fontSize: '0.86rem', color: T.fgSecondary }}>Newest first</Typography>}
          </Stack>
          {g.items.map((i) => (
            <FeedCard key={i.id} item={i} related={related.get(i.id) ?? { companies: [], events: [] }} fresh={feed.fresh.has(i.id)} onJump={jump} />
          ))}
        </Box>
      ))}

      {feed.items.length > 0 && !feed.exhausted && (
        <Box sx={{ p: 2, borderTop: `1px solid ${T.border}`, textAlign: 'center' }}>
          <Button
            variant="text"
            disabled={loadingMore}
            onClick={async () => {
              setLoadingMore(true);
              try { await feed.loadMore(); } finally { setLoadingMore(false); }
            }}
            sx={{ color: T.fgSecondary }}
          >
            {loadingMore ? 'Loading…' : 'Load older events'}
          </Button>
        </Box>
      )}
    </Paper>
  );
};
