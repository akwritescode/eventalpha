package com.eventalpha.api.feed;

import com.eventalpha.api.common.Sql;
import com.eventalpha.api.feed.FeedItem.Classification;
import com.eventalpha.api.feed.FeedItem.Contributor;
import com.eventalpha.api.feed.FeedItem.Fact;
import com.eventalpha.api.feed.FeedItem.Macro;
import com.eventalpha.api.feed.FeedItem.MacroRow;
import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/** Builds feed cards from articles + scores, released economic events, and signals. */
@Repository
class FeedRepository {

    static final ZoneId NY = ZoneId.of("America/New_York");
    private static final TypeReference<Map<String, Double>> EVENTS = new TypeReference<>() {};
    private static final Map<String, String> ITEM_NAMES = Map.ofEntries(
            Map.entry("1.01", "Material agreement"), Map.entry("1.02", "Agreement terminated"),
            Map.entry("1.03", "Bankruptcy"), Map.entry("1.05", "Cybersecurity incident"),
            Map.entry("2.01", "Acquisition or disposition"), Map.entry("2.02", "Results of operations"),
            Map.entry("2.03", "New financial obligation"), Map.entry("2.05", "Exit or disposal costs"),
            Map.entry("2.06", "Material impairment"), Map.entry("3.01", "Delisting notice"),
            Map.entry("3.02", "Unregistered equity sale"), Map.entry("3.03", "Change to holders' rights"),
            Map.entry("4.01", "Auditor change"), Map.entry("4.02", "Non-reliance on financials"),
            Map.entry("5.01", "Change in control"), Map.entry("5.02", "Director or officer change"),
            Map.entry("5.03", "Charter or bylaw amendment"), Map.entry("5.07", "Shareholder vote"),
            Map.entry("7.01", "Regulation FD disclosure"), Map.entry("8.01", "Other events"),
            Map.entry("9.01", "Financial statements and exhibits"));

    private final JdbcClient jdbc;
    private final JsonMapper json;

    FeedRepository(JdbcClient jdbc, JsonMapper json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    private static final String ITEM_ID = "('article:' || a.id) COLLATE \"C\"";

    // ---------- articles (SEC filings and news) ----------

    /**
     * Newest first, keyset-paged by (published_at, item id). Several filings often share a
     * timestamp, so the id breaks ties; COLLATE "C" makes SQL order ids exactly like Java's
     * String.compareTo, which FeedController sorts and pages with.
     */
    List<FeedItem> articles(Instant since, Instant before, String beforeId, int limit, boolean sec, boolean news,
                            String ticker) {
        String source = sec && news ? "" : sec ? "AND a.source = 'sec_edgar'" : "AND a.source <> 'sec_edgar'";
        if (ticker != null) source += " AND a.tickers @> ARRAY[CAST(:ticker AS varchar)]";
        String cursor = beforeId == null ? "a.published_at < :before"
                : "(a.published_at < :before OR (a.published_at = :before AND " + ITEM_ID + " < :beforeId))";
        return jdbc.sql("""
                        WITH latest AS (
                            SELECT DISTINCT ON (article_id) * FROM article_scores ORDER BY article_id, scored_at DESC)
                        SELECT a.id, a.source, a.form_type, a.title, a.summary, left(a.body, 4000) AS body, a.url,
                               a.company, a.cik, a.tickers, a.sec_items, a.published_at,
                               s.sentiment, s.sentiment_score, s.sentiment_confidence, s.p_bullish, s.p_bearish,
                               s.p_neutral, s.materiality, s.company_specific, s.events::text AS events
                        FROM articles a LEFT JOIN latest s ON s.article_id = a.id
                        WHERE a.published_at >= :since AND %s %s
                        ORDER BY a.published_at DESC, %s DESC LIMIT :limit""".formatted(cursor, source, ITEM_ID))
                .param("since", Timestamp.from(since)).param("before", Timestamp.from(before)).param("limit", limit)
                .param("ticker", ticker == null ? "" : ticker)
                .param("beforeId", beforeId == null ? "" : beforeId)
                .query(this::article)
                .list();
    }

    private FeedItem article(ResultSet rs, int row) throws SQLException {
        String source = rs.getString("source");
        boolean sec = "sec_edgar".equals(source);
        String form = rs.getString("form_type");
        String feed = sec ? null : feedName(source);
        Instant published = Sql.instant(rs, "published_at");
        List<String> items = Sql.textArray(rs, "sec_items");

        Classification cls = null;
        if (rs.getString("sentiment") != null) {
            cls = new Classification(rs.getString("sentiment"), rs.getDouble("sentiment_score"),
                    Sql.nullableDouble(rs, "sentiment_confidence"), rs.getDouble("p_bullish"), rs.getDouble("p_bearish"),
                    rs.getDouble("p_neutral"), rs.getDouble("materiality"), rs.getDouble("company_specific"),
                    json.readValue(rs.getString("events"), EVENTS));
        }
        List<Fact> facts = new ArrayList<>();
        if (sec) {
            if (rs.getString("company") != null) facts.add(new Fact("Company", rs.getString("company")));
            facts.add(new Fact("Form", form));
            for (String code : items) {
                facts.add(new Fact("Item " + code, ITEM_NAMES.getOrDefault(code, "")));
            }
            facts.add(new Fact("Accepted", etDateTime(published)));
        } else {
            facts.add(new Fact("Feed", feed));
            facts.add(new Fact("Published", etDateTime(published)));
        }
        String summary = sec ? leadSentences(rs.getString("body")) : rs.getString("summary");
        if (summary == null && sec) {
            summary = items.isEmpty() ? null : String.join("; ", items.stream().map(c -> ITEM_NAMES.getOrDefault(c, c)).toList());
        }
        return new FeedItem(
                "article:" + rs.getLong("id"),
                sec ? "sec" : "news",
                sec ? "SEC · " + form : "NEWS · " + feed.toUpperCase(Locale.ROOT),
                published, true,
                rs.getString("title"),
                trim(summary, 280),
                rs.getString("url"),
                sec ? "Source: SEC EDGAR · Form " + form : "Source: " + feed,
                Sql.textArray(rs, "tickers"),
                cls, facts, null, null);
    }

    private static String feedName(String source) {
        String f = source.replaceFirst("^rss:", "");
        if (f.startsWith("prnewswire")) return "PR Newswire";
        if (f.equals("federal_reserve")) return "Federal Reserve";
        if (f.equals("sec_press")) return "SEC press releases";
        return f.replace('_', ' ');
    }

    /** First substantive sentences of a filing's text: skips exhibit headers and short title lines. */
    static String leadSentences(String body) {
        if (body == null) return null;
        StringBuilder out = new StringBuilder();
        for (String line : body.split("\\R")) {
            String l = line.strip();
            long upper = l.chars().filter(Character::isUpperCase).count();
            boolean shouty = l.length() > 0 && upper > l.length() * 0.6;
            if (l.length() < 60 || shouty || l.toLowerCase(Locale.ROOT).startsWith("exhibit")) {
                continue;
            }
            out.append(l).append(' ');
            if (out.length() > 220) break;
        }
        return out.isEmpty() ? null : out.toString().strip();
    }

    private static String trim(String s, int max) {
        if (s == null || s.length() <= max) return s;
        int cut = s.lastIndexOf(". ", max);
        return cut > max / 2 ? s.substring(0, cut + 1) : s.substring(0, max).strip() + "…";
    }

    // ---------- signals ----------

    List<FeedItem> signals(Instant since, Instant before) {
        return jdbc.sql("""
                        SELECT signal_type, session_date, generated_at, score, confidence, payload::text AS payload
                        FROM signals WHERE generated_at >= :since AND generated_at <= :before""")  // controller pages
                .param("since", Timestamp.from(since)).param("before", Timestamp.from(before))
                .query((rs, i) -> signal(rs.getString("signal_type"), rs.getObject("session_date", LocalDate.class),
                        rs.getObject("generated_at", OffsetDateTime.class).toInstant(),
                        (Double) rs.getObject("score"), (Double) rs.getObject("confidence"),
                        json.readTree(rs.getString("payload"))))
                .list();
    }

    private FeedItem signal(String type, LocalDate session, Instant at, Double score, Double confidence, JsonNode p) {
        String direction = score == null ? "No read" : score > 0.15 ? "Bullish" : score < -0.15 ? "Bearish" : "Neutral";
        List<Contributor> contributors = new ArrayList<>();
        Map<String, Object> components = new LinkedHashMap<>();
        String title;
        String summary;
        int contributing;
        if ("spx_overnight".equals(type)) {
            JsonNode c = p.path("components");
            JsonNode counts = p.path("counts");
            components.put("Top-50 news", num(c.path("megacap_news")));
            components.put("Breadth", num(c.path("breadth")));
            contributing = counts.path("company_specific").asInt(0);
            title = "SPX · " + direction + " overnight outlook";
            List<String> parts = new ArrayList<>();
            parts.add(counts.path("megacap_articles").asInt(0) + " top-50 company items and "
                    + contributing + " company news items in the session");
            List<String> macro = new ArrayList<>();
            p.path("macro_next_session").forEach(m -> macro.add(m.path("title").asString("")));
            if (!macro.isEmpty()) parts.add("next session: " + String.join(", ", macro));
            summary = String.join("; ", parts) + ".";
            p.path("megacap_news").forEach(a -> contributors.add(contributor(a)));
        } else {
            JsonNode counts = p.path("counts");
            contributing = counts.path("material_articles").asInt(0);
            title = "Premarket · " + counts.path("companies").asInt(0) + " companies with material news";
            List<String> top = new ArrayList<>();
            p.path("tickers").forEach(a -> {
                if (top.size() < 5 && a.path("tickers").size() > 0) top.add(a.path("tickers").get(0).asString(""));
            });
            summary = "News tone " + (score == null ? "n/a" : String.format(Locale.ROOT, "%+.2f", score))
                    + (top.isEmpty() ? "" : "; strongest: " + String.join(", ", top)) + ".";
            components.put("News tone", score);
            p.path("tickers").forEach(a -> contributors.add(contributor(a)));
        }
        return new FeedItem("signal:" + type + ":" + session, "signal", "TRADING SIGNAL", at, true, title, summary, null,
                "Source: EventAlpha signal · session " + session, List.of(), null, List.of(), null,
                new FeedItem.Signal(type, score, confidence, contributors, contributing, components));
    }

    private Contributor contributor(JsonNode a) {
        List<String> tickers = new ArrayList<>();
        a.path("tickers").forEach(t -> tickers.add(t.asString("")));
        return new Contributor(a.path("title").asString(""), a.path("url").asString(null), tickers,
                a.path("sentiment").asString(null), a.path("sentiment_score").isMissingNode() ? null : a.path("sentiment_score").asDouble());
    }

    private static Double num(JsonNode n) {
        return n.isNumber() ? n.asDouble() : null;
    }

    // ---------- released economic events ----------

    List<FeedItem> macro(Instant since, Instant before) {
        record Ev(String source, String key, String title, LocalDate day, Instant at, String importance) {}
        var events = jdbc.sql("""
                        SELECT source, event_key, title, event_date, scheduled_at, importance FROM econ_events
                        WHERE coalesce(scheduled_at, (event_date + time '08:30') AT TIME ZONE 'America/New_York')
                              >= :since
                          AND coalesce(scheduled_at, (event_date + time '08:30') AT TIME ZONE 'America/New_York')
                              <= least(:before, now())  -- inclusive: FeedController applies the (time, id) cursor
                          AND (importance = 'high' OR title LIKE 'Producer Price Index%')""")
                .param("since", Timestamp.from(since)).param("before", Timestamp.from(before))
                .query((rs, i) -> new Ev(rs.getString("source"), rs.getString("event_key"), rs.getString("title"),
                        rs.getObject("event_date", LocalDate.class),
                        rs.getObject("scheduled_at", OffsetDateTime.class) == null ? null
                                : rs.getObject("scheduled_at", OffsetDateTime.class).toInstant(),
                        rs.getString("importance")))
                .list();
        List<FeedItem> out = new ArrayList<>();
        for (Ev e : events) {
            Instant at = e.at() != null ? e.at() : e.day().atTime(LocalTime.of(8, 30)).atZone(NY).toInstant();
            out.add(macroItem(e.source() + ":" + e.key(), e.title(), e.day(), at, e.at() != null, e.importance()));
        }
        return out;
    }

    private FeedItem macroItem(String key, String title, LocalDate day, Instant at, boolean timeKnown, String importance) {
        LocalDate period = day.withDayOfMonth(1).minusMonths(1); // monthly releases report the prior month
        String month = period.format(DateTimeFormatter.ofPattern("MMM", Locale.US));
        List<MacroRow> rows = new ArrayList<>();
        String label = "MACRO · " + shortName(title);
        String headline = title;
        String verdict = null;
        String tone = "neutral";
        String note = null;

        if (title.startsWith("Consumer Price Index")) {
            MacroRow cpi = cpiRow("CPI m/m", "CUSR0000SA0", "cpi", period, day);
            MacroRow core = cpiRow("Core CPI m/m", "CUSR0000SA0L1E", "core_cpi", period, day);
            if (cpi != null) rows.add(cpi);
            if (core != null) rows.add(core);
            if (cpi != null && cpi.surprise() != null) {
                double s = cpi.surprise();
                headline = s >= 0.05 ? "US CPI comes in above forecast" : s <= -0.05 ? "US CPI comes in below forecast"
                        : "US CPI comes in line with forecast";
                verdict = s >= 0.05 ? "Inflationary surprise" : s <= -0.05 ? "Disinflationary surprise" : "In line";
                tone = s >= 0.05 ? "bad" : s <= -0.05 ? "good" : "neutral";
            } else {
                headline = "US CPI for " + month;
            }
            note = "Forecast: Federal Reserve Bank of Cleveland inflation nowcast (last estimate before release). "
                    + "Actual: BLS, seasonally adjusted.";
        } else if (title.startsWith("Employment Situation")) {
            Double pay = change("fred", "PAYEMS", period);
            Double payPrior = change("fred", "PAYEMS", period.minusMonths(1));
            Double ur = value("fred", "UNRATE", period);
            Double urPrior = value("fred", "UNRATE", period.minusMonths(1));
            if (pay != null) rows.add(new MacroRow("Payrolls change", "K", null, pay, payPrior, null));
            if (ur != null) rows.add(new MacroRow("Unemployment rate", "%", null, ur, urPrior, null));
            if (pay != null) {
                headline = String.format(Locale.US, "US payrolls %+,.0fK in %s", pay, month)
                        + (ur != null ? String.format(Locale.US, "; unemployment %.1f%%", ur) : "");
            }
            note = "No consensus forecast in the free official sources; compared with the prior month. Source: BLS via FRED.";
        } else if (title.startsWith("Producer Price Index")) {
            Double ppi = pctChange("bls", "WPSFD4", period);
            Double prior = pctChange("bls", "WPSFD4", period.minusMonths(1));
            if (ppi != null) {
                rows.add(new MacroRow("PPI final demand m/m", "%", null, round(ppi, 2), prior == null ? null : round(prior, 2), null));
                headline = String.format(Locale.US, "US PPI %+.1f%% m/m in %s", ppi, month);
            }
            note = "Compared with the prior month. Source: BLS, seasonally adjusted (the headline figure).";
        } else if (title.startsWith("FOMC")) {
            Double after = dailyValue("DFF", day.plusDays(1), true);
            Double priorRate = dailyValue("DFF", day.minusDays(1), false);
            if (after != null && priorRate != null) {
                double d = after - priorRate;
                rows.add(new MacroRow("Effective fed funds rate", "%", null, after, priorRate, null));
                headline = d <= -0.1 ? "Fed cuts rates" : d >= 0.1 ? "Fed raises rates" : "Fed holds rates steady";
                verdict = d <= -0.1 ? "Rate cut" : d >= 0.1 ? "Rate hike" : "Unchanged";
            }
            note = "Effective federal funds rate the day before vs after the decision. Source: FRED.";
        }
        if (rows.isEmpty() && note == null) {
            note = "Figures for this release aren't collected yet.";
        }
        String summary = rows.isEmpty() ? (importance.equals("high") ? "High-importance release." : "Release.") : null;
        return new FeedItem("macro:" + key, "macro", label, at, timeKnown, headline, summary, null,
                "Source: " + (title.startsWith("FOMC") ? "Federal Reserve" : "BLS / FRED") + " · " + title,
                List.of(), null, List.of(), new Macro(title, importance, rows, verdict, tone, note), null);
    }

    private static String shortName(String title) {
        if (title.startsWith("Consumer Price Index")) return "CPI";
        if (title.startsWith("Producer Price Index")) return "PPI";
        if (title.startsWith("Employment Situation")) return "JOBS";
        if (title.startsWith("FOMC")) return "FOMC";
        if (title.startsWith("Gross Domestic Product")) return "GDP";
        if (title.startsWith("Personal Income")) return "PCE";
        if (title.startsWith("Advance Monthly Sales")) return "RETAIL SALES";
        return title.toUpperCase(Locale.ROOT);
    }

    private MacroRow cpiRow(String label, String series, String measure, LocalDate period, LocalDate releaseDay) {
        Double actual = pctChange("bls", series, period);
        if (actual == null) return null;
        Double prior = pctChange("bls", series, period.minusMonths(1));
        Double forecast = jdbc.sql("""
                        SELECT value FROM inflation_nowcasts
                        WHERE horizon = 'mom' AND measure = :m AND target_period = :p AND vintage < :d
                        ORDER BY vintage DESC LIMIT 1""")
                .param("m", measure).param("p", period.format(DateTimeFormatter.ofPattern("yyyy-MM"))).param("d", releaseDay)
                .query(Double.class).optional().orElse(null);
        Double surprise = forecast == null ? null : round(actual - forecast, 2);
        return new MacroRow(label, "%", forecast == null ? null : round(forecast, 2), round(actual, 2),
                prior == null ? null : round(prior, 2), surprise);
    }

    private Double value(String source, String series, LocalDate period) {
        return jdbc.sql("SELECT value FROM macro_observations WHERE source = :s AND series_id = :id AND period = :p")
                .param("s", source).param("id", series).param("p", period)
                .query(BigDecimal.class).optional().map(BigDecimal::doubleValue).orElse(null);
    }

    private Double change(String source, String series, LocalDate period) {
        Double now = value(source, series, period);
        Double prev = value(source, series, period.minusMonths(1));
        return now == null || prev == null ? null : round(now - prev, 0);
    }

    private Double pctChange(String source, String series, LocalDate period) {
        Double now = value(source, series, period);
        Double prev = value(source, series, period.minusMonths(1));
        return now == null || prev == null || prev == 0 ? null : (now / prev - 1) * 100;
    }

    /** A daily series' value on or after (or on or before) a date. */
    private Double dailyValue(String series, LocalDate day, boolean onOrAfter) {
        String sql = onOrAfter
                ? "SELECT value FROM macro_observations WHERE source='fred' AND series_id=:id AND period >= :d AND value IS NOT NULL ORDER BY period LIMIT 1"
                : "SELECT value FROM macro_observations WHERE source='fred' AND series_id=:id AND period <= :d AND value IS NOT NULL ORDER BY period DESC LIMIT 1";
        return jdbc.sql(sql).param("id", series).param("d", day)
                .query(BigDecimal.class).optional().map(BigDecimal::doubleValue).orElse(null);
    }

    private static Double round(double v, int digits) {
        double f = Math.pow(10, digits);
        return Math.round(v * f) / f;
    }

    private static String etDateTime(Instant at) {
        return at == null ? "" : at.atZone(NY).format(DateTimeFormatter.ofPattern("MMM d, h:mm a 'ET'", Locale.US));
    }
}
