import React, { useMemo } from 'react';
import { CacheProvider } from '@emotion/react';
import createCache from '@emotion/cache';
import CssBaseline from '@mui/material/CssBaseline';
import { ThemeProvider as MuiThemeProvider, alpha, createTheme } from '@mui/material/styles';

/*
 * Dark navy + amber (theme-color #0a0e1a), with Linear's
 * restraint (quiet borders, generous spacing, few colors) and Perplexity-style content cards.
 * Type badges follow the stream mock: SEC blue, NEWS violet, MACRO orange, SIGNAL green.
 */
const slate = { 100: '#f1f5f9', 200: '#e2e8f0', 300: '#cbd5e1', 400: '#94a3b8', 500: '#64748b', 600: '#475569', 700: '#334155' };

export const T = {
  bg: '#0a0e1a',
  surface: '#0d1220',
  raised: '#121a2c',
  popover: '#141c30',
  border: alpha(slate[400], 0.14),
  borderStrong: alpha(slate[400], 0.24),
  fg: slate[100],
  fgSecondary: slate[400],
  fgMuted: slate[500],
  amber: '#f59e0b',
  amberHover: '#fbbf24',
  up: '#4ade80',
  down: '#f87171',
  series: ['#4ade80', '#60a5fa', '#a78bfa', '#f59e0b', '#f472b6'],
  pill: alpha(slate[400], 0.14),
  badge: {
    sec: { fg: '#60a5fa', bg: alpha('#3b82f6', 0.16) },
    news: { fg: '#a78bfa', bg: alpha('#8b5cf6', 0.16) },
    macro: { fg: '#fb923c', bg: alpha('#f97316', 0.16) },
    signal: { fg: '#4ade80', bg: alpha('#22c55e', 0.16) },
  },
  tone: {
    bullish: { fg: '#4ade80', bg: alpha('#22c55e', 0.16) },
    bearish: { fg: '#f87171', bg: alpha('#ef4444', 0.16) },
    neutral: { fg: slate[300], bg: alpha(slate[400], 0.14) },
  },
};

export type Tokens = typeof T;
export const useTokens = (): Tokens => T;

export const MONO = '"Geist Mono", ui-monospace, SFMono-Regular, Menlo, monospace';
const SANS = 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif';

const emotionCache = createCache({ key: 'css', prepend: true });

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const theme = useMemo(
    () =>
      createTheme({
        palette: {
          mode: 'dark',
          primary: { main: T.amber, contrastText: '#1a1205' },
          success: { main: T.up },
          error: { main: T.down },
          background: { default: T.bg, paper: T.surface },
          text: { primary: T.fg, secondary: T.fgSecondary },
          divider: T.border,
          action: { hover: alpha(slate[400], 0.06) },
        },
        shape: { borderRadius: 8 },
        typography: {
          fontFamily: SANS,
          fontSize: 14,
          h1: { fontSize: '1.15rem', fontWeight: 600, letterSpacing: '-0.01em' },
          h2: { fontSize: '1rem', fontWeight: 600 },
          h3: { fontSize: '1.02rem', fontWeight: 600, lineHeight: 1.35 },
          body1: { lineHeight: 1.6 },
          overline: { fontSize: '0.72rem', letterSpacing: '0.04em', fontWeight: 500, lineHeight: 1.6 },
        },
        components: {
          MuiCssBaseline: { styleOverrides: { body: { backgroundColor: T.bg } } },
          MuiPaper: {
            defaultProps: { elevation: 0 },
            styleOverrides: { root: { backgroundImage: 'none', border: `1px solid ${T.border}`, borderRadius: 14 } },
          },
          MuiButton: { styleOverrides: { root: { textTransform: 'none', borderRadius: 8, fontWeight: 600 } } },
          MuiAppBar: { styleOverrides: { root: { backgroundImage: 'none' } } },
        },
      }),
    []
  );
  return (
    <CacheProvider value={emotionCache}>
      <MuiThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </MuiThemeProvider>
    </CacheProvider>
  );
};
