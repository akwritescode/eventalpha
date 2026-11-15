import { act, renderHook, waitFor } from '@testing-library/react';
import { FeedItem } from '../api';
import { useFeed } from './useFeed';

jest.mock('../api', () => ({ ...jest.requireActual('../api'), getJson: jest.fn() }));
const { getJson } = jest.requireMock('../api') as { getJson: jest.Mock };

const item = (id: string): FeedItem => ({ id, type: 'sec', occurredAt: '2026-11-13T21:00:00Z', tickers: [] } as unknown as FeedItem);

describe('useFeed', () => {
  it('ignores a slow response for a filter the user already left', async () => {
    let resolveOld: (v: unknown) => void = () => {};
    getJson.mockImplementation((path: string) =>
      path.includes('types=sec')
        ? new Promise((r) => { resolveOld = r; }) // the first tab's request is slow
        : Promise.resolve({ data: [item('news:1')] })
    );
    const { result, rerender } = renderHook(({ types }) => useFeed(types, 0), {
      initialProps: { types: ['sec'] as ('sec' | 'news')[] },
    });
    rerender({ types: ['news'] }); // switch tabs before the first answer arrives
    await waitFor(() => expect(result.current.items.map((i) => i.id)).toEqual(['news:1']));

    await act(async () => resolveOld({ data: [item('article:9')] })); // late answer for the old tab
    expect(result.current.items.map((i) => i.id)).toEqual(['news:1']);
  });
});
