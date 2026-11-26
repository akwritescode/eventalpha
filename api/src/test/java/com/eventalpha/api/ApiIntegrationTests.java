package com.eventalpha.api;

import static org.hamcrest.Matchers.closeTo;
import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.notNullValue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import static org.assertj.core.api.Assertions.assertThat;

import com.eventalpha.api.moves.MoveQuestionParser;
import com.eventalpha.api.moves.MoveQuestionParser.ParsedQuestion;
import com.eventalpha.api.moves.MoveQuestionParser.WindowKind;
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
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
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

    @MockitoBean
    MoveQuestionParser parser;

    @MockitoBean
    com.eventalpha.api.moves.MoveCauses causes;

    @MockitoBean
    com.eventalpha.api.moves.WebMoveSearch web;

    private org.springframework.test.web.servlet.ResultActions ask(String body) throws Exception {
        return mvc.perform(post("/api/v1/move-query").contentType(MediaType.APPLICATION_JSON).content(body));
    }

    private void parsed(ParsedQuestion answer) {
        when(parser.available()).thenReturn(true);
        when(parser.parse(anyString(), any())).thenReturn(answer);
    }

    @Test
    void bareTickerSkipsTheModelAndAsksForATimeFrame() throws Exception {
        ask("{\"question\":\"aaon\"}")
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.ticker").value("AAON"))
                .andExpect(jsonPath("$.data.tickerName").value("AAON, INC."))
                .andExpect(jsonPath("$.data.start").doesNotExist())
                .andExpect(jsonPath("$.data.message").value("Which time frame for AAON?"));
        verify(parser, never()).parse(anyString(), any());
    }

    @Test
    void browsersMayPostQuestionsButNothingElse() throws Exception {
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options("/api/v1/move-query")
                        .header("Origin", "http://localhost:3000")
                        .header("Access-Control-Request-Method", "POST")
                        .header("Access-Control-Request-Headers", "content-type"))
                .andExpect(status().isOk())
                .andExpect(header().string("Access-Control-Allow-Origin", "http://localhost:3000"));
        mvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options("/api/v1/articles")
                        .header("Origin", "http://localhost:3000")
                        .header("Access-Control-Request-Method", "POST"))
                .andExpect(status().isForbidden());
    }

    @Test
    void freeTextWithoutAModelIsUnavailable() throws Exception {
        when(parser.available()).thenReturn(false);
        ask("{\"question\":\"why did aaon drop?\"}").andExpect(status().isServiceUnavailable());
    }

    @Test
    void questionBecomesATickerAndConcreteWindow() throws Exception {
        parsed(new ParsedQuestion(true, "aaon", WindowKind.LAST_MINUTES, 60, "", "", false));
        var body = ask("{\"question\":\"why did aaon drop in the last hour?\"}")
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.ticker").value("AAON"))
                .andExpect(jsonPath("$.data.message").doesNotExist())
                .andReturn().getResponse().getContentAsString();
        var start = java.time.Instant.parse(JsonPath.read(body, "$.data.start"));
        var end = java.time.Instant.parse(JsonPath.read(body, "$.data.end"));
        assertThat(Duration.between(start, end)).isEqualTo(Duration.ofHours(1));
    }

    @Test
    void unknownCompanyAndOffTopicGetAReply() throws Exception {
        parsed(new ParsedQuestion(true, "Nonexistent Corp", WindowKind.NONE, 0, "", "", false));
        ask("{\"question\":\"why did Nonexistent Corp move?\"}")
                .andExpect(jsonPath("$.data.ticker").doesNotExist())
                .andExpect(jsonPath("$.data.message").value(org.hamcrest.Matchers.startsWith("I couldn’t find")));
        parsed(new ParsedQuestion(false, "", WindowKind.NONE, 0, "", "", false));
        ask("{\"question\":\"hello\"}")
                .andExpect(jsonPath("$.data.message").value(org.hamcrest.Matchers.startsWith("I can explain")));
    }

    @Test
    void followUpReplaysTheWindowOnScreen() throws Exception {
        parsed(new ParsedQuestion(true, "", WindowKind.PREVIOUS, 0, "", "", true));
        var end = java.time.Instant.now().minus(Duration.ofHours(1)).truncatedTo(java.time.temporal.ChronoUnit.MINUTES);
        var start = end.minus(Duration.ofMinutes(30));
        ask("{\"question\":\"what was known by then?\",\"contextTicker\":\"AAON\",\"contextStart\":\"%s\",\"contextEnd\":\"%s\"}"
                .formatted(start, end))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.ticker").value("AAON"))
                .andExpect(jsonPath("$.data.start").value(start.toString()))
                .andExpect(jsonPath("$.data.replay").value(true));
    }

    @Test
    void moveExplanationAcceptsTwoWeekWindowsButNotLonger() throws Exception {
        mvc.perform(get("/api/v1/tickers/AAON/move-explanation")
                        .param("start", "2026-01-02T14:30:00Z").param("end", "2026-01-16T14:30:00Z"))
                .andExpect(status().isOk());
        mvc.perform(get("/api/v1/tickers/AAON/move-explanation")
                        .param("start", "2026-01-02T14:30:00Z").param("end", "2026-01-16T14:31:00Z"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").value("The move window must have a positive duration of at most 14 days."));
    }

    @Test
    void anyPastWindowUpToTwoWeeksIsAccepted() throws Exception {
        parsed(new ParsedQuestion(true, "AAON", WindowKind.RANGE, 0,
                "2026-01-05T09:30:00-05:00", "2026-01-16T16:00:00-05:00", false));
        ask("{\"question\":\"aaon jan 5 to 16\"}")
                .andExpect(jsonPath("$.data.ticker").value("AAON"))
                .andExpect(jsonPath("$.data.start").value("2026-01-05T14:30:00Z"))
                .andExpect(jsonPath("$.data.message").doesNotExist());
        parsed(new ParsedQuestion(true, "AAON", WindowKind.RANGE, 0,
                "2026-01-01T09:30:00-05:00", "2026-01-21T16:00:00-05:00", false));
        ask("{\"question\":\"aaon in january\"}")
                .andExpect(jsonPath("$.data.start").doesNotExist())
                .andExpect(jsonPath("$.data.message").value("That window must be up to 14 days long. Pick a time frame for AAON."));
    }

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
                .andExpect(jsonPath("$.data.summary").value("No verified catalyst found for this move."));

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

        mvc.perform(get(path).param("start", start).param("end", end).param("asOf", end))
                .andExpect(status().isOk())
                .andExpect(result -> {
                    var body = JsonPath.parse(result.getResponse().getContentAsString());
                    assertThat(body.<String>read("$.data.timeline[0].url")).isEqualTo(
                            "https://www.sec.gov/Archives/edgar/data/1045810/000104581025000082/nvda-20250409.htm");
                    String filing = body.read("$.data.timeline[0].id");
                    assertThat(body.<List<String>>read("$.data.candidateEvidenceIds")).contains(filing);
                    assertThat(body.<String>read("$.data.catalysts[0].evidenceId")).isEqualTo(filing);
                });

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
    void spyNoonReboundWithoutReleasesOrNewsSaysNoCatalyst() throws Exception {
        jdbc.sql("""
                INSERT INTO price_bars_minute (symbol, started_at, open, close, first_seen_at)
                VALUES ('SPY', '2025-06-10 11:59-04', 500, 500, '2025-06-10 12:00-04'),
                       ('SPY', '2025-06-10 12:29-04', 504, 505, '2025-06-10 12:30-04')
                """).update();
        mvc.perform(get("/api/v1/tickers/SPY/move-explanation")
                        .param("start", "2025-06-10T12:00:00-04:00")
                        .param("end", "2025-06-10T12:30:00-04:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.catalysts", hasSize(0)))
                .andExpect(jsonPath("$.data.summary").value("No verified catalyst found for this move."));
    }

    /**
     * Nov 25, 2026 as collected in production: SPY closed 718.50 the day before, gapped down after
     * the 08:30 GDP and PCE releases, bottomed at 11:15, and rallied from noon. A midday article that
     * only reports the chip rally is tagged SPY and scored material: it must not be quoted as a cause.
     */
    private void loadNov25() {
        jdbc.sql("""
                INSERT INTO price_bars_minute (symbol, started_at, open, close, first_seen_at)
                SELECT symbol, started_at::timestamptz, close, close, now() - interval '1 minute'
                FROM (VALUES ('SPY', '2026-11-24 15:59-05', 718.50), ('SPY', '2026-11-25 09:30-05', 702.63),
                             ('SPY', '2026-11-25 11:15-05', 697.89), ('SPY', '2026-11-25 11:59-05', 701.50),
                             ('SPY', '2026-11-25 12:14-05', 708.01), ('SPY', '2026-11-25 13:45-05', 716.96),
                             ('SPY', '2026-11-25 13:59-05', 716.25),
                             ('SMH', '2026-11-25 11:59-05', 400.00), ('SMH', '2026-11-25 13:59-05', 413.20),
                             ('XLK', '2026-11-25 11:59-05', 250.00), ('XLK', '2026-11-25 13:59-05', 256.50),
                             ('XLU', '2026-11-25 11:59-05', 80.00), ('XLU', '2026-11-25 13:59-05', 79.68)
                     ) bar(symbol, started_at, close)
                """).update();
        jdbc.sql("""
                INSERT INTO econ_events (source, event_key, title, event_date, scheduled_at, importance)
                VALUES ('fred', '53|2026-11-25', 'Gross Domestic Product', '2026-11-25', '2026-11-25 08:30-05', 'high'),
                       ('fred', '54|2026-11-25', 'Personal Income and Outlays', '2026-11-25', '2026-11-25 08:30-05', 'high'),
                       ('fred', '180|2026-11-25', 'Unemployment Insurance Weekly Claims Report', '2026-11-25',
                        '2026-11-25 08:30-05', 'medium')
                """).update();
        jdbc.sql("""
                INSERT INTO articles (id, source, source_id, url, title, body, tickers, published_at, content_hash)
                VALUES (9001, 'rss:prnewswire_all', 'test-chip-rally', 'https://example.com/chips',
                        'Chip stocks rally as semiconductor ETF jumps 4% at midday',
                        'Semiconductor shares rebounded in midday trading.', '{SPY,SMH}', '2026-11-25 12:30-05', 'chip-rally')
                """).update();
        jdbc.sql("""
                INSERT INTO article_scores (article_id, model, questions_version, sentiment, p_bullish, p_bearish,
                    p_neutral, sentiment_score, sentiment_confidence, materiality, materiality_confidence,
                    company_specific, events, scored_at)
                VALUES (9001, 'typesafe:test', 'v1', 'bullish', 0.9, 0.05, 0.05, 0.8, 0.8, 3.0, 0.8, 0.95, '{}',
                        '2026-11-25 12:31-05')
                """).update();
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    void noonToTwoRallyAbstainsWhenOnlyCalendarAndCommentaryAreAvailable() throws Exception {
        loadNov25();
        mvc.perform(get("/api/v1/tickers/SPY/move-explanation")
                        .param("start", "2026-11-25T12:00:00-05:00")
                        .param("end", "2026-11-25T14:00:00-05:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.catalysts", hasSize(0)))
                .andExpect(jsonPath("$.data.summary").value(
                        "No verified catalyst found for this move. Economic calendar: the 8:30 AM GDP and PCE releases. "
                                + "Leading sectors: Semiconductors +3.3%, Technology +2.6%; lagging: Utilities -0.4%."))
                .andExpect(jsonPath("$.data.summary").value(org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString("Chip stocks rally"))))
                // The title alone decides nothing: the article still went to JEV (which said no here).
                .andDo(result -> org.mockito.Mockito.verify(causes).judge(org.mockito.ArgumentMatchers.eq("SPY"),
                        org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any(),
                        org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.argThat(list -> list.stream()
                                .anyMatch(c -> c.evidenceId().equals("article:9001")))))
                .andExpect(jsonPath("$.data.timeline[?(@.id == 'article:9001')].status").value("market_commentary"))
                // hasItems: seed.sql adds a CPI release two days before today, which the lookback also covers.
                .andExpect(jsonPath("$.data.timeline[?(@.status == 'economic_release')].title").value(
                        org.hamcrest.Matchers.hasItems("Gross Domestic Product (GDP)",
                                "Personal Income and Outlays (PCE)", "Unemployment Insurance Weekly Claims Report "
                                        + "(jobless claims)")))
                .andExpect(jsonPath("$.data.timeline[?(@.status == 'economic_release')].timing").value(
                        org.hamcrest.Matchers.everyItem(org.hamcrest.Matchers.is("before"))));
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    void wideningTheReboundWindowIncludesPreOpenMacroContextWithoutInventingACause() throws Exception {
        loadNov25();
        String endpoint = "/api/v1/tickers/SPY/move-explanation";
        String end = "2026-11-25T14:00:00-05:00";
        mvc.perform(get(endpoint).param("start", "2026-11-25T11:00:00-05:00").param("end", end))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.catalysts", hasSize(0)))
                .andExpect(jsonPath("$.data.timeline[?(@.id == 'release:fred:54|2026-11-25')].timing").value("before"));
        mvc.perform(get(endpoint).param("start", "2026-11-25T08:30:00-05:00").param("end", end))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.catalysts", hasSize(0)))
                .andExpect(jsonPath("$.data.timeline[?(@.id == 'release:fred:54|2026-11-25')].timing").value("during"))
                .andExpect(jsonPath("$.data.summary").value(org.hamcrest.Matchers.allOf(
                        org.hamcrest.Matchers.containsString("then reversed"),
                        org.hamcrest.Matchers.containsString("No verified catalyst found"),
                        org.hamcrest.Matchers.containsString("GDP and PCE"))));
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    void indexRetrievalShortlistsUntaggedFedNewsWithoutPromotingItToACatalyst() throws Exception {
        jdbc.sql("""
                INSERT INTO articles (id, source, source_id, url, title, summary, tickers, published_at,
                                      ingested_at, updated_at, content_hash)
                VALUES (9002, 'rss:federal_reserve', 'test-fed-index', 'https://example.com/fed', 'Fed statement',
                        'The Fed changed its policy rate.', '{}', '2025-06-10 10:01-04', '2025-06-10 10:02-04',
                        '2025-06-10 10:02-04', 'fed-index'),
                       (9003, 'rss:federal_reserve', 'test-fed-late', 'https://example.com/fed-late', 'Late Fed statement',
                        'Another Fed statement.', '{}', '2025-06-10 10:03-04', '2025-06-10 10:40-04',
                        '2025-06-10 10:40-04', 'fed-late')
                """).update();
        mvc.perform(get("/api/v1/tickers/SPY/move-explanation")
                        .param("start", "2025-06-10T10:00:00-04:00").param("end", "2025-06-10T10:30:00-04:00")
                        .param("asOf", "2025-06-10T10:30:00-04:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.candidateEvidenceIds[*]").value(org.hamcrest.Matchers.contains("article:9002")))
                .andExpect(jsonPath("$.data.catalysts", hasSize(0)))
                .andDo(result -> org.mockito.Mockito.verify(causes).judge(org.mockito.ArgumentMatchers.eq("SPY"),
                        org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any(),
                        org.mockito.ArgumentMatchers.argThat(items -> items.size() == 1
                                && items.getFirst().body().equals("The Fed changed its policy rate."))));
        mvc.perform(get("/api/v1/tickers/NVDA/move-explanation")
                        .param("start", "2025-06-10T10:00:00-04:00").param("end", "2025-06-10T10:30:00-04:00")
                        .param("asOf", "2025-06-10T10:30:00-04:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.candidateEvidenceIds", hasSize(0)));
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    void aReplayOmitsCalendarRowsFetchedAfterItsCutoff() throws Exception {
        loadNov25();
        jdbc.sql("UPDATE econ_events SET fetched_at = '2026-11-25 08:00-05' WHERE event_key = '53|2026-11-25'").update();
        jdbc.sql("UPDATE econ_events SET fetched_at = '2026-11-25 14:01-05' WHERE event_key = '54|2026-11-25'").update();
        mvc.perform(get("/api/v1/tickers/SPY/move-explanation")
                        .param("start", "2026-11-25T12:00:00-05:00").param("end", "2026-11-25T14:00:00-05:00")
                        .param("asOf", "2026-11-25T14:00:00-05:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.timeline[?(@.id == 'release:fred:53|2026-11-25')].firstSeenAt")
                        .value("2026-11-25T13:00:00Z"))
                .andExpect(jsonPath("$.data.timeline[?(@.id == 'release:fred:54|2026-11-25')]").isEmpty());
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    void theRallyArticleIsJudgedOnItsBodyAndQuotedWhenJevAccepts() throws Exception {
        loadNov25();
        jdbc.sql("""
                UPDATE articles SET body = 'SPY rebounded after the Commerce Department said at noon it would '
                    || 'delay the proposed chip tariffs.', content_hash = 'test-spy-tariff-delay'
                WHERE id = 9001
                """).update();
        org.mockito.Mockito.when(causes.judge(org.mockito.ArgumentMatchers.eq("SPY"),
                        org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any(),
                        org.mockito.ArgumentMatchers.eq(com.eventalpha.api.moves.JevClient.Direction.UP),
                        org.mockito.ArgumentMatchers.argThat(list -> list.stream().anyMatch(c -> c.evidenceId().equals(
                                "article:9001") && c.body().contains("delay the proposed chip tariffs")))))
                .thenReturn(List.of(new com.eventalpha.api.moves.MoveCauses.Cause("article:9001",
                        "Chip stocks rally as semiconductor ETF jumps 4% at midday",
                        "the Commerce Department delaying the proposed chip tariffs", 0.98)));
        mvc.perform(get("/api/v1/tickers/SPY/move-explanation")
                        .param("start", "2026-11-25T12:00:00-05:00")
                        .param("end", "2026-11-25T14:00:00-05:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.summary").value("SPY rose 2.1% in this window, possibly due to the Commerce "
                        + "Department delaying the proposed chip tariffs (per “Chip stocks rally as semiconductor ETF jumps "
                        + "4% at midday”, JEV 0.98). Leading sectors: Semiconductors +3.3%, Technology +2.6%; "
                        + "lagging: Utilities -0.4%."))
                .andExpect(jsonPath("$.data.catalysts[0].evidenceId").value("article:9001"))
                .andExpect(jsonPath("$.data.timeline[?(@.id == 'article:9001')].status").value("explains_move"))
                .andExpect(jsonPath("$.data.timeline[?(@.id == 'article:9001')].causeScore").value(0.98));
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    void aMondayWindowLooksBackThreeTradingDaysNotThree24Hours() throws Exception {
        // Sessions: Tue 10, Wed 11 (Veterans Day: stocks open), Thu 12, Fri 13. Monday the 16th reaches back to Wed the 11th.
        jdbc.sql("""
                INSERT INTO market_sessions (day, is_open, open_time, close_time, description, source)
                SELECT d, true, '09:30', '16:00', 'test', 'test' FROM unnest(ARRAY['2026-11-10', '2026-11-11', '2026-11-12',
                    '2026-11-13']::date[]) d
                ON CONFLICT (day) DO UPDATE SET is_open = true
                """).update();
        jdbc.sql("""
                INSERT INTO econ_events (source, event_key, title, event_date, scheduled_at, importance)
                VALUES ('bls', 'cpi-test', 'Consumer Price Index', '2026-11-12', '2026-11-12 08:30-05', 'high'),
                       ('bls', 'ppi-test', 'Producer Price Index', '2026-11-10', '2026-11-10 08:30-05', 'medium')
                """).update();
        jdbc.sql("""
                INSERT INTO price_bars_minute (symbol, started_at, open, close, first_seen_at)
                SELECT 'SPY', started_at::timestamptz, close, close, now() - interval '1 minute'
                FROM (VALUES ('2026-11-11 15:59-05', 700.0), ('2026-11-13 15:59-05', 686.0),
                             ('2026-11-16 10:30-05', 690.0), ('2026-11-16 10:59-05', 693.0)) bar(started_at, close)
                """).update();
        mvc.perform(get("/api/v1/tickers/SPY/move-explanation")
                        .param("start", "2026-11-16T10:00:00-05:00")
                        .param("end", "2026-11-16T11:00:00-05:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.summary").value(
                        "No verified catalyst found for this move. Economic calendar: the Nov 12, 8:30 AM CPI release."))
                .andExpect(jsonPath("$.data.timeline[?(@.status == 'economic_release')].title")
                        .value(org.hamcrest.Matchers.contains("Consumer Price Index (CPI)")));
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    void webSearchIsOfferedOnlyWhenOurSourcesFoundNothingAndDescribesTheMove() throws Exception {
        loadNov25();
        mvc.perform(get("/api/v1/tickers/SPY/move-explanation")
                        .param("start", "2026-11-25T12:00:00-05:00").param("end", "2026-11-25T14:00:00-05:00"))
                .andExpect(jsonPath("$.data.foundInSources").value(false)); // calendar entries do not establish a cause
        mvc.perform(get("/api/v1/tickers/SPY/move-explanation")
                        .param("start", "2025-06-10T12:00:00-04:00").param("end", "2025-06-10T12:30:00-04:00"))
                .andExpect(jsonPath("$.data.foundInSources").value(false));

        org.mockito.Mockito.when(web.available()).thenReturn(true);
        org.mockito.Mockito.when(web.search(org.mockito.ArgumentMatchers.anyString(), org.mockito.ArgumentMatchers.anyString()))
                .thenReturn(new com.eventalpha.api.moves.WebMoveSearch.WebAnswer("Reports said chipmakers rebounded.",
                        List.of(new com.eventalpha.api.moves.WebMoveSearch.Source("Chips rebound", "https://example.com/a")),
                        true));
        mvc.perform(get("/api/v1/tickers/SPY/move-web-search")
                        .param("start", "2026-11-25T12:00:00-05:00").param("end", "2026-11-25T14:00:00-05:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.answer").value("Reports said chipmakers rebounded."))
                .andExpect(jsonPath("$.data.sources[0].url").value("https://example.com/a"));
        org.mockito.Mockito.verify(web).search(org.mockito.ArgumentMatchers.anyString(), org.mockito.ArgumentMatchers.eq(
                "SPY rose 2.1% between 12:00 PM and 2:00 PM ET (window starting Wednesday, Nov 25, 2026, ending "
                        + "Wednesday, Nov 25, 2026)"));
        mvc.perform(get("/api/v1/tickers/SPY/move-web-search")
                        .param("start", java.time.OffsetDateTime.now().minusMinutes(30).toString())
                        .param("end", java.time.OffsetDateTime.now().plusMinutes(30).toString()))
                .andExpect(status().isBadRequest());
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    void nineToTwoShowsTheReversalAndThePreOpenCalendarContext() throws Exception {
        loadNov25();
        mvc.perform(get("/api/v1/tickers/SPY/move-explanation")
                        .param("start", "2026-11-25T09:00:00-05:00")
                        .param("end", "2026-11-25T14:00:00-05:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.catalysts", hasSize(0)))
                .andExpect(jsonPath("$.data.summary").value(org.hamcrest.Matchers.startsWith(
                        "SPY fell 2.9% to a 11:15 AM low, then reversed to end -0.3% for the window. "
                                + "No verified catalyst found in EventAlpha's sources. Economic calendar: "
                                + "the 8:30 AM GDP and PCE releases.")));
    }

    @Test
    @org.springframework.transaction.annotation.Transactional
    void ranksAtMostThreeSectorEtfsPerDirectionOnMatchingCandles() throws Exception {
        jdbc.sql("""
                INSERT INTO price_bars_minute (symbol, started_at, open, close, first_seen_at)
                SELECT sector.symbol, bar.started_at::timestamptz, 100,
                    CASE WHEN bar.is_end THEN sector.closing ELSE 100 END, '2025-06-10 12:30-04'
                FROM (VALUES ('SPY', 102), ('IGV', 106), ('SMH', 105), ('XLK', 104), ('XLI', 103),
                             ('XLP', 94), ('XLF', 95), ('XLE', 96), ('XLU', 97), ('XLV', 100)) sector(symbol, closing)
                CROSS JOIN (VALUES ('2025-06-10 11:59-04', false), ('2025-06-10 12:29-04', true)) bar(started_at, is_end)
                UNION ALL
                SELECT 'XLC', '2025-06-10 11:59-04'::timestamptz, 100, 100, '2025-06-10 12:30-04'::timestamptz
                UNION ALL
                SELECT 'XLC', '2025-06-10 12:28-04'::timestamptz, 100, 120, '2025-06-10 12:30-04'::timestamptz
                """).update();
        mvc.perform(get("/api/v1/tickers/SPY/move-explanation")
                        .param("start", "2025-06-10T12:00:00-04:00")
                        .param("end", "2025-06-10T12:30:00-04:00"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.priceMoves[0].returnPercent").value(2.0))
                .andExpect(jsonPath("$.data.sectorMovers.gainers[*].price.symbol")
                        .value(org.hamcrest.Matchers.contains("IGV", "SMH", "XLK")))
                .andExpect(jsonPath("$.data.sectorMovers.decliners[*].price.symbol")
                        .value(org.hamcrest.Matchers.contains("XLP", "XLF", "XLE")));
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
                .andExpect(jsonPath("$.data.summary").value("No verified catalyst found for this move."));
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
    @org.springframework.transaction.annotation.Transactional
    void feedUsesTheUniverseSizeFromEachSignal() throws Exception {
        jdbc.sql("""
                UPDATE signals
                SET payload = '{"universe_size": 100, "components": {"megacap_news": 0.1}}'
                WHERE signal_type = 'spx_overnight' AND session_date = current_date - 2
                """).update();
        mvc.perform(get("/api/v1/feed").param("types", "signal"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[?(@.signal.score == 0.04)].summary")
                        .value("0 top-50 company items and 369 company news items in the session."))
                .andExpect(jsonPath("$.data[?(@.signal.score == -0.2)].summary")
                        .value("0 top-100 company items and 0 company news items in the session."))
                .andExpect(jsonPath("$.data[?(@.signal.score == -0.2)].signal.components['Top-100 news']")
                        .value(0.1));
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
