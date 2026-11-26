package com.eventalpha.api.moves;

import com.eventalpha.api.moves.JevClient.Direction;
import java.time.Duration;
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
 * without Claude the reason falls back to the article's title. Verdicts are cached in Redis per
 * article version and direction, so repeated requests don't call either model again.
 */
@Component
public class MoveCauses {

    private static final Logger log = LoggerFactory.getLogger(MoveCauses.class);

    static final double THRESHOLD = 0.6;
    static final int MAX_CANDIDATES = 3;
    private static final int MAX_CHARS = 6000;
    private static final Duration CACHE_TTL = Duration.ofDays(14);
    private static final String SEPARATOR = "\u001f";

    public record Candidate(String evidenceId, String title, String body, String contentHash) {}

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
    public List<Cause> judge(String ticker, Direction direction, List<Candidate> candidates) {
        if (!jev.available() || candidates.isEmpty()) return List.of();
        try (var pool = Executors.newVirtualThreadPerTaskExecutor()) {
            var futures = candidates.stream().limit(MAX_CANDIDATES)
                    .map(c -> pool.submit(() -> judgeOne(ticker, direction, c))).toList();
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

    private Cause judgeOne(String ticker, Direction direction, Candidate c) {
        String key = "eventalpha:move-cause:v1:" + c.evidenceId() + ":" + c.contentHash() + ":" + direction;
        String cached = cacheGet(key);
        double p;
        String reason;
        if (cached != null) {
            var parts = cached.split(SEPARATOR, 2);
            p = Double.parseDouble(parts[0]);
            reason = parts.length > 1 ? parts[1] : "";
        } else {
            String text = text(c);
            var judged = jev.explainsMove(text, direction);
            if (judged.isEmpty()) return null; // not cached: try again next time
            p = judged.getAsDouble();
            reason = p >= THRESHOLD ? summarizer.reason(ticker, move(direction), text).orElse("") : "";
            cachePut(key, p + SEPARATOR + reason);
        }
        if (p < THRESHOLD) return null;
        return new Cause(c.evidenceId(), c.title(), reason.isBlank() ? "the cause reported in “" + c.title() + "”" : reason, p);
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
