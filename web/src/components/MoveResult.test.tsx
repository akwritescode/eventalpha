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
  expect(screen.getByText('No verified catalyst found.')).toBeInTheDocument();
  expect(screen.getByText(/Intraday prices unavailable for this ticker and window/)).toBeInTheDocument();
});

it('hides the web section when the provider is disabled', () => {
  render(<MoveResult result={base} web={{ status: 'done', answer: { answer: null, sources: [], available: false } }} />);
  expect(screen.queryByText(/From the web/)).not.toBeInTheDocument();
});

it('falls back to release-anchored returns and keeps calendar context collapsed', () => {
  render(<MoveResult result={{
    ...base,
    ticker: 'TSLA',
    start: '2026-11-25T21:00:00Z',
    end: '2026-11-26T14:35:00Z',
    asOf: '2026-11-26T14:36:00Z',
    summary: "TSLA fell 1% for the window. No verified catalyst found in EventAlpha's sources. Economic calendar: the 8:30 AM GDP release.",
    catalysts: [],
    lookbackEligible: true,
    benchmarks: ['SPY', 'XLY'],
    economicComparison: {
      since: '2026-11-25T13:30:00Z',
      priceMoves: [{ symbol: 'TSLA', returnPercent: -2 }, { symbol: 'XLY', returnPercent: -0.5 },
        { symbol: 'SPY', returnPercent: -0.25 }],
    },
    priceMoves: [{ symbol: 'TSLA', returnPercent: -1 }],
    timeline: [{
      id: 'release:gdp', title: 'Gross Domestic Product (GDP)', url: 'https://example.com/gdp',
      publishedAt: '2026-11-25T13:30:00Z', firstSeenAt: '2026-11-20T11:00:09Z', timing: 'before',
      status: 'economic_release', originalId: null, verifiedAt: null,
    }],
  }} web={{ status: 'done', answer: { answer: null, sources: [], available: true } }} />);

  expect(screen.getByLabelText('TSLA -2%')).toBeInTheDocument();
  expect(screen.getByLabelText('XLY -0.5%')).toBeInTheDocument();
  expect(screen.getByLabelText('SPY -0.25%')).toBeInTheDocument();
  expect(screen.queryByLabelText('TSLA -1%')).not.toBeInTheDocument();
  expect(screen.queryByText(/From the web|No verified catalyst|Evidence timeline/)).not.toBeInTheDocument();
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
  render(<MoveResult result={{ ...base, ticker: 'SPY', timeline: [], sectorMovers: {
    gainers: [{ sector: 'Software', price: { symbol: 'IGV', returnPercent: 3 } }],
    decliners: [{ sector: 'Consumer staples', price: { symbol: 'XLP', returnPercent: -2 } }],
  } }} />);
  expect(screen.getByText('Top gainers')).toBeInTheDocument();
  expect(screen.getByText('Top decliners')).toBeInTheDocument();
  expect(screen.getByText('IGV').closest('li')).toHaveTextContent('Software IGV+3%');
  expect(screen.getByText('XLP').closest('li')).toHaveTextContent('Consumer staples XLP-2%');
  expect(screen.queryByLabelText('SMH -1%')).not.toBeInTheDocument();
});

it('labels commentary and JEV-judged causes without showing calendar context or X links', () => {
  render(<MoveResult result={{ ...base, priceMoves: [], catalysts: [{ summary: 'Tariff delay', evidenceId: 'article:9002' }], timeline: [
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
  expect(screen.queryByText('Economic calendar context')).not.toBeInTheDocument();
  expect(screen.getByText('Market commentary')).toBeInTheDocument();
  expect(screen.getByText('Explains the move · JEV 0.98')).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'View X post' })).not.toBeInTheDocument();
});

it('replaces window returns with one set of returns anchored to the web article', () => {
  const publishedAt = '2025-04-15T21:24:30Z';
  render(<MoveResult result={{
    ...base,
    ticker: 'TSLA',
    benchmarks: ['SPY', 'XLY'],
    lookbackEligible: true,
    economicComparison: { since: '2025-04-15T13:00:00Z', priceMoves: [{ symbol: 'TSLA', returnPercent: 3 }] },
    priceMoves: [{ symbol: 'TSLA', returnPercent: 2 }],
  }} web={{ status: 'done', answer: {
    available: true, answer: 'Reporting attributed the move to a delivery update.', publishedAt,
    sources: [{ title: 'Tesla deliveries', url: 'https://example.com/deliveries' }],
    comparison: { since: publishedAt, priceMoves: [
      { symbol: 'TSLA', returnPercent: 1.5 }, { symbol: 'XLY', returnPercent: 0.5 }, { symbol: 'SPY', returnPercent: 0.1 },
    ] },
  } }} />);
  expect(screen.getByText('From the web')).toBeInTheDocument();
  expect(screen.getByText(/Published Apr 15, 5:24:30 PM EDT/)).toBeInTheDocument();
  expect(screen.getByLabelText('TSLA +1.5%')).toBeInTheDocument();
  expect(screen.getByLabelText('XLY +0.5%')).toBeInTheDocument();
  expect(screen.getByLabelText('SPY +0.1%')).toBeInTheDocument();
  expect(screen.queryByLabelText('TSLA +2%')).not.toBeInTheDocument();
  expect(screen.queryByText(/Economic calendar context|No verified catalyst|What we found/)).not.toBeInTheDocument();
});

it('uses a calendar-backed holiday message and waits for the search to conclude', () => {
  const result = { ...base, timeline: [], priceMoves: [], lookbackEligible: false,
    priceUnavailableReason: 'U.S. markets were closed (Thanksgiving). No new prices are available for this window.' };
  const { rerender } = render(<MoveResult result={result} web={{ status: 'loading' }} />);
  expect(screen.getByText(/markets were closed \(Thanksgiving\)/)).toBeInTheDocument();
  expect(screen.queryByText(/every 15 minutes|No verified catalyst|What we found/)).not.toBeInTheDocument();
  rerender(<MoveResult result={result} web={{ status: 'done', answer: { answer: null, available: true, sources: [] } }} />);
  expect(screen.getAllByText('No verified catalyst found.')).toHaveLength(1);
  expect(screen.queryByText('From the web')).not.toBeInTheDocument();
});

it('keeps the selected-window benchmarks on a small move and hides calendar entries', () => {
  render(<MoveResult result={{
    ...base, ticker: 'TSLA', benchmarks: ['SPY', 'XLY'], lookbackEligible: false,
    priceMoves: [{ symbol: 'TSLA', returnPercent: 0.1 }, { symbol: 'XLY', returnPercent: 0.15 },
      { symbol: 'SPY', returnPercent: 0.05 }],
    timeline: [{ ...base.timeline[0], id: 'release:gdp', title: 'GDP', status: 'economic_release', timing: 'during' }],
  }} />);
  expect(screen.getByLabelText('TSLA +0.1%')).toBeInTheDocument();
  expect(screen.getByLabelText('XLY +0.15%')).toBeInTheDocument();
  expect(screen.getByLabelText('SPY +0.05%')).toBeInTheDocument();
  expect(screen.getByText('No verified catalyst found.')).toBeInTheDocument();
  expect(screen.queryByText('Economic calendar context')).not.toBeInTheDocument();
});

it('hides earlier context after a web explanation and lists the remaining evidence by newest publication', () => {
  const result: Explanation = {
    ...base,
    start: '2026-11-25T13:22:00Z',
    end: '2026-11-27T02:22:00Z',
    asOf: '2026-11-27T02:23:00Z',
    lookbackEligible: true,
    timeline: [
      { ...base.timeline[0], id: 'article:earlier', title: 'Pre-window article', status: 'original_source',
        timing: 'before', publishedAt: '2026-11-23T20:00:00Z' },
      { ...base.timeline[0], id: 'x:morning', title: 'Morning discovery', status: 'verified_discovery',
        timing: 'during', originalId: 'article:earlier', publishedAt: '2026-11-25T15:00:00Z', firstSeenAt: '2026-11-25T19:00:00Z' },
      { ...base.timeline[0], id: 'article:afternoon', title: 'Afternoon article', status: 'market_commentary',
        timing: 'during', publishedAt: '2026-11-25T18:32:00Z', firstSeenAt: '2026-11-25T18:45:11Z' },
    ],
  };

  const { rerender } = render(<MoveResult result={result} />);
  expect(screen.getByText('Pre-window article')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Original evidence' })).toBeInTheDocument();

  rerender(<MoveResult result={result} web={{ status: 'done', answer: {
    available: true, answer: 'Reports attributed the selloff to a company announcement.',
    sources: [{ title: 'Coverage', url: 'https://example.com/coverage' }], publishedAt: null,
  } }} />);

  const rows = screen.getAllByRole('listitem');
  expect(rows).toHaveLength(2);
  expect(rows[0]).toHaveTextContent('Afternoon article');
  expect(rows[1]).toHaveTextContent('Morning discovery');
  expect(screen.queryByText('Pre-window article')).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Original evidence' })).not.toBeInTheDocument();
});
