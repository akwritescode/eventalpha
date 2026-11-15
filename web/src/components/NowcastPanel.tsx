import React from 'react';
import { Box, Typography } from '@mui/material';
import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, XAxis, YAxis } from 'recharts';
import { Nowcast } from '../api';
import { MONO, useTokens } from '../theme';
import { AsOf, Empty, Panel } from './ui';

const LABELS: Record<string, string> = { cpi: 'CPI', core_cpi: 'Core CPI', pce: 'PCE', core_pce: 'Core PCE' };

export const NowcastPanel: React.FC<{ rows?: Nowcast[]; asOf?: string | null }> = ({ rows = [], asOf }) => {
  const t = useTokens();
  const periods = Array.from(new Set(rows.map((r) => r.targetPeriod))).sort().reverse();
  const current = periods[0];
  const previous = periods[1];
  const data = Object.keys(LABELS).map((m) => {
    const now = rows.find((r) => r.targetPeriod === current && r.measure === m);
    const last = rows.find((r) => r.targetPeriod === previous && r.measure === m);
    return { name: LABELS[m], nowcast: now?.value != null ? Number(now.value) : null, lastActual: last?.actual != null ? Number(last.actual) : null };
  });
  return (
    <Panel id="inflation" title="Inflation nowcast" subtitle={`Cleveland Fed · month-over-month % · ${current ?? ''}`} right={<AsOf iso={asOf} />} dense>
      {rows.length === 0 ? (
        <Empty>No nowcast loaded yet.</Empty>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={150}>
            <BarChart data={data} layout="vertical" margin={{ left: 8, right: 36, top: 0, bottom: 0 }}>
              <XAxis type="number" hide domain={[0, 'dataMax']} />
              <YAxis type="category" dataKey="name" width={64} tick={{ fill: t.fgSecondary, fontSize: 11 }} tickLine={false} axisLine={false} />
              <Bar dataKey="nowcast" barSize={14} radius={[0, 3, 3, 0]}>
                {data.map((d) => <Cell key={d.name} fill={t.series[2]} />)}
                <LabelList dataKey="nowcast" position="right" formatter={(v: number) => (v == null ? '' : `${v.toFixed(2)}%`)}
                  style={{ fill: t.fg, fontSize: 11, fontFamily: MONO }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <Box sx={{ mt: 0.5 }}>
            <Typography variant="caption" color="text.secondary">
              {previous} actual: {data.filter((d) => d.lastActual != null).map((d) => `${d.name} ${d.lastActual?.toFixed(2)}%`).join(' · ') || 'not released yet'}
            </Typography>
          </Box>
        </>
      )}
    </Panel>
  );
};
