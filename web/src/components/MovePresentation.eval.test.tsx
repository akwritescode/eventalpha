import { render, screen } from '@testing-library/react';
import { readFileSync } from 'fs';
import { resolve } from 'path';
import { Explanation, MoveResult, WebSearch } from './MoveResult';

type Scenario = {
  id: string;
  lookbackEligible: boolean;
  holiday?: boolean;
  web: 'empty' | 'article' | 'earlierArticle' | 'pending' | 'undatedArticle';
  expectedSections: string[];
  expectedPrices: string[];
};

// Synthetic API responses. Render the real result component and independently grade the visible choices.
const scenarios: Scenario[] = JSON.parse(readFileSync(
  resolve(__dirname, '../../../evals/move_presentation.json'), 'utf8',
));
const releaseAt = '2026-11-25T13:30:00Z';
const start = '2026-11-25T21:00:00Z';
const end = '2026-11-26T16:30:00Z';
const prices = (ticker: number, sector: number, market: number) => [
  { symbol: 'TSLA', returnPercent: ticker },
  { symbol: 'XLY', returnPercent: sector },
  { symbol: 'SPY', returnPercent: market },
];

function webResponse(scenario: Scenario): WebSearch {
  if (scenario.web === 'pending') return { status: 'loading' };
  if (scenario.web === 'empty') {
    return { status: 'done', answer: { available: true, answer: null, sources: [] } };
  }

  const publishedAt = scenario.web === 'undatedArticle' ? null
    : scenario.web === 'earlierArticle' ? '2026-11-25T20:00:00Z' : '2026-11-26T16:00:00Z';
  return { status: 'done', answer: {
    available: true,
    answer: 'The report attributed the move to a company announcement.',
    sources: [{ title: 'Company coverage', url: 'https://example.com/report' }],
    publishedAt,
    comparison: publishedAt ? {
      since: publishedAt,
      priceMoves: scenario.holiday ? [] : prices(0.08, 0.06, 0.03),
    } : null,
  } };
}

it.each(scenarios)('$id', scenario => {
  const result: Explanation = {
    ticker: 'TSLA', start, end, asOf: '2026-11-26T16:35:00Z',
    summary: 'No verified catalyst found for this move.',
    windowSummary: scenario.holiday ? '' : 'TSLA was little changed (+0.1%) for the window.',
    catalysts: [], benchmarks: ['SPY', 'XLY'],
    priceMoves: scenario.holiday ? [] : prices(0.1, 0.15, 0.05),
    priceUnavailableReason: scenario.holiday ? 'U.S. markets were closed (Thanksgiving).' : null,
    lookbackEligible: scenario.lookbackEligible,
    economicComparison: scenario.lookbackEligible ? { since: releaseAt, priceMoves: prices(-1.2, -0.5, -0.25) } : null,
    timeline: [{
      id: 'release:gdp', title: 'Gross Domestic Product (GDP)', url: 'https://example.com/gdp',
      publishedAt: releaseAt, firstSeenAt: releaseAt, timing: 'before', status: 'economic_release',
      originalId: null, verifiedAt: null,
    }],
  };
  render(<MoveResult result={result} web={webResponse(scenario)} />);

  const availableSections = Object.entries({
    holiday: /markets were closed \(Thanksgiving\)/,
    web: /^From the web$/,
    publicationTime: /^Published Nov /,
    calendar: /^Economic calendar context$/,
    noCatalyst: /^No verified catalyst found\.$/,
    searching: /^Searching news coverage/,
  }).filter(([, text]) => screen.queryByText(text)).map(([section]) => section);

  expect(availableSections.sort()).toEqual([...scenario.expectedSections].sort());
  const cards = screen.queryAllByLabelText(/^(TSLA|SPY|XLY) (?:[+-]?\d|Unavailable)/);
  expect(cards.map(card => card.getAttribute('aria-label')).sort()).toEqual([...scenario.expectedPrices].sort());
  if (scenario.web === 'undatedArticle') {
    expect(screen.getByText(result.windowSummary!)).toBeInTheDocument();
  }
});
