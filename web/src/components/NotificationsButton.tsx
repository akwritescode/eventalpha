import React, { useState } from 'react';
import { IconButton, ListItemIcon, ListItemText, Menu, MenuItem, Tooltip, Typography } from '@mui/material';
import CheckIcon from '@mui/icons-material/Check';
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActiveOutlined';
import NotificationsOffIcon from '@mui/icons-material/NotificationsOffOutlined';
import { NotifyLevel } from '../hooks/useNotifications';
import { T } from '../theme';

const OPTIONS: { value: NotifyLevel; label: string; hint: string }[] = [
  { value: 'high', label: 'High-impact events', hint: 'Material, company-specific news, signals, macro releases' },
  { value: 'all', label: 'Everything', hint: 'Every new filing and news item' },
  { value: 'off', label: 'Off', hint: '' },
];

export const NotificationsButton: React.FC<{
  level: NotifyLevel;
  setLevel: (l: NotifyLevel) => void;
  permission: NotificationPermission | 'unsupported';
}> = ({ level, setLevel, permission }) => {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const on = level !== 'off' && permission === 'granted';
  return (
    <>
      <Tooltip title={on ? 'Browser notifications on' : 'Browser notifications'}>
        <IconButton size="small" onClick={(e) => setAnchor(e.currentTarget)} aria-label="notifications"
          sx={{ color: on ? T.amber : T.fgSecondary }}>
          {on ? <NotificationsActiveIcon fontSize="small" /> : <NotificationsOffIcon fontSize="small" />}
        </IconButton>
      </Tooltip>
      <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)}
        PaperProps={{ sx: { bgcolor: T.popover, border: `1px solid ${T.border}`, maxWidth: 320 } }}>
        <Typography sx={{ px: 2, pt: 1, pb: 0.5, fontSize: '0.78rem', color: T.fgMuted }}>
          Notify me while EventAlpha is open in a tab
        </Typography>
        {OPTIONS.map((o) => (
          <MenuItem key={o.value} onClick={() => { setLevel(o.value); setAnchor(null); }}>
            <ListItemIcon sx={{ color: T.amber }}>{level === o.value ? <CheckIcon fontSize="small" /> : null}</ListItemIcon>
            <ListItemText primary={o.label} secondary={o.hint || undefined}
              secondaryTypographyProps={{ sx: { fontSize: '0.75rem', color: T.fgMuted } }} />
          </MenuItem>
        ))}
        {permission === 'denied' && (
          <Typography sx={{ px: 2, py: 1, fontSize: '0.75rem', color: T.down }}>
            Notifications are blocked for this site in your browser settings.
          </Typography>
        )}
        {permission === 'unsupported' && (
          <Typography sx={{ px: 2, py: 1, fontSize: '0.75rem', color: T.fgMuted }}>This browser doesn't support notifications.</Typography>
        )}
      </Menu>
    </>
  );
};
