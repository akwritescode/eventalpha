import { render, screen, within } from '@testing-library/react';
import { Explanation, MoveResult } from './MoveResult';

const base: Explanation = {
  ticker: 'NVDA',
  start: '2025-04-15T21:20:00Z',
  end: '2025-04-15T21:35:00Z',
  asOf: '2025-04-15T22:00:00Z',
  summary: 'No clear catalyst found',
  catalysts: [],
  priceMoves: [
    { symbol: 'NVDA', returnPercent: -2.5 },
    { symbol: 'SPY', returnPercent: -0.2 },
    { symbol: 'SMH', returnPercent: -1 },
  ],
  timeline: [{
    id: 'x:1001',
    title: 'A later post speculated about order cancellations.',
    url: 'https://x.com/i/status/1001',
    publishedAt: '2025-04-15T21:40:00Z',
    firstSeenAt: '2025-04-15T21:41:00Z',
    timing: 'after',
    status: 'unverified_lead',
    originalId: null,
    verifiedAt: null,
  }],
};

it('shows returns, the demo note and a late lead in the retrospective timeline', () => {
  render(<MoveResult result={base} />);
  expect(screen.getByText(/real SEC filing with simulated X posts/)).toBeInTheDocument();
  expect(screen.getByLabelText('NVDA -2.5%')).toBeInTheDocument();
  expect(screen.getByLabelText('SPY -0.2%')).toBeInTheDocument();
  expect(screen.getByLabelText('SMH -1%')).toBeInTheDocument();
  const lead = within(screen.getByRole('listitem'));
  expect(lead.getByText('After · later context')).toBeInTheDocument();
  expect(lead.getByText('Unverified X lead')).toBeInTheDocument();
  expect(lead.getByRole('link', { name: 'View X post' })).toHaveAttribute('href', 'https://x.com/i/status/1001');
  expect(screen.queryByText('As known at window end')).not.toBeInTheDocument();
});

it('marks a replay and explains missing prices and evidence', () => {
  render(<MoveResult result={{ ...base, asOf: base.end, priceMoves: [], timeline: [] }} />);
  expect(screen.getByText('As known at window end')).toBeInTheDocument();
  expect(screen.getByText('No matching evidence in the timeline.')).toBeInTheDocument();
  expect(screen.getByText(/Intraday prices unavailable for this ticker and window/)).toBeInTheDocument();
});
