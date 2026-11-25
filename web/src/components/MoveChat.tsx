import React, { FormEvent, useEffect, useRef, useState } from 'react';
import { Box, Button, Chip, CircularProgress, FormControlLabel, IconButton, InputAdornment, Stack, Switch, TextField, Typography } from '@mui/material';
import { alpha } from '@mui/material/styles';
import AutoAwesomeRounded from '@mui/icons-material/AutoAwesomeRounded';
import SendRounded from '@mui/icons-material/SendRounded';
import { ApiError } from '../api';
import { ChatContext, Conversation, deleteConversation, loadConversations, newConversationId, saveConversation, Turn } from '../conversations';
import { askMoveQuery, fetchExplanation, frameWindow, MINUTE_MS, MoveWindow, TickerOption, TIME_FRAMES, TimeFrame, windowError } from '../moveInput';
import { MONO, T } from '../theme';
import { MoveResult, MoveResultSummary, windowLabel } from './MoveResult';
import { ConversationList } from './ConversationList';
import { DateRange, DateRangeField } from './DateRangeField';
import { Panel } from './ui';

type Context = ChatContext;

const MAX_TURNS = 40; // history kept in memory: 20 exchanges
const PAGE_TURNS = 6; // shown at once: the last 3 exchanges; "Show earlier" adds a page
const SUGGESTIONS = ['Why did NVDA move in the last hour?', 'What moved AAPL since yesterday’s close?', 'TSLA'];

/** datetime-local value in the viewer's zone. */
function pickerValue(time: number) {
  return new Date(time - new Date(time).getTimezoneOffset() * MINUTE_MS).toISOString().slice(0, 16);
}

function errorText(error: unknown) {
  return error instanceof ApiError && error.detail ? error.detail : 'I couldn’t load that just now. Please try again.';
}

export function MoveChat() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState('');
  const [context, setContext] = useState<Context>({});
  const [replay, setReplay] = useState(false);
  const [custom, setCustom] = useState<DateRange>();
  const [busy, setBusy] = useState(false);
  const [shown, setShown] = useState(PAGE_TURNS);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [conversationId, setConversationId] = useState(newConversationId);
  const [conversations, setConversations] = useState<Conversation[]>(loadConversations);
  const [saveTick, setSaveTick] = useState(0);
  const nextId = useRef(0);
  const bottom = useRef<HTMLDivElement>(null);
  const latest = useRef({ conversationId, turns, context, replay });
  latest.current = { conversationId, turns, context, replay };

  // Save once an exchange has settled (reply, ticker and window all updated). Opening an old
  // conversation doesn't save, so browsing history doesn't reorder it.
  useEffect(() => {
    if (saveTick === 0) return;
    const { conversationId: id, turns: all, context: ctx, replay: asOfEnd } = latest.current;
    if (all.length) setConversations(saveConversation({ id, turns: all, context: ctx, replay: asOfEnd }));
  }, [saveTick]);

  useEffect(() => { bottom.current?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' }); }, [turns.length]);

  /** Shows a conversation (or a blank one); the one on screen is already saved. */
  function show(id: string, conversation?: Conversation) {
    setConversationId(id);
    setTurns(conversation?.turns || []);
    setContext(conversation?.context || {});
    setReplay(conversation?.replay || false);
    setCustom(undefined);
    setQuestion('');
    setShown(PAGE_TURNS);
    setExpanded(new Set());
    nextId.current = Math.max(0, ...(conversation?.turns || []).map(t => t.id + 1));
  }

  const newConversation = () => show(newConversationId());

  function removeConversation(id: string) {
    setConversations(deleteConversation(id));
    if (id === conversationId) newConversation();
  }

  /** Adds the user's line and a pending reply, runs `work`, then replaces the pending reply. */
  async function exchange(userText: string, work: () => Promise<Omit<Extract<Turn, { role: 'assistant' }>, 'id' | 'role'>>) {
    if (busy) return;
    const replyId = nextId.current + 1;
    nextId.current += 2;
    setShown(PAGE_TURNS); // a new question collapses the thread back to its latest page
    setTurns(t => [...t, { id: replyId - 1, role: 'user' as const, text: userText },
      { id: replyId, role: 'assistant' as const, pending: true }].slice(-MAX_TURNS));
    setBusy(true);
    let reply: Omit<Extract<Turn, { role: 'assistant' }>, 'id' | 'role'>;
    try {
      reply = await work();
    } catch (error) {
      reply = { text: errorText(error) };
    }
    setTurns(t => t.map(turn => (turn.id === replyId ? { id: replyId, role: 'assistant' as const, ...reply } : turn)));
    setBusy(false);
    setSaveTick(n => n + 1);
  }

  async function explain(ticker: string, window: MoveWindow, asOfEnd: boolean, name?: string) {
    const { data } = await fetchExplanation(ticker, window, asOfEnd);
    setContext({ ticker, name, window });
    return {
      text: asOfEnd ? `Here’s what EventAlpha had collected by the end of that window.`
        : `Here are possible drivers for ${ticker}, ${windowLabel(window.start, window.end)}.`,
      result: data,
    };
  }

  /** Entry point for typed text (and, later, voice transcripts). */
  function submitText(raw: string) {
    const text = raw.trim();
    if (!text || busy) return;
    setQuestion('');
    setCustom(undefined);
    void exchange(text, async () => {
      const { data } = await askMoveQuery(text, context);
      if (data.tickerOptions.length) return { text: data.message || 'Which one did you mean?', options: data.tickerOptions };
      if (!data.ticker) return { text: data.message || 'Which stock? Type a ticker like NVDA.' };
      const sameTicker = data.ticker === context.ticker;
      const name = data.tickerName || (sameTicker ? context.name : undefined);
      if (data.start && data.end) {
        if (data.replay) setReplay(true);
        return explain(data.ticker, { start: data.start, end: data.end }, data.replay, name);
      }
      setContext({ ticker: data.ticker, name, window: sameTicker ? context.window : undefined });
      return { text: data.message || `Which time frame for ${data.ticker}?` };
    });
  }

  function pickTicker(option: TickerOption) {
    void exchange(`${option.ticker} · ${option.name}`, async () => {
      setContext({ ticker: option.ticker, name: option.name });
      return { text: `Which time frame for ${option.ticker}?` };
    });
  }

  function pickFrame(frame: TimeFrame) {
    const ticker = context.ticker;
    if (!ticker) return;
    setCustom(undefined);
    void exchange(`${ticker} · ${frame.label}`, async () => {
      const window = await frameWindow(frame);
      if (typeof window === 'string') return { text: window };
      return explain(ticker, window, replay, context.name);
    });
  }

  function submitCustom(event: FormEvent) {
    event.preventDefault();
    const ticker = context.ticker;
    if (!ticker || !custom) return;
    const start = Date.parse(custom.start);
    const end = Date.parse(custom.end);
    const window = { start: new Date(start).toISOString(), end: new Date(end).toISOString() };
    const problem = windowError(start, end);
    void exchange(`${ticker} · ${problem ? 'Custom window' : windowLabel(window.start, window.end)}`, async () => {
      if (problem) return { text: problem };
      setCustom(undefined);
      return explain(ticker, window, replay, context.name);
    });
  }

  function openCustom() {
    const end = Math.floor(Date.now() / MINUTE_MS) * MINUTE_MS;
    setCustom({ start: pickerValue(end - 60 * MINUTE_MS), end: pickerValue(end) });
  }

  const visible = turns.slice(-shown);
  const hiddenQuestions = Math.ceil((turns.length - visible.length) / 2);
  // Only the newest result is open; older ones shrink to a one-line summary until expanded.
  const latestResult = [...turns].reverse().find(t => t.role === 'assistant' && t.result)?.id;
  const toggle = (id: number) => setExpanded(prev => {
    const next = new Set(prev);
    if (!next.delete(id)) next.add(id);
    return next;
  });

  return (
    <Panel title="Ask EventAlpha" subtitle="Ask why a stock moved, or type a ticker and pick a time frame.">
      <Box sx={{ display: 'grid', gap: { xs: 2, md: 2.5 }, gridTemplateColumns: { xs: '1fr', md: '200px minmax(0, 1fr)' }, alignItems: 'start' }}>
      <Box sx={{ pr: { md: 2 }, borderRight: { md: `1px solid ${T.border}` } }}>
        <ConversationList conversations={conversations} currentId={conversationId} disabled={busy}
          onNew={newConversation} onOpen={c => show(c.id, c)} onDelete={removeConversation} />
      </Box>
      <Box sx={{ minWidth: 0 }}>
      {turns.length === 0 && (
        <Box sx={{ py: 1 }}>
          <Typography color="text.secondary" sx={{ mb: 1.5 }}>
            I look through SEC filings, press releases and news around a price move and show what came before, during and after it.
          </Typography>
          <Stack direction="row" gap={1} flexWrap="wrap">
            {SUGGESTIONS.map(s => <Chip key={s} label={s} variant="outlined" onClick={() => submitText(s)} />)}
          </Stack>
        </Box>
      )}

      {hiddenQuestions > 0 && (
        <Button size="small" fullWidth onClick={() => setShown(s => s + PAGE_TURNS)}
          sx={{ mb: 1.5, color: T.fgSecondary, border: `1px dashed ${T.border}` }}>
          Show earlier messages ({hiddenQuestions} {hiddenQuestions === 1 ? 'question' : 'questions'})
        </Button>
      )}
      <Stack spacing={1.5} role="log" aria-label="Messages" aria-live="polite">
        {visible.map(turn => turn.role === 'user' ? (
          <Box key={turn.id} sx={{ alignSelf: 'flex-end', maxWidth: '85%', px: 1.75, py: 1, borderRadius: '16px 16px 4px 16px',
            bgcolor: alpha(T.amber, 0.14), color: T.fg }}>
            <Typography>{turn.text}</Typography>
          </Box>
        ) : (
          <Stack key={turn.id} direction="row" spacing={1.25} alignItems="flex-start">
            <Box sx={{ flex: '0 0 auto', width: 28, height: 28, borderRadius: '50%', display: 'grid', placeItems: 'center',
              bgcolor: alpha(T.amber, 0.14), color: T.amber, mt: 0.25 }}>
              <AutoAwesomeRounded sx={{ fontSize: 16 }} />
            </Box>
            <Box sx={{ minWidth: 0, flex: 1 }}>
              {turn.pending ? (
                <Stack direction="row" spacing={1} alignItems="center" sx={{ color: T.fgSecondary, py: 0.5 }}>
                  <CircularProgress size={14} color="inherit" /><Typography variant="body2">Looking into it…</Typography>
                </Stack>
              ) : (
                <>
                  {turn.text && <Typography sx={{ py: 0.25 }}>{turn.text}</Typography>}
                  {turn.options && (
                    <Stack direction="row" gap={1} flexWrap="wrap" sx={{ mt: 1 }}>
                      {turn.options.map(o => (
                        <Chip key={o.ticker} label={`${o.ticker} · ${o.name}`} onClick={() => pickTicker(o)} disabled={busy}
                          sx={{ fontFamily: MONO }} />
                      ))}
                    </Stack>
                  )}
                  {turn.result && (turn.id === latestResult || expanded.has(turn.id) ? (
                    <>
                      <MoveResult result={turn.result} />
                      {turn.id !== latestResult && (
                        <Button size="small" onClick={() => toggle(turn.id)} sx={{ mt: 0.5, color: T.fgSecondary }}>Hide details</Button>
                      )}
                    </>
                  ) : <MoveResultSummary result={turn.result} onExpand={() => toggle(turn.id)} />)}
                </>
              )}
            </Box>
          </Stack>
        ))}
        <div ref={bottom} />
      </Stack>

      {context.ticker && (
        <Box sx={{ mt: 2, p: 1.5, borderRadius: 3, border: `1px dashed ${T.borderStrong}` }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between" gap={1} flexWrap="wrap" sx={{ mb: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {context.window ? 'Try another time frame for ' : 'Time frame for '}
              <Box component="span" sx={{ color: T.fg, fontFamily: MONO, fontWeight: 600 }}>{context.ticker}</Box>
              {context.name ? ` · ${context.name}` : ''}
            </Typography>
            <FormControlLabel sx={{ mr: 0 }} control={<Switch size="small" checked={replay} disabled={busy}
              onChange={e => setReplay(e.target.checked)} />}
              label={<Typography variant="body2" color="text.secondary">Only what was known at the time</Typography>} />
          </Stack>
          <Stack direction="row" gap={1} flexWrap="wrap" role="group" aria-label="Time frame">
            {TIME_FRAMES.map(frame => <Chip key={frame.label} label={frame.label} onClick={() => pickFrame(frame)} disabled={busy} />)}
            <Chip label="Custom…" variant={custom ? 'filled' : 'outlined'} onClick={openCustom} disabled={busy} />
          </Stack>
          {custom && (
            <Stack component="form" onSubmit={submitCustom} gap={1} alignItems="flex-start" sx={{ mt: 1.5 }}>
              <DateRangeField value={custom} onChange={setCustom} disabled={busy}
                max={pickerValue(Math.floor(Date.now() / MINUTE_MS) * MINUTE_MS)} />
              <Button type="submit" variant="contained" disabled={busy} sx={{ flexShrink: 0 }}>Explain</Button>
            </Stack>
          )}
        </Box>
      )}

      <Box component="form" onSubmit={(e: FormEvent) => { e.preventDefault(); submitText(question); }} sx={{ mt: 2 }}>
        <TextField fullWidth value={question} disabled={busy} onChange={e => setQuestion(e.target.value)}
          placeholder={context.ticker ? `Ask a follow-up about ${context.ticker}, or another stock…` : 'Ask about a stock, or type a ticker…'}
          inputProps={{ 'aria-label': 'Ask about a move', maxLength: 300 }}
          sx={{ '& .MuiOutlinedInput-root': { borderRadius: 999, bgcolor: T.raised, pr: 0.75 } }}
          InputProps={{
            // A microphone button can sit next to send later; it would call submitText with the transcript.
            endAdornment: (
              <InputAdornment position="end">
                <IconButton type="submit" aria-label="Ask" disabled={busy || !question.trim()}
                  sx={{ bgcolor: T.amber, color: '#1a1205', '&:hover': { bgcolor: T.amberHover }, '&.Mui-disabled': { bgcolor: alpha(T.amber, 0.25) } }}>
                  {busy ? <CircularProgress size={18} color="inherit" /> : <SendRounded fontSize="small" />}
                </IconButton>
              </InputAdornment>
            ),
          }} />
      </Box>
      </Box>
      </Box>
    </Panel>
  );
}
