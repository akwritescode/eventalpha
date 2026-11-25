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

    /** Longest move window: enough for a week or two around a weekend. */
    static final Duration MAX_WINDOW = Duration.ofDays(14);

    private final MoveRepository repo;

    MoveController(MoveRepository repo) {
        this.repo = repo;
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
        if (!windowEnd.isAfter(windowStart) || Duration.between(windowStart, windowEnd).compareTo(MAX_WINDOW) > 0) {
            throw new IllegalArgumentException("The move window must have a positive duration of at most "
                    + MAX_WINDOW.toDays() + " days.");
        }
        Instant now = Instant.now();
        Instant cutoff = asOf == null ? now : asOf.toInstant();
        if (cutoff.isAfter(now)) {
            throw new IllegalArgumentException("The as-of cutoff must be in the past or present.");
        }
        return repo.explain(ticker.toUpperCase(Locale.ROOT), windowStart, windowEnd, cutoff);
    }
}
