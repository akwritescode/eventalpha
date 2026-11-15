import React from 'react';
import { Box, Paper, Stack, Typography } from '@mui/material';
import { MONO, T } from '../theme';
import { timeAgo } from '../format';

type Tone = { fg: string; bg: string };

/** Rounded tinted pill (sentiment, confidence, tickers, verdicts). */
export const Pill: React.FC<{ tone?: Tone; children: React.ReactNode; mono?: boolean; title?: string }> = ({
  tone = { fg: T.fg, bg: T.pill },
  children,
  mono,
  title,
}) => (
  <Box
    component="span"
    title={title}
    sx={{
      display: 'inline-flex', alignItems: 'center', height: 26, px: 1.25, borderRadius: 999, fontSize: '0.8rem',
      fontWeight: 500, color: tone.fg, bgcolor: tone.bg, whiteSpace: 'nowrap', letterSpacing: '0.01em',
      fontFamily: mono ? MONO : undefined,
    }}
  >
    {children}
  </Box>
);

/** Small uppercase type badge: "SEC · 8-K", "MACRO · CPI", "TRADING SIGNAL". */
export const TypeBadge: React.FC<{ tone: Tone; children: React.ReactNode }> = ({ tone, children }) => (
  <Box
    component="span"
    sx={{
      display: 'inline-flex', alignItems: 'center', height: 26, px: 1.1, borderRadius: 2, fontSize: '0.78rem',
      fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: tone.fg, bgcolor: tone.bg,
    }}
  >
    {children}
  </Box>
);

export const Num: React.FC<{ children: React.ReactNode; color?: string; size?: string; weight?: number }> = ({
  children, color, size, weight,
}) => (
  <Box component="span" sx={{ fontFamily: MONO, fontVariantNumeric: 'tabular-nums', color, fontSize: size, fontWeight: weight }}>
    {children}
  </Box>
);

/** Side-rail card. */
export const Panel: React.FC<{ id?: string; title: string; subtitle?: React.ReactNode; right?: React.ReactNode; children: React.ReactNode; dense?: boolean }> = ({
  id, title, subtitle, right, children,
}) => (
  <Paper id={id} sx={{ p: 2, scrollMarginTop: 72 }}>
    <Stack direction="row" alignItems="flex-start" justifyContent="space-between" spacing={1} sx={{ mb: 1.5 }}>
      <Box>
        <Typography variant="h2">{title}</Typography>
        {subtitle && <Typography variant="caption" color="text.secondary">{subtitle}</Typography>}
      </Box>
      {right}
    </Stack>
    {children}
  </Paper>
);

export const AsOf: React.FC<{ iso?: string | null; label?: string }> = ({ iso, label = 'updated' }) => (
  <Typography variant="caption" sx={{ color: T.fgMuted, whiteSpace: 'nowrap' }}>
    {label} <Num>{timeAgo(iso)}</Num>
  </Typography>
);

export const Empty: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <Typography variant="body2" color="text.secondary" sx={{ py: 3, textAlign: 'center' }}>{children}</Typography>
);
