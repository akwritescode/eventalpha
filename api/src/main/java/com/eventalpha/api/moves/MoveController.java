package com.eventalpha.api.moves;

import com.eventalpha.api.common.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.constraints.Pattern;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.Locale;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class MoveController {

    private static final java.time.format.DateTimeFormatter WHEN =
            java.time.format.DateTimeFormatter.ofPattern("h:mm a", java.util.Locale.US).withZone(java.time.ZoneId.of("America/New_York"));
    private static final java.time.format.DateTimeFormatter DAY =
            java.time.format.DateTimeFormatter.ofPattern("EEEE, MMM d, yyyy", java.util.Locale.US)
                    .withZone(java.time.ZoneId.of("America/New_York"));

    /** Longest move window: enough for a week or two around a weekend. */
    static final Duration MAX_WINDOW = Duration.ofDays(14);

    private final MoveRepository repo;
    private final WebMoveSearch web;
    private final com.eventalpha.api.common.RateLimiter webLimiter;

    MoveController(MoveRepository repo, WebMoveSearch web,
                   @org.springframework.beans.factory.annotation.Value("${eventalpha.ask.web-searches-per-minute:5}") int perMinute) {
        this.repo = repo;
        this.web = web;
        this.webLimiter = new com.eventalpha.api.common.RateLimiter(perMinute, 60_000, java.time.Clock.systemUTC());
    }

    @Operation(summary = "News coverage of a move from a web search, for windows EventAlpha's own sources don't explain")
    @GetMapping("/api/v1/tickers/{ticker}/move-web-search")
    org.springframework.http.ResponseEntity<ApiResponse<WebMoveSearch.WebAnswer>> webSearch(
            @PathVariable @Pattern(regexp = "[A-Za-z.\\-]{1,10}") String ticker,
            @RequestParam OffsetDateTime start,
            @RequestParam OffsetDateTime end,
            jakarta.servlet.http.HttpServletRequest http) {
        Instant windowStart = start.toInstant();
        Instant windowEnd = end.toInstant();
        Instant now = Instant.now();
        checkWindow(windowStart, windowEnd);
        if (windowEnd.isAfter(now)) {
            throw new IllegalArgumentException("Web search covers windows that have already ended.");
        }
        if (!web.available()) {
            return org.springframework.http.ResponseEntity.ok(ApiResponse.of(WebMoveSearch.WebAnswer.none(false), now));
        }
        long retryAfter = webLimiter.acquire(http.getRemoteAddr());
        if (retryAfter > 0) {
            return org.springframework.http.ResponseEntity.status(429).header("Retry-After", Long.toString(retryAfter))
                    .body(ApiResponse.of(WebMoveSearch.WebAnswer.none(true), now));
        }
        String symbol = ticker.toUpperCase(Locale.ROOT);
        String moved = repo.windowMove(symbol, windowStart, windowEnd, now)
                .map(m -> m.returnPercent().signum() == 0 ? "was flat"
                        : (m.returnPercent().signum() > 0 ? "rose " : "fell ") + m.returnPercent().abs()
                                .setScale(1, java.math.RoundingMode.HALF_UP).toPlainString() + "%")
                .orElse("moved");
        String move = symbol + " " + moved + " between " + WHEN.format(windowStart) + " and " + WHEN.format(windowEnd)
                + " ET (window starting " + DAY.format(windowStart) + ", ending " + DAY.format(windowEnd) + ")";
        var key = symbol + ":" + windowStart.getEpochSecond() + ":" + windowEnd.getEpochSecond();
        return org.springframework.http.ResponseEntity.ok(ApiResponse.of(web.search(key, move), now));
    }

    private static void checkWindow(Instant windowStart, Instant windowEnd) {
        if (!windowEnd.isAfter(windowStart) || Duration.between(windowStart, windowEnd).compareTo(MAX_WINDOW) > 0) {
            throw new IllegalArgumentException("The move window must have a positive duration of at most "
                    + MAX_WINDOW.toDays() + " days.");
        }
    }

    @Operation(summary = "Today's regular-session window in New York using the exchange calendar")
    @GetMapping("/api/v1/move-window/today")
    ApiResponse<MoveRepository.SessionWindow> today() {
        var now = Instant.now();
        return ApiResponse.of(repo.today(now), now);
    }

    @Operation(summary = "Previous trading session's close (or open) through now, in New York")
    @GetMapping("/api/v1/move-window/since-yesterday")
    ApiResponse<MoveRepository.SessionWindow> sinceYesterday(
            @RequestParam(defaultValue = "close") @Pattern(regexp = "open|close") String anchor) {
        var now = Instant.now();
        return ApiResponse.of(repo.sinceYesterday(now, anchor), now);
    }

    @Operation(summary = "Evidence around an explicit move window, optionally replayed as of a cutoff")
    @GetMapping("/api/v1/tickers/{ticker}/move-explanation")
    ApiResponse<MoveRepository.Explanation> explain(
            @PathVariable @Pattern(regexp = "[A-Za-z.\\-]{1,10}") String ticker,
            @RequestParam OffsetDateTime start,
            @RequestParam OffsetDateTime end,
            @RequestParam(required = false) OffsetDateTime asOf) {
        Instant windowStart = start.toInstant();
        Instant windowEnd = end.toInstant();
        checkWindow(windowStart, windowEnd);
        Instant now = Instant.now();
        Instant cutoff = asOf == null ? now : asOf.toInstant();
        if (cutoff.isAfter(now)) {
            throw new IllegalArgumentException("The as-of cutoff must be in the past or present.");
        }
        return repo.explain(ticker.toUpperCase(Locale.ROOT), windowStart, windowEnd, cutoff);
    }
}
