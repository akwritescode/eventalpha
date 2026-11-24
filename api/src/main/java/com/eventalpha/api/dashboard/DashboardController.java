package com.eventalpha.api.dashboard;

import com.eventalpha.api.common.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** Read models for the web dashboard. Each response carries dataAsOf like every other endpoint. */
@RestController
@RequestMapping("/api/v1")
class DashboardController {

    private final JdbcClient jdbc;
    private final JsonMapper json;

    DashboardController(JdbcClient jdbc, JsonMapper json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    record SignalView(String signalType, LocalDate sessionDate, Instant generatedAt, Double score, Double confidence,
                      JsonNode payload, JsonNode inputsAsOf) {}

    @Operation(summary = "Latest signal of each type (premarket, spx_overnight) with its full payload")
    @GetMapping("/signals/latest")
    ApiResponse<List<SignalView>> latestSignals() {
        var rows = jdbc.sql("""
                        SELECT DISTINCT ON (signal_type) signal_type, session_date, generated_at, score, confidence,
                               payload::text AS payload, inputs_as_of::text AS inputs_as_of
                        FROM signals ORDER BY signal_type, session_date DESC, generated_at DESC""")
                .query((rs, i) -> new SignalView(
                        rs.getString("signal_type"),
                        rs.getObject("session_date", LocalDate.class),
                        rs.getObject("generated_at", OffsetDateTime.class).toInstant(),
                        (Double) rs.getObject("score"),
                        (Double) rs.getObject("confidence"),
                        json.readTree(rs.getString("payload")),
                        json.readTree(rs.getString("inputs_as_of"))))
                .list();
        Instant asOf = rows.stream().map(SignalView::generatedAt).max(Instant::compareTo).orElse(null);
        return ApiResponse.of(rows, asOf);
    }

    record SentimentDay(LocalDate day, int articles, int scored, int bullish, int bearish, int neutral,
                        Double meanScore, int highMateriality) {}

    @Operation(summary = "Market-wide daily sentiment of company-specific news (US/Eastern days)")
    @GetMapping("/stats/sentiment-daily")
    ApiResponse<List<SentimentDay>> sentimentDaily(@RequestParam(defaultValue = "14") @Min(1) @Max(120) int days) {
        var rows = jdbc.sql("""
                        WITH latest AS (
                            SELECT DISTINCT ON (article_id) * FROM article_scores ORDER BY article_id, scored_at DESC)
                        SELECT (a.published_at AT TIME ZONE 'America/New_York')::date AS day,
                               count(*) AS articles,
                               count(s.article_id) AS scored,
                               count(*) FILTER (WHERE s.sentiment = 'bullish' AND s.company_specific >= 0.8) AS bullish,
                               count(*) FILTER (WHERE s.sentiment = 'bearish' AND s.company_specific >= 0.8) AS bearish,
                               count(*) FILTER (WHERE s.sentiment = 'neutral' AND s.company_specific >= 0.8) AS neutral,
                               avg(s.sentiment_score) FILTER (WHERE s.company_specific >= 0.8) AS mean_score,
                               count(*) FILTER (WHERE s.materiality >= 2.5 AND s.company_specific >= 0.8) AS high_materiality
                        FROM articles a LEFT JOIN latest s ON s.article_id = a.id
                        WHERE a.published_at >= now() - make_interval(days => :days)
                        GROUP BY 1 ORDER BY 1""")
                .param("days", days)
                .query(SentimentDay.class)
                .list();
        return ApiResponse.of(rows, maxInstant("SELECT max(scored_at) FROM article_scores"));
    }

    record InsiderBuy(String ticker, String issuerName, String ownerName, String officerTitle, BigDecimal shares,
                      BigDecimal value, LocalDate lastTransaction, int insiders30d) {}

    @Operation(summary = "Largest open-market insider purchases (Form 4 code P), one row per insider per stock")
    @GetMapping("/insiders/buys")
    ApiResponse<List<InsiderBuy>> insiderBuys(@RequestParam(defaultValue = "14") @Min(1) @Max(365) int days,
                                              @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit) {
        var rows = jdbc.sql("""
                        WITH buys AS (
                            SELECT ticker, max(issuer_name) AS issuer_name, owner_name, max(officer_title) AS officer_title,
                                   sum(shares) AS shares, sum(shares * price) AS value, max(transaction_date) AS last_transaction
                            FROM insider_transactions
                            WHERE transaction_code = 'P' AND NOT is_derivative AND price IS NOT NULL AND ticker IS NOT NULL
                              AND transaction_date >= current_date - :days
                            GROUP BY ticker, owner_name),
                        clusters AS (
                            SELECT ticker, count(DISTINCT owner_name) AS insiders_30d FROM insider_transactions
                            WHERE transaction_code = 'P' AND NOT is_derivative AND transaction_date >= current_date - 30
                            GROUP BY ticker)
                        SELECT b.*, c.insiders_30d AS insiders30d FROM buys b JOIN clusters c USING (ticker)
                        ORDER BY b.value DESC LIMIT :limit""")
                .param("days", days).param("limit", limit)
                .query(InsiderBuy.class)
                .list();
        return ApiResponse.of(rows, maxInstant("SELECT max(filed_at) FROM insider_transactions"));
    }

    record EconEvent(LocalDate eventDate, Instant scheduledAt, String title, String importance, String source) {}

    record EarningsEvent(String ticker, LocalDate eventDate, String status, Double marketCap) {}

    record Calendar(List<EconEvent> economic, List<EarningsEvent> earnings) {}

    // Event dates are New York calendar dates. The database runs in UTC, so `current_date` would
    // roll over at 19:00/20:00 ET and drop today's after-close earnings while they're reporting.
    @Operation(summary = "Upcoming economic releases (BLS, FRED, FOMC) and earnings dates")
    @GetMapping("/calendar/upcoming")
    ApiResponse<Calendar> upcoming(@RequestParam(defaultValue = "14") @Min(1) @Max(60) int days) {
        var econ = jdbc.sql("""
                        SELECT event_date, scheduled_at, title, importance, source FROM econ_events
                        WHERE event_date BETWEEN (now() AT TIME ZONE 'America/New_York')::date AND (now() AT TIME ZONE 'America/New_York')::date + :days
                        ORDER BY event_date, scheduled_at NULLS LAST, importance, title""")
                .param("days", days)
                .query((rs, i) -> new EconEvent(rs.getObject("event_date", LocalDate.class),
                        rs.getObject("scheduled_at", OffsetDateTime.class) == null ? null
                                : rs.getObject("scheduled_at", OffsetDateTime.class).toInstant(),
                        rs.getString("title"), rs.getString("importance"), rs.getString("source")))
                .list();
        var earnings = jdbc.sql("""
                        SELECT ticker, event_date, status, market_cap FROM earnings_events
                        WHERE event_date BETWEEN (now() AT TIME ZONE 'America/New_York')::date AND (now() AT TIME ZONE 'America/New_York')::date + :days
                        ORDER BY event_date, market_cap DESC NULLS LAST, ticker""")  // largest company first
                .param("days", days)
                .query(EarningsEvent.class)
                .list();
        return ApiResponse.of(new Calendar(econ, earnings),
                maxInstant("SELECT greatest((SELECT max(fetched_at) FROM econ_events), (SELECT max(fetched_at) FROM earnings_events))"));
    }

    record Nowcast(String measure, String targetPeriod, LocalDate vintage, BigDecimal value, BigDecimal actual) {}

    @Operation(summary = "Cleveland Fed inflation nowcast (month-over-month): latest vintage for the current and previous month")
    @GetMapping("/macro/nowcast")
    ApiResponse<List<Nowcast>> nowcast() {
        var rows = jdbc.sql("""
                        SELECT DISTINCT ON (target_period, measure) measure, target_period, vintage, value,
                               -- the actual appears on rows fetched after the release, not on every vintage
                               max(actual) OVER (PARTITION BY target_period, measure) AS actual
                        FROM inflation_nowcasts
                        WHERE horizon = 'mom' AND target_period IN (
                            SELECT DISTINCT target_period FROM inflation_nowcasts WHERE horizon = 'mom'
                            ORDER BY target_period DESC LIMIT 2)
                        ORDER BY target_period DESC, measure, vintage DESC""")
                .query(Nowcast.class)
                .list();
        return ApiResponse.of(rows, maxInstant("SELECT max(fetched_at) FROM inflation_nowcasts"));
    }

    private Instant maxInstant(String sql) {
        return jdbc.sql(sql).query(Instant.class).optional().orElse(null);
    }
}
