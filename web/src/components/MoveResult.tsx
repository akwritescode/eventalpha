import React, { useId } from 'react';
import { Alert, Box, Link, Stack, Typography } from '@mui/material';
import { alpha } from '@mui/material/styles';
import ArrowDropDownRounded from '@mui/icons-material/ArrowDropDownRounded';
import ArrowDropUpRounded from '@mui/icons-material/ArrowDropUpRounded';
import demo from '../fixtures/move-demo.json';
import { MONO, T } from '../theme';
import { Pill } from './ui';

type Evidence = {
  id: string;
  title: string;
  url: string;
  publishedAt: string;
  firstSeenAt: string;
  timing: 'before' | 'during' | 'after';
  status: 'original_source' | 'verified_discovery' | 'unverified_lead';
  originalId: string | null;
  verifiedAt: string | null;
};

export type Explanation = {
  ticker: string;
  start: string;
  end: string;
  asOf: string;
  summary: string;
  catalysts: { summary: string; evidenceId: string }[];
  timeline: Evidence[];
  benchmarks?: string[];
  priceMoves: { symbol: string; returnPercent: number; measuredStart?: string; measuredEnd?: string; dataAsOf?: string }[];
};

const eastern = (options: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', ...options });
const dayTime = eastern({ month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
const timeOnly = eastern({ hour: 'numeric', minute: '2-digit', timeZoneName: 'short' });
const precise = eastern({ month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', second: '2-digit', timeZoneName: 'short' });
const sameDay = (a: string, b: string) =>
  eastern({ dateStyle: 'short' }).format(new Date(a)) === eastern({ dateStyle: 'short' }).format(new Date(b));

/** "Nov 24, 9:30 AM – 10:30 AM EST", dropping the second date when both ends share a day. */
export const windowLabel = (start: string, end: string) =>
  `${dayTime.format(new Date(start))} – ${sameDay(start, end) ? timeOnly.format(new Date(end)) : precise.format(new Date(end))}`;
const stamp = (iso: string) => precise.format(new Date(iso));
const percent = new Intl.NumberFormat('en-US', { style: 'percent', signDisplay: 'exceptZero', maximumFractionDigits: 2 });

const labels: Record<Evidence['status'], string> = {
  original_source: 'Original source',
  verified_discovery: 'X discovery',
  unverified_lead: 'Unverified X lead',
};
const timing: Record<Evidence['timing'], { label: string; color: string }> = {
  before: { label: 'Before', color: T.fgSecondary },
  during: { label: 'During', color: T.amber },
  after: { label: 'After · later context', color: T.fgMuted },
};

function Returns({ result }: { result: Explanation }) {
  if (!result.priceMoves.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        Intraday prices unavailable for this ticker and window. The timeline shows available filings and releases.
        Price collection runs every 15 minutes, so recent windows may still be pending.
      </Typography>
    );
  }
  const symbols = Array.from(new Set([result.ticker, ...(result.benchmarks || result.priceMoves.map(p => p.symbol))]));
  return (
    <>
      <Box sx={{ display: 'grid', gap: 1, gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))' }}>
        {symbols.map((symbol) => {
          const move = result.priceMoves.find(p => p.symbol === symbol);
          const value = move?.returnPercent;
          const color = value === undefined || value === 0 ? T.fgSecondary : value > 0 ? T.up : T.down;
          return (
            <Box key={symbol} aria-label={`${symbol} ${value === undefined ? 'Unavailable' : percent.format(value / 100)}`}
              title={move?.measuredEnd ? `${stamp(move.measuredStart!)} to ${stamp(move.measuredEnd)}. Observed ${stamp(move.dataAsOf!)}.` : undefined}
              sx={{ p: 1.25, borderRadius: 2, bgcolor: alpha(color, symbol === result.ticker ? 0.12 : 0.06), border: `1px solid ${alpha(color, 0.2)}` }}>
              <Typography variant="caption" sx={{ color: T.fgSecondary, fontFamily: MONO }}>
                {symbol}{symbol === result.ticker ? '' : symbol === 'SPY' ? ' · market' : symbol === 'SMH' ? ' · chips' : ''}
              </Typography>
              <Stack direction="row" alignItems="center" sx={{ color, fontFamily: MONO, fontWeight: 600, fontSize: '1.1rem' }}>
                {value !== undefined && value > 0 && <ArrowDropUpRounded sx={{ ml: -0.75 }} />}
                {value !== undefined && value < 0 && <ArrowDropDownRounded sx={{ ml: -0.75 }} />}
                {value === undefined ? 'n/a' : percent.format(value / 100)}
              </Stack>
            </Box>
          );
        })}
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
        Returns use the latest completed candles at the window edges. Hover a card for exact times.
      </Typography>
    </>
  );
}

/** One-line stand-in for an older result in the chat: ticker, window, its return; click to expand. */
export function MoveResultSummary({ result, onExpand }: { result: Explanation; onExpand: () => void }) {
  const move = result.priceMoves.find(p => p.symbol === result.ticker);
  const color = !move || move.returnPercent === 0 ? T.fgSecondary : move.returnPercent > 0 ? T.up : T.down;
  return (
    <Box component="button" type="button" onClick={onExpand} aria-label={`Show details for ${result.ticker}, ${windowLabel(result.start, result.end)}`}
      sx={{ mt: 1, width: '100%', display: 'flex', alignItems: 'center', gap: 1.25, flexWrap: 'wrap', textAlign: 'left',
        px: 1.5, py: 1, borderRadius: 2, border: `1px solid ${T.border}`, bgcolor: T.raised, color: T.fg, font: 'inherit',
        cursor: 'pointer', '&:hover': { borderColor: T.borderStrong } }}>
      <Box component="span" sx={{ fontFamily: MONO, fontWeight: 700 }}>{result.ticker}</Box>
      <Typography component="span" variant="body2" color="text.secondary">{windowLabel(result.start, result.end)}</Typography>
      {move && <Box component="span" sx={{ fontFamily: MONO, fontWeight: 600, color }}>{percent.format(move.returnPercent / 100)}</Box>}
      <Typography component="span" variant="body2" sx={{ ml: 'auto', color: T.amber }}>Show details</Typography>
    </Box>
  );
}

export function MoveResult({ result }: { result: Explanation }) {
  const anchor = useId();
  const isDemo = result.ticker === demo.ticker && Date.parse(result.start) === Date.parse(demo.start)
    && Date.parse(result.end) === Date.parse(demo.end);
  const replayed = Date.parse(result.asOf) <= Date.parse(result.end);
  const source = (id: string) => <Link href={`#move-${anchor}-${id}`} underline="hover">source</Link>;

  return (
    <Box sx={{ mt: 1.5, p: { xs: 1.5, sm: 2 }, borderRadius: 3, bgcolor: T.raised, border: `1px solid ${T.border}` }}>
      {isDemo && (
        <Alert severity="info" sx={{ mb: 1.5 }}>The demo uses a real SEC filing with simulated X posts and observation times.</Alert>
      )}
      <Stack direction="row" alignItems="baseline" gap={1} flexWrap="wrap" sx={{ mb: 1.5 }}>
        <Typography sx={{ fontFamily: MONO, fontWeight: 700, fontSize: '1.15rem' }}>{result.ticker}</Typography>
        <Typography variant="body2" color="text.secondary">{windowLabel(result.start, result.end)}</Typography>
        {replayed && <Pill tone={{ fg: T.amber, bg: alpha(T.amber, 0.14) }}>As known at window end</Pill>}
      </Stack>

      <Returns result={result} />

      <Box sx={{ mt: 2, pl: 1.5, py: 0.5, borderLeft: `3px solid ${T.amber}` }}>
        <Typography variant="overline" color="text.secondary">What we found</Typography>
        <Typography>
          {result.summary}
          {result.catalysts.length === 1 && <> ({source(result.catalysts[0].evidenceId)})</>}
        </Typography>
        {result.catalysts.length > 1 && (
          <Box component="ul" sx={{ pl: 2.5, my: 0.5 }}>
            {result.catalysts.map(c => <li key={c.evidenceId}>{c.summary} ({source(c.evidenceId)})</li>)}
          </Box>
        )}
        <Typography variant="caption" color="text.secondary">Evidence available as of {stamp(result.asOf)}.</Typography>
      </Box>

      <Typography variant="overline" component="h3" color="text.secondary" sx={{ display: 'block', mt: 2 }}>Evidence timeline</Typography>
      {result.timeline.length === 0 ? <Typography color="text.secondary">No matching evidence in the timeline.</Typography> : (
        <Box component="ol" sx={{ listStyle: 'none', pl: 0, my: 0 }}>
          {result.timeline.map((item, index) => (
            <Box component="li" id={`move-${anchor}-${item.id}`} key={item.id}
              sx={{ position: 'relative', pl: 3, pb: index === result.timeline.length - 1 ? 0 : 2, scrollMarginTop: 80 }}>
              {index < result.timeline.length - 1 && (
                <Box sx={{ position: 'absolute', left: 5, top: 14, bottom: 0, width: '2px', bgcolor: T.border }} />
              )}
              <Box sx={{ position: 'absolute', left: 0, top: 6, width: 12, height: 12, borderRadius: '50%',
                bgcolor: timing[item.timing].color, boxShadow: `0 0 0 3px ${T.raised}` }} />
              <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center">
                <Typography variant="caption" sx={{ color: timing[item.timing].color, fontWeight: 600 }}>{timing[item.timing].label}</Typography>
                <Typography variant="caption" color="text.secondary">{labels[item.status]}</Typography>
              </Stack>
              <Typography sx={{ mt: 0.25 }}>
                {item.status === 'original_source' && /^https?:\/\//i.test(item.url)
                  ? <Link href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</Link>
                  : item.title}
                {item.status !== 'original_source' && (
                  <> · <Link href={item.url} target="_blank" rel="noopener noreferrer">View X post</Link></>
                )}
                {item.originalId && <> · <Link href={`#move-${anchor}-${item.originalId}`}>Original evidence</Link></>}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Published {stamp(item.publishedAt)} · First seen {stamp(item.firstSeenAt)}
                {item.verifiedAt && ` · Verified ${stamp(item.verifiedAt)}`}
              </Typography>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}
