import React, { useId } from 'react';
import { Alert, Box, CircularProgress, Link, Stack, Typography } from '@mui/material';
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
  status: 'original_source' | 'verified_discovery' | 'unverified_lead' | 'economic_release' | 'market_commentary' | 'explains_move';
  causeScore?: number | null; // JEV's probability that the article explains the move
  originalId: string | null;
  verifiedAt: string | null;
};

type PriceMove = { symbol: string; returnPercent: number; measuredStart?: string; measuredEnd?: string; dataAsOf?: string };
type SectorMove = { sector: string; price: PriceMove };

export type Explanation = {
  ticker: string;
  start: string;
  end: string;
  asOf: string;
  summary: string;
  catalysts: { summary: string; evidenceId: string }[];
  timeline: Evidence[];
  benchmarks?: string[];
  priceMoves: PriceMove[];
  sectorMovers?: { gainers: SectorMove[]; decliners: SectorMove[] };
  foundInSources?: boolean; // false: EventAlpha's sources hold nothing, so the chat asks a web search
};

const eastern = (options: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', ...options });
const dayTime = eastern({ month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
const calendarStamp = eastern({ month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' });
const timeOnly = eastern({ hour: 'numeric', minute: '2-digit', timeZoneName: 'short' });
const precise = eastern({ month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', second: '2-digit', timeZoneName: 'short' });
const sameDay = (a: string, b: string) =>
  eastern({ dateStyle: 'short' }).format(new Date(a)) === eastern({ dateStyle: 'short' }).format(new Date(b));

/** "Nov 24, 9:30 AM – 10:30 AM EST", dropping the second date when both ends share a day. */
export const windowLabel = (start: string, end: string) =>
  `${dayTime.format(new Date(start))} – ${sameDay(start, end) ? timeOnly.format(new Date(end)) : precise.format(new Date(end))}`;
const stamp = (iso: string) => precise.format(new Date(iso));
const percent = new Intl.NumberFormat('en-US', { style: 'percent', signDisplay: 'exceptZero', maximumFractionDigits: 2 });

const isXPost = (item: Evidence) => item.status === 'verified_discovery' || item.status === 'unverified_lead';

const labels: Record<Evidence['status'], string> = {
  original_source: 'Original source',
  verified_discovery: 'X discovery',
  unverified_lead: 'Unverified X lead',
  economic_release: 'Economic release',
  market_commentary: 'Market commentary',
  explains_move: 'Explains the move',
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
        Intraday prices unavailable for this ticker and window.
        Price collection runs every 15 minutes, so recent windows may still be pending.
      </Typography>
    );
  }
  const benchmarks = result.benchmarks || result.priceMoves.map(p => p.symbol);
  const symbols = Array.from(new Set([result.ticker, ...benchmarks.filter(symbol => !result.sectorMovers || symbol !== 'SMH')]));
  const sectorGroups = result.sectorMovers && [
    { label: 'Top gainers', moves: result.sectorMovers.gainers },
    { label: 'Top decliners', moves: result.sectorMovers.decliners },
  ].filter(group => group.moves.length > 0);
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
      {sectorGroups && sectorGroups.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="overline" component="h3" color="text.secondary">Sector ETF moves</Typography>
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' } }}>
            {sectorGroups.map(({ label, moves }) => (
              <Box key={label}>
                <Typography variant="subtitle2">{label}</Typography>
                <Stack component="ul" spacing={0.5} sx={{ listStyle: 'none', p: 0, my: 0.5 }}>
                  {moves.map(({ sector, price }) => (
                    <Stack component="li" key={price.symbol} direction="row" justifyContent="space-between" gap={1}>
                      <Typography variant="body2">{sector} <Box component="span" sx={{ color: T.fgSecondary }}>{price.symbol}</Box></Typography>
                      <Typography variant="body2" sx={{ fontFamily: MONO, color: price.returnPercent > 0 ? T.up : T.down }}>
                        {percent.format(price.returnPercent / 100)}
                      </Typography>
                    </Stack>
                  ))}
                </Stack>
              </Box>
            ))}
          </Box>
        </Box>
      )}
    </>
  );
}

function Timeline({ items, anchor }: { items: Evidence[]; anchor: string }) {
  return (
    <Box component="ol" sx={{ listStyle: 'none', pl: 0, my: 0 }}>
      {items.map((item, index) => (
        <Box component="li" id={`move-${anchor}-${item.id}`} key={item.id}
          sx={{ position: 'relative', pl: 3, pb: index === items.length - 1 ? 0 : 2, scrollMarginTop: 80 }}>
          {index < items.length - 1 && (
            <Box sx={{ position: 'absolute', left: 5, top: 14, bottom: 0, width: '2px', bgcolor: T.border }} />
          )}
          <Box sx={{ position: 'absolute', left: 0, top: 6, width: 12, height: 12, borderRadius: '50%',
            bgcolor: timing[item.timing].color, boxShadow: `0 0 0 3px ${T.raised}` }} />
          <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center">
            <Typography variant="caption" sx={{ color: timing[item.timing].color, fontWeight: 600 }}>{timing[item.timing].label}</Typography>
            <Typography variant="caption" color={item.status === 'explains_move' ? 'primary' : 'text.secondary'}>
              {labels[item.status]}{item.causeScore != null ? ` · JEV ${item.causeScore.toFixed(2)}` : ''}
            </Typography>
          </Stack>
          <Typography sx={{ mt: 0.25 }}>
            {!isXPost(item) && /^https?:\/\//i.test(item.url)
              ? <Link href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</Link>
              : item.title}
            {isXPost(item) && (
              <> · <Link href={item.url} target="_blank" rel="noopener noreferrer">View X post</Link></>
            )}
            {item.originalId && <> · <Link href={`#move-${anchor}-${item.originalId}`}>Original evidence</Link></>}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {item.status === 'economic_release' ? (
              <>Scheduled release · {calendarStamp.format(new Date(item.publishedAt))}</>
            ) : (
              <>Published {stamp(item.publishedAt)} · First seen {stamp(item.firstSeenAt)}
                {item.verifiedAt && ` · Verified ${stamp(item.verifiedAt)}`}</>
            )}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

function EconomicCalendar({ releases, anchor }: { releases: Evidence[]; anchor: string }) {
  // The API returns releases in chronological order.
  const nearby = releases.find(item => item.timing === 'during') ?? releases[releases.length - 1];
  const names = Array.from(new Set(releases.filter(item => item.publishedAt === nearby.publishedAt)
    .map(item => item.title.match(/\(([^()]+)\)$/)?.[1] ?? item.title)));
  const name = names.length > 3 ? `${names.length} releases` : new Intl.ListFormat('en-US').format(names);
  const relation = { before: 'Before the move window', during: 'During the move window', after: 'After the move window' };
  return (
    <Box component="details" sx={{ mt: 2 }}>
      <Typography component="summary" color="text.secondary" sx={{ cursor: 'pointer' }}>
        Economic calendar context
        <Typography component="span" variant="caption" sx={{ display: 'block', ml: 2 }}>
          {relation[nearby.timing]} · {name}, {calendarStamp.format(new Date(nearby.publishedAt))}
        </Typography>
      </Typography>
      <Box sx={{ mt: 1 }}><Timeline items={releases} anchor={anchor} /></Box>
    </Box>
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

export type WebAnswer = { answer: string | null; sources: { title: string; url: string }[]; available: boolean };
export type WebSearch = { status: 'loading' } | { status: 'failed' } | { status: 'done'; answer: WebAnswer };

function isWebUrl(value: string) {
  try {
    const { protocol, hostname } = new URL(value);
    return Boolean(hostname) && (protocol === 'http:' || protocol === 'https:');
  } catch {
    return false;
  }
}

/** A web search's answer, kept apart from EventAlpha's own evidence and labelled as such. */
function WebSection({ web }: { web: WebSearch }) {
  if (web.status === 'done' && (!web.answer.available || !web.answer.answer)) return null;
  return (
    <Box sx={{ mt: 2, p: 1.5, borderRadius: 2, border: `1px dashed ${T.borderStrong}` }} aria-live="polite">
      <Typography variant="overline" color="text.secondary">From a web search · outside EventAlpha's sources</Typography>
      {web.status === 'loading' ? (
        <Stack direction="row" spacing={1} alignItems="center" sx={{ color: T.fgSecondary }}>
          <CircularProgress size={12} color="inherit" /><Typography variant="body2">Searching news coverage…</Typography>
        </Stack>
      ) : web.status === 'failed' ? (
        <Typography variant="body2" color="text.secondary">Couldn’t search news coverage right now.</Typography>
      ) : (
        <>
          <Typography variant="body2">{web.answer.answer}</Typography>
          <Stack direction="row" gap={1.5} flexWrap="wrap" sx={{ mt: 0.75 }}>
            {web.answer.sources.filter(s => isWebUrl(s.url)).map(s => (
              <Link key={s.url} href={s.url} target="_blank" rel="noopener noreferrer" variant="caption">{s.title}</Link>
            ))}
          </Stack>
        </>
      )}
    </Box>
  );
}

export function MoveResult({ result, web }: { result: Explanation; web?: WebSearch }) {
  const anchor = useId();
  const isDemo = result.ticker === demo.ticker && Date.parse(result.start) === Date.parse(demo.start)
    && Date.parse(result.end) === Date.parse(demo.end);
  const replayed = Date.parse(result.asOf) <= Date.parse(result.end);
  const evidence = result.timeline.filter(item => item.status !== 'economic_release');
  const releases = result.timeline.filter(item => item.status === 'economic_release');
  // The API also includes calendar context in its prose summary. The calendar control displays it here.
  const summary = releases.length > 0
    ? result.summary.replace(/(^| )Economic calendar: [^.]+\.(?= |$)/, '').trim()
    : result.summary;
  const searchedWithoutCause = web?.status === 'done' && web.answer.available && !web.answer.answer;
  const conclusion = searchedWithoutCause
    ? summary.replace(/No verified catalyst found (?:for this move|in EventAlpha's sources)\./,
      'No specific catalyst was found in EventAlpha’s sources or in news coverage.')
    : summary;
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
        <Typography aria-live="polite">
          {conclusion}
          {result.catalysts.length === 1 && <> ({source(result.catalysts[0].evidenceId)})</>}
        </Typography>
        {result.catalysts.length > 1 && (
          <Box component="ul" sx={{ pl: 2.5, my: 0.5 }}>
            {result.catalysts.map(c => <li key={c.evidenceId}>{c.summary} ({source(c.evidenceId)})</li>)}
          </Box>
        )}
        <Typography variant="caption" color="text.secondary">Evidence available as of {stamp(result.asOf)}.</Typography>
      </Box>

      {web && <WebSection web={web} />}

      {(evidence.length > 0 || releases.length === 0) && (
        <>
          <Typography variant="overline" component="h3" color="text.secondary" sx={{ display: 'block', mt: 2 }}>Evidence timeline</Typography>
          {evidence.length > 0 ? <Timeline items={evidence} anchor={anchor} />
            : <Typography color="text.secondary">No matching evidence in the timeline.</Typography>}
        </>
      )}
      {releases.length > 0 && <EconomicCalendar releases={releases} anchor={anchor} />}
    </Box>
  );
}
