import React, { FormEvent, useEffect, useId, useState } from 'react';
import { Alert, Autocomplete, Box, Button, Checkbox, FormControlLabel, Link, Stack, TextField, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import demo from '../fixtures/move-demo.json';
import { Panel, Pill } from './ui';
import { fetchExplanation, MINUTE_MS, recentWindow, searchTickers, TickerMatch, windowError } from '../moveInput';

type Evidence = {
  id: string;
  title: string;
  url: string;
  publishedAt: string;
  firstSeenAt: string;
  timing: 'before' | 'during' | 'after';
  status: 'original_source' | 'verified_discovery' | 'unverified_lead';
  originalId: string | null;
  verifiedAt: string | null;
};

export type Explanation = {
  ticker: string;
  start: string;
  end: string;
  asOf: string;
  summary: string;
  catalysts: { summary: string; evidenceId: string }[];
  timeline: Evidence[];
  benchmarks?: string[];
  priceMoves: { symbol: string; returnPercent: number; measuredStart?: string; measuredEnd?: string; dataAsOf?: string }[];
};

type WindowInput = { ticker: string; start: string; end: string };

const localZone = Intl.DateTimeFormat().resolvedOptions().timeZone;

function pickerValue(time: number) {
  const date = new Date(time);
  return new Date(time - date.getTimezoneOffset() * MINUTE_MS).toISOString().slice(0, 16);
}

function lastMinutes(minutes: number) {
  const window = recentWindow(minutes);
  return { start: pickerValue(Date.parse(window.start)), end: pickerValue(Date.parse(window.end)) };
}

const demoWindow = { ticker: demo.ticker, start: pickerValue(Date.parse(demo.start)), end: pickerValue(Date.parse(demo.end)) };
const eastern = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/New_York', year: 'numeric', month: 'short', day: 'numeric',
  hour: 'numeric', minute: '2-digit', second: '2-digit', timeZoneName: 'short',
});
const stamp = (iso: string) => eastern.format(new Date(iso));
const labels: Record<Evidence['status'], string> = {
  original_source: 'Original source',
  verified_discovery: 'X discovery',
  unverified_lead: 'Unverified X lead',
};

export function MoveExplanation() {
  const [window, setWindow] = useState<WindowInput>(() => ({ ticker: '', ...lastMinutes(60) }));
  const [preset, setPreset] = useState<number | null>(60);
  const [suggestions, setSuggestions] = useState<TickerMatch[]>([]);
  const [tickerOpen, setTickerOpen] = useState(false);

  useEffect(() => {
    const query = window.ticker.trim();
    if (!tickerOpen || !query) return;
    let active = true;
    const timer = setTimeout(() => {
      searchTickers(query)
        .then(({ data }) => { if (active) setSuggestions(data); })
        .catch(() => { if (active) setSuggestions([]); });
    }, 200);
    return () => { active = false; clearTimeout(timer); };
  }, [tickerOpen, window.ticker]);
  const [replay, setReplay] = useState(false);
  const [result, setResult] = useState<Explanation>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function explain(input: WindowInput, asOfEnd: boolean) {
    setResult(undefined);
    setError('');
    const isDemo = input === demoWindow;
    const ticker = input.ticker.trim().toUpperCase();
    const startTime = Date.parse(isDemo ? demo.start : input.start);
    const endTime = Date.parse(isDemo ? demo.end : input.end);
    if (!/^[A-Z.-]{1,10}$/.test(ticker) || !Number.isFinite(startTime) || !Number.isFinite(endTime)
        || (!isDemo && (pickerValue(startTime) !== input.start || pickerValue(endTime) !== input.end))
        ) {
      setError('Choose a stock ticker and a valid start and end time up to 24 hours apart.');
      return;
    }
    const validation = windowError(startTime, endTime, isDemo);
    if (validation) {
      setError(validation);
      return;
    }
    const end = new Date(endTime).toISOString();
    setBusy(true);
    try {
      const response = await fetchExplanation(ticker, { start: new Date(startTime).toISOString(), end }, asOfEnd);
      setResult(response.data);
    } catch {
      setError('The move timeline could not be loaded. Check the window and try again.');
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void explain(window, replay);
  }

  return (
    <Panel title="Explain a stock move" subtitle="Enter a ticker and a time window from the past 7 days.">
      <Box component="form" onSubmit={submit}>
        <Stack spacing={1.5}>
          <Autocomplete freeSolo open={tickerOpen} onOpen={() => setTickerOpen(true)}
            onClose={() => setTickerOpen(false)} disabled={busy} options={suggestions}
            inputValue={window.ticker} filterOptions={(options) => options}
            getOptionLabel={(option) => typeof option === 'string' ? option : option.ticker}
            onChange={(_, option) => {
              setTickerOpen(false);
              setWindow({ ...window, ticker: typeof option === 'string' ? option : option?.ticker ?? '' });
            }}
            onInputChange={(_, ticker, reason) => {
              if (reason !== 'input' && reason !== 'clear') return;
              setSuggestions([]);
              setWindow({ ...window, ticker });
            }}
            renderOption={({ key, ...props }, option) => <li key={key} {...props}>{option.ticker} · {option.name}</li>}
            renderInput={(params) => <TextField {...params} required size="small" label="Ticker"
              placeholder="Search by symbol or company" />}
            sx={{ width: { xs: '100%', sm: 310 } }} />
          <ToggleButtonGroup size="small" exclusive value={preset} aria-label="Move window preset"
            disabled={busy} onChange={(_, minutes: number | null) => {
              const selected = minutes ?? preset;
              if (selected === null) return;
              setPreset(selected);
              setWindow({ ...window, ...lastMinutes(selected) });
            }}>
            <ToggleButton value={30}>Last 30 min</ToggleButton>
            <ToggleButton value={60}>Last hour</ToggleButton>
            <ToggleButton value={120}>Last 2 hours</ToggleButton>
          </ToggleButtonGroup>
          <Stack spacing={1.5} direction={{ xs: 'column', sm: 'row' }}>
            {(['start', 'end'] as const).map((boundary) => (
              <TextField key={boundary} required disabled={busy} size="small" label={boundary === 'start' ? 'Start' : 'End'}
                type="datetime-local" InputLabelProps={{ shrink: true }} value={window[boundary]}
                onChange={(event) => {
                  setPreset(null);
                  setWindow({ ...window, [boundary]: event.target.value });
                }} sx={{ width: { xs: '100%', sm: 222 } }} />
            ))}
          </Stack>
        </Stack>
        <Typography variant="caption" color="text.secondary">Picker time zone · {localZone}</Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} gap={1} alignItems={{ sm: 'center' }} sx={{ mt: 1 }}>
          <Button variant="contained" type="submit" disabled={busy}>{busy ? 'Loading…' : 'Explore possible drivers'}</Button>
          <Button disabled={busy} onClick={() => {
            setPreset(null);
            setWindow(demoWindow);
            void explain(demoWindow, replay);
          }}>Load NVDA demo</Button>
          <FormControlLabel disabled={busy} control={<Checkbox checked={replay}
            onChange={(event) => setReplay(event.target.checked)} />} label="Replay as of window end" />
        </Stack>
      </Box>
      {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      {result && <MoveResult result={result} />}
    </Panel>
  );
}

export function MoveResult({ result }: { result: Explanation }) {
  const anchor = useId();
  return (
    <Box sx={{ mt: 2 }} aria-live="polite">

          {result.ticker === demo.ticker && Date.parse(result.start) === Date.parse(demo.start)
            && Date.parse(result.end) === Date.parse(demo.end) && (
            <Alert severity="info" sx={{ mb: 1.5 }}>
              The demo uses a real SEC filing with simulated X posts and observation times.
            </Alert>
          )}
          <Typography variant="subtitle2">{result.ticker} · {stamp(result.start)} to {stamp(result.end)}</Typography>
          <Typography variant="caption" color="text.secondary">Evidence available as of {stamp(result.asOf)}.</Typography>
          {(
            <Box sx={{ mt: 1 }}>
              {result.priceMoves.length ? (
                <>
                  <Stack direction="row" gap={1} flexWrap="wrap">
                    {Array.from(new Set([result.ticker, ...(result.benchmarks || result.priceMoves.map(price => price.symbol))])).map((symbol) => {
                      const move = result.priceMoves.find((price) => price.symbol === symbol);
                      const value = move ? new Intl.NumberFormat('en-US', {
                        style: 'percent', signDisplay: 'exceptZero', maximumFractionDigits: 2,
                      }).format(move.returnPercent / 100) : 'Unavailable';
                      return <Box key={symbol}><Pill>{symbol} {value}</Pill>
                        {move?.measuredEnd && <Typography variant="caption" display="block">
                          {stamp(move.measuredStart!)} to {stamp(move.measuredEnd)}.
                          {' '}Observed {stamp(move.dataAsOf!)}.
                        </Typography>}
                      </Box>;
                    })}
                  </Stack>
                  <Typography variant="caption" color="text.secondary">Returns use the latest available completed candles at the window boundaries. SPY tracks the broad market; SMH tracks semiconductors.</Typography>
                </>
              ) : <Typography variant="body2" color="text.secondary">Intraday prices unavailable for this ticker and window. The timeline shows available filings and releases. Price collection runs every 15 minutes, so recent windows may still be pending.</Typography>}
            </Box>
          )}
          <Typography sx={{ mt: 1 }}>
            {result.summary}
            {result.catalysts.length === 1 && (
              <> <Link href={`#move-${anchor}-${result.catalysts[0].evidenceId}`}>Supporting source</Link></>
            )}
          </Typography>
          {result.catalysts.length > 1 && (
            <Box component="ul" sx={{ pl: 2.5 }}>
              {result.catalysts.map((catalyst) => (
                <li key={catalyst.evidenceId}>
                  {catalyst.summary}{' '}
                  <Link href={`#move-${anchor}-${catalyst.evidenceId}`}>Supporting source</Link>
                </li>
              ))}
            </Box>
          )}
          <Typography variant="h2" sx={{ mt: 2 }}>Evidence timeline</Typography>
          {result.timeline.length === 0 ? <Typography color="text.secondary">No matching evidence in the timeline.</Typography> : (
            <Box component="ol" sx={{ listStyle: 'none', pl: 0, mb: 0 }}>
              {result.timeline.map((item) => (
                <Box component="li" id={`move-${anchor}-${item.id}`} key={item.id}
                  sx={{ py: 1.25, borderTop: '1px solid', borderColor: 'divider', scrollMarginTop: 80 }}>
                  <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center">
                    <Pill>{item.timing === 'after' ? 'After · later context' : item.timing === 'before' ? 'Before' : 'During'}</Pill>
                    <Typography variant="caption" color="text.secondary">{labels[item.status]}</Typography>
                  </Stack>
                  <Typography sx={{ mt: 0.5 }}>
                    {item.status === 'original_source' && /^https?:\/\//i.test(item.url)
                      ? <Link href={item.url} target="_blank" rel="noopener noreferrer">{item.title}</Link>
                      : item.title}
                    {item.status !== 'original_source' && (
                      <> · <Link href={item.url} target="_blank" rel="noopener noreferrer">View X post</Link></>
                    )}
                    {item.originalId && <> · <Link href={`#move-${anchor}-${item.originalId}`}>Original evidence</Link></>}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Published {stamp(item.publishedAt)} · First seen {stamp(item.firstSeenAt)}
                    {item.verifiedAt && ` · Verified ${stamp(item.verifiedAt)}`}
                  </Typography>
                </Box>
              ))}
            </Box>
          )}
    </Box>
  );
}
