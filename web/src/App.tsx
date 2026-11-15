import React from 'react';
import { Box, Container, Link, Typography } from '@mui/material';
import { Calendar, InsiderBuy, Nowcast, SentimentDay } from './api';
import { usePolling } from './hooks/usePolling';
import { useEventStream } from './hooks/useEventStream';
import { useNotifications } from './hooks/useNotifications';
import { TopBar } from './components/TopBar';
import { Stream } from './components/Stream';
import { SentimentChart } from './components/SentimentChart';
import { CalendarPanel } from './components/CalendarPanel';
import { InsiderPanel } from './components/InsiderPanel';
import { NowcastPanel } from './components/NowcastPanel';
import { T } from './theme';

const App: React.FC = () => {
  const notifications = useNotifications();
  const stream = useEventStream(notifications.notify);
  const sentiment = usePolling<SentimentDay[]>('/api/v1/stats/sentiment-daily?days=14', 300_000);
  const calendar = usePolling<Calendar>('/api/v1/calendar/upcoming?days=14', 600_000);
  const insiders = usePolling<InsiderBuy[]>('/api/v1/insiders/buys?days=14&limit=20', 600_000);
  const nowcast = usePolling<Nowcast[]>('/api/v1/macro/nowcast', 1_800_000);

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <TopBar notify={notifications} />
      <Container maxWidth="lg" sx={{ py: { xs: 2, sm: 4 } }}>
        <Box sx={{ display: 'grid', gap: 3, gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 1fr) 340px' }, alignItems: 'start' }}>
          <Stream live={stream.connected} pushVersion={stream.version} />
          <Box sx={{ display: 'grid', gap: 2, position: { lg: 'sticky' }, top: { lg: 84 } }}>
            <SentimentChart days={sentiment.data?.data} asOf={sentiment.data?.dataAsOf} />
            <CalendarPanel calendar={calendar.data?.data} asOf={calendar.data?.dataAsOf} />
            <NowcastPanel rows={nowcast.data?.data} asOf={nowcast.data?.dataAsOf} />
            <InsiderPanel buys={insiders.data?.data} asOf={insiders.data?.dataAsOf} />
          </Box>
        </Box>
        <Typography sx={{ mt: 4, fontSize: '0.78rem', color: T.fgMuted, maxWidth: 760 }}>
          Sources: SEC EDGAR; syndicated press-release and Federal Reserve RSS feeds; U.S. Bureau of Labor Statistics;
          FRED, Federal Reserve Bank of St. Louis; Federal Reserve Bank of Cleveland inflation nowcasts; Tradier market
          data. Classifications are model output. Research signals, not investment advice.{' '}
          <Link href="https://github.com/akwritescode/eventalpha" target="_blank" rel="noopener noreferrer" color="inherit">Source code</Link>
        </Typography>
      </Container>
    </Box>
  );
};

export default App;
