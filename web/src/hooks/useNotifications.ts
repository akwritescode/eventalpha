import { useCallback, useEffect, useRef, useState } from 'react';
import { FeedPush } from '../api';

export type NotifyLevel = 'off' | 'high' | 'all';
const KEY = 'notifyLevel';
const supported = typeof window !== 'undefined' && 'Notification' in window;

const read = (): NotifyLevel => {
  try {
    const v = localStorage.getItem(KEY);
    return v === 'high' || v === 'all' ? v : 'off';
  } catch {
    return 'off';
  }
};

/**
 * Browser notifications for pushed stream items while the site is open in any tab (foreground or
 * background). With the site closed this needs Web Push (service worker), which isn't set up.
 * Also counts unseen items in the tab title while the tab is hidden: "(3) EventAlpha".
 */
export function useNotifications() {
  const [level, setLevelState] = useState<NotifyLevel>(read);
  const [permission, setPermission] = useState<NotificationPermission | 'unsupported'>(
    supported ? Notification.permission : 'unsupported'
  );
  const unseen = useRef(0);
  const baseTitle = useRef(document.title);

  useEffect(() => {
    const onVisible = () => {
      if (!document.hidden) {
        unseen.current = 0;
        document.title = baseTitle.current;
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, []);

  const setLevel = useCallback(async (next: NotifyLevel) => {
    if (next !== 'off' && supported && Notification.permission === 'default') {
      setPermission(await Notification.requestPermission());
    }
    setLevelState(next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      /* ignore */
    }
  }, []);

  const notify = useCallback(
    (item: FeedPush) => {
      if (level === 'off' || (level === 'high' && item.impact !== 'high')) return;
      if (document.hidden) {
        unseen.current += 1;
        document.title = `(${unseen.current}) ${baseTitle.current}`;
      }
      if (!supported || Notification.permission !== 'granted') return;
      const tickers = item.tickers ? item.tickers.split(',').slice(0, 3).join(', ') : '';
      const n = new Notification(item.label ? `${item.label}${tickers ? ` · ${tickers}` : ''}` : 'EventAlpha', {
        body: item.title + (item.sentiment ? ` (${item.sentiment})` : ''),
        tag: item.ref, // one notification per item, even across tabs
        icon: '/favicon.svg',
      });
      n.onclick = () => {
        window.focus();
        window.location.hash = encodeURIComponent(item.ref);
        n.close();
      };
    },
    [level]
  );

  return { level, setLevel, permission, notify, supported };
}
