import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { MoveExplanation } from './MoveExplanation';

jest.mock('../api', () => ({ getJson: jest.fn() }));
const { getJson } = jest.requireMock('../api') as { getJson: jest.Mock };

it('shows the late lead in the retrospective timeline and requests a window-end replay', async () => {
  getJson.mockImplementation((path: string) => {
    const params = new URLSearchParams(path.split('?')[1]);
    return Promise.resolve({ data: {
      ticker: 'NVDA',
      start: '2025-04-15T21:20:00Z',
      end: '2025-04-15T21:35:00Z',
      asOf: params.get('asOf') || '2025-04-15T22:00:00Z',
      summary: 'No clear catalyst found',
      catalysts: [],
      priceMoves: params.has('asOf') ? [] : [
        { symbol: 'NVDA', returnPercent: -2.5 },
        { symbol: 'SPY', returnPercent: -0.2 },
        { symbol: 'SMH', returnPercent: -1 },
      ],
      timeline: params.has('asOf') ? [] : [{
        id: 'x:1001',
        title: 'A later post speculated about order cancellations.',
        url: 'https://x.com/i/status/1001',
        publishedAt: '2025-04-15T21:40:00Z',
        firstSeenAt: '2025-04-15T21:41:00Z',
        timing: 'after',
        status: 'unverified_lead',
      }],
    } });
  });

  render(<MoveExplanation />);
  fireEvent.click(screen.getByRole('button', { name: 'Load NVDA demo' }));
  await act(async () => { await getJson.mock.results[0].value; });
  const lead = within(screen.getByRole('listitem'));
  expect(lead.getByText('After · later context')).toBeInTheDocument();
  expect(screen.getByText('NVDA -2.5%')).toBeInTheDocument();
  expect(screen.getByText('SPY -0.2%')).toBeInTheDocument();
  expect(screen.getByText('SMH -1%')).toBeInTheDocument();
  expect(lead.getByText('Unverified X lead')).toBeInTheDocument();
  expect(lead.getByRole('link', { name: 'View X post' })).toHaveAttribute('href', 'https://x.com/i/status/1001');

  fireEvent.click(screen.getByRole('checkbox', { name: 'Replay as of window end' }));
  fireEvent.click(screen.getByRole('button', { name: 'Explore possible drivers' }));
  await act(async () => { await getJson.mock.results[1].value; });
  expect(screen.getByText('No matching evidence in the timeline.')).toBeInTheDocument();
  expect(screen.queryByText('Unverified X lead')).not.toBeInTheDocument();
  expect(screen.getByText('Intraday prices unavailable for this ticker and window. The timeline shows available filings and releases. Price collection runs every 15 minutes, so recent windows may still be pending.')).toBeInTheDocument();
  const replay = new URLSearchParams(getJson.mock.calls[1][0].split('?')[1]);
  expect(replay.get('asOf')).toBe(replay.get('end'));
});

it('explains the seven-day limit before requesting evidence for an older window', () => {
  getJson.mockClear();
  render(<MoveExplanation />);
  fireEvent.change(screen.getByLabelText(/Ticker/), { target: { value: 'NVDA' } });
  fireEvent.change(screen.getByLabelText(/^Start/), { target: { value: '2025-04-15T17:20' } });
  fireEvent.change(screen.getByLabelText(/^End/), { target: { value: '2025-04-15T17:35' } });
  fireEvent.click(screen.getByRole('button', { name: 'Explore possible drivers' }));

  expect(screen.getByRole('alert')).toHaveTextContent('Choose a window entirely within the past 7 days.');
  expect(getJson).not.toHaveBeenCalled();
});

it('prefills the last hour, applies a shorter preset, and accepts a company search result', async () => {
  getJson.mockResolvedValue({ data: [{ ticker: 'NVDA', name: 'NVIDIA CORP' }] });
  render(<MoveExplanation />);

  const start = screen.getByLabelText(/^Start/) as HTMLInputElement;
  const end = screen.getByLabelText(/^End/) as HTMLInputElement;
  expect(Date.parse(end.value) - Date.parse(start.value)).toBe(60 * 60_000);

  fireEvent.click(screen.getByRole('button', { name: 'Last 30 min' }));
  expect(Date.parse(end.value) - Date.parse(start.value)).toBe(30 * 60_000);

  const ticker = screen.getByRole('combobox', { name: /Ticker/ });
  fireEvent.change(ticker, { target: { value: 'NVIDIA' } });
  fireEvent.click(await screen.findByRole('option', { name: 'NVDA · NVIDIA CORP' }));
  expect(getJson).toHaveBeenCalledWith('/api/v1/tickers/search?q=NVIDIA');
  expect(ticker).toHaveValue('NVDA');
});
