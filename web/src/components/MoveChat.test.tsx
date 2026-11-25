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
const thread = () => within(screen.getByRole('log', { name: 'Messages' }));
const flush = () => act(async () => { for (let i = 0; i < 5; i++) await Promise.resolve(); });

async function ask(text: string) {
  fireEvent.change(screen.getByLabelText('Ask about a move'), { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }));
  await flush();
}

beforeEach(() => {
  window.localStorage.clear();
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
  expect(thread().getByText('Why did Nvidia drop in the last hour?')).toBeInTheDocument();
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
  expect(thread().getByText('NVDA · Last 30 min')).toBeInTheDocument();
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

it('explains a custom range of up to two weeks and rejects longer ones', async () => {
  api.postJson.mockReturnValue(query({ ticker: 'NVDA', message: 'Which time frame for NVDA?' }));
  render(<MoveChat />);
  await ask('NVDA');
  fireEvent.click(within(screen.getByRole('group', { name: 'Time frame' })).getByText('Custom…'));
  const range = within(screen.getByRole('group', { name: 'Custom range' }));
  fireEvent.change(range.getByLabelText('From'), { target: { value: '2026-11-08T09:30' } });
  fireEvent.change(range.getByLabelText('To'), { target: { value: '2026-11-20T16:00' } });
  fireEvent.click(screen.getByRole('button', { name: 'Explain' }));
  await flush();
  const params = new URLSearchParams(api.getJson.mock.calls[0][0].split('?')[1]);
  expect(Date.parse(params.get('end')!) - Date.parse(params.get('start')!)).toBe((12 * 24 + 6.5) * 3600_000); // a 12-day window: two weeks is allowed

  fireEvent.click(within(screen.getByRole('group', { name: 'Time frame' })).getByText('Custom…'));
  fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-11-01T09:30' } });
  fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-11-20T16:00' } });
  fireEvent.click(screen.getByRole('button', { name: 'Explain' }));
  await flush();
  expect(thread().getByText('Windows can be up to 14 days long.')).toBeInTheDocument();
  expect(api.getJson).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button', { name: 'Close custom range' }));
  expect(screen.queryByRole('group', { name: 'Custom range' })).not.toBeInTheDocument();
  expect(within(screen.getByRole('group', { name: 'Time frame' })).getByText('Custom…')).toBeInTheDocument();
});

it('starts a new conversation and keeps the old one in the list', async () => {
  api.postJson.mockReturnValue(query({ ticker: 'NVDA', start: '2026-11-24T14:30:00Z', end: '2026-11-24T15:30:00Z' }));
  render(<MoveChat />);
  expect(screen.getByText('Past conversations appear here.')).toBeInTheDocument();
  await ask('Why did NVDA move?');
  const list = within(screen.getByRole('navigation', { name: 'Conversations' }));
  expect(list.getByText('Why did NVDA move?')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'New conversation' }));
  expect(screen.queryByRole('group', { name: 'Time frame' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'TSLA' })).toBeInTheDocument(); // back to the starter suggestions
  expect(list.getByText('Why did NVDA move?')).toBeInTheDocument(); // the old one is a record now
  await ask('What was known by then?');
  expect(api.postJson).toHaveBeenLastCalledWith('/api/v1/move-query', expect.objectContaining({ contextTicker: undefined }));
  expect(list.getByText('What was known by then?')).toBeInTheDocument();
});

it('reopens a past conversation after a reload and continues it', async () => {
  api.postJson.mockReturnValue(query({ ticker: 'NVDA', tickerName: 'NVIDIA CORP', start: '2026-11-24T14:30:00Z', end: '2026-11-24T15:30:00Z' }));
  const { unmount } = render(<MoveChat />);
  await ask('Why did NVDA move?');
  unmount();

  render(<MoveChat />); // a fresh page load
  expect(screen.queryByLabelText('NVDA -1.25%')).not.toBeInTheDocument();
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Conversations' })).getByText('Why did NVDA move?'));
  expect(screen.getByLabelText('NVDA -1.25%')).toBeInTheDocument();
  expect(screen.getByText(/Try another time frame for/)).toBeInTheDocument();

  api.postJson.mockReturnValue(query({ ticker: 'NVDA', start: '2026-11-24T14:30:00Z', end: '2026-11-24T15:30:00Z', replay: true }));
  await ask('What was known by then?');
  expect(api.postJson).toHaveBeenLastCalledWith('/api/v1/move-query', expect.objectContaining({
    contextTicker: 'NVDA', contextStart: '2026-11-24T14:30:00Z' }));
  const stored = JSON.parse(window.localStorage.getItem('eventalpha.conversations.v1')!);
  expect(stored).toHaveLength(1);
  expect(stored[0].turns).toHaveLength(4);
});

it('deletes a conversation, starting a new one if it was open', async () => {
  api.postJson.mockReturnValue(query({ ticker: 'NVDA', message: 'Which time frame for NVDA?' }));
  render(<MoveChat />);
  await ask('NVDA');
  fireEvent.click(screen.getByRole('button', { name: 'Delete conversation “NVDA”' }));
  expect(screen.getByText('Past conversations appear here.')).toBeInTheDocument();
  expect(screen.queryByText('Which time frame for NVDA?')).not.toBeInTheDocument();
  expect(JSON.parse(window.localStorage.getItem('eventalpha.conversations.v1')!)).toEqual([]);
});

it('pages older questions away and keeps only the newest result open', async () => {
  api.postJson.mockReturnValue(query({ ticker: 'NVDA', start: '2026-11-24T14:30:00Z', end: '2026-11-24T15:30:00Z' }));
  render(<MoveChat />);
  for (const n of [1, 2, 3, 4, 5]) await ask(`Question ${n}`);

  expect(thread().queryByText('Question 1')).not.toBeInTheDocument();
  expect(thread().queryByText('Question 2')).not.toBeInTheDocument();
  expect(thread().getByText('Question 5')).toBeInTheDocument();
  // Questions 3 and 4 are visible but collapsed; only question 5's result is open.
  expect(screen.getAllByLabelText(/^Show details for NVDA/)).toHaveLength(2);
  expect(screen.getAllByText('Evidence timeline')).toHaveLength(1);

  fireEvent.click(screen.getByRole('button', { name: 'Show earlier messages (2 questions)' }));
  expect(thread().getByText('Question 1')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Show earlier messages/ })).not.toBeInTheDocument();

  fireEvent.click(screen.getAllByLabelText(/^Show details for NVDA/)[0]);
  expect(screen.getAllByText('Evidence timeline')).toHaveLength(2);
  fireEvent.click(screen.getByRole('button', { name: 'Hide details' }));
  expect(screen.getAllByText('Evidence timeline')).toHaveLength(1);

  await ask('Question 6');
  expect(thread().queryByText('Question 1')).not.toBeInTheDocument();
});
