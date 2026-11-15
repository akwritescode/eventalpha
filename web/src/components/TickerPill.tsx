import React from 'react';
import { Box } from '@mui/material';
import { setTicker, useTicker } from '../hooks/useTicker';
import { MONO, T } from '../theme';

/**
 * Every ticker on the page renders through this: a pill that filters the stream to that company.
 * `dashed` marks a not-yet-confirmed earnings date; `title` overrides the tooltip.
 */
export const TickerPill: React.FC<{ ticker: string; dashed?: boolean; title?: string; size?: 'sm' | 'md' }> = ({
  ticker, dashed, title, size = 'md',
}) => {
  const active = useTicker() === ticker.toUpperCase();
  return (
    <Box
      component="button"
      type="button"
      onClick={(e: React.MouseEvent) => {
        e.stopPropagation();
        setTicker(active ? null : ticker);
      }}
      title={title ?? (active ? 'Show all companies' : `Show only ${ticker}`)}
      aria-pressed={active}
      sx={{
        display: 'inline-flex', alignItems: 'center', height: size === 'sm' ? 24 : 26, px: size === 'sm' ? 1 : 1.25,
        borderRadius: 999, fontSize: size === 'sm' ? '0.76rem' : '0.8rem', fontWeight: 600, fontFamily: MONO,
        letterSpacing: '0.01em', whiteSpace: 'nowrap', cursor: 'pointer',
        color: active ? T.amberHover : dashed ? T.fgSecondary : T.fg,
        bgcolor: active ? 'rgba(245,158,11,0.12)' : T.pill,
        border: `1px ${dashed ? 'dashed' : 'solid'} ${active ? 'rgba(245,158,11,0.45)' : dashed ? T.borderStrong : 'transparent'}`,
        transition: 'background-color .15s, color .15s',
        '&:hover': { color: T.amberHover, bgcolor: 'rgba(245,158,11,0.12)' },
        '&:focus-visible': { outline: `2px solid ${T.amber}`, outlineOffset: 2 },
      }}
    >
      {ticker}
    </Box>
  );
};
