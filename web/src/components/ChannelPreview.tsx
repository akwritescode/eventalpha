import React, { useEffect, useState } from 'react';
import { Box, Button, CircularProgress, Dialog, IconButton, Stack, Typography, useMediaQuery, useTheme } from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import TelegramIcon from '@mui/icons-material/Telegram';
import { ChannelPreview as Preview, TELEGRAM_URL, getJson } from '../api';
import { etDate, etTime } from '../format';
import { T } from '../theme';

const escapeAttr = (v: string) =>
  v.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/** Telegram-style HTML (b, i, a, code) from our own messages → safe markup. Anything else becomes text. */
export function sanitize(html: string): string {
  const doc = new DOMParser().parseFromString(`<div>${html.replace(/\n/g, '<br>')}</div>`, 'text/html');
  const allowed = new Set(['B', 'STRONG', 'I', 'EM', 'A', 'CODE', 'BR']);
  const walk = (node: Node): string =>
    Array.from(node.childNodes)
      .map((n) => {
        if (n.nodeType === Node.TEXT_NODE) {
          const span = document.createElement('span');
          span.textContent = n.textContent;
          return span.innerHTML;
        }
        const el = n as HTMLElement;
        if (!allowed.has(el.tagName)) return walk(el);
        if (el.tagName === 'BR') return '<br>';
        if (el.tagName === 'A') {
          const href = el.getAttribute('href') ?? '';
          // getAttribute() returns the decoded value: re-escape it, or a quote in the URL
          // would end the attribute and let the rest of the URL inject markup.
          return /^https?:\/\//.test(href) ? `<a href="${escapeAttr(href)}" target="_blank" rel="noopener noreferrer">${walk(el)}</a>` : walk(el);
        }
        const tag = el.tagName.toLowerCase();
        return `<${tag}>${walk(el)}</${tag}>`;
      })
      .join('');
  return walk(doc.body.firstChild as Node);
}

/**
 * A private channel's invite link shows no messages, so visitors preview the channel here first:
 * its recent posts as sent, then the Join button at the bottom.
 */
export const ChannelPreview: React.FC<{ open: boolean; onClose: () => void }> = ({ open, onClose }) => {
  const fullScreen = useMediaQuery(useTheme().breakpoints.down('sm'));
  const [data, setData] = useState<Preview>();
  const [error, setError] = useState<string>();

  useEffect(() => {
    if (!open) return;
    getJson<Preview>('/api/v1/channel/preview?limit=20')
      .then((r) => { setData(r.data); setError(undefined); })
      .catch((e) => setError((e as Error).message));
  }, [open]);

  return (
    <Dialog open={open} onClose={onClose} fullScreen={fullScreen} maxWidth="sm" fullWidth
      PaperProps={{ sx: { bgcolor: T.bg, display: 'flex', flexDirection: 'column', maxHeight: fullScreen ? '100%' : '85vh' } }}>
      <Stack direction="row" alignItems="center" spacing={1.5} sx={{ px: 2.5, py: 2, borderBottom: `1px solid ${T.border}` }}>
        <Box sx={{ width: 40, height: 40, borderRadius: '50%', bgcolor: T.raised, display: 'grid', placeItems: 'center' }}>
          <Box component="img" src="/favicon.svg" alt="" sx={{ width: 24, height: 24 }} />
        </Box>
        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          <Typography sx={{ fontWeight: 600 }} noWrap>{data?.channelName ?? 'EventAlpha Alerts'}</Typography>
          <Typography sx={{ fontSize: '0.8rem', color: T.fgSecondary }}>
            Telegram channel · signals at 09:15 and before the SPX close, plus high-impact events
          </Typography>
        </Box>
        <IconButton onClick={onClose} aria-label="close" size="small"><CloseIcon fontSize="small" /></IconButton>
      </Stack>

      <Box sx={{ flexGrow: 1, overflowY: 'auto', px: { xs: 1.5, sm: 2.5 }, py: 2,
        backgroundImage: `radial-gradient(${T.border} 1px, transparent 1px)`, backgroundSize: '18px 18px' }}>
        <Typography sx={{ textAlign: 'center', fontSize: '0.78rem', color: T.fgMuted, mb: 2 }}>
          Preview of recent posts · newest at the bottom
        </Typography>
        {!data && !error && <Box sx={{ py: 6, textAlign: 'center' }}><CircularProgress size={22} /></Box>}
        {error && <Typography sx={{ textAlign: 'center', color: T.fgSecondary }}>Couldn't load the preview ({error}).</Typography>}
        {data && data.posts.length === 0 && (
          <Typography sx={{ textAlign: 'center', color: T.fgSecondary }}>No posts yet.</Typography>
        )}
        <Stack spacing={1.25}>
          {data?.posts.slice().reverse().map((p) => (
            <Box key={p.id} sx={{ alignSelf: 'flex-start', maxWidth: '92%', bgcolor: T.raised, border: `1px solid ${T.border}`,
              borderRadius: '14px 14px 14px 4px', px: 1.75, py: 1.25 }}>
              <Box
                sx={{ fontSize: '0.88rem', lineHeight: 1.5, color: T.fg, wordBreak: 'break-word',
                  '& a': { color: '#60a5fa' }, '& i': { color: T.fgSecondary } }}
                dangerouslySetInnerHTML={{ __html: sanitize(p.html) }}
              />
              <Typography sx={{ textAlign: 'right', fontSize: '0.72rem', color: T.fgMuted, mt: 0.5 }}>
                {etDate(p.postedAt)} · {etTime(p.postedAt)} ET
              </Typography>
            </Box>
          ))}
        </Stack>
      </Box>

      <Box sx={{ p: 2, borderTop: `1px solid ${T.border}`, bgcolor: T.surface }}>
        {TELEGRAM_URL ? (
          <Button fullWidth variant="contained" size="large" startIcon={<TelegramIcon />} href={TELEGRAM_URL}
            target="_blank" rel="noopener noreferrer"
            sx={{ height: 46, boxShadow: 'none', '&:hover': { boxShadow: 'none', bgcolor: T.amberHover } }}>
            Join on Telegram
          </Button>
        ) : (
          <Button fullWidth variant="contained" size="large" startIcon={<TelegramIcon />} disabled sx={{ height: 46 }}>
            Join on Telegram (set REACT_APP_TELEGRAM_URL)
          </Button>
        )}
        <Typography sx={{ textAlign: 'center', fontSize: '0.75rem', color: T.fgMuted, mt: 1 }}>
          Free. Research signals, not investment advice. Leave anytime.
        </Typography>
      </Box>
    </Dialog>
  );
};
