import React from 'react';
import { Box, Stack, Typography } from '@mui/material';
import { InsiderBuy } from '../api';
import { money } from '../format';
import { useTokens } from '../theme';
import { AsOf, Empty, Num, Panel } from './ui';

/** Largest open-market purchases; bar length = value, dot = several insiders buying (a cluster). */
export const InsiderPanel: React.FC<{ buys?: InsiderBuy[]; asOf?: string | null }> = ({ buys = [], asOf }) => {
  const t = useTokens();
  const max = Math.max(1, ...buys.map((b) => Number(b.value)));
  return (
    <Panel id="insiders" title="Insider buying" subtitle="Open-market purchases (Form 4, code P) · last 14 days" right={<AsOf iso={asOf} />} dense>
      {buys.length === 0 && <Empty>No open-market purchases.</Empty>}
      <Stack spacing={0.9}>
        {buys.slice(0, 10).map((b) => (
          <Box key={b.ticker + b.ownerName}>
            <Stack direction="row" justifyContent="space-between" alignItems="baseline" spacing={1}>
              <Typography sx={{ fontSize: '0.82rem', minWidth: 0 }} noWrap>
                <b>{b.ticker}</b>{' '}
                <Typography component="span" variant="caption" color="text.secondary">
                  {b.ownerName}{b.officerTitle ? `, ${b.officerTitle}` : ''}
                </Typography>
              </Typography>
              <Stack direction="row" spacing={0.75} alignItems="center">
                {b.insiders30d > 1 && (
                  <Typography variant="caption" sx={{ color: t.series[3], whiteSpace: 'nowrap' }}>{b.insiders30d} insiders</Typography>
                )}
                <Num size="0.8rem">{money(Number(b.value))}</Num>
              </Stack>
            </Stack>
            <Box sx={{ height: 3, mt: 0.4, borderRadius: 2, bgcolor: t.border }}>
              <Box sx={{ height: 3, borderRadius: 2, width: `${(Number(b.value) / max) * 100}%`, bgcolor: t.up }} />
            </Box>
          </Box>
        ))}
      </Stack>
    </Panel>
  );
};
