import React, { useState } from 'react';
import { Box, Button, IconButton, Stack, Typography } from '@mui/material';
import { alpha } from '@mui/material/styles';
import AddRounded from '@mui/icons-material/AddRounded';
import CloseRounded from '@mui/icons-material/CloseRounded';
import ExpandMoreRounded from '@mui/icons-material/ExpandMoreRounded';
import type { Conversation } from '../conversations';
import { timeAgo } from '../format';
import { T } from '../theme';

/**
 * Left column of the chat: "New conversation" on top, then past conversations, newest first.
 * On narrow screens the list folds behind a "Recent" toggle so the chat stays in view.
 */
export function ConversationList({ conversations, currentId, disabled, onNew, onOpen, onDelete }: {
  conversations: Conversation[];
  currentId: string;
  disabled: boolean;
  onNew: () => void;
  onOpen: (conversation: Conversation) => void;
  onDelete: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Box component="nav" aria-label="Conversations" sx={{ minWidth: 0 }}>
      <Stack direction={{ xs: 'row', md: 'column' }} gap={1}>
        <Button variant="outlined" startIcon={<AddRounded />} onClick={onNew} disabled={disabled}
          sx={{ flex: { xs: 1, md: 'none' }, justifyContent: 'flex-start', borderColor: T.borderStrong, color: T.fg }}>
          New conversation
        </Button>
        <Button onClick={() => setOpen(o => !o)} aria-expanded={open} endIcon={<ExpandMoreRounded
          sx={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 150ms' }} />}
          sx={{ display: { md: 'none' }, color: T.fgSecondary }}>
          Recent ({conversations.length})
        </Button>
      </Stack>

      <Box sx={{ display: { xs: open ? 'block' : 'none', md: 'block' }, mt: 1.5 }}>
        <Typography variant="overline" color="text.secondary" sx={{ display: { xs: 'none', md: 'block' } }}>Recent</Typography>
        {conversations.length === 0 ? (
          <Typography variant="caption" color="text.secondary">Past conversations appear here.</Typography>
        ) : (
          <Box component="ul" sx={{ listStyle: 'none', p: 0, m: 0, display: 'grid', gap: 0.5, maxHeight: { md: 520 }, overflowY: 'auto' }}>
            {conversations.map(c => {
              const current = c.id === currentId;
              return (
                <Box component="li" key={c.id} sx={{ position: 'relative', minWidth: 0, '&:hover .delete': { opacity: 1 } }}>
                  <Box component="button" type="button" disabled={disabled} aria-current={current ? 'true' : undefined}
                    onClick={() => { onOpen(c); setOpen(false); }}
                    sx={{ display: 'block', width: '100%', minWidth: 0, overflow: 'hidden', textAlign: 'left', font: 'inherit', color: T.fg, cursor: disabled ? 'default' : 'pointer',
                      border: 0, borderRadius: 2, py: 0.75, pl: 1.25, pr: 4,
                      bgcolor: current ? alpha(T.amber, 0.12) : 'transparent',
                      '&:hover': { bgcolor: current ? alpha(T.amber, 0.16) : T.pill } }}>
                    <Typography variant="body2" noWrap title={c.title}>{c.title}</Typography>
                    <Typography variant="caption" color="text.secondary">{timeAgo(c.updatedAt)}</Typography>
                  </Box>
                  <IconButton className="delete" size="small" aria-label={`Delete conversation “${c.title}”`} disabled={disabled}
                    onClick={() => onDelete(c.id)}
                    sx={{ position: 'absolute', right: 2, top: 6, opacity: { xs: 1, md: 0 }, color: T.fgMuted, '&:focus-visible': { opacity: 1 } }}>
                    <CloseRounded sx={{ fontSize: 16 }} />
                  </IconButton>
                </Box>
              );
            })}
          </Box>
        )}
      </Box>
    </Box>
  );
}
