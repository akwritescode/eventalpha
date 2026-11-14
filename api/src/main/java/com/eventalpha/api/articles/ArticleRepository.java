package com.eventalpha.api.articles;

import com.eventalpha.api.common.Sql;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.json.JsonMapper;

@Repository
public class ArticleRepository {

    private static final TypeReference<Map<String, Double>> EVENTS = new TypeReference<>() {};

    private final JdbcClient jdbc;
    private final JsonMapper json;

    ArticleRepository(JdbcClient jdbc, JsonMapper json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    public record Query(String ticker, String source, String formType, String eventType, double minEventProb,
                        Instant since, int limit) {}

    public List<ArticleView> find(Query q) {
        // Filters are appended only when present: no "(:x IS NULL OR ...)" tricks, which
        // also keep the planner from using the indexes.
        var where = new ArrayList<String>();
        var params = new HashMap<String, Object>();
        where.add("a.published_at >= :since");
        params.put("since", java.sql.Timestamp.from(q.since()));
        if (q.ticker() != null) {
            where.add(":ticker = ANY(a.tickers)");
            params.put("ticker", q.ticker().toUpperCase());
        }
        if (q.source() != null) {
            where.add("a.source = :source");
            params.put("source", q.source());
        }
        if (q.formType() != null) {
            where.add("a.form_type = :formType");
            params.put("formType", q.formType().toUpperCase());
        }
        if (q.eventType() != null) {
            where.add("(s.events ->> :eventType)::float >= :minEventProb");
            params.put("eventType", q.eventType());
            params.put("minEventProb", q.minEventProb());
        }
        String join = q.eventType() != null ? "JOIN" : "LEFT JOIN";
        String sql = "WITH " + Sql.LATEST_SCORES + """
                SELECT a.id, a.source, a.form_type, a.title, a.url, a.company, a.tickers, a.sec_items,
                       a.published_at, s.sentiment, s.sentiment_score, s.materiality, s.company_specific,
                       s.events::text AS events, s.model, s.scored_at
                FROM articles a
                %s latest_scores s ON s.article_id = a.id
                WHERE %s
                ORDER BY a.published_at DESC
                LIMIT :limit
                """.formatted(join, String.join(" AND ", where));
        params.put("limit", q.limit());
        return jdbc.sql(sql).params(params).query(this::map).list();
    }

    public Instant lastIngestedAt() {
        return jdbc.sql("SELECT max(ingested_at) FROM articles").query(Instant.class).optional().orElse(null);
    }

    private ArticleView map(ResultSet rs, int row) throws SQLException {
        ArticleView.Score score = rs.getString("sentiment") == null ? null : new ArticleView.Score(
                rs.getString("sentiment"),
                rs.getDouble("sentiment_score"),
                rs.getDouble("materiality"),
                rs.getDouble("company_specific"),
                json.readValue(rs.getString("events"), EVENTS),
                rs.getString("model"),
                Sql.instant(rs, "scored_at"));
        return new ArticleView(
                rs.getLong("id"),
                rs.getString("source"),
                rs.getString("form_type"),
                rs.getString("title"),
                rs.getString("url"),
                rs.getString("company"),
                Sql.textArray(rs, "tickers"),
                Sql.textArray(rs, "sec_items"),
                Sql.instant(rs, "published_at"),
                score);
    }
}
