import { useCallback, useEffect, useRef, useState } from 'react';
import { FeedItem, FeedType, getJson } from '../api';

const PAGE = 60;

/**
 * The stream's items for the selected types. Updates are push-driven: every new item is
 * announced on the feed stream (SSE), and each announcement refetches the first page. No polling.
 */
export function useFeed(types: FeedType[], pushVersion: number, ticker: string | null = null) {
  const [items, setItems] = useState<FeedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [exhausted, setExhausted] = useState(false);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const known = useRef<Set<string>>(new Set());
  // A single company has fewer items, so its view looks further back.
  const query = `types=${types.join(',')}&days=${ticker ? 60 : 30}&limit=${PAGE}${ticker ? `&ticker=${encodeURIComponent(ticker)}` : ''}`;

  const loadFirst = useCallback(async () => {
    try {
      const resp = await getJson<FeedItem[]>(`/api/v1/feed?${query}`);
      const incoming = resp.data;
      const added = incoming.filter((i) => known.current.size > 0 && !known.current.has(i.id)).map((i) => i.id);
      incoming.forEach((i) => known.current.add(i.id));
      setItems((prev) => {
        const ids = new Set(incoming.map((i) => i.id));
        return [...incoming, ...prev.filter((p) => !ids.has(p.id) && p.occurredAt < (incoming[incoming.length - 1]?.occurredAt ?? ''))];
      });
      if (added.length) setFresh(new Set(added));
      setExhausted(incoming.length < PAGE);
      setError(undefined);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [query]);

  const loadMore = useCallback(async () => {
    const last = items[items.length - 1];
    if (!last) return;
    const resp = await getJson<FeedItem[]>(`/api/v1/feed?${query}&before=${encodeURIComponent(last.occurredAt)}`);
    resp.data.forEach((i) => known.current.add(i.id));
    setItems((prev) => [...prev, ...resp.data.filter((i) => !prev.some((p) => p.id === i.id))]);
    setExhausted(resp.data.length < PAGE);
  }, [items, query]);

  // Type or ticker filter changed: start over.
  useEffect(() => {
    known.current = new Set();
    setItems([]);
    setLoading(true);
    loadFirst();
  }, [loadFirst]);

  // Pushed event: refresh the top of the stream.
  useEffect(() => {
    if (pushVersion > 0) loadFirst();
  }, [pushVersion, loadFirst]);

  // Coming back to a tab: catch up once (the stream replays missed items too).
  useEffect(() => {
    const onVisibility = () => !document.hidden && loadFirst();
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, [loadFirst]);

  return { items, loading, error, exhausted, loadMore, fresh };
}
