import React, { useState } from 'react';
import { Box, Collapse, Link, Stack, Typography } from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { FeedItem } from '../api';
import { etTime, humanize } from '../format';
import { MONO, T } from '../theme';
import { Num, Pill, TypeBadge } from './ui';

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const pct = (x: number | null | undefined) => (x == null ? '—' : `${Math.round(x * 100)}%`);
const fmt = (v: number | null, unit: string, signed = false) =>
  v == null ? '—' : `${signed && v > 0 ? '+' : ''}${unit === 'K' ? v.toLocaleString('en-US') : v.toFixed(unit === '%' ? 2 : 1)}${unit === 'K' ? 'K' : unit === '%' ? '%' : ''}`;

export interface Related {
  companies: string[];
  events: FeedItem[];
}

const MetaLine: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <Typography sx={{ fontSize: '0.86rem', color: T.fgSecondary, mt: 0.75 }}>{children}</Typography>
);

const Bar: React.FC<{ label: string; value: number; color: string }> = ({ label, value, color }) => (
  <Box sx={{ display: 'grid', gridTemplateColumns: '120px 1fr 44px', alignItems: 'center', gap: 1 }}>
    <Typography sx={{ fontSize: '0.8rem', color: T.fgSecondary }}>{label}</Typography>
    <Box sx={{ height: 6, borderRadius: 3, bgcolor: T.pill }}>
      <Box sx={{ height: 6, borderRadius: 3, width: `${Math.max(2, value * 100)}%`, bgcolor: color }} />
    </Box>
    <Num size="0.78rem" color={T.fgSecondary}>{pct(value)}</Num>
  </Box>
);

/** One stream entry. Collapsed: what happened. Expanded: the evidence and the connections. */
export const FeedCard: React.FC<{ item: FeedItem; related: Related; fresh: boolean; onJump: (id: string) => void }> = ({
  item, related, fresh, onJump,
}) => {
  const [open, setOpen] = useState(false);
  const c = item.classification;
  const sig = item.signal;
  const m = item.macro;
  const sentiment = c?.sentiment ?? (sig?.score == null ? undefined : sig.score > 0.15 ? 'bullish' : sig.score < -0.15 ? 'bearish' : 'neutral');
  const confidence = c?.confidence ?? sig?.confidence ?? null;
  const hasForecast = m?.rows.some((r) => r.forecast != null);

  return (
    <Box
      id={item.id}
      sx={{
        px: { xs: 2, sm: 2.5 }, py: 2.5, borderTop: `1px solid ${T.border}`, scrollMarginTop: 80,
        transition: 'background-color 1.2s', bgcolor: fresh ? 'rgba(245,158,11,0.07)' : 'transparent',
        '&:target': { bgcolor: 'rgba(245,158,11,0.07)' },
      }}
    >
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
        <TypeBadge tone={T.badge[item.type]}>{item.label}</TypeBadge>
        <Typography sx={{ fontSize: '0.86rem', color: T.fgSecondary, whiteSpace: 'nowrap' }}>
          {item.timeKnown ? `${etTime(item.occurredAt)} ET` : 'date only'}
        </Typography>
      </Stack>

      <Typography variant="h3" sx={{ mt: 1.5, fontSize: { xs: '1rem', sm: '1.08rem' } }}>
        {item.url ? (
          <Link href={item.url} target="_blank" rel="noopener noreferrer" color="inherit" underline="hover">{item.title}</Link>
        ) : item.title}
      </Typography>

      {item.summary && (
        <Typography sx={{ mt: 1, color: T.fg, opacity: 0.88, fontSize: { xs: '0.92rem', sm: '0.98rem' } }}>{item.summary}</Typography>
      )}

      {m && m.rows.length > 0 && (
        <Box sx={{ mt: 1.5 }}>
          {m.rows.map((r) => (
            <Box key={r.label} sx={{ mb: 1 }}>
              {m.rows.length > 1 && <Typography sx={{ fontSize: '0.78rem', color: T.fgMuted, mb: 0.25 }}>{r.label}</Typography>}
              <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 2 }}>
                {(hasForecast
                  ? [['Forecast', fmt(r.forecast, r.unit)], ['Actual', fmt(r.actual, r.unit)], ['Surprise', r.surprise == null ? '—' : `${r.surprise > 0 ? '+' : ''}${r.surprise.toFixed(2)} pp`]]
                  : [[m.rows.length > 1 ? 'Actual' : r.label, fmt(r.actual, r.unit)], ['Prior', fmt(r.prior, r.unit)],
                     ['Change', r.actual != null && r.prior != null ? fmt(Number((r.actual - r.prior).toFixed(r.unit === 'K' ? 0 : 2)), r.unit === 'K' ? 'K' : r.unit === '%' ? '%' : '', true) : '—']]
                ).map(([k, v], idx) => (
                  <Box key={k}>
                    <Typography sx={{ fontSize: '0.84rem', color: T.fgSecondary }}>{k}</Typography>
                    <Num size="1.2rem" weight={600}
                      color={hasForecast && idx === 2 && r.surprise != null ? (m.verdictTone === 'bad' ? T.down : m.verdictTone === 'good' ? T.up : T.fg) : T.fg}>
                      {v}
                    </Num>
                  </Box>
                ))}
              </Box>
            </Box>
          ))}
        </Box>
      )}

      <Stack direction="row" spacing={1} sx={{ mt: 1.5, flexWrap: 'wrap', rowGap: 1 }}>
        {m?.verdict && <Pill tone={m.verdictTone === 'bad' ? T.tone.bearish : m.verdictTone === 'good' ? T.tone.bullish : T.tone.neutral}>{m.verdict}</Pill>}
        {sentiment && (
          <Pill tone={T.tone[sentiment as 'bullish' | 'bearish' | 'neutral']}>{sig ? sentiment.toUpperCase() : cap(sentiment)}</Pill>
        )}
        {confidence != null && <Pill>Confidence {pct(confidence)}</Pill>}
        {item.tickers.slice(0, 4).map((t) => <Pill key={t}>{t}</Pill>)}
      </Stack>

      {sig && <MetaLine>Signal generated from {sig.contributingEvents} contributing events</MetaLine>}
      {(related.companies.length > 1 || related.events.length > 0) && (
        <MetaLine>
          {related.companies.length > 1 && `${related.companies.length} related companies`}
          {related.companies.length > 1 && related.events.length > 0 && ' · '}
          {related.events.length > 0 && `${related.events.length} related event${related.events.length > 1 ? 's' : ''}`}
        </MetaLine>
      )}
      <MetaLine>{item.sourceLine}</MetaLine>

      <Stack direction="row" spacing={2.5} sx={{ mt: 1 }}>
        {item.url && (
          <Link href={item.url} target="_blank" rel="noopener noreferrer" underline="hover" sx={{ fontSize: '0.88rem', color: T.fgSecondary }}>
            {item.type === 'sec' ? 'View filing →' : 'Read source →'}
          </Link>
        )}
        <Link component="button" underline="none" onClick={() => setOpen((o) => !o)}
          sx={{ fontSize: '0.88rem', color: T.fgSecondary, display: 'inline-flex', alignItems: 'center', '&:hover': { color: T.fg } }}>
          {open ? 'Hide details' : 'Details'}
          <ExpandMoreIcon fontSize="small" sx={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }} />
        </Link>
      </Stack>

      <Collapse in={open} unmountOnExit>
        <Box sx={{ mt: 2, p: 2, borderRadius: 2, bgcolor: T.raised, border: `1px solid ${T.border}`, display: 'grid', gap: 2 }}>
          {item.facts.length > 0 && (
            <Box>
              <Typography variant="overline" sx={{ color: T.fgMuted }}>Extracted facts</Typography>
              <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '120px 1fr' }, columnGap: 2, rowGap: 0.5 }}>
                {item.facts.map((f) => (
                  <React.Fragment key={f.label}>
                    <Typography sx={{ fontSize: '0.84rem', color: T.fgSecondary }}>{f.label}</Typography>
                    <Typography sx={{ fontSize: '0.84rem' }}>{f.value}</Typography>
                  </React.Fragment>
                ))}
              </Box>
            </Box>
          )}
          {c && (
            <Box sx={{ display: 'grid', gap: 0.75 }}>
              <Typography variant="overline" sx={{ color: T.fgMuted }}>Classification</Typography>
              <Bar label="Bullish" value={c.pBullish} color={T.up} />
              <Bar label="Neutral" value={c.pNeutral} color={T.fgSecondary} />
              <Bar label="Bearish" value={c.pBearish} color={T.down} />
              <Bar label={`Materiality ${c.materiality.toFixed(1)}/3`} value={c.materiality / 3} color={T.amber} />
              <Bar label="Company-specific" value={c.companySpecific} color={T.series[1]} />
              {Object.entries(c.events).sort((a, b) => b[1] - a[1]).slice(0, 4).filter(([, p]) => p >= 0.2).map(([k, p]) => (
                <Bar key={k} label={humanize(k)} value={p} color={T.series[2]} />
              ))}
              <Typography sx={{ fontSize: '0.78rem', color: T.fgMuted, mt: 0.5 }}>
                Model-estimated probabilities, one per question; not investment advice.
              </Typography>
            </Box>
          )}
          {m?.note && <Typography sx={{ fontSize: '0.84rem', color: T.fgSecondary }}>{m.note}</Typography>}
          {sig && (
            <Box>
              <Typography variant="overline" sx={{ color: T.fgMuted }}>Components</Typography>
              <Stack direction="row" spacing={2} sx={{ flexWrap: 'wrap' }}>
                {Object.entries(sig.components).map(([k, v]) => (
                  <Typography key={k} sx={{ fontSize: '0.84rem' }}>
                    {k}: <Num>{v == null ? 'none' : v.toFixed(2)}</Num>
                  </Typography>
                ))}
              </Stack>
              {sig.contributors.length > 0 && (
                <>
                  <Typography variant="overline" sx={{ color: T.fgMuted, display: 'block', mt: 1.5 }}>Strongest contributing events</Typography>
                  <Stack spacing={0.75}>
                    {sig.contributors.slice(0, 8).map((x) => (
                      <Stack key={x.url ?? x.title} direction="row" spacing={1} alignItems="center">
                        <Typography sx={{ fontSize: '0.8rem', fontWeight: 600, minWidth: 54, fontFamily: MONO }}>{x.tickers[0] ?? ''}</Typography>
                        {x.sentiment && <Pill tone={T.tone[x.sentiment as 'bullish']}>{cap(x.sentiment)}</Pill>}
                        <Link href={x.url ?? undefined} target="_blank" rel="noopener noreferrer" underline="hover" color="inherit" noWrap sx={{ fontSize: '0.84rem', minWidth: 0 }}>
                          {x.title}
                        </Link>
                      </Stack>
                    ))}
                  </Stack>
                </>
              )}
            </Box>
          )}
          {related.events.length > 0 && (
            <Box>
              <Typography variant="overline" sx={{ color: T.fgMuted }}>Related events</Typography>
              <Stack spacing={0.75}>
                {related.events.slice(0, 6).map((r) => (
                  <Link key={r.id} component="button" underline="hover" color="inherit" onClick={() => onJump(r.id)}
                    sx={{ textAlign: 'left', fontSize: '0.84rem', display: 'flex', gap: 1, alignItems: 'baseline' }}>
                    <Box component="span" sx={{ color: T.badge[r.type].fg, fontSize: '0.72rem', fontWeight: 600, letterSpacing: '0.05em', whiteSpace: 'nowrap' }}>
                      {r.label}
                    </Box>
                    <span>{r.title}</span>
                  </Link>
                ))}
              </Stack>
            </Box>
          )}
        </Box>
      </Collapse>
    </Box>
  );
};
