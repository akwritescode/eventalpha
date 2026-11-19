package com.eventalpha.api;

import static org.hamcrest.Matchers.closeTo;
import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.notNullValue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import static org.assertj.core.api.Assertions.assertThat;

import com.jayway.jsonpath.JsonPath;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.web.servlet.MockMvc;

/**
 * Runs against Postgres 18 in Testcontainers, loaded with the DDL Alembic generates
 * (scripts/export-schema.sh), so every query here is checked against the real schema.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, // real server for the SSE test
        properties = {"spring.datasource.hikari.read-only=false", // tests must load fixtures
                "eventalpha.cors.allowed-origins=http://localhost:3000, https://eventalpha-*.vercel.app"})
@AutoConfigureMockMvc
@Sql(scripts = {"/db/schema.sql", "/db/seed.sql"}, executionPhase = Sql.ExecutionPhase.BEFORE_TEST_CLASS,
        config = @org.springframework.test.context.jdbc.SqlConfig(
                separator = org.springframework.jdbc.datasource.init.ScriptUtils.EOF_STATEMENT_SEPARATOR))
class ApiIntegrationTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    org.springframework.jdbc.core.simple.JdbcClient jdbc;

    @Autowired
    StringRedisTemplate redis;

    @LocalServerPort
    int port;

    @Test
    void sseStreamResumesFromLastEventId() throws Exception {
        String stream = "eventalpha:events";
        var first = redis.opsForStream().add(StreamRecords.string(Map.of("article_id", "1", "title", "first"))
                .withStreamKey(stream));
        redis.opsForStream().add(StreamRecords.string(Map.of("article_id", "2", "title", "second"))
                .withStreamKey(stream));

        // A client that saw `first` reconnects and must receive exactly what it missed.
        var request = HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/api/v1/stream/events"))
                .header("Last-Event-ID", first.getValue())
                .timeout(Duration.ofSeconds(10))
                .build();
        var response = HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.ofInputStream());
        assertThat(response.headers().firstValue("content-type")).hasValueSatisfying(
                ct -> assertThat(ct).startsWith("text/event-stream"));
        var lines = new ArrayList<String>();
        try (var in = new BufferedReader(new InputStreamReader(response.body()))) {
            String line;
            while ((line = in.readLine()) != null) {
                lines.add(line);
                if (line.startsWith("data:")) {
                    break;
                }
            }
        }
        assertThat(lines).anySatisfy(l -> assertThat(l).startsWith("id:").doesNotContain(first.getValue()));
        assertThat(lines.getLast()).contains("\"article_id\":\"2\"").contains("second");
    }

    @Test
    void articlesUseLatestScoreAndCarryFreshness() throws Exception {
        mvc.perform(get("/api/v1/articles").param("ticker", "aaon"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data", hasSize(2)))
                .andExpect(jsonPath("$.data[0].id").value(2)) // newest first
                .andExpect(jsonPath("$.data[1].score.model").doesNotExist()) // model ids stay internal
                .andExpect(jsonPath("$.data[1].score.sentimentScore").value(0.7)) // newest score wins
                .andExpect(jsonPath("$.data[1].score.sentiment").value("bullish"))
                .andExpect(jsonPath("$.data[1].tickers[0]").value("AAON"))
                .andExpect(jsonPath("$.dataAsOf", notNullValue()));
    }

    @Test
    void eventsFilterOnClassifierProbability() throws Exception {
        mvc.perform(get("/api/v1/events").param("type", "guidance_lowered").param("minProb", "0.8"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data", hasSize(1)))
                .andExpect(jsonPath("$.data[0].title").value("AAON 8-K: Guidance cut"))
                .andExpect(jsonPath("$.data[0].score.events.guidance_lowered").value(0.95));
    }

    @Test
    @Sql("/db/move-window.sql")
    void moveExplanationGroupsSourcesAndReplaysAvailability() throws Exception {
        String path = "/api/v1/tickers/nvda/move-explanation";
        String start = "2025-04-15T17:20:00-04:00";
        String end = "2025-04-15T17:35:00-04:00";

        mvc.perform(get(path).param("start", start).param("end", end))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.timeline", hasSize(4)))
                .andExpect(jsonPath("$.data.timeline[0].publishedAt").value("2025-04-15T21:22:59Z"))
                .andExpect(jsonPath("$.data.timeline[0].firstSeenAt").value("2025-04-15T21:26:00Z"))
                .andExpect(jsonPath("$.data.timeline[0].status").value("original_source"))
                .andExpect(jsonPath("$.data.timeline[0].timing").value("during"))
                .andExpect(jsonPath("$.data.timeline[3].timing").value("after"))
                .andExpect(jsonPath("$.data.timeline[3].status").value("unverified_lead"))
                .andExpect(jsonPath("$.data.catalysts", hasSize(1)))
                .andExpect(result -> {
                    var body = JsonPath.parse(result.getResponse().getContentAsString());
                    String original = body.read("$.data.timeline[0].id");
                    assertThat(body.<String>read("$.data.timeline[1].originalId")).isEqualTo(original);
                    assertThat(body.<String>read("$.data.timeline[2].originalId")).isEqualTo(original);
                    assertThat(body.<String>read("$.data.catalysts[0].evidenceId")).isEqualTo(original);
                });

        mvc.perform(get(path).param("start", start).param("end", end).param("asOf", "2025-04-15T17:24:00-04:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.timeline", hasSize(0)))
                .andExpect(jsonPath("$.data.summary").value("No clear catalyst found"));

        mvc.perform(get(path).param("start", start).param("end", end).param("asOf", "2025-04-15T17:26:00-04:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.timeline", hasSize(2)))
                .andExpect(jsonPath("$.data.timeline[1].status").value("unverified_lead"))
                .andExpect(jsonPath("$.data.catalysts", hasSize(0)));

        mvc.perform(get(path).param("start", "2025-04-15T17:24:00-04:00").param("end", end).param("asOf", end))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.timeline", hasSize(2)))
                .andExpect(jsonPath("$.data.timeline[0].timing").value("before"))
                .andExpect(jsonPath("$.data.timeline[1].status").value("verified_discovery"))
                .andExpect(jsonPath("$.data.catalysts", hasSize(1)));

        mvc.perform(get(path).param("start", start).param("end", "2025-04-15T17:22:00-04:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.timeline[0].timing").value("after"))
                .andExpect(jsonPath("$.data.catalysts", hasSize(0)));

        mvc.perform(get(path).param("start", end).param("end", start))
                .andExpect(status().isBadRequest());
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    @Sql("/db/move-prices.sql")
    void moveExplanationUsesSecDirectlyAndComparesAlignedBars() throws Exception {
        String path = "/api/v1/tickers/nvda/move-explanation";
        String start = "2025-06-10T10:24:00-04:00";
        String end = "2025-06-10T10:39:00-04:00";
        mvc.perform(get(path).param("start", start).param("end", end))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.timeline", hasSize(1)))
                .andExpect(jsonPath("$.data.catalysts[0].summary").value("NVDA 8-K: Guidance update"))
                .andExpect(jsonPath("$.data.priceMoves", hasSize(3)))
                .andExpect(jsonPath("$.data.priceMoves[0].symbol").value("NVDA"))
                .andExpect(jsonPath("$.data.priceMoves[0].returnPercent").value(closeTo(-2.5, 0.0001), Double.class))
                .andExpect(jsonPath("$.data.priceMoves[1].symbol").value("SPY"))
                .andExpect(jsonPath("$.data.priceMoves[1].returnPercent").value(closeTo(-0.2, 0.0001), Double.class))
                .andExpect(jsonPath("$.data.priceMoves[2].symbol").value("SMH"))
                .andExpect(jsonPath("$.data.priceMoves[2].returnPercent").value(closeTo(-1.0, 0.0001), Double.class));
        mvc.perform(get(path).param("start", start).param("end", end).param("asOf", end))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.timeline", hasSize(1)))
                .andExpect(jsonPath("$.data.catalysts", hasSize(0)))
                .andExpect(jsonPath("$.data.priceMoves", hasSize(3)));
        mvc.perform(get(path).param("start", start).param("end", "2025-06-10T10:40:00-04:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.priceMoves", hasSize(3)))
                .andExpect(jsonPath("$.data.priceMoves[0].symbol").value("NVDA"));
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    @Sql("/db/move-window.sql")
    void verifiedDiscoveryRetainsOlderOriginalOutsideContextRange() throws Exception {
        jdbc.sql("""
                UPDATE articles SET published_at = '2025-04-10 17:22-04',
                    ingested_at = '2025-04-10 17:26-04', updated_at = '2025-04-10 17:26-04'
                WHERE source_id = 'demo-move-0001045810-25-000082'
                """).update();
        mvc.perform(get("/api/v1/tickers/NVDA/move-explanation")
                        .param("start", "2025-04-15T17:20:00-04:00")
                        .param("end", "2025-04-15T17:35:00-04:00")
                        .param("asOf", "2025-04-15T17:35:00-04:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.timeline[0].status").value("original_source"))
                .andExpect(jsonPath("$.data.timeline[1].status").value("verified_discovery"));
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    @Sql("/db/move-prices.sql")
    void anOpeningBarAloneCannotMeasureAnAfterHoursOrWeekendMove() throws Exception {
        for (var bounds : List.of(
                List.of("2025-06-10T17:20:00-04:00", "2025-06-10T17:35:00-04:00"),
                List.of("2025-06-13T16:00:00-04:00", "2025-06-16T08:00:00-04:00"))) {
            mvc.perform(get("/api/v1/tickers/NVDA/move-explanation")
                            .param("start", bounds.get(0)).param("end", bounds.get(1)))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.data.benchmarks", hasSize(2)))
                    .andExpect(jsonPath("$.data.priceMoves", hasSize(0)));
        }
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    @Sql("/db/move-window.sql")
    void aLeadCannotVerifyAgainstAnOriginalForAnotherTicker() throws Exception {
        jdbc.sql("UPDATE articles SET tickers = '{AAPL}' WHERE source_id = 'demo-move-0001045810-25-000082'").update();
        mvc.perform(get("/api/v1/tickers/NVDA/move-explanation")
                        .param("start", "2025-04-15T17:20:00-04:00")
                        .param("end", "2025-04-15T17:35:00-04:00")
                        .param("asOf", "2025-04-15T17:35:00-04:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.timeline", hasSize(1)))
                .andExpect(jsonPath("$.data.timeline[0].status").value("unverified_lead"))
                .andExpect(jsonPath("$.data.timeline[0].originalId").isEmpty());
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    @Sql("/db/move-prices.sql")
    void laggedPricesExposeMeasuredBoundariesAndHonorReplay() throws Exception {
        mvc.perform(get("/api/v1/tickers/NVDA/move-explanation")
                        .param("start", "2025-06-10T10:24:00-04:00")
                        .param("end", "2025-06-10T11:00:00-04:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.priceMoves", hasSize(3)))
                .andExpect(jsonPath("$.data.priceMoves[0].measuredStart").value("2025-06-10T14:24:00Z"))
                .andExpect(jsonPath("$.data.priceMoves[0].measuredEnd").value("2025-06-10T14:40:00Z"))
                .andExpect(jsonPath("$.data.priceMoves[0].dataAsOf").value("2025-06-10T14:42:00Z"));
        mvc.perform(get("/api/v1/tickers/NVDA/move-explanation")
                        .param("start", "2025-06-10T10:24:00-04:00")
                        .param("end", "2025-06-10T10:39:00-04:00")
                        .param("asOf", "2025-06-10T10:39:00-04:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.priceMoves[0].measuredEnd").value("2025-06-10T14:25:00Z"));
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    void todayHandlesMissingSessionTimes() throws Exception {
        jdbc.sql("""
                INSERT INTO market_sessions (day, is_open, description, source)
                VALUES ((now() AT TIME ZONE 'America/New_York')::date, true, 'missing times', 'test')
                ON CONFLICT (day) DO UPDATE SET is_open = true, open_time = NULL
                """).update();
        mvc.perform(get("/api/v1/move-window/today"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.message").value("Today's trading calendar is unavailable. Choose a start and end time below."));
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    @Sql("/db/move-prices.sql")
    void materialFilingAfterWindowIsContextOnly() throws Exception {
        mvc.perform(get("/api/v1/tickers/NVDA/move-explanation")
                        .param("start", "2025-06-10T10:20:00-04:00")
                        .param("end", "2025-06-10T10:25:00-04:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.timeline[0].timing").value("after"))
                .andExpect(jsonPath("$.data.catalysts", hasSize(0)))
                .andExpect(jsonPath("$.data.summary").value("No clear catalyst found"));
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    @Sql("/db/move-prices.sql")
    void prNewswireCanQualifyWithoutSocialDiscovery() throws Exception {
        // The same material classified release can arrive directly through the existing RSS feed.
        jdbc.sql("UPDATE articles SET source = 'rss:prnewswire_all' WHERE source_id = 'test-intraday-filing'")
                .update();
        mvc.perform(get("/api/v1/tickers/NVDA/move-explanation")
                        .param("start", "2025-06-10T10:24:00-04:00")
                        .param("end", "2025-06-10T10:39:00-04:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.catalysts", hasSize(1)));
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    @Sql("/db/move-prices.sql")
    void muUsesItsOwnStoredMinutePrices() throws Exception {
        jdbc.sql("""
                INSERT INTO price_bars_minute (symbol, started_at, open, close, first_seen_at)
                SELECT 'MU', started_at, open, close, first_seen_at FROM price_bars_minute WHERE symbol = 'NVDA'
                """).update();
        mvc.perform(get("/api/v1/tickers/MU/move-explanation")
                        .param("start", "2025-06-10T10:24:00-04:00")
                        .param("end", "2025-06-10T10:39:00-04:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.priceMoves[0].symbol").value("MU"))
                .andExpect(jsonPath("$.data.priceMoves[0].returnPercent").value(closeTo(-2.5, 0.0001), Double.class));
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    void todayHandlesAClosedMarketDay() throws Exception {
        jdbc.sql("""
                INSERT INTO market_sessions (day, is_open, description, source)
                VALUES ((now() AT TIME ZONE 'America/New_York')::date, false, 'test holiday', 'test')
                ON CONFLICT (day) DO UPDATE SET is_open = false
                """).update();
        mvc.perform(get("/api/v1/move-window/today"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.message").value("The market is closed today. Choose a recent trading day below."));
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    void sinceYesterdaySkipsClosedDaysAndRespectsEarlyClose() throws Exception {
        jdbc.sql("""
                INSERT INTO market_sessions (day, is_open, open_time, close_time, description, source)
                SELECT (now() AT TIME ZONE 'America/New_York')::date - n, n = 4,
                       '09:30'::time, '13:00'::time, 'test calendar', 'test'
                FROM generate_series(1, 7) n
                ON CONFLICT (day) DO UPDATE SET is_open = EXCLUDED.is_open,
                    open_time = EXCLUDED.open_time, close_time = EXCLUDED.close_time
                """).update();
        var date = java.time.LocalDate.now(java.time.ZoneId.of("America/New_York")).minusDays(4);
        String close = date.atTime(13, 0).atZone(java.time.ZoneId.of("America/New_York")).toInstant().toString();
        mvc.perform(get("/api/v1/move-window/since-yesterday"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.start").value(close));
        String open = date.atTime(9, 30).atZone(java.time.ZoneId.of("America/New_York")).toInstant().toString();
        mvc.perform(get("/api/v1/move-window/since-yesterday").param("anchor", "open"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.start").value(open));
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    void multiDayPricesUseTheCandleEndingAtPreviousClose() throws Exception {
        jdbc.sql("""
                INSERT INTO price_bars_minute (symbol, started_at, open, close, first_seen_at)
                VALUES ('MU', '2025-06-06 12:59-04', 99, 100, '2025-06-06 13:02-04'),
                       ('MU', '2025-06-10 10:38-04', 98, 97.5, '2025-06-10 10:42-04')
                """).update();
        mvc.perform(get("/api/v1/tickers/MU/move-explanation")
                        .param("start", "2025-06-06T13:00:00-04:00")
                        .param("end", "2025-06-10T10:39:00-04:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.priceMoves[0].symbol").value("MU"))
                .andExpect(jsonPath("$.data.priceMoves[0].returnPercent").value(closeTo(-2.5, 0.0001), Double.class));
    }

    @Test
    void tickerSearchFindsExistingSymbolsAndCompanyNames() throws Exception {
        for (String query : List.of("aa", "aaon", "aaon, inc")) {
            mvc.perform(get("/api/v1/tickers/search").param("q", query))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.data[0].ticker").value("AAON"))
                    .andExpect(jsonPath("$.data[0].name").value("AAON, INC."));
        }
        mvc.perform(get("/api/v1/tickers/search").param("q", "%"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data", hasSize(0)));
    }

    @Test
    void dailySentiment() throws Exception {
        mvc.perform(get("/api/v1/tickers/AAON/sentiment"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[*].articles", notNullValue()));
    }

    @Test
    void insiderSummaryNetsOpenMarketTradesOnly() throws Exception {
        mvc.perform(get("/api/v1/tickers/AAON/insider-trades"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.trades").value(3))
                .andExpect(jsonPath("$.data.openMarketBuys").value(1))
                .andExpect(jsonPath("$.data.openMarketSells").value(1))
                // 1000 x 50 bought - 200 x 55 sold; the F (tax withholding) row is ignored
                .andExpect(jsonPath("$.data.netOpenMarketValue").value(closeTo(39000.0, 0.001)));
    }

    @Test
    void secStatusFromLedger() throws Exception {
        mvc.perform(get("/api/v1/status/sec"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].family").value("events"))
                .andExpect(jsonPath("$.data[0].loaded").value(1))
                .andExpect(jsonPath("$.data[0].failed").value(1));
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    void calendarTodayIsTheNewYorkTradingDateNotTheUtcDate() throws Exception {
        // After 19:00 ET the UTC date is already tomorrow; today's after-close reporters must stay.
        jdbc.sql("""
                INSERT INTO earnings_events (ticker, event_date, description, status, fiscal_year, market_cap, source)
                VALUES ('NYTODAY', (now() AT TIME ZONE 'America/New_York')::date, 'Earnings Result', 'Confirmed',
                        2027, 9.9e12, 'tradier'),
                       ('NYPAST', (now() AT TIME ZONE 'America/New_York')::date - 1, 'Earnings Result', 'Confirmed',
                        2027, 9.8e12, 'tradier')""").update();
        mvc.perform(get("/api/v1/calendar/upcoming")).andExpect(status().isOk())
                .andExpect(jsonPath("$.data.earnings[0].ticker").value("NYTODAY"))
                .andExpect(jsonPath("$.data.earnings[?(@.ticker == 'NYPAST')]", hasSize(0)));
    }

    @Test
    void latestSignalPerTypeWithPayload() throws Exception {
        mvc.perform(get("/api/v1/signals/latest"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data", hasSize(2)))
                .andExpect(jsonPath("$.data[1].signalType").value("spx_overnight"))
                .andExpect(jsonPath("$.data[1].score").value(0.04)) // the newer of the two sessions
                .andExpect(jsonPath("$.data[1].payload.counts.company_specific").value(369));
    }

    @Test
    void dashboardReadModels() throws Exception {
        mvc.perform(get("/api/v1/stats/sentiment-daily")).andExpect(status().isOk())
                .andExpect(jsonPath("$.data[*].bullish", notNullValue()));
        mvc.perform(get("/api/v1/insiders/buys")).andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].ticker").value("AAON"))
                .andExpect(jsonPath("$.data[0].insiders30d").value(1));
        mvc.perform(get("/api/v1/calendar/upcoming")).andExpect(status().isOk())
                .andExpect(jsonPath("$.data.economic", hasSize(1))) // GDP is outside the 14-day window
                .andExpect(jsonPath("$.data.earnings[0].ticker").value("NVDA")) // same day: largest first,
                .andExpect(jsonPath("$.data.earnings[1].ticker").value("AAA"))  // not alphabetical
                .andExpect(jsonPath("$.data.earnings[0].marketCap").value(4.5e12));
        mvc.perform(get("/api/v1/macro/nowcast")).andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].targetPeriod").value("2026-11"))
                .andExpect(jsonPath("$.data[0].value").value(0.135))
                .andExpect(jsonPath("$.data[1].actual").value(0.35));
    }

    @Test
    void feedMergesArticlesMacroAndSignalsNewestFirst() throws Exception {
        mvc.perform(get("/api/v1/feed"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[?(@.type == 'sec')]", hasSize(2)))
                .andExpect(jsonPath("$.data[?(@.type == 'signal')]", hasSize(3)))
                .andExpect(jsonPath("$.data[?(@.id == 'article:2')].label").value("SEC · 8-K"))
                .andExpect(jsonPath("$.data[?(@.id == 'article:2')].classification.sentiment").value("bearish"));
    }

    @Test
    void cpiCardHasForecastActualAndSurprise() throws Exception {
        mvc.perform(get("/api/v1/feed").param("types", "macro"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data", hasSize(1))) // the future CPI release isn't in the stream
                .andExpect(jsonPath("$.data[0].label").value("MACRO · CPI"))
                .andExpect(jsonPath("$.data[0].title").value("US CPI comes in above forecast"))
                .andExpect(jsonPath("$.data[0].macro.rows[0].forecast").value(0.2))
                .andExpect(jsonPath("$.data[0].macro.rows[0].actual").value(0.3))
                .andExpect(jsonPath("$.data[0].macro.rows[0].prior").value(0.2))
                .andExpect(jsonPath("$.data[0].macro.rows[0].surprise").value(0.1))
                .andExpect(jsonPath("$.data[0].macro.verdict").value("Inflationary surprise"));
    }

    @Test
    void feedFiltersToOneTicker() throws Exception {
        mvc.perform(get("/api/v1/feed").param("ticker", "aaon"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[?(@.type == 'sec')]", hasSize(2)))
                .andExpect(jsonPath("$.data[?(@.type == 'news')]", hasSize(0)))  // the Fed item names no ticker
                .andExpect(jsonPath("$.data[?(@.type == 'macro')]", hasSize(0)));
        mvc.perform(get("/api/v1/feed").param("ticker", "ZZZZ"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[?(@.type != 'signal')]", hasSize(0)));
    }

    @Test
    void browsersOnTheWebOriginsMayReadTheApi() throws Exception {
        for (String origin : List.of("http://localhost:3000", "https://eventalpha-git-feature-x.vercel.app")) {
            mvc.perform(get("/api/v1/feed").header("Origin", origin))
                    .andExpect(status().isOk())
                    .andExpect(header().string("Access-Control-Allow-Origin", origin));
        }
        mvc.perform(get("/api/v1/feed").header("Origin", "https://evil.example.com"))
                .andExpect(status().isForbidden());
    }

    @Test
    @Sql(statements = """
            INSERT INTO articles (id, source, source_id, form_type, url, title, tickers, published_at, content_hash)
            SELECT 100 + n, 'sec_edgar', 'tie-' || n, '8-K', 'https://example.com/tie/' || n, 'Tie ' || n, '{TIE}',
                   date_trunc('second', now()) - interval '4 days', 'tie' || n
            FROM generate_series(1, 3) n;""")  // the ';' stops @Sql splitting the statement on newlines
    @Sql(statements = "DELETE FROM articles WHERE source_id LIKE 'tie-%'",
            executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD)
    void feedPagesThroughItemsThatShareATimestamp() throws Exception {
        // Three filings with the same timestamp, one per page: each must appear exactly once.
        var seen = new ArrayList<String>();
        String before = null;
        String beforeId = null;
        for (int page = 0; page < 4; page++) {
            var req = get("/api/v1/feed").param("types", "sec").param("ticker", "TIE").param("limit", "1");
            if (before != null) {
                req = req.param("before", before).param("beforeId", beforeId);
            }
            String body = mvc.perform(req).andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
            List<String> ids = JsonPath.read(body, "$.data[*].id");
            if (ids.isEmpty()) {
                break;
            }
            seen.add(ids.getFirst());
            before = JsonPath.read(body, "$.data[0].occurredAt");
            beforeId = ids.getFirst();
        }
        assertThat(seen).containsExactly("article:103", "article:102", "article:101");
    }

    @Test
    void feedRejectsInvalidTickers() throws Exception {
        mvc.perform(get("/api/v1/feed").param("ticker", "DROP TABLE")).andExpect(status().isBadRequest());
    }

    @Test
    void feedRejectsUnknownTypes() throws Exception {
        mvc.perform(get("/api/v1/feed").param("types", "sec,crypto")).andExpect(status().isBadRequest());
    }

    @Test
    void channelPreviewShowsSignalMessagesAndEventsAsSent() throws Exception {
        String stream = "eventalpha:events";
        // Posted before the relay existed: must NOT appear in the preview.
        redis.opsForStream().add(StreamRecords.string(Map.of("article_id", "8", "title", "Never posted",
                "tickers", "OLD", "sentiment", "neutral", "sentiment_score", "0.0", "materiality", "2.6",
                "events", "", "url", "https://example.com/8")).withStreamKey(stream));
        // The relay starts here (as TelegramRelay.ensureGroup does) ...
        redis.opsForStream().createGroup(stream, org.springframework.data.redis.connection.stream.ReadOffset.latest(), "telegram");
        redis.opsForValue().set("eventalpha:relay:telegram:since",
                redis.opsForStream().groups(stream).stream().filter(g -> g.groupName().equals("telegram")).findFirst().orElseThrow().lastDeliveredId());
        // ... and delivers this one.
        redis.opsForStream().add(StreamRecords.string(Map.of("article_id", "9", "title", "Acme cuts guidance",
                "tickers", "ACME", "sentiment", "bearish", "sentiment_score", "-0.900", "materiality", "2.90",
                "events", "guidance_lowered", "url", "https://example.com/9", "model", "internal"))
                .withStreamKey(stream));
        redis.opsForStream().read(org.springframework.data.redis.connection.stream.Consumer.from("telegram", "test"),
                org.springframework.data.redis.connection.stream.StreamOffset.create(stream,
                        org.springframework.data.redis.connection.stream.ReadOffset.lastConsumed()));
        mvc.perform(get("/api/v1/channel/preview"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.channelName").value("EventAlpha Alerts"))
                .andExpect(jsonPath("$.data.posts[0].kind").value("event")) // newest first
                .andExpect(jsonPath("$.data.posts[0].html").value(org.hamcrest.Matchers.containsString("Acme cuts guidance")))
                .andExpect(jsonPath("$.data.posts[0].html").value(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("internal"))))
                .andExpect(jsonPath("$.data.posts[?(@.html =~ /.*Never posted.*/)]", hasSize(0)))
                .andExpect(jsonPath("$.data.posts[?(@.kind == 'signal')].html").value(org.hamcrest.Matchers.hasItem("<b>SPX overnight</b>\nneutral +0.04")));
    }

    @Test
    void invalidParametersReturnProblemDetail() throws Exception {
        mvc.perform(get("/api/v1/articles").param("limit", "100000"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.title").value("Invalid request"));
    }

    @Test
    void rootRedirectsToDocs() throws Exception {
        mvc.perform(get("/")).andExpect(status().is3xxRedirection())
                .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl("/docs"));
    }

    @Test
    void healthAndOpenApi() throws Exception {
        mvc.perform(get("/actuator/health")).andExpect(status().isOk());
        mvc.perform(get("/openapi")).andExpect(status().isOk());
    }
}
