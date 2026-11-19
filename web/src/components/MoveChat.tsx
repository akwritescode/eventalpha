import React, { FormEvent, useState } from 'react';
import { Box, Button, Stack, TextField, Typography } from '@mui/material';
import { getJson } from '../api';
import { Explanation, MoveResult } from './MoveExplanation';
import { Panel } from './ui';
import { fetchExplanation, isReplay, MoveWindow, recentWindow, resolveTicker, windowError } from '../moveInput';

type Turn = { question: string; answer: string; result?: Explanation };

export function MoveChat() {
  const [question, setQuestion] = useState('');
  const [turn, setTurn] = useState<Turn>();
  const [ticker, setTicker] = useState('');
  const [window, setWindow] = useState<MoveWindow>();
  const [busy, setBusy] = useState(false);

  async function ask(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || busy) return;
    setQuestion('');
    setTurn(undefined);
    setBusy(true);
    let result: Explanation | undefined;
    let answer = '';
    let selected = window;
    try {
      const sinceYesterday = text.match(/since\s+yesterday(?:['’]s)?(?:\s+(open|close))?/i);
      const today = /\btoday\b/i.test(text);
      const replay = isReplay(text);
      const duration = text.match(/last\s+(?:(half an?|an?|one|\d+)\s*)?(minutes?|mins?|hours?)/i);
      const { query, matches } = await resolveTicker(text);
      let resolved = ticker;
      if (matches.length === 1) {
        resolved = matches[0].ticker;
        setTicker(resolved);
      } else if (matches.length > 1) {
        answer = `Which ticker did you mean? ${matches.map(item => item.ticker + ' · ' + item.name).join(', ')}.`;
      } else if (query) {
        answer = `I couldn’t find “${query}” in EventAlpha’s ticker universe. Try its stock symbol.`;
      }
      if (answer) return;
      if (/last week|yesterday|\d{4}-\d{2}-\d{2}/i.test(text) && !duration && !sinceYesterday) {
        answer = 'Choose a window in the past 7 days using the date pickers below. Here you can ask about the last 30 minutes, hour, or 2 hours.';
      } else if (!resolved) {
        answer = 'Which stock? Try “Why did AAPL move in the last 30 minutes?”';
      } else if (!duration && !replay && !today && !sinceYesterday) {
        answer = 'Which window? Try “last 30 minutes” or “last hour”. To revisit the previous window, ask “What was available by the end?”';
      } else {
        if (today || sinceYesterday) {
          const route = sinceYesterday
            ? `/api/v1/move-window/since-yesterday?anchor=${sinceYesterday[1]?.toLowerCase() || 'close'}`
            : '/api/v1/move-window/today';
          const response = await getJson<MoveWindow & { message?: string }>(route);
          if (response.data.message) answer = response.data.message;
          else selected = { start: response.data.start, end: response.data.end };
        } else if (duration) {
          const amount = duration[1]?.toLowerCase() ?? '1';
          const numeric = /^\d+$/.test(amount) ? Number(amount) : amount.startsWith('half') ? 0.5 : 1;
          const minutes = numeric * (/hour/i.test(duration[2]) ? 60 : 1);
          if (minutes < 1 || minutes > 24 * 60) {
            answer = 'Choose a window from 1 minute to 24 hours.';
          } else {
            selected = recentWindow(minutes);
            answer = windowError(Date.parse(selected.start), Date.parse(selected.end)) || '';
          }
        }
        if (!answer && !selected) {
          answer = 'Ask about a move first, then replay that window.';
        }
        if (!answer && selected) {
          result = (await fetchExplanation(resolved, selected, replay)).data;
          setWindow(selected);
          answer = replay
            ? 'Here is what EventAlpha had collected by the end of that window.'
            : sinceYesterday
              ? `Using the previous trading session’s ${sinceYesterday[1]?.toLowerCase() || 'close'} through now. Here are the available sources and returns.`
              : 'Here are possible drivers from the sources EventAlpha tracks, with available window returns.';
        }
      }
    } catch {
      answer = 'I couldn’t load this window. Please try again.';
    } finally {
      setTurn({ question: text, answer, result });
      setBusy(false);
    }
  }

  return (
    <Panel title="Ask EventAlpha" subtitle="Ask about a stock and follow up on the same window.">
      <Stack spacing={2} sx={{ maxHeight: 650, overflowY: 'auto', mb: 2 }} aria-live="polite">
        {turn && (
          <Box>
            <Typography fontWeight={600}>{turn.question}</Typography>
            <Typography sx={{ mt: 0.5 }}>{turn.answer}</Typography>
            {turn.result && <MoveResult result={turn.result} />}
          </Box>
        )}
      </Stack>
      <Box component="form" onSubmit={ask}>
        <Stack spacing={1}>
          <TextField fullWidth required label="Ask about a move" value={question}
            placeholder="Why did NVDA move in the last 30 minutes?"
            onChange={(event) => setQuestion(event.target.value)} disabled={busy} />
          <Button type="submit" variant="contained" disabled={busy} sx={{ alignSelf: 'flex-start' }}>
            {busy ? 'Checking…' : 'Ask'}
          </Button>
        </Stack>
      </Box>
    </Panel>
  );
}
