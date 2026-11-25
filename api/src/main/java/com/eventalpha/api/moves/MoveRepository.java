package com.eventalpha.api.moves;

import com.eventalpha.api.common.ApiResponse;
import com.eventalpha.api.common.Sql;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalTime;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
class MoveRepository {

    private static final ZoneId NEW_YORK = ZoneId.of("America/New_York");
    private static final Duration CONTEXT = Duration.ofDays(1);
    private static final List<String> BENCHMARKS = List.of("SPY", "SMH");
    // Keep aligned with the minute-candle collection universe.
    private static final Map<String, String> SECTOR_ETFS = Map.ofEntries(
            Map.entry("XLC", "Communication services"), Map.entry("XLY", "Consumer discretionary"),
            Map.entry("XLP", "Consumer staples"), Map.entry("XLE", "Energy"),
            Map.entry("XLF", "Financials"), Map.entry("XLV", "Health care"),
            Map.entry("XLI", "Industrials"), Map.entry("XLB", "Materials"),
            Map.entry("XLRE", "Real estate"), Map.entry("XLK", "Technology"),
            Map.entry("XLU", "Utilities"), Map.entry("SMH", "Semiconductors"), Map.entry("IGV", "Software"));
    private static final int SECTOR_MOVER_LIMIT = 3;

    // Use a single warehouse snapshot. Replays omit articles that have since been edited
    // because the article store retains only the current version.
    private static final String TIMELINE = """
            WITH visible_articles AS (
                SELECT id, title, url, source, published_at, ingested_at, updated_at, content_hash
                FROM articles
                WHERE tickers @> ARRAY[:ticker]::varchar[]
                  AND (published_at BETWEEN :contextStart AND :contextEnd OR EXISTS (
                      SELECT 1 FROM x_leads linked WHERE linked.article_id = articles.id
                        AND linked.ticker = :ticker AND linked.article_content_hash = articles.content_hash
                        AND linked.published_at BETWEEN :contextStart AND :contextEnd
                        AND linked.published_at <= :cutoff AND linked.first_seen_at <= :cutoff
                        AND linked.verified_at BETWEEN articles.updated_at AND :cutoff
                  ))
                  AND published_at <= :cutoff AND ingested_at <= :cutoff AND updated_at <= :cutoff
            )
            SELECT 'article:' || id AS id, source, title, url, published_at, ingested_at AS first_seen_at,
                   'original_source' AS status, NULL AS original_id, NULL::timestamptz AS verified_at,
                   CASE WHEN score.materiality >= 2.5 AND score.company_specific >= 0.8
                        THEN score.scored_at ELSE updated_at END AS available_at,
                   CASE WHEN score.materiality >= 2.5 AND score.company_specific >= 0.8
                        THEN score.materiality END AS catalyst_materiality
            FROM visible_articles a
            LEFT JOIN LATERAL (
                SELECT s.materiality, s.company_specific, s.scored_at
                FROM article_scores s
                WHERE (a.source = 'sec_edgar' OR a.source IN ('rss:prnewswire_all', 'rss:prnewswire_earnings'))
                  AND a.published_at <= :windowEnd AND s.article_id = a.id
                  AND s.scored_at BETWEEN a.updated_at AND :cutoff
                ORDER BY s.scored_at DESC, s.model, s.questions_version
                LIMIT 1
            ) score ON true
            UNION ALL
            SELECT 'x:' || x.post_id, 'x', x.paraphrase, 'https://x.com/i/status/' || x.post_id,
                   x.published_at, x.first_seen_at,
                   CASE WHEN a.id IS NULL THEN 'unverified_lead' ELSE 'verified_discovery' END,
                   'article:' || a.id,
                   CASE WHEN a.id IS NOT NULL THEN x.verified_at END,
                   CASE WHEN a.id IS NULL THEN x.first_seen_at ELSE GREATEST(x.verified_at, a.updated_at) END, NULL
            FROM x_leads x
            LEFT JOIN visible_articles a ON a.id = x.article_id AND a.content_hash = x.article_content_hash
                AND a.published_at <= :cutoff AND a.ingested_at <= :cutoff AND a.updated_at <= :cutoff
                AND a.updated_at <= x.verified_at AND x.verified_at <= :cutoff
            WHERE x.ticker = :ticker AND x.published_at BETWEEN :contextStart AND :contextEnd
              AND x.published_at <= :cutoff AND x.first_seen_at <= :cutoff
            ORDER BY published_at, id
            """;

    private static final String PRICES = """
            SELECT opening.symbol, opening.close AS open, closing.close,
                   opening.started_at + interval '1 minute' AS measured_start,
                   closing.started_at + interval '1 minute' AS measured_end,
                   GREATEST(opening.first_seen_at, closing.first_seen_at) AS available_at
            FROM (
                SELECT DISTINCT ON (symbol) symbol, close, started_at, first_seen_at
                FROM price_bars_minute
                WHERE symbol IN (:symbols) AND close > 0 AND started_at < :start
                  AND started_at >= :priceFloor AND first_seen_at <= :cutoff
                ORDER BY symbol, started_at DESC
            ) opening
            JOIN LATERAL (
                SELECT close, started_at, first_seen_at FROM price_bars_minute
                WHERE symbol = opening.symbol AND started_at < :end
                  AND started_at >= :start AND first_seen_at <= :cutoff
                ORDER BY started_at DESC LIMIT 1
            ) closing ON true
            """;

    private final JdbcClient jdbc;

    MoveRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    record SessionWindow(Instant start, Instant end, String message) {}

    SessionWindow today(Instant now) {
        var date = now.atZone(NEW_YORK).toLocalDate();
        return jdbc.sql("SELECT is_open, open_time, close_time FROM market_sessions WHERE day = :day")
                .param("day", date)
                .query((rs, row) -> {
                    if (!rs.getBoolean("is_open")) {
                        return new SessionWindow(null, null, "The market is closed today. Choose a recent trading day below.");
                    }
                    if (rs.getObject("open_time") == null || rs.getObject("close_time") == null) {
                        return new SessionWindow(null, null, "Today's trading calendar is unavailable. Choose a start and end time below.");
                    }
                    var open = date.atTime(rs.getObject("open_time", LocalTime.class)).atZone(NEW_YORK).toInstant();
                    var close = date.atTime(rs.getObject("close_time", LocalTime.class)).atZone(NEW_YORK).toInstant();
                    var end = now.isBefore(close) ? now.truncatedTo(ChronoUnit.MINUTES) : close;
                    if (!end.isAfter(open)) {
                        return new SessionWindow(null, null, "Today's regular session has not started yet. Choose a recent window below.");
                    }
                    return new SessionWindow(open, end, null);
                }).optional().orElse(new SessionWindow(null, null,
                        "Today's trading calendar is unavailable. Choose a start and end time below."));
    }

    private record Session(LocalDate day, boolean open, LocalTime opensAt, LocalTime closesAt) {}

    SessionWindow sinceYesterday(Instant now, String anchor) {
        var date = now.atZone(NEW_YORK).toLocalDate();
        var sessions = jdbc.sql("""
                SELECT day, is_open, open_time, close_time FROM market_sessions
                WHERE day >= :floor AND day < :today ORDER BY day DESC
                """).param("floor", date.minusDays(7)).param("today", date)
                .query((rs, row) -> new Session(rs.getObject("day", LocalDate.class), rs.getBoolean("is_open"),
                        rs.getObject("open_time", LocalTime.class), rs.getObject("close_time", LocalTime.class))).list();
        var expected = date.minusDays(1);
        for (var session : sessions) {
            if (!session.day().equals(expected)) break;
            if (session.open()) {
                var time = anchor.equals("open") ? session.opensAt() : session.closesAt();
                if (time == null) break;
                var start = session.day().atTime(time).atZone(NEW_YORK).toInstant();
                var end = now.truncatedTo(ChronoUnit.MINUTES);
                if (Duration.between(start, end).compareTo(Duration.ofDays(7)) > 0) break;
                return new SessionWindow(start, end, null);
            }
            expected = expected.minusDays(1);
        }
        return new SessionWindow(null, null,
                "The previous trading session could not be verified within the past 7 days. Choose a window below.");
    }

    record Evidence(String id, String source, String title, String url, Instant publishedAt, Instant firstSeenAt,
                    String timing, String status, String originalId, Instant verifiedAt) {}

    record Catalyst(String summary, String evidenceId) {}

    record PriceMove(String symbol, BigDecimal startPrice, BigDecimal endPrice, BigDecimal returnPercent,
                     Instant measuredStart, Instant measuredEnd, Instant dataAsOf) {}

    record SectorMove(String sector, PriceMove price) {}

    record SectorMovers(List<SectorMove> gainers, List<SectorMove> decliners) {}

    record Explanation(String ticker, Instant start, Instant end, Instant asOf, String summary,
                       List<Catalyst> catalysts, List<Evidence> timeline, List<PriceMove> priceMoves,
                       List<String> benchmarks, SectorMovers sectorMovers) {}

    private record TimelineRow(Evidence evidence, Instant availableAt, Double catalystMateriality) {}

    private record PriceRow(PriceMove move, Instant availableAt) {}

    ApiResponse<Explanation> explain(String ticker, Instant start, Instant end, Instant cutoff) {
        var rows = jdbc.sql(TIMELINE)
                .param("ticker", ticker)
                .param("contextStart", Timestamp.from(start.minus(CONTEXT)))
                .param("contextEnd", Timestamp.from(end.plus(CONTEXT)))
                .param("windowEnd", Timestamp.from(end))
                .param("cutoff", Timestamp.from(cutoff))
                .query((rs, row) -> {
                    Instant published = Sql.instant(rs, "published_at");
                    String timing = published.isBefore(start) ? "before" : published.isAfter(end) ? "after" : "during";
                    var evidence = new Evidence(rs.getString("id"), rs.getString("source"), rs.getString("title"),
                            rs.getString("url"), published, Sql.instant(rs, "first_seen_at"), timing,
                            rs.getString("status"), rs.getString("original_id"), Sql.instant(rs, "verified_at"));
                    return new TimelineRow(evidence, Sql.instant(rs, "available_at"),
                            Sql.nullableDouble(rs, "catalyst_materiality"));
                }).list();

        var timeline = rows.stream().map(TimelineRow::evidence).toList();
        var originals = new LinkedHashMap<String, Evidence>();
        for (var item : timeline) {
            if (item.status().equals("original_source") && !item.timing().equals("after")) {
                originals.put(item.id(), item);
            }
        }
        var grouped = new LinkedHashMap<String, Catalyst>();
        for (var item : timeline) {
            if (item.originalId() != null && originals.containsKey(item.originalId()) && !item.timing().equals("after")) {
                grouped.putIfAbsent(item.originalId(), new Catalyst(item.title(), item.originalId()));
            }
        }
        // Promote material, company-specific filings even when nobody discovered them on X.
        rows.stream().filter(row -> row.catalystMateriality() != null
                        && !row.evidence().timing().equals("after"))
                .sorted(Comparator.comparing(TimelineRow::catalystMateriality).reversed()
                        .thenComparing(row -> row.evidence().publishedAt(), Comparator.reverseOrder()))
                .forEach(row -> {
                    var item = row.evidence();
                    grouped.putIfAbsent(item.id(), new Catalyst(item.title(), item.id()));
                });

        var catalysts = List.copyOf(grouped.values());
        var prices = priceMoves(ticker, start, end, cutoff);
        String summary = "No verified catalyst found for this move.";
        if (!catalysts.isEmpty()) {
            summary = "Plausible catalyst — " + catalysts.getFirst().summary() + ". The timing supports a possible link.";
        } else if (ticker.equals("SPY") && start.atZone(NEW_YORK).toLocalTime().equals(LocalTime.NOON)
                && prices.stream().map(PriceRow::move).anyMatch(move -> move.symbol().equals(ticker)
                        && move.measuredStart().equals(start) && move.returnPercent().signum() > 0)) {
            summary = "No verified catalyst found for the noon rebound.";
        }
        var moves = prices.stream().map(PriceRow::move).toList();
        var sectorMovers = sectorMovers(ticker, moves);
        Instant freshness = Stream.concat(rows.stream().map(TimelineRow::availableAt),
                prices.stream().map(PriceRow::availableAt)).max(Comparator.naturalOrder()).orElse(null);
        return ApiResponse.of(new Explanation(ticker, start, end, cutoff, summary, catalysts, timeline,
                moves.stream().filter(move -> move.symbol().equals(ticker) || BENCHMARKS.contains(move.symbol())).toList(),
                BENCHMARKS, sectorMovers), freshness);
    }

    private SectorMovers sectorMovers(String ticker, List<PriceMove> moves) {
        var reference = moves.stream().filter(move -> move.symbol().equals(ticker) || move.symbol().equals("SPY"))
                .findFirst().orElse(null);
        if (reference == null) return new SectorMovers(List.of(), List.of());

        var comparable = moves.stream().filter(move -> SECTOR_ETFS.containsKey(move.symbol())
                        && move.measuredStart().equals(reference.measuredStart())
                        && move.measuredEnd().equals(reference.measuredEnd()))
                .toList();
        var byReturn = Comparator.comparing(PriceMove::returnPercent);
        var gainers = comparable.stream().filter(move -> move.returnPercent().signum() > 0)
                .sorted(byReturn.reversed().thenComparing(PriceMove::symbol)).limit(SECTOR_MOVER_LIMIT)
                .map(move -> new SectorMove(SECTOR_ETFS.get(move.symbol()), move)).toList();
        var decliners = comparable.stream().filter(move -> move.returnPercent().signum() < 0)
                .sorted(byReturn.thenComparing(PriceMove::symbol)).limit(SECTOR_MOVER_LIMIT)
                .map(move -> new SectorMove(SECTOR_ETFS.get(move.symbol()), move)).toList();
        return new SectorMovers(gainers, decliners);
    }

    private List<PriceRow> priceMoves(String ticker, Instant start, Instant end, Instant cutoff) {
        if (end.isAfter(cutoff)
                || !start.equals(start.truncatedTo(ChronoUnit.MINUTES))
                || !end.equals(end.truncatedTo(ChronoUnit.MINUTES))
) {
            return List.of();
        }
        var symbols = Stream.concat(Stream.of(ticker), Stream.concat(BENCHMARKS.stream(), SECTOR_ETFS.keySet().stream()))
                .distinct().toList();
        return jdbc.sql(PRICES)
                .param("symbols", symbols)
                .param("start", Timestamp.from(start))
                .param("priceFloor", Timestamp.from(start.minus(Duration.ofDays(7))))
                .param("end", Timestamp.from(end))
                .param("cutoff", Timestamp.from(cutoff))
                .query((rs, row) -> {
                    var opened = rs.getBigDecimal("open");
                    var closed = rs.getBigDecimal("close");
                    var change = closed.subtract(opened).movePointRight(2).divide(opened, 4, RoundingMode.HALF_UP);
                    return new PriceRow(new PriceMove(rs.getString("symbol"), opened, closed, change,
                            Sql.instant(rs, "measured_start"), Sql.instant(rs, "measured_end"),
                            Sql.instant(rs, "available_at")),
                            Sql.instant(rs, "available_at"));
                }).list().stream()
                .sorted(Comparator.comparingInt(row -> symbols.indexOf(row.move().symbol())))
                .toList();
    }
}
