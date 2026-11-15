import React, { useState } from 'react';
import { Button } from '@mui/material';
import TelegramIcon from '@mui/icons-material/Telegram';
import { T } from '../theme';
import { ChannelPreview } from './ChannelPreview';

/** The call to action (sticky top bar, always in view): previews the channel, then offers Join. */
export const SubscribeButton: React.FC<{ compact?: boolean }> = ({ compact }) => {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="contained" size="small" startIcon={<TelegramIcon />} onClick={() => setOpen(true)}
        sx={{ px: 1.75, height: 36, whiteSpace: 'nowrap', boxShadow: 'none', '&:hover': { boxShadow: 'none', bgcolor: T.amberHover } }}>
        {compact ? 'Subscribe' : 'Subscribe to Alerts'}
      </Button>
      <ChannelPreview open={open} onClose={() => setOpen(false)} />
    </>
  );
};
