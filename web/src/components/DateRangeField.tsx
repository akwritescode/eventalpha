import React, { FormEvent, useState } from 'react';
import { Box, IconButton, InputBase } from '@mui/material';
import { alpha } from '@mui/material/styles';
import ArrowForwardRounded from '@mui/icons-material/ArrowForwardRounded';
import CalendarMonthRounded from '@mui/icons-material/CalendarMonthRounded';
import CloseRounded from '@mui/icons-material/CloseRounded';
import { T } from '../theme';

export type DateRange = { start: string; end: string }; // datetime-local values, viewer's zone

/**
 * A chip-height pill holding a whole range: "[calendar] start – end (→) (×)". Clicking a time opens
 * the browser's native picker; → submits the range, × closes the pill.
 */
export function DateRangeField({ value, onChange, onSubmit, onClose, max, disabled }: {
  value: DateRange;
  onChange: (value: DateRange) => void;
  onSubmit: (event: FormEvent) => void;
  onClose: () => void;
  max?: string;
  disabled?: boolean;
}) {
  const [focused, setFocused] = useState(false);
  const input = (edge: keyof DateRange, label: string) => (
    <InputBase type="datetime-local" required disabled={disabled} value={value[edge]}
      onChange={e => onChange({ ...value, [edge]: e.target.value })}
      inputProps={{
        'aria-label': label, max, min: edge === 'end' ? value.start : undefined,
        onClick: (e: React.MouseEvent<HTMLInputElement>) => { try { e.currentTarget.showPicker?.(); } catch { /* unsupported */ } },
      }}
      sx={{ fontSize: '0.8125rem', fontVariantNumeric: 'tabular-nums', color: T.fg,
        '& input': { width: '20ch', p: 0, cursor: 'pointer', colorScheme: 'dark' },
        '& input::-webkit-calendar-picker-indicator': { display: 'none' } }} />
  );
  return (
    <Box component="form" role="group" aria-label="Custom range" onSubmit={onSubmit}
      onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
      sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap', maxWidth: '100%',
        minHeight: 32, pl: 1.25, pr: 0.5, py: 0.25, borderRadius: 999, bgcolor: T.pill,
        boxShadow: `inset 0 0 0 1px ${focused ? T.amber : 'transparent'}`, transition: 'box-shadow 120ms' }}>
      <CalendarMonthRounded sx={{ fontSize: 16, color: T.fgSecondary }} />
      {input('start', 'From')}
      <Box component="span" aria-hidden sx={{ color: T.fgMuted }}>–</Box>
      {input('end', 'To')}
      <IconButton type="submit" size="small" aria-label="Explain" disabled={disabled}
        sx={{ width: 24, height: 24, bgcolor: T.amber, color: '#1a1205', '&:hover': { bgcolor: T.amberHover },
          '&.Mui-disabled': { bgcolor: alpha(T.amber, 0.3) } }}>
        <ArrowForwardRounded sx={{ fontSize: 16 }} />
      </IconButton>
      <IconButton size="small" aria-label="Close custom range" onClick={onClose} disabled={disabled}
        sx={{ width: 24, height: 24, color: T.fgMuted }}>
        <CloseRounded sx={{ fontSize: 16 }} />
      </IconButton>
    </Box>
  );
}
