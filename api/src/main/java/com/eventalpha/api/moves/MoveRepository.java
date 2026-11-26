package com.eventalpha.api.moves;

import com.eventalpha.api.common.ApiResponse;
import com.eventalpha.api.common.Sql;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import com.eventalpha.api.moves.MoveNarrative.Candle;
import com.eventalpha.api.moves.MoveNarrative.PriceClose;
import com.eventalpha.api.moves.MoveNarrative.Release;
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
    /** Index ETFs: their summary names the leading and lagging sectors. */
    private static final Set<String> INDEX_ETFS = Set.of("SPY", "QQQ", "DIA");
    /** How many trading sessions before the window to look for releases and articles that may explain it. */
    static final int LOOKBACK_TRADING_DAYS = 3;

    // A date-only calendar entry has no reliable intraday placement.
    private static final String RELEASES = """
            SELECT source, event_key, title, importance, scheduled_at AS at, fetched_at
            FROM econ_events
            WHERE importance IN ('high', 'medium') AND scheduled_at BETWEEN :from AND :to
              AND scheduled_at <= :cutoff AND fetched_at <= :cutoff
            ORDER BY scheduled_at, title
            """;

    private static final String PRICE_BEFORE = """
            SELECT close, started_at + interval '1 minute' AS closed_at FROM price_bars_minute
            WHERE symbol = :symbol AND started_at <= :latestStart AND started_at >= :floor
              AND first_seen_at <= :cutoff AND close > 0
            ORDER BY started_at DESC LIMIT 1
            """;

    private static final String PATH = """
            SELECT started_at, close FROM price_bars_minute
            WHERE symbol = :symbol AND started_at >= :start AND started_at < :end
              AND first_seen_at <= :cutoff AND close > 0
            ORDER BY started_at
            """;

    // Replays omit articles edited after the cutoff because the store retains only the current version.
    private static final String TIMELINE = """
            WITH visible_articles AS (
                SELECT id, title, url, source, published_at, ingested_at, updated_at, content_hash,
                       COALESCE(NULLIF(BTRIM(body), ''), summary) AS body,
                       tickers @> ARRAY[:ticker]::varchar[] AS direct_match
                FROM articles
                WHERE (tickers @> ARRAY[:ticker]::varchar[] OR (:includeMarketNews AND source = 'rss:federal_reserve'))
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
                        THEN score.materiality END AS catalyst_materiality,
                   a.body, a.content_hash, a.direct_match
            FROM visible_articles a
            LEFT JOIN LATERAL (
                SELECT s.materiality, s.company_specific, s.scored_at
                FROM article_scores s
                WHERE a.direct_match
                  AND (a.source = 'sec_edgar' OR a.source IN ('rss:prnewswire_all', 'rss:prnewswire_earnings'))
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
                   CASE WHEN a.id IS NULL THEN x.first_seen_at ELSE GREATEST(x.verified_at, a.updated_at) END, NULL,
                   NULL, NULL, false
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
    private final MoveCauses causes;

    MoveRepository(JdbcClient jdbc, MoveCauses causes) {
        this.jdbc = jdbc;
        this.causes = causes;
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

    /** causeScore: JEV's probability that the article explains the move, when it was asked. */
    record Evidence(String id, String source, String title, String url, Instant publishedAt, Instant firstSeenAt,
                    String timing, String status, String originalId, Instant verifiedAt, Double causeScore) {}

    record Catalyst(String summary, String evidenceId) {}

    record PriceMove(String symbol, BigDecimal startPrice, BigDecimal endPrice, BigDecimal returnPercent,
                     Instant measuredStart, Instant measuredEnd, Instant dataAsOf) {}

    record SectorMove(String sector, PriceMove price) {}

    record SectorMovers(List<SectorMove> gainers, List<SectorMove> decliners) {}

    // foundInSources is true only when the warehouse establishes a catalyst candidate. Calendar
    // context alone must not suppress the frontend's web-search fallback for live requests.
    record Explanation(String ticker, Instant start, Instant end, Instant asOf, String summary,
                       List<Catalyst> catalysts, List<Evidence> timeline, List<PriceMove> priceMoves,
                       List<String> benchmarks, SectorMovers sectorMovers, boolean foundInSources,
                       List<String> candidateEvidenceIds) {}

    private record TimelineRow(Evidence evidence, Instant availableAt, Double catalystMateriality, String body,
                               String contentHash, boolean directMatch) {}

    private record PriceRow(PriceMove move, Instant availableAt) {}

    ApiResponse<Explanation> explain(String ticker, Instant start, Instant end, Instant cutoff) {
        Instant floor = lookbackFloor(start);
        // Verified catalysts stay within a day of the window; older articles only feed JEV and the narrative.
        Instant catalystFloor = start.minus(CONTEXT);
        var rows = jdbc.sql(TIMELINE)
                .param("ticker", ticker)
                .param("includeMarketNews", INDEX_ETFS.contains(ticker))
                .param("contextStart", Timestamp.from(floor))
                .param("contextEnd", Timestamp.from(end.plus(CONTEXT)))
                .param("windowEnd", Timestamp.from(end))
                .param("cutoff", Timestamp.from(cutoff))
                .query((rs, row) -> {
                    Instant published = Sql.instant(rs, "published_at");
                    String timing = published.isBefore(start) ? "before" : published.isAfter(end) ? "after" : "during";
                    // An article that only reports the move ("Chip stocks rally") is shown, but never a cause.
                    boolean commentary = rs.getString("status").equals("original_source")
                            && MarketCommentary.isCommentary(rs.getString("title"));
                    var evidence = new Evidence(rs.getString("id"), rs.getString("source"), rs.getString("title"),
                            rs.getString("url"), published, Sql.instant(rs, "first_seen_at"), timing,
                            commentary ? "market_commentary" : rs.getString("status"), rs.getString("original_id"),
                            Sql.instant(rs, "verified_at"), null);
                    return new TimelineRow(evidence, Sql.instant(rs, "available_at"),
                            commentary ? null : Sql.nullableDouble(rs, "catalyst_materiality"),
                            rs.getString("body"), rs.getString("content_hash"), rs.getBoolean("direct_match"));
                }).list();

        List<Evidence> articleTimeline = rows.stream().map(TimelineRow::evidence).toList();
        var originals = new LinkedHashMap<String, Evidence>();
        for (var item : articleTimeline) {
            if (item.status().equals("original_source") && !item.timing().equals("after")
                    && !item.publishedAt().isBefore(catalystFloor)) {
                originals.put(item.id(), item);
            }
        }
        var grouped = new LinkedHashMap<String, Catalyst>();
        for (var item : articleTimeline) {
            if (item.originalId() != null && originals.containsKey(item.originalId()) && !item.timing().equals("after")) {
                grouped.putIfAbsent(item.originalId(), new Catalyst(item.title(), item.originalId()));
            }
        }
        // Promote material, company-specific filings even when nobody discovered them on X.
        rows.stream().filter(row -> row.catalystMateriality() != null
                        && !row.evidence().timing().equals("after")
                        && !row.evidence().publishedAt().isBefore(catalystFloor))
                .sorted(Comparator.comparing(TimelineRow::catalystMateriality).reversed()
                        .thenComparing(row -> row.evidence().publishedAt(), Comparator.reverseOrder()))
                .forEach(row -> {
                    var item = row.evidence();
                    grouped.putIfAbsent(item.id(), new Catalyst(item.title(), item.id()));
                });

        List<Catalyst> catalysts = List.copyOf(grouped.values());
        var prices = priceMoves(ticker, start, end, cutoff);
        var moves = prices.stream().map(PriceRow::move).toList();
        var tickerMove = moves.stream().filter(move -> move.symbol().equals(ticker)).findFirst().orElse(null);
        var sectorMovers = sectorMovers(ticker, moves);

        var releases = releases(floor, end, cutoff, start, end);
        // No verified catalyst: ask JEV whether nearby articles explain the move (title + body).
        var shortlist = candidates(rows, floor);
        var measured = tickerMove == null ? null : new MoveCauses.MeasuredReturn(tickerMove.measuredStart(),
                tickerMove.measuredEnd(), tickerMove.returnPercent());
        var found = catalysts.isEmpty()
                ? causes.judge(ticker, start, end, measured, shortlist) : List.<MoveCauses.Cause>of();
        var scores = found.stream().collect(java.util.stream.Collectors.toMap(MoveCauses.Cause::evidenceId,
                MoveCauses.Cause::probability));
        articleTimeline = articleTimeline.stream().map(e -> scores.containsKey(e.id())
                ? new Evidence(e.id(), e.source(), e.title(), e.url(), e.publishedAt(), e.firstSeenAt(), e.timing(),
                        "explains_move", e.originalId(), e.verifiedAt(), scores.get(e.id()))
                : e).toList();
        var timeline = Stream.concat(articleTimeline.stream(), releases.stream().map(ReleaseRow::evidence))
                .sorted(Comparator.comparing(Evidence::publishedAt).thenComparing(Evidence::id)).toList();
        var windowOpen = tickerMove == null ? null : new PriceClose(tickerMove.measuredStart(), tickerMove.startPrice());
        var path = windowOpen == null ? List.<Candle>of() : path(ticker, start, end, cutoff);
        var latestBefore = releases.stream().map(ReleaseRow::release).filter(r -> r.at().isBefore(start))
                .map(Release::at).max(Comparator.naturalOrder()).orElse(null);
        var priceBeforeRelease = latestBefore == null || path.isEmpty() || !windowOpen.at().isAfter(latestBefore) ? null
                : priceBefore(ticker, latestBefore, cutoff);
        String summary = MoveNarrative.summarize(new MoveNarrative.Input(ticker, start, end, catalysts, found, windowOpen,
                path, releases.stream().map(ReleaseRow::release).toList(), priceBeforeRelease, sectorMovers,
                INDEX_ETFS.contains(ticker)));
        if (!found.isEmpty()) {
            catalysts = found.stream().map(c -> new Catalyst(c.reason(), c.evidenceId())).toList();
        }
        Instant freshness = Stream.concat(Stream.concat(rows.stream().map(TimelineRow::availableAt),
                        prices.stream().map(PriceRow::availableAt)),
                releases.stream().map(row -> row.evidence().firstSeenAt())).max(Comparator.naturalOrder()).orElse(null);
        return ApiResponse.of(new Explanation(ticker, start, end, cutoff, summary, catalysts, timeline,
                moves.stream().filter(move -> move.symbol().equals(ticker) || BENCHMARKS.contains(move.symbol())).toList(),
                BENCHMARKS, sectorMovers, !catalysts.isEmpty(),
                shortlist.stream().map(MoveCauses.Candidate::evidenceId).toList()), freshness);
    }

    private record ReleaseRow(Release release, Evidence evidence) {}

    /** The ticker's own move over the window, if minute prices cover it. */
    Optional<PriceMove> windowMove(String ticker, Instant start, Instant end, Instant cutoff) {
        return priceMoves(ticker, start, end, cutoff).stream().map(PriceRow::move)
                .filter(move -> move.symbol().equals(ticker)).findFirst();
    }

    /**
     * Midnight (New York) of the trading day {@link #LOOKBACK_TRADING_DAYS} sessions before the window's
     * day, from the exchange calendar: a Monday window reaches back through Wednesday. Without calendar
     * rows, weekdays stand in for sessions.
     */
    Instant lookbackFloor(Instant start) {
        LocalDate day = start.atZone(NEW_YORK).toLocalDate();
        var session = jdbc.sql("""
                        SELECT day FROM market_sessions WHERE is_open AND day < :day AND day >= :floor
                        ORDER BY day DESC OFFSET :skip LIMIT 1
                        """)
                .param("day", day).param("floor", day.minusDays(21)).param("skip", LOOKBACK_TRADING_DAYS - 1)
                .query(LocalDate.class).optional();
        LocalDate from = session.orElseGet(() -> {
            LocalDate d = day;
            for (int n = 0; n < LOOKBACK_TRADING_DAYS; ) {
                d = d.minusDays(1);
                if (d.getDayOfWeek().getValue() <= 5) n++;
            }
            return d;
        });
        return from.atStartOfDay(NEW_YORK).toInstant();
    }

    /** Articles in the window or the lookback before it that JEV should read: in-window ones first, then the latest. */
    private static List<MoveCauses.Candidate> candidates(List<TimelineRow> rows, Instant floor) {
        return rows.stream()
                .filter(r -> r.evidence().id().startsWith("article:") && !r.evidence().timing().equals("after")
                        && !r.evidence().publishedAt().isBefore(floor)
                        && (r.evidence().status().equals("original_source") || r.evidence().status().equals("market_commentary")))
                .sorted(Comparator.comparing((TimelineRow r) -> !r.evidence().timing().equals("during"))
                        .thenComparing(TimelineRow::directMatch, Comparator.reverseOrder())
                        .thenComparing(r -> r.evidence().publishedAt(), Comparator.reverseOrder())
                        .thenComparing(r -> r.evidence().id()))
                .limit(MoveCauses.MAX_CANDIDATES)
                .map(r -> new MoveCauses.Candidate(r.evidence().id(), r.evidence().title(), r.body(), r.contentHash()))
                .toList();
    }

    /** Economic releases between from and to, as narrative inputs and timeline entries. */
    private List<ReleaseRow> releases(Instant from, Instant to, Instant cutoff, Instant start, Instant end) {
        return jdbc.sql(RELEASES)
                .param("from", Timestamp.from(from)).param("to", Timestamp.from(to)).param("cutoff", Timestamp.from(cutoff))
                .query((rs, row) -> {
                    Instant at = Sql.instant(rs, "at");
                    String title = rs.getString("title");
                    String name = releaseName(title);
                    String timing = at.isBefore(start) ? "before" : at.isAfter(end) ? "after" : "during";
                    var evidence = new Evidence("release:" + rs.getString("source") + ":" + rs.getString("event_key"),
                            "macro", title.equalsIgnoreCase(name) ? title : title + " (" + name + ")",
                            releaseUrl(rs.getString("source"), rs.getString("event_key"), title), at,
                            Sql.instant(rs, "fetched_at"), timing,
                            "economic_release", null, null, null);
                    return new ReleaseRow(new Release(name, at, rs.getString("importance").equals("high")), evidence);
                }).list();
    }

    /** Short names used in summaries: "the 8:30 AM GDP and PCE releases". */
    /**
     * Short names never contain a period: the web app finds the summary's "Economic calendar: ...".
     * sentence by its full stop, and "U.S." used to cut it short (the sentence was shown twice).
     */
    static String releaseName(String title) {
        if (title.startsWith("Gross Domestic Product")) return "GDP";
        if (title.startsWith("Personal Income and Outlays")) return "PCE";
        if (title.startsWith("Consumer Price Index")) return "CPI";
        if (title.startsWith("Producer Price Index")) return "PPI";
        if (title.startsWith("Employment Situation")) return "jobs report";
        if (title.startsWith("Unemployment Insurance Weekly Claims")) return "jobless claims";
        if (title.startsWith("Advance Monthly Sales")) return "retail sales";
        if (title.startsWith("New Residential Construction")) return "housing starts";
        if (title.startsWith("Industrial Production")) return "industrial production";
        if (title.startsWith("Surveys of Consumers")) return "consumer sentiment";
        if (title.startsWith("Manufacturers' Shipments")) return "factory orders";
        if (title.startsWith("ADP National Employment")) return "ADP payrolls";
        if (title.startsWith("Job Openings and Labor Turnover")) return "JOLTS";
        if (title.startsWith("Employment Cost Index")) return "employment cost index";
        if (title.startsWith("U.S. Import and Export Price")) return "import prices";
        if (title.startsWith("Real Earnings")) return "real earnings";
        if (title.startsWith("Productivity and Costs")) return "productivity and costs";
        if (title.startsWith("FOMC")) return "FOMC decision";
        return title.replace(".", "");
    }

    private static String releaseUrl(String source, String key, String title) {
        if (title.startsWith("FOMC")) return "https://www.federalreserve.gov/newsevents/pressreleases.htm";
        if (source.equals("fred")) return "https://fred.stlouisfed.org/release?rid=" + key.split("\\|")[0];
        if (source.equals("bls")) return "https://www.bls.gov/bls/newsrels.htm";
        return "";
    }

    /** The last price known before a release: the anchor for the descriptive pre-window move. */
    private PriceClose priceBefore(String ticker, Instant at, Instant cutoff) {
        return jdbc.sql(PRICE_BEFORE).param("symbol", ticker)
                .param("latestStart", Timestamp.from(at.minus(Duration.ofMinutes(1))))
                .param("floor", Timestamp.from(at.minus(Duration.ofDays(10)))).param("cutoff", Timestamp.from(cutoff))
                .query((rs, row) -> new PriceClose(Sql.instant(rs, "closed_at"), rs.getBigDecimal("close")))
                .optional().orElse(null);
    }

    private List<Candle> path(String ticker, Instant start, Instant end, Instant cutoff) {
        return jdbc.sql(PATH).param("symbol", ticker).param("start", Timestamp.from(start))
                .param("end", Timestamp.from(end)).param("cutoff", Timestamp.from(cutoff))
                .query((rs, row) -> new Candle(Sql.instant(rs, "started_at"), rs.getBigDecimal("close"))).list();
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
