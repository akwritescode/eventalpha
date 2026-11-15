import React, { useState } from 'react';
import { Box, Stack, Typography } from '@mui/material';
import { Calendar } from '../api';
import { etDate, etTime } from '../format';
import { useTokens } from '../theme';
import { AsOf, Empty, Num, Panel } from './ui';
import { TickerPill } from './TickerPill';

const capLabel = (v: number) =>
  v >= 1e12 ? `$${(v / 1e12).toFixed(1)}T market cap` : v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B market cap` : `$${Math.round(v / 1e6)}M market cap`;

export const CalendarPanel: React.FC<{ calendar?: Calendar; asOf?: string | null }> = ({ calendar, asOf }) => {
  const t = useTokens();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const byDay = new Map<string, { econ: Calendar['economic']; earnings: Calendar['earnings'] }>();
  calendar?.economic.forEach((e) => {
    const d = byDay.get(e.eventDate) ?? { econ: [], earnings: [] };
    d.econ.push(e);
    byDay.set(e.eventDate, d);
  });
  calendar?.earnings.forEach((e) => {
    const d = byDay.get(e.eventDate) ?? { econ: [], earnings: [] };
    d.earnings.push(e);
    byDay.set(e.eventDate, d);
  });
  const days = Array.from(byDay.entries()).sort(([a], [b]) => a.localeCompare(b)).slice(0, 6);
  return (
    <Panel id="calendar" title="Calendar" subtitle="Next 14 days · BLS, FRED, FOMC, earnings" right={<AsOf iso={asOf} />} dense>
      {days.length === 0 && <Empty>No scheduled events.</Empty>}
      <Stack spacing={1.25}>
        {days.map(([day, d]) => (
          <Box key={day}>
            <Typography variant="overline" color="text.secondary">
              {etDate(day, { weekday: 'short', month: 'short', day: 'numeric' })}
            </Typography>
            {d.econ.map((e) => (
              <Stack key={e.title + e.source} direction="row" spacing={1} alignItems="center">
                <Num size="0.75rem" color={t.fgSecondary}>{e.scheduledAt ? etTime(e.scheduledAt) : '—:—'}</Num>
                <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: e.importance === 'high' ? t.series[3] : t.fgSecondary }} />
                <Typography sx={{ fontSize: '0.82rem' }} noWrap>{e.title}</Typography>
              </Stack>
            ))}
            {d.earnings.length > 0 && (
              <Stack direction="row" spacing={0.5} sx={{ mt: 0.5, flexWrap: 'wrap', rowGap: 0.5 }}>
                <Typography variant="caption" color="text.secondary" sx={{ mr: 0.5 }}>earnings</Typography>
                {(expanded.has(day) ? d.earnings : d.earnings.slice(0, 8)).map((e) => (
                  <TickerPill key={e.ticker} ticker={e.ticker} size="sm" dashed={e.status !== 'Confirmed'}
                    title={`${e.ticker}${e.marketCap ? ` · ${capLabel(e.marketCap)}` : ''} · ${e.status === 'Confirmed' ? 'date confirmed' : 'estimated date'}. Click to filter the stream.`} />
                ))}
                {d.earnings.length > 8 && !expanded.has(day) && (
                  <Box component="button" type="button" onClick={() => setExpanded((x) => new Set(x).add(day))}
                    sx={{ border: 0, bgcolor: 'transparent', color: t.fgSecondary, cursor: 'pointer', fontSize: '0.75rem', fontFamily: 'inherit', '&:hover': { color: t.fg } }}>
                    +{d.earnings.length - 8} more
                  </Box>
                )}
              </Stack>
            )}
          </Box>
        ))}
      </Stack>
      {calendar && calendar.earnings.length > 0 && (
        <Typography variant="caption" color="text.secondary" component="div" sx={{ mt: 1.5 }}>
          Earnings: largest company first. Dashed outline = estimated date, not yet confirmed. Click a ticker to filter the stream.
        </Typography>
      )}
    </Panel>
  );
};
