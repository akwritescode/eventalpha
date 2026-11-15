package com.eventalpha.api;

import static org.hamcrest.Matchers.closeTo;
import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.notNullValue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
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
        properties = "spring.datasource.hikari.read-only=false") // tests must load fixtures
@AutoConfigureMockMvc
@Sql(scripts = {"/db/schema.sql", "/db/seed.sql"}, executionPhase = Sql.ExecutionPhase.BEFORE_TEST_CLASS)
class ApiIntegrationTests {

    @Autowired
    MockMvc mvc;

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
                .andExpect(jsonPath("$.data[1].score.model").value("typesafe:jev-1.14.0"))
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
