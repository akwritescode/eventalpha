import React from 'react';
import { AppBar, Box, Stack, Toolbar, Typography, useMediaQuery, useTheme } from '@mui/material';
import { T } from '../theme';
import { SubscribeButton } from './SubscribeButton';
import { NotificationsButton } from './NotificationsButton';
import { NotifyLevel } from '../hooks/useNotifications';

/** Sticky on every screen size, so "Subscribe to Alerts" is always in view while scrolling. */
export const TopBar: React.FC<{
  notify: { level: NotifyLevel; setLevel: (l: NotifyLevel) => void; permission: NotificationPermission | 'unsupported' };
}> = ({ notify }) => {
  const small = useMediaQuery(useTheme().breakpoints.down('sm'));
  return (
    <AppBar position="sticky" elevation={0}
      sx={{ bgcolor: 'rgba(10,14,26,0.82)', backdropFilter: 'blur(12px)', borderBottom: `1px solid ${T.border}`, color: T.fg }}>
      <Toolbar sx={{ gap: 1.5, minHeight: { xs: 56, sm: 60 } }}>
        <Stack direction="row" alignItems="center" spacing={1.25} sx={{ flexGrow: 1, minWidth: 0 }}>
          <Box component="img" src="/favicon.svg" alt="" sx={{ width: 24, height: 24 }} />
          <Typography sx={{ fontWeight: 700, letterSpacing: '-0.01em', fontSize: '1.02rem' }}>EventAlpha</Typography>
          {!small && (
            <Typography sx={{ color: T.fgMuted, fontSize: '0.9rem' }} noWrap>
              Event-driven market intelligence
            </Typography>
          )}
        </Stack>
        <NotificationsButton level={notify.level} setLevel={notify.setLevel} permission={notify.permission} />
        <SubscribeButton compact={small} />
      </Toolbar>
    </AppBar>
  );
};
