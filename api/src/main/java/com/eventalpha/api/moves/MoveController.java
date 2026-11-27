package com.eventalpha.api.moves;

import com.eventalpha.api.common.ApiResponse;
import com.eventalpha.api.common.RateLimiter;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.constraints.Pattern;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class MoveController {

    private static final DateTimeFormatter WHEN =
            DateTimeFormatter.ofPattern("h:mm a", Locale.US).withZone(ZoneId.of("America/New_York"));
    private static final DateTimeFormatter DAY =
            DateTimeFormatter.ofPattern("EEEE, MMM d, yyyy", Locale.US)
                    .withZone(ZoneId.of("America/New_York"));

    /** Longest move window: enough for a week or two around a weekend. */
    static final Duration MAX_WINDOW = Duration.ofDays(14);

    private final MoveRepository repo;
    private final WebMoveSearch web;
    private final RateLimiter webLimiter;

    MoveController(MoveRepository repo, WebMoveSearch web,
                   @Value("${eventalpha.ask.web-searches-per-minute:5}") int perMinute) {
        this.repo = repo;
        this.web = web;
        this.webLimiter = new RateLimiter(perMinute, 60_000, Clock.systemUTC());
    }

    @Operation(summary = "News coverage of a move from a web search, for windows EventAlpha's own sources don't explain")
    @GetMapping("/api/v1/tickers/{ticker}/move-web-search")
    ResponseEntity<ApiResponse<WebMoveSearch.WebAnswer>> webSearch(
            @PathVariable @Pattern(regexp = "[A-Za-z.\\-]{1,10}") String ticker,
            @RequestParam OffsetDateTime start,
            @RequestParam OffsetDateTime end,
            @RequestParam(defaultValue = "false") boolean inWindowOnly,
            HttpServletRequest http) {
        Instant windowStart = start.toInstant();
        Instant windowEnd = end.toInstant();
        Instant now = Instant.now();
        checkWindow(windowStart, windowEnd);
        if (windowEnd.isAfter(now)) {
            throw new IllegalArgumentException("Web search covers windows that have already ended.");
        }
        if (!web.available()) {
            return ResponseEntity.ok(ApiResponse.of(WebMoveSearch.WebAnswer.none(false), now));
        }
        String symbol = ticker.toUpperCase(Locale.ROOT);
        var windowMove = repo.windowMove(symbol, windowStart, windowEnd, now);
        boolean material = repo.canLookBack(symbol, windowStart, windowEnd, now, windowMove);
        String moved = windowMove
                .map(m -> m.returnPercent().signum() == 0 ? "was flat"
                        : (m.returnPercent().signum() > 0 ? "rose " : "fell ") + m.returnPercent().abs()
                                .setScale(1, RoundingMode.HALF_UP).toPlainString() + "%")
                .orElse("has no measured price change available");
        String move = symbol + " " + moved + " between " + WHEN.format(windowStart) + " and " + WHEN.format(windowEnd)
                + " ET (window starting " + DAY.format(windowStart) + ", ending " + DAY.format(windowEnd) + ")";
        if (material && windowMove.filter(m -> m.returnPercent().abs().compareTo(BigDecimal.ONE) <= 0).isPresent()) {
            move += ". The price moved more than 1% from its starting price during the window"
                    + "; look for coverage of that intrawindow move";
        }
        String key = symbol + ":" + windowStart.getEpochSecond() + ":" + windowEnd.getEpochSecond();
        var inWindow = new PublicationRange(windowStart, windowEnd, false);
        var first = searchScope(key, move, inWindow, http, false);
        if (first.status() != HttpStatus.OK) return first.response(now);
        var answer = first.answer();
        if (!inWindowOnly && material && answer.answer() == null) {
            var earlier = new PublicationRange(repo.lookbackFloor(windowStart), windowStart, true);
            // The same request can make one follow-up lookup after it has cleared the limit.
            var fallback = searchScope(key, move, earlier, http, first.performed());
            if (fallback.status() != HttpStatus.OK) return fallback.response(now);
            answer = fallback.answer();
        }
        if (answer.publishedAt() != null) {
            answer = answer.withComparison(repo.returnsSince(symbol, answer.publishedAt(), windowEnd, now));
        }
        return ResponseEntity.ok(ApiResponse.of(answer, now));
    }

    private record PublicationRange(Instant start, Instant end, boolean beforeWindow) {
        String describe() {
            return " Publication range: " + start + " through " + end
                    + (beforeWindow ? " (end exclusive). Confirm an exact publication timestamp." : " (inclusive).");
        }

        boolean accepts(WebMoveSearch.WebAnswer answer) {
            if (answer.answer() == null) return true;
            var at = answer.publishedAt();
            if (at == null) return !beforeWindow;
            return !at.isBefore(start) && (beforeWindow ? at.isBefore(end) : !at.isAfter(end));
        }
    }

    private record SearchAttempt(WebMoveSearch.WebAnswer answer, HttpStatus status, boolean performed, long retryAfter) {
        ResponseEntity<ApiResponse<WebMoveSearch.WebAnswer>> response(Instant now) {
            var response = ResponseEntity.status(status);
            if (retryAfter > 0) response.header("Retry-After", Long.toString(retryAfter));
            return response.body(ApiResponse.of(answer, now));
        }
    }

    private SearchAttempt searchScope(String key, String move,
            PublicationRange range, HttpServletRequest request, boolean alreadyLimited) {
        String prompt = move + "." + range.describe();
        var cached = web.cachedAnswer(key, prompt);
        if (cached.isPresent()) return new SearchAttempt(accepted(cached.get(), range), HttpStatus.OK, false, 0);
        long retryAfter = alreadyLimited ? 0 : webLimiter.acquire(request.getRemoteAddr());
        if (retryAfter > 0) {
            return new SearchAttempt(WebMoveSearch.WebAnswer.none(true), HttpStatus.TOO_MANY_REQUESTS, false, retryAfter);
        }
        var answer = web.search(key, prompt);
        return new SearchAttempt(accepted(answer, range),
                answer.available() ? HttpStatus.OK : HttpStatus.SERVICE_UNAVAILABLE, true, 0);
    }

    private static WebMoveSearch.WebAnswer accepted(WebMoveSearch.WebAnswer answer, PublicationRange range) {
        return range.accepts(answer) ? answer : WebMoveSearch.WebAnswer.none(true);
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
