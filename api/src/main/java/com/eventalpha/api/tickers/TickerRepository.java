package com.eventalpha.api.tickers;

import com.eventalpha.api.common.Sql;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
class TickerRepository {

    private final JdbcClient jdbc;

    TickerRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    record SentimentDay(
            LocalDate day,
            int articles,
            int bullish,
            int bearish,
            int neutral,
            Double meanScore,
            Double materialityWeightedScore,
            Double maxMateriality) {}

    record InsiderTrade(
            String accession,
            LocalDate transactionDate,
            String ownerName,
            String officerTitle,
            boolean isDirector,
            boolean isOfficer,
            boolean isTenPercentOwner,
            String transactionCode,
            String acquiredDisposed,
            BigDecimal shares,
            BigDecimal price,
            BigDecimal sharesOwnedAfter,
            boolean isDerivative,
            Instant filedAt) {}

    /** Daily sentiment, bucketed by US/Eastern date (the trading day the news belongs to). */
    List<SentimentDay> sentimentByDay(String ticker, int days) {
        String sql = "WITH " + Sql.LATEST_SCORES + """
                SELECT (a.published_at AT TIME ZONE 'America/New_York')::date AS day,
                       count(*)                                         AS articles,
                       count(*) FILTER (WHERE s.sentiment = 'bullish')   AS bullish,
                       count(*) FILTER (WHERE s.sentiment = 'bearish')   AS bearish,
                       count(*) FILTER (WHERE s.sentiment = 'neutral')   AS neutral,
                       avg(s.sentiment_score)                           AS mean_score,
                       sum(s.sentiment_score * s.materiality) / nullif(sum(s.materiality), 0)
                                                                        AS weighted_score,
                       max(s.materiality)                               AS max_materiality
                FROM articles a
                JOIN latest_scores s ON s.article_id = a.id
                WHERE :ticker = ANY(a.tickers)
                  AND a.published_at >= now() - make_interval(days => :days)
                GROUP BY 1
                ORDER BY 1 DESC
                """;
        return jdbc.sql(sql).param("ticker", ticker).param("days", days)
                .query((rs, i) -> new SentimentDay(
                        rs.getObject("day", LocalDate.class),
                        rs.getInt("articles"),
                        rs.getInt("bullish"),
                        rs.getInt("bearish"),
                        rs.getInt("neutral"),
                        Sql.nullableDouble(rs, "mean_score"),
                        Sql.nullableDouble(rs, "weighted_score"),
                        Sql.nullableDouble(rs, "max_materiality")))
                .list();
    }

    List<InsiderTrade> insiderTrades(String ticker, int days, boolean openMarketOnly) {
        String sql = """
                SELECT accession, transaction_date, owner_name, officer_title, is_director, is_officer,
                       is_ten_percent_owner, transaction_code, acquired_disposed, shares, price,
                       shares_owned_after, is_derivative, filed_at
                FROM insider_transactions
                WHERE ticker = :ticker
                  AND transaction_date >= current_date - :days
                  %s
                ORDER BY transaction_date DESC, accession, row_no
                """.formatted(openMarketOnly ? "AND transaction_code IN ('P', 'S')" : "");
        return jdbc.sql(sql).param("ticker", ticker).param("days", days)
                .query(InsiderTrade.class)
                .list();
    }

    Instant lastScoredAt() {
        return jdbc.sql("SELECT max(scored_at) FROM article_scores").query(Instant.class).optional().orElse(null);
    }

    Instant lastInsiderFiling() {
        return jdbc.sql("SELECT max(filed_at) FROM insider_transactions").query(Instant.class).optional().orElse(null);
    }
}
