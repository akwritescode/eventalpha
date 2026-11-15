import { useEffect, useRef, useState } from 'react';
import { API_URL, FeedPush } from '../api';

/**
 * Every new stream item, pushed over Server-Sent Events (`stream=feed`): classified filings and
 * news, signals, macro releases. No polling. The browser reconnects by itself and sends
 * Last-Event-ID, so items published while disconnected are replayed.
 */
export function useEventStream(onItem?: (item: FeedPush) => void) {
  const [connected, setConnected] = useState(false);
  const [version, setVersion] = useState(0); // bumps on every pushed item
  const handler = useRef(onItem);
  handler.current = onItem;

  useEffect(() => {
    const source = new EventSource(`${API_URL}/api/v1/stream/events?stream=feed`);
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.addEventListener('event', (e) => {
      const msg = e as MessageEvent;
      try {
        const item = { ...(JSON.parse(msg.data) as Omit<FeedPush, 'id'>), id: msg.lastEventId } as FeedPush;
        setVersion((v) => v + 1);
        handler.current?.(item);
      } catch {
        /* ignore malformed */
      }
    });
    return () => source.close();
  }, []);

  return { connected, version };
}
