import React from 'react';
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { SentimentDay } from '../api';
import { etDate } from '../format';
import { MONO, useTokens } from '../theme';
import { AsOf, Empty, Panel } from './ui';

/** Featured chart: daily company-specific news by sentiment, with the mean sentiment score. */
export const SentimentChart: React.FC<{ days?: SentimentDay[]; asOf?: string | null }> = ({ days = [], asOf }) => {
  const t = useTokens();
  const data = days.map((d) => ({ ...d, label: etDate(d.day), mean: d.meanScore == null ? null : Number(d.meanScore.toFixed(3)) }));
  const axis = { fill: t.fgSecondary, fontSize: 11, fontFamily: MONO };
  return (
    <Panel
      id="overview"
      title="News sentiment"
      subtitle="Company-specific items per day · line: mean score"
      right={<AsOf iso={asOf} />}
    >
      {data.length === 0 ? (
        <Empty>No scored news yet.</Empty>
      ) : (
        <ResponsiveContainer width="100%" height={190}>
          <ComposedChart data={data} margin={{ top: 8, right: 4, left: -16, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={t.border} />
            <XAxis dataKey="label" tick={axis} tickLine={false} axisLine={{ stroke: t.border }} />
            <YAxis yAxisId="n" tick={axis} tickLine={false} axisLine={false} />
            <YAxis yAxisId="s" orientation="right" domain={[-1, 1]} tick={axis} tickLine={false} axisLine={false} />
            <Tooltip
              contentStyle={{ background: t.popover, border: `1px solid ${t.border}`, borderRadius: 6, fontSize: 12 }}
              labelStyle={{ color: t.fg }}
              cursor={{ fill: t.border }}
            />
            <Legend wrapperStyle={{ fontSize: 11, color: t.fgSecondary }} iconSize={7} />
            <Bar yAxisId="n" dataKey="bullish" stackId="s" fill={t.up} name="Bullish" />
            <Bar yAxisId="n" dataKey="neutral" stackId="s" fill={t.fgSecondary} fillOpacity={0.45} name="Neutral" />
            <Bar yAxisId="n" dataKey="bearish" stackId="s" fill={t.down} name="Bearish" radius={[3, 3, 0, 0]} />
            <Line yAxisId="s" dataKey="mean" stroke={t.series[1]} strokeWidth={2} dot={{ r: 2 }} name="Mean score" connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </Panel>
  );
};
