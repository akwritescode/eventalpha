package com.eventalpha.api.common;

import java.sql.Array;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;

public final class Sql {

    private Sql() {}

    /** Latest score per article (a re-classification with a newer model wins). */
    public static final String LATEST_SCORES = """
            latest_scores AS (
                SELECT DISTINCT ON (article_id) *
                FROM article_scores
                ORDER BY article_id, scored_at DESC
            )""";

    public static List<String> textArray(ResultSet rs, String column) throws SQLException {
        Array array = rs.getArray(column);
        return array == null ? List.of() : List.of((String[]) array.getArray());
    }

    public static Instant instant(ResultSet rs, String column) throws SQLException {
        Timestamp ts = rs.getTimestamp(column);
        return ts == null ? null : ts.toInstant();
    }

    public static Double nullableDouble(ResultSet rs, String column) throws SQLException {
        double v = rs.getDouble(column);
        return rs.wasNull() ? null : v;
    }
}
