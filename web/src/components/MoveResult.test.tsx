import { fireEvent, render, screen, within } from '@testing-library/react';
import { Explanation, MoveResult } from './MoveResult';

const base: Explanation = {
  ticker: 'NVDA',
  start: '2025-04-15T21:20:00Z',
  end: '2025-04-15T21:35:00Z',
  asOf: '2025-04-15T22:00:00Z',
  summary: 'No verified catalyst found for this move.',
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

it('hides the web section when the provider is disabled', () => {
  render(<MoveResult result={base} web={{ status: 'done', answer: { answer: null, sources: [], available: false } }} />);
  expect(screen.queryByText(/From a web search/)).not.toBeInTheDocument();
});

it('combines an empty web result with the main conclusion and keeps calendar context collapsed', () => {
  render(<MoveResult result={{
    ...base,
    ticker: 'TSLA',
    start: '2026-11-25T21:00:00Z',
    end: '2026-11-26T14:35:00Z',
    asOf: '2026-11-26T14:36:00Z',
    summary: "TSLA fell 1% for the window. No verified catalyst found in EventAlpha's sources. Economic calendar: the 8:30 AM GDP release.",
    catalysts: [],
    priceMoves: [{ symbol: 'TSLA', returnPercent: -1 }],
    timeline: [{
      id: 'release:gdp', title: 'Gross Domestic Product (GDP)', url: 'https://example.com/gdp',
      publishedAt: '2026-11-25T13:30:00Z', firstSeenAt: '2026-11-20T11:00:09Z', timing: 'before',
      status: 'economic_release', originalId: null, verifiedAt: null,
    }],
  }} web={{ status: 'done', answer: { answer: null, sources: [], available: true } }} />);

  expect(screen.getByText('TSLA fell 1% for the window. No specific catalyst was found in EventAlpha’s sources or in news coverage.'))
    .toBeInTheDocument();
  expect(screen.queryByText(/From a web search|No reported cause|Evidence timeline/)).not.toBeInTheDocument();
  const preview = screen.getByText('Economic calendar context');
  expect(preview).toHaveTextContent(/Before the move window · GDP, Nov 25,? (?:at )?8:30 AM EST/);
  expect(preview.closest('details')).not.toHaveAttribute('open');
  fireEvent.click(preview);
  expect(preview.closest('details')).toHaveAttribute('open');
  expect(screen.getByText(/Scheduled release · Nov 25/)).toBeInTheDocument();
  expect(screen.queryByText(/First seen|Nov 20|Published/)).not.toBeInTheDocument();
});

it('moves calendar context out of the summary for every release the API names', () => {
  // "import prices" is the API's name for "U.S. Import and Export Price Indexes": no periods to cut the sentence short.
  render(<MoveResult result={{
    ...base,
    summary: 'SPY was little changed (+0.1%) for the window. Economic calendar: the 8:30 AM import prices release. '
      + 'Leading sectors: Technology +0.4%.',
    timeline: [{
      id: 'release:imports', title: 'U.S. Import and Export Price Indexes (import prices)', url: 'https://example.com/imports',
      publishedAt: '2026-11-17T13:30:00Z', firstSeenAt: '2026-11-10T11:00:00Z', timing: 'before',
      status: 'economic_release', originalId: null, verifiedAt: null,
    }],
  }} />);
  expect(screen.getByText('SPY was little changed (+0.1%) for the window. Leading sectors: Technology +0.4%.'))
    .toBeInTheDocument();
  expect(screen.queryByText(/Economic calendar:/)).not.toBeInTheDocument();
  expect(screen.getByText('Economic calendar context')).toHaveTextContent(/import prices/);
});

it('renders web citations only for HTTP and HTTPS URLs', () => {
  render(<MoveResult result={base} web={{ status: 'done', answer: {
    answer: 'Attributed news coverage.', available: true,
    sources: [
      { title: 'Report', url: 'https://example.com/report' },
      // eslint-disable-next-line no-script-url -- Intentional unsafe citation to exercise the URL filter.
      { title: 'Unsafe', url: 'javascript:alert(1)' },
    ],
  } }} />);
  expect(screen.getByRole('link', { name: 'Report' })).toHaveAttribute('href', 'https://example.com/report');
  expect(screen.queryByRole('link', { name: 'Unsafe' })).not.toBeInTheDocument();
});

it('shows ranked sector ETFs with their names and returns', () => {
  render(<MoveResult result={{ ...base, timeline: [], sectorMovers: {
    gainers: [{ sector: 'Software', price: { symbol: 'IGV', returnPercent: 3 } }],
    decliners: [{ sector: 'Consumer staples', price: { symbol: 'XLP', returnPercent: -2 } }],
  } }} />);
  expect(screen.getByText('Top gainers')).toBeInTheDocument();
  expect(screen.getByText('Top decliners')).toBeInTheDocument();
  expect(screen.getByText('IGV').closest('li')).toHaveTextContent('Software IGV+3%');
  expect(screen.getByText('XLP').closest('li')).toHaveTextContent('Consumer staples XLP-2%');
  expect(screen.queryByLabelText('SMH -1%')).not.toBeInTheDocument();
});

it('labels releases, commentary and JEV-judged causes without X links', () => {
  render(<MoveResult result={{ ...base, priceMoves: [], timeline: [
    { id: 'release:fred:54|2026-11-25', title: 'Personal Income and Outlays (PCE)', url: 'https://fred.stlouisfed.org/release?rid=54',
      publishedAt: '2026-11-25T13:30:00Z', firstSeenAt: '2026-11-25T13:30:00Z', timing: 'before', status: 'economic_release',
      originalId: null, verifiedAt: null },
    { id: 'article:9001', title: 'Chip stocks rally as semiconductor ETF jumps 4% at midday', url: 'https://example.com/chips',
      publishedAt: '2026-11-25T17:30:00Z', firstSeenAt: '2026-11-25T17:30:00Z', timing: 'during', status: 'market_commentary',
      originalId: null, verifiedAt: null },
    { id: 'article:9002', title: 'Semiconductor shares rebound after tariff delay', url: 'https://example.com/delay',
      publishedAt: '2026-11-25T17:40:00Z', firstSeenAt: '2026-11-25T17:40:00Z', timing: 'during', status: 'explains_move',
      originalId: null, verifiedAt: null, causeScore: 0.98 },
  ] }} />);
  fireEvent.click(screen.getByText('Economic calendar context'));
  expect(screen.getByText('Economic release')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Personal Income and Outlays (PCE)' })).toHaveAttribute('href', 'https://fred.stlouisfed.org/release?rid=54');
  expect(screen.getByText('Market commentary')).toBeInTheDocument();
  expect(screen.getByText('Explains the move · JEV 0.98')).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'View X post' })).not.toBeInTheDocument();
});
