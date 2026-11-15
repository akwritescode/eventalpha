import { useEffect, useState } from 'react';

/*
 * The stream's ticker filter lives in the URL (?ticker=DIS), so a filtered view can be
 * bookmarked or shared and the browser's Back button clears it.
 */
const EVENT = 'eventalpha:ticker';

export function currentTicker(): string | null {
  const t = new URLSearchParams(window.location.search).get('ticker');
  return t ? t.trim().toUpperCase() : null;
}

export function setTicker(ticker: string | null): void {
  const url = new URL(window.location.href);
  if (ticker) url.searchParams.set('ticker', ticker.toUpperCase());
  else url.searchParams.delete('ticker');
  url.hash = '';
  window.history.pushState(null, '', url);
  window.dispatchEvent(new Event(EVENT));
  document.getElementById('stream')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

export function useTicker(): string | null {
  const [ticker, set] = useState(currentTicker);
  useEffect(() => {
    const sync = () => set(currentTicker());
    window.addEventListener(EVENT, sync);
    window.addEventListener('popstate', sync);
    return () => {
      window.removeEventListener(EVENT, sync);
      window.removeEventListener('popstate', sync);
    };
  }, []);
  return ticker;
}
