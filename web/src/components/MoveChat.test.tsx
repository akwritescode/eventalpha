import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { MoveChat } from './MoveChat';

jest.mock('../api', () => {
  class ApiError extends Error {
    status: number;
    detail?: string;
    constructor(status: number, detail?: string) { super(detail); this.status = status; this.detail = detail; }
  }
  return { getJson: jest.fn(), postJson: jest.fn(), ApiError };
});
const api = jest.requireMock('../api') as { getJson: jest.Mock; postJson: jest.Mock; ApiError: any };

const query = (fields: object) => Promise.resolve({ data: {
  ticker: null, tickerName: null, tickerOptions: [], start: null, end: null, replay: false, message: null, ...fields,
} });
const explanation = (path: string) => {
  const params = new URLSearchParams(path.split('?')[1]);
  return Promise.resolve({ data: {
    ticker: path.split('/')[4], start: params.get('start'), end: params.get('end'),
    asOf: params.get('asOf') || new Date().toISOString(),
    summary: 'No clear catalyst found', catalysts: [], timeline: [], priceMoves: [{ symbol: 'NVDA', returnPercent: -1.25 }],
  } });
};
const flush = () => act(async () => { for (let i = 0; i < 5; i++) await Promise.resolve(); });

async function ask(text: string) {
  fireEvent.change(screen.getByLabelText('Ask about a move'), { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
  await flush();
}

beforeEach(() => {
  api.getJson.mockReset().mockImplementation(explanation);
  api.postJson.mockReset();
});

it('explains a question the server resolved to a ticker and window', async () => {
  api.postJson.mockReturnValue(query({ ticker: 'NVDA', tickerName: 'NVIDIA CORP',
    start: '2026-11-24T14:30:00Z', end: '2026-11-24T15:30:00Z' }));
  render(<MoveChat />);
  await ask('Why did Nvidia drop in the last hour?');

  expect(api.postJson).toHaveBeenCalledWith('/api/v1/move-query', expect.objectContaining({ question: 'Why did Nvidia drop in the last hour?' }));
  const request = api.getJson.mock.calls[0][0];
  expect(request).toContain('/tickers/NVDA/move-explanation?');
  expect(new URLSearchParams(request.split('?')[1]).get('start')).toBe('2026-11-24T14:30:00Z');
  expect(screen.getByText('Why did Nvidia drop in the last hour?')).toBeInTheDocument();
  expect(screen.getByLabelText('NVDA -1.25%')).toBeInTheDocument();
  expect(screen.getByText(/Try another time frame for/)).toBeInTheDocument();
});

it('asks for a time frame after a bare ticker, then explains the chip picked', async () => {
  api.postJson.mockReturnValue(query({ ticker: 'NVDA', tickerName: 'NVIDIA CORP', message: 'Which time frame for NVDA?' }));
  render(<MoveChat />);
  await ask('nvda');
  expect(screen.getByText('Which time frame for NVDA?')).toBeInTheDocument();
  expect(api.getJson).not.toHaveBeenCalled();

  fireEvent.click(within(screen.getByRole('group', { name: 'Time frame' })).getByText('Last 30 min'));
  await flush();
  const params = new URLSearchParams(api.getJson.mock.calls[0][0].split('?')[1]);
  expect(Date.parse(params.get('end')!) - Date.parse(params.get('start')!)).toBe(30 * 60_000);
  expect(params.has('asOf')).toBe(false);
  expect(screen.getByText('NVDA · Last 30 min')).toBeInTheDocument();
});

it('sends follow-ups with the window on screen and replays as of its end', async () => {
  api.postJson.mockReturnValueOnce(query({ ticker: 'NVDA', start: '2026-11-24T14:30:00Z', end: '2026-11-24T15:30:00Z' }));
  render(<MoveChat />);
  await ask('Why did NVDA move in the last hour?');

  api.postJson.mockReturnValueOnce(query({ ticker: 'NVDA', start: '2026-11-24T14:30:00Z', end: '2026-11-24T15:30:00Z', replay: true }));
  await ask('What was known by then?');
  expect(api.postJson).toHaveBeenLastCalledWith('/api/v1/move-query', {
    question: 'What was known by then?', contextTicker: 'NVDA',
    contextStart: '2026-11-24T14:30:00Z', contextEnd: '2026-11-24T15:30:00Z',
  });
  const replay = new URLSearchParams(api.getJson.mock.calls[1][0].split('?')[1]);
  expect(replay.get('asOf')).toBe('2026-11-24T15:30:00Z');
  expect(screen.getByRole('checkbox', { name: 'Only what was known at the time' })).toBeChecked();
});

it('lets the user pick among ambiguous companies', async () => {
  api.postJson.mockReturnValue(query({ message: 'Which one did you mean?', tickerOptions: [
    { ticker: 'ABC', name: 'Example Holdings' }, { ticker: 'XYZ', name: 'Example Industries' },
  ] }));
  render(<MoveChat />);
  await ask('Why did Example move?');
  fireEvent.click(screen.getByText('XYZ · Example Industries'));
  await flush();
  expect(screen.getByText('Which time frame for XYZ?')).toBeInTheDocument();
  expect(screen.getByRole('group', { name: 'Time frame' })).toBeInTheDocument();
});

it('shows the server’s explanation when free-text questions are off', async () => {
  api.postJson.mockRejectedValue(new api.ApiError(503, 'Free-text questions are not set up on this server. Type a ticker symbol instead.'));
  render(<MoveChat />);
  await ask('why did nvidia drop?');
  expect(screen.getByText('Free-text questions are not set up on this server. Type a ticker symbol instead.')).toBeInTheDocument();
});

it('reports a closed market for the Today chip instead of guessing a window', async () => {
  api.postJson.mockReturnValue(query({ ticker: 'NVDA', message: 'Which time frame for NVDA?' }));
  api.getJson.mockImplementation((path: string) => path === '/api/v1/move-window/today'
    ? Promise.resolve({ data: { start: null, end: null, message: 'The market is closed today. Choose a recent trading day below.' } })
    : explanation(path));
  render(<MoveChat />);
  await ask('NVDA');
  fireEvent.click(within(screen.getByRole('group', { name: 'Time frame' })).getByText('Today'));
  await flush();
  expect(screen.getByText(/The market is closed today/)).toBeInTheDocument();
  expect(api.getJson.mock.calls.some(([path]) => path.includes('move-explanation'))).toBe(false);
});

it('runs the demo without the seven-day limit', async () => {
  render(<MoveChat />);
  fireEvent.click(screen.getByText('See the NVDA demo'));
  await flush();
  expect(api.postJson).not.toHaveBeenCalled();
  const params = new URLSearchParams(api.getJson.mock.calls[0][0].split('?')[1]);
  expect(params.get('start')).toBe('2025-04-15T21:20:00.000Z');
});
