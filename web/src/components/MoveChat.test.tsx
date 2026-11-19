import { act, fireEvent, render, screen } from '@testing-library/react';
import { MoveChat } from './MoveChat';

jest.mock('../api', () => ({ getJson: jest.fn() }));
const { getJson } = jest.requireMock('../api') as { getJson: jest.Mock };

it('resolves a relative AAPL window and reuses it for an as-of follow-up', async () => {
  getJson.mockImplementation((path: string) => {
    if (path.includes('/search?')) return Promise.resolve({ data: [{ ticker: 'AAPL', name: 'Apple Inc.' }] });
    const params = new URLSearchParams(path.split('?')[1]);
    return Promise.resolve({ data: {
      ticker: 'AAPL', start: params.get('start'), end: params.get('end'),
      asOf: params.get('asOf') || new Date().toISOString(),
      summary: 'No clear catalyst found', catalysts: [], timeline: [], priceMoves: [],
    } });
  });
  render(<MoveChat />);
  const ask = async (text: string) => {
    fireEvent.change(screen.getByLabelText(/Ask about a move/), { target: { value: text } });
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  };
  await ask('Why did apple drop in the last 30 minutes?');
  expect(getJson.mock.calls[1][0]).toContain('/tickers/AAPL/move-explanation?');
  expect(screen.getByText(/Intraday prices unavailable for this ticker/)).toBeInTheDocument();
  const first = new URLSearchParams(getJson.mock.calls[1][0].split('?')[1]);
  expect(Date.parse(first.get('end')!) - Date.parse(first.get('start')!)).toBe(30 * 60_000);
  await ask('replay');
  await ask('What was available by the end?');
  expect(getJson.mock.calls[2][0]).toContain('/tickers/AAPL/move-explanation?');
  expect(screen.queryByText('Why did apple drop in the last 30 minutes?')).not.toBeInTheDocument();
  const replay = new URLSearchParams(getJson.mock.calls[2][0].split('?')[1]);
  expect(replay.get('start')).toBe(first.get('start'));
  expect(replay.get('asOf')).toBe(first.get('end'));
  const phrasedReplay = new URLSearchParams(getJson.mock.calls[3][0].split('?')[1]);
  expect(phrasedReplay.get('asOf')).toBe(first.get('end'));
});

it('asks for a specific ticker when a company search is ambiguous', async () => {
  getJson.mockClear();
  getJson.mockResolvedValue({ data: [
    { ticker: 'ABC', name: 'Example Holdings' },
    { ticker: 'XYZ', name: 'Example Industries' },
  ] });
  render(<MoveChat />);
  fireEvent.change(screen.getByLabelText(/Ask about a move/), {
    target: { value: 'Why did Example move in the last hour?' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  expect(screen.getByText(/Which ticker did you mean/)).toBeInTheDocument();
  expect(getJson).toHaveBeenCalledTimes(1);
});


it('understands falling today and uses the exchange calendar window for MU', async () => {
  getJson.mockClear();
  getJson.mockImplementation((path: string) => {
    if (path.includes('/search?')) return Promise.resolve({ data: [{ ticker: 'MU', name: 'Micron Technology' }] });
    if (path === '/api/v1/move-window/today') return Promise.resolve({ data: {
      start: '2026-11-18T14:30:00Z', end: '2026-11-18T19:53:00Z',
    } });
    const params = new URLSearchParams(path.split('?')[1]);
    return Promise.resolve({ data: {
      ticker: 'MU', start: params.get('start'), end: params.get('end'),
      asOf: new Date().toISOString(), summary: 'No clear catalyst found',
      catalysts: [], timeline: [], priceMoves: [{ symbol: 'MU', returnPercent: -1 }],
    } });
  });
  render(<MoveChat />);
  for (const question of ['Why is MU falling today?', 'Why did MU fall today?']) {
    fireEvent.change(screen.getByLabelText(/Ask about a move/), { target: { value: question } });
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
  }
  const request = getJson.mock.calls.find(([path]) => path.includes('/tickers/MU/move-explanation?'))![0];
  const params = new URLSearchParams(request.split('?')[1]);
  expect(params.get('start')).toBe('2026-11-18T14:30:00Z');
  expect(params.get('end')).toBe('2026-11-18T19:53:00Z');
  expect(screen.queryByText('Why is MU falling today?')).not.toBeInTheDocument();
  expect(screen.getByText('Why did MU fall today?')).toBeInTheDocument();
  expect(screen.getByText('MU -1%')).toBeInTheDocument();
  const searches = getJson.mock.calls.filter(([path]) => path.includes('/search?')).length;
  fireEvent.change(screen.getByLabelText(/Ask about a move/), { target: { value: 'today' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
  await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
  expect(getJson.mock.calls.filter(([path]) => path.includes('/search?'))).toHaveLength(searches);
  expect(screen.getByText('MU -1%')).toBeInTheDocument();
});

it('resolves since yesterday through the trading-calendar endpoint and replays the same window', async () => {
  getJson.mockClear();
  getJson.mockImplementation((path: string) => {
    if (path.includes('/search?')) return Promise.resolve({ data: [{ ticker: 'MU', name: 'Micron' }] });
    if (path.startsWith('/api/v1/move-window/since-yesterday')) return Promise.resolve({ data: {
      start: '2026-11-13T21:00:00Z', end: '2026-11-16T15:00:00Z',
    } });
    const params = new URLSearchParams(path.split('?')[1]);
    return Promise.resolve({ data: {
      ticker: 'MU', start: params.get('start'), end: params.get('end'),
      asOf: new Date().toISOString(), summary: 'No clear catalyst found', catalysts: [], timeline: [], priceMoves: [],
    } });
  });
  render(<MoveChat />);
  const ask = async (question: string) => {
    fireEvent.change(screen.getByLabelText(/Ask about a move/), { target: { value: question } });
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
  };
  await ask('Why did MU fall since yesterday?');
  expect(getJson).toHaveBeenCalledWith('/api/v1/move-window/since-yesterday?anchor=close');
  expect(screen.getByText(/Using the previous trading session’s close through now/)).toBeInTheDocument();
  await ask('What was available by the end?');
  const request = getJson.mock.calls[getJson.mock.calls.length - 1][0];
  expect(new URLSearchParams(request.split('?')[1]).get('asOf')).toBe('2026-11-16T15:00:00Z');
});

it('asks instead of choosing the first confirmed uppercase ticker', async () => {
  getJson.mockReset();
  getJson.mockImplementation((path: string) => {
    const query = new URLSearchParams(path.split('?')[1]).get('q');
    return Promise.resolve({ data: query === 'AI' || query === 'NVDA'
      ? [{ ticker: query, name: query === 'AI' ? 'C3.ai' : 'Nvidia' }] : [] });
  });
  render(<MoveChat />);
  fireEvent.change(screen.getByLabelText(/Ask about a move/), {
    target: { value: 'AI and NVDA on CPI news in the last hour?' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
  expect(await screen.findByText(/Which ticker did you mean.*AI.*NVDA/)).toBeInTheDocument();
  expect(getJson.mock.calls.every(([path]) => path.includes('/search?'))).toBe(true);
});
