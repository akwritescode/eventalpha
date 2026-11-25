import React, { useState } from 'react';
import { Box, InputBase } from '@mui/material';
import ArrowForwardRounded from '@mui/icons-material/ArrowForwardRounded';
import CalendarMonthRounded from '@mui/icons-material/CalendarMonthRounded';
import { T } from '../theme';

export type DateRange = { start: string; end: string }; // datetime-local values, viewer's zone

/** One field holding both ends of a range: "[calendar] start → end", using native pickers. */
export function DateRangeField({ value, onChange, max, disabled }: {
  value: DateRange;
  onChange: (value: DateRange) => void;
  max?: string;
  disabled?: boolean;
}) {
  const [focused, setFocused] = useState(false);
  const input = (edge: keyof DateRange, label: string) => (
    <InputBase type="datetime-local" required disabled={disabled} value={value[edge]}
      onChange={e => onChange({ ...value, [edge]: e.target.value })}
      inputProps={{ 'aria-label': label, max, min: edge === 'end' ? value.start : undefined }}
      sx={{ flex: '1 1 0', minWidth: 190, fontSize: '0.9rem', '& input': { colorScheme: 'dark', py: 0.75 } }} />
  );
  return (
    <Box role="group" aria-label="Custom range" onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
      sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: { xs: 'wrap', sm: 'nowrap' }, minWidth: 0, width: '100%',
        px: 1.5, borderRadius: 2, bgcolor: T.raised, border: `1px solid ${focused ? T.amber : T.borderStrong}`,
        transition: 'border-color 120ms' }}>
      <CalendarMonthRounded sx={{ fontSize: 18, color: T.fgSecondary }} />
      {input('start', 'From')}
      <ArrowForwardRounded sx={{ fontSize: 16, color: T.fgMuted }} />
      {input('end', 'To')}
    </Box>
  );
}
