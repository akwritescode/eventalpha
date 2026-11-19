import { isReplay, MAX_CANDIDATES, recentWindow, resolveTicker, tickerQuery, windowError } from './moveInput';

test('ticker discovery ignores finance acronyms and stock suffixes', () => {
  expect(tickerQuery('Why is NVDA stock down')).toBe('NVDA');
  expect(tickerQuery('Did the SEC filing affect NVDA in the last hour?')).toBe('NVDA');
  expect(tickerQuery('Why did the stock drop?')).toBeUndefined();
  expect(tickerQuery('Why did the Nvidia stock drop?')).toBe('Nvidia');
  expect(tickerQuery('Why is Nvidia stock down today?')).toBe('Nvidia');
});

test('relative windows align to completed minutes and validate bounds', () => {
  const now = Date.parse('2026-11-18T18:30:23Z');
  expect(recentWindow(30, now)).toEqual({ start: '2026-11-18T18:00:00.000Z', end: '2026-11-18T18:30:00.000Z' });
  expect(windowError(now, now)).toContain('valid start and end');
  expect(windowError(now - 25 * 3600_000, now)).toContain('24 hours');
});

test('replay requires distinct words', () => {
  expect(isReplay('AMD has offset the decline in the last hour')).toBe(false);
  expect(isReplay('as of the end')).toBe(true);
  expect(isReplay('What was available by the end?')).toBe(true);
});

test('the company subject wins over acronyms elsewhere in the question', () => {
  expect(tickerQuery('Why did Nvidia move on the AI news?')).toBe('Nvidia');
  expect(tickerQuery('Why did NVDA move at 3 PM?')).toBe('NVDA');
  expect(tickerQuery('Did FDA approval move LLY?')).toBe('LLY');
  expect(tickerQuery('Why did AI move today?')).toBe('AI');
});

test('one-word followups reuse the existing ticker', () => {
  expect(tickerQuery('today')).toBeUndefined();
  expect(tickerQuery('replay')).toBeUndefined();
  expect(tickerQuery('TODAY')).toBeUndefined();
  expect(tickerQuery('REPLAY')).toBeUndefined();
  expect(tickerQuery('AAPL')).toBe('AAPL');
});

jest.mock('./api', () => ({ getJson: jest.fn() }));
const { getJson } = jest.requireMock('./api') as { getJson: jest.Mock };

test('a named company after the verb takes precedence over incidental AI news', async () => {
  getJson.mockReset();
  getJson.mockResolvedValue({ data: [{ ticker: 'NVDA', name: 'Nvidia' }] });
  expect((await resolveTicker('Did the AI news move Nvidia?')).matches.map(item => item.ticker)).toEqual(['NVDA']);
  expect(getJson).toHaveBeenCalledTimes(1);
  expect(getJson.mock.calls[0][0]).toContain('q=Nvidia');
});

test('fallback confirms uppercase candidates and preserves ambiguity', async () => {
  getJson.mockReset();
  getJson.mockImplementation((path: string) => {
    const query = new URLSearchParams(path.split('?')[1]).get('q');
    const known: Record<string, string> = { AI: 'C3.ai', NVDA: 'Nvidia' };
    return Promise.resolve({ data: known[query!] ? [{ ticker: query, name: known[query!] }] : [{ ticker: 'CPIR', name: 'Prefix match' }] });
  });
  const result = await resolveTicker('AI and NVDA on CPI GDP FOMC NYSE IPO EPS news?');
  expect(result.matches.map(item => item.ticker)).toEqual(['AI', 'NVDA']);
  // Capped at MAX_CANDIDATES lookups: AI, NVDA, CPI, GDP, FOMC.
  expect(getJson).toHaveBeenCalledTimes(MAX_CANDIDATES);
});

const exactOnly = (known: Record<string, string>) => (path: string) => {
  const query = new URLSearchParams(path.split('?')[1]).get('q')!;
  return known[query] ? Promise.resolve({ data: [{ ticker: query, name: known[query] }] }) : Promise.resolve({ data: [] });
};

test('clock times and time zones are never ticker candidates', async () => {
  getJson.mockReset();
  getJson.mockImplementation(exactOnly({ NVDA: 'Nvidia', AM: 'Antero Midstream', PM: 'Philip Morris', ET: 'Energy Transfer' }));
  const result = await resolveTicker('NVDA since 10 AM ET, or 3:30PM EST?');
  expect(result.matches.map(item => item.ticker)).toEqual(['NVDA']);
  expect(getJson).toHaveBeenCalledTimes(1);
});

test('past-tense verbs name their object instead of falling back to uppercase words', () => {
  expect(tickerQuery('What moved NVDA since 10 AM ET?')).toBe('NVDA');
  expect(tickerQuery('What affected AAPL after earnings?')).toBe('AAPL');
  expect(tickerQuery('What moved after CPI?')).toBeUndefined();
});

test('one failed lookup keeps the candidates the others confirmed', async () => {
  getJson.mockReset();
  getJson.mockImplementation((path: string) => path.includes('q=AI')
    ? Promise.reject(new Error('429')) : exactOnly({ NVDA: 'Nvidia' })(path));
  expect((await resolveTicker('AI and NVDA news?')).matches.map(item => item.ticker)).toEqual(['NVDA']);
});
