import { askMoveQuery, frameWindow, recentWindow, TIME_FRAMES, windowError } from './moveInput';

jest.mock('./api', () => ({ getJson: jest.fn(), postJson: jest.fn() }));
const { getJson, postJson } = jest.requireMock('./api') as { getJson: jest.Mock; postJson: jest.Mock };

test('relative windows align to completed minutes and validate bounds', () => {
  const now = Date.parse('2026-11-18T18:30:23Z');
  expect(recentWindow(30, now)).toEqual({ start: '2026-11-18T18:00:00.000Z', end: '2026-11-18T18:30:00.000Z' });
  expect(windowError(now, now)).toContain('up to 24 hours');
  expect(windowError(now - 25 * 3600_000, now)).toContain('24 hours');
  expect(windowError(Date.now() - 8 * 86_400_000, Date.now() - 8 * 86_400_000 + 60_000)).toContain('past 7 days');
});

test('the question goes to the server with what is on screen as context', async () => {
  postJson.mockResolvedValue({ data: {} });
  await askMoveQuery('what was known by then?', { ticker: 'NVDA', window: { start: 'a', end: 'b' } });
  expect(postJson).toHaveBeenCalledWith('/api/v1/move-query', {
    question: 'what was known by then?', contextTicker: 'NVDA', contextStart: 'a', contextEnd: 'b',
  });
});

test('session chips use the exchange calendar and surface its message', async () => {
  const since = TIME_FRAMES.find(f => f.kind === 'since')!;
  getJson.mockResolvedValueOnce({ data: { start: '2026-11-13T21:00:00Z', end: '2026-11-16T15:00:00Z' } });
  expect(await frameWindow(since)).toEqual({ start: '2026-11-13T21:00:00Z', end: '2026-11-16T15:00:00Z' });
  expect(getJson).toHaveBeenLastCalledWith('/api/v1/move-window/since-yesterday?anchor=close');

  const today = TIME_FRAMES.find(f => f.kind === 'today')!;
  getJson.mockResolvedValueOnce({ data: { start: null, end: null, message: 'The market is closed today.' } });
  expect(await frameWindow(today)).toBe('The market is closed today.');
});
