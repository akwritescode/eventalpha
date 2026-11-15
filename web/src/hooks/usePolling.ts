import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiResponse, getJson } from '../api';

/**
 * Fetch `path` now and every `intervalMs` while the tab is visible: no polling in
 * background tabs, an immediate refresh when the tab comes back.
 */
export function usePolling<T>(path: string, intervalMs = 60_000) {
  const [state, setState] = useState<{ data?: ApiResponse<T>; error?: string; loading: boolean }>({ loading: true });
  const timer = useRef<number>();

  const load = useCallback(async () => {
    try {
      const data = await getJson<T>(path);
      setState({ data, loading: false });
    } catch (e) {
      setState((s) => ({ ...s, error: (e as Error).message, loading: false }));
    }
  }, [path]);

  useEffect(() => {
    const start = () => {
      load();
      window.clearInterval(timer.current);
      timer.current = window.setInterval(load, intervalMs);
    };
    const onVisibility = () => (document.hidden ? window.clearInterval(timer.current) : start());
    start();
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      window.clearInterval(timer.current);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [load, intervalMs]);

  return state;
}
