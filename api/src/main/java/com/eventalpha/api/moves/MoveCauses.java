package com.eventalpha.api.moves;

import com.eventalpha.api.moves.JevClient.Direction;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.Executors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

/**
 * Decides which candidate articles explain a move: JEV judges title + body (not the title alone),
 * and only articles at or above {@link #THRESHOLD} count. For those, Claude writes the reason;
 * a candidate is promoted only when Claude extracts a reason. Verdicts are cached per article
 * version and move window.
 */
@Component
public class MoveCauses {

    private static final Logger log = LoggerFactory.getLogger(MoveCauses.class);

    static final double THRESHOLD = 0.6;
    static final int MAX_CANDIDATES = 3;
    private static final int MAX_CHARS = 6000;
    private static final Duration CACHE_TTL = Duration.ofDays(14);
    private static final String SEPARATOR = "\u001f";
    private static final DateTimeFormatter EASTERN = DateTimeFormatter.ISO_OFFSET_DATE_TIME
            .withZone(ZoneId.of("America/New_York"));

    public record Candidate(String evidenceId, String title, String body, String contentHash) {}

    public record MeasuredReturn(Instant start, Instant end, BigDecimal percent) {
        Direction direction() {
            return switch (percent.signum()) {
                case 1 -> Direction.UP;
                case -1 -> Direction.DOWN;
                default -> Direction.UNKNOWN;
            };
        }
    }

    /** An article judged to explain the move: JEV's probability and the reason to quote. */
    public record Cause(String evidenceId, String title, String reason, double probability) {}

    private final JevClient jev;
    private final CauseSummarizer summarizer;
    private final StringRedisTemplate redis;

    MoveCauses(JevClient jev, CauseSummarizer summarizer, StringRedisTemplate redis) {
        this.jev = jev;
        this.summarizer = summarizer;
        this.redis = redis;
    }

    boolean available() {
        return jev.available();
    }

    /** Causes found among the candidates, highest probability first. Never throws. */
    public List<Cause> judge(String ticker, Instant start, Instant end, MeasuredReturn measured, List<Candidate> candidates) {
        if (!jev.available() || candidates.isEmpty()) return List.of();
        Direction direction = measured == null ? Direction.UNKNOWN : measured.direction();
        // The measured return only sets the direction. Passing it to the models made JEV accept
        // same-size moves from other days and Claude drop causes of gap moves (evals/README.md).
        String windowMove = describeMove(start, end, direction, null);
        try (var pool = Executors.newVirtualThreadPerTaskExecutor()) {
            var futures = candidates.stream().limit(MAX_CANDIDATES)
                    .map(c -> pool.submit(() -> judgeOne(ticker, windowMove, direction, c))).toList();
            return futures.stream().map(f -> {
                        try {
                            return f.get();
                        } catch (Exception e) {
                            log.warn("Cause judgement failed: {}", e.getClass().getSimpleName());
                            return null;
                        }
                    }).filter(Objects::nonNull)
                    .sorted((a, b) -> Double.compare(b.probability(), a.probability())).toList();
        }
    }

    private Cause judgeOne(String ticker, String windowMove, Direction direction, Candidate c) {
        String key = "eventalpha:move-cause:v5:" + c.evidenceId() + ":" + c.contentHash() + ":" + ticker + " " + windowMove;
        String cached = cacheGet(key);
        double p;
        String reason;
        if (cached != null) {
            var parts = cached.split(SEPARATOR, 2);
            p = Double.parseDouble(parts[0]);
            reason = parts.length > 1 ? parts[1] : "";
        } else {
            String text = text(c);
            var judged = jev.explainsMove(judgeInput(ticker, windowMove, text), direction);
            if (judged.isEmpty()) return null; // not cached: try again next time
            p = judged.getAsDouble();
            if (!Double.isFinite(p) || p < 0 || p > 1) return null;
            reason = p >= THRESHOLD ? summarizer.reason(ticker, windowMove, text).orElse("") : "";
            if (p >= THRESHOLD && reason.isBlank()) return null;
            cachePut(key, p + SEPARATOR + reason);
        }
        if (p < THRESHOLD || reason.isBlank()) return null;
        return new Cause(c.evidenceId(), c.title(), reason, p);
    }

    static String judgeInput(String ticker, String windowMove, String article) {
        return "Target move: " + ticker + " " + windowMove + "\n\nArticle:\n" + article;
    }

    static String describeMove(Instant start, Instant end, Direction direction, MeasuredReturn measured) {
        String requested = move(direction) + " between " + EASTERN.format(start) + " and " + EASTERN.format(end)
                + " (Eastern time)";
        if (measured == null) return requested;
        String sign = measured.percent().signum() > 0 ? "+" : "";
        return requested + ". Measured return: " + sign + measured.percent().stripTrailingZeros().toPlainString()
                + "% from the candle closes at " + EASTERN.format(measured.start()) + " and "
                + EASTERN.format(measured.end()) + " (Eastern time)";
    }

    static String text(Candidate c) {
        String body = c.body() == null ? "" : c.body().strip();
        String text = c.title() + (body.isEmpty() ? "" : "\n\n" + body);
        return text.length() > MAX_CHARS ? text.substring(0, MAX_CHARS) : text;
    }

    private static String move(Direction direction) {
        return switch (direction) {
            case UP -> "rose";
            case DOWN -> "fell";
            case UNKNOWN -> "moved";
        };
    }

    private String cacheGet(String key) {
        try {
            return redis.opsForValue().get(key);
        } catch (RuntimeException e) {
            return null; // Redis down: judge without the cache
        }
    }

    private void cachePut(String key, String value) {
        try {
            redis.opsForValue().set(key, value, CACHE_TTL);
        } catch (RuntimeException e) {
            log.debug("Cause cache write failed: {}", e.getClass().getSimpleName());
        }
    }
}
