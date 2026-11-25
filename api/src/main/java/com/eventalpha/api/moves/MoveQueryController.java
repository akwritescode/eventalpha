package com.eventalpha.api.moves;

import com.eventalpha.api.common.ApiResponse;
import com.eventalpha.api.common.RateLimiter;
import com.eventalpha.api.moves.MoveQuestionParser.ParsedQuestion;
import com.eventalpha.api.moves.MoveQuestionParser.ParserException;
import com.eventalpha.api.moves.MoveQuestionParser.WindowKind;
import com.eventalpha.api.tickers.TickerRepository;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.servlet.http.HttpServletRequest;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeParseException;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/**
 * Resolves a chat question into a ticker and a concrete move window. The model only proposes
 * fields; the ticker must exist in ticker_universe and the window is validated here, so the
 * result can go straight to /tickers/{ticker}/move-explanation. A bare ticker skips the model.
 */
@RestController
class MoveQueryController {

    private static final ZoneId NEW_YORK = ZoneId.of("America/New_York");
    private static final Pattern BARE_TICKER = Pattern.compile("\\$?([A-Za-z][A-Za-z.\\-]{0,9})");
    private static final Pattern TICKER = Pattern.compile("[A-Za-z.\\-]{1,10}");
    private static final int MAX_QUESTION = 300;
    private static final int MAX_OPTIONS = 5;
    private static final Duration MAX_WINDOW = MoveController.MAX_WINDOW;
    static final String TRY = "Try “Why did NVDA move in the last hour?” or just type a ticker.";

    private final MoveQuestionParser parser;
    private final TickerRepository tickers;
    private final MoveRepository moves;
    private final RateLimiter limiter;

    MoveQueryController(MoveQuestionParser parser, TickerRepository tickers, MoveRepository moves,
                        @Value("${eventalpha.ask.requests-per-minute:10}") int perMinute) {
        this.parser = parser;
        this.tickers = tickers;
        this.moves = moves;
        this.limiter = new RateLimiter(perMinute, 60_000, Clock.systemUTC());
    }

    /** contextTicker/contextStart/contextEnd: what the chat currently shows, for follow-ups. */
    record MoveQueryRequest(String question, String contextTicker, Instant contextStart, Instant contextEnd) {}

    record TickerOption(String ticker, String name) {}

    /**
     * ticker + start/end: ready for move-explanation. ticker without start: ask for a time frame.
     * tickerOptions: ask which one. message: what to tell the user.
     */
    record MoveQuery(String ticker, String tickerName, List<TickerOption> tickerOptions,
                     Instant start, Instant end, boolean replay, String message) {}

    @Operation(summary = "Turn a question such as \"Why did NVDA drop in the last hour?\" into a ticker and move window")
    @PostMapping("/api/v1/move-query")
    ApiResponse<MoveQuery> query(@RequestBody MoveQueryRequest request, HttpServletRequest http) {
        String question = request.question() == null ? "" : request.question().strip();
        if (question.isEmpty() || question.length() > MAX_QUESTION) {
            throw new IllegalArgumentException("Ask a question of 1 to " + MAX_QUESTION + " characters.");
        }
        String contextTicker = request.contextTicker();
        if (contextTicker != null && !TICKER.matcher(contextTicker).matches()) {
            throw new IllegalArgumentException("contextTicker must be a ticker symbol.");
        }
        Instant now = Instant.now();

        var bare = BARE_TICKER.matcher(question);
        if (bare.matches()) {
            var exact = exactTicker(bare.group(1));
            if (exact != null) {
                return ApiResponse.of(new MoveQuery(exact.ticker(), exact.name(), List.of(), null, null, false,
                        "Which time frame for " + exact.ticker() + "?"), now);
            }
        }
        if (!parser.available()) {
            throw new ParserUnavailable();
        }
        long retryAfter = limiter.acquire(http.getRemoteAddr());
        if (retryAfter > 0) {
            throw new TooManyQuestions(retryAfter);
        }

        ParsedQuestion parsed = parser.parse(question, now.atZone(NEW_YORK));
        if (!parsed.aboutStockMove()) {
            return ApiResponse.of(message("I can explain recent stock moves. " + TRY), now);
        }

        // Ticker: the one named in the question, else the one already on screen.
        String company = parsed.company() == null ? "" : parsed.company().strip().replaceFirst("^\\$", "");
        String ticker;
        String tickerName = null;
        if (company.isEmpty()) {
            if (contextTicker == null) {
                return ApiResponse.of(message("Which stock? " + TRY), now);
            }
            ticker = contextTicker.toUpperCase(Locale.ROOT);
        } else {
            var matches = tickers.search(company.toUpperCase(Locale.ROOT));
            var exact = matches.stream().filter(m -> m.ticker().equalsIgnoreCase(company)).findFirst();
            if (exact.isPresent() || matches.size() == 1) {
                var match = exact.orElse(matches.getFirst());
                ticker = match.ticker();
                tickerName = match.name();
            } else if (matches.isEmpty()) {
                return ApiResponse.of(message("I couldn’t find “" + company
                        + "” among the stocks EventAlpha tracks. Try its ticker symbol."), now);
            } else {
                var options = matches.stream().limit(MAX_OPTIONS)
                        .map(m -> new TickerOption(m.ticker(), m.name())).toList();
                return ApiResponse.of(new MoveQuery(null, null, options, null, null, parsed.replay(),
                        "Which one did you mean?"), now);
            }
        }

        // Window.
        WindowKind kind = parsed.window() == null ? WindowKind.NONE : parsed.window();
        if (kind == WindowKind.NONE && parsed.replay()) {
            kind = WindowKind.PREVIOUS;
        }
        Instant start = null;
        Instant end = null;
        String note = null;
        switch (kind) {
            case LAST_MINUTES -> {
                if (parsed.minutes() < 1 || parsed.minutes() > MAX_WINDOW.toMinutes()) {
                    note = "Choose a window from 1 minute to " + MAX_WINDOW.toDays() + " days.";
                } else {
                    end = now.truncatedTo(ChronoUnit.MINUTES);
                    start = end.minus(Duration.ofMinutes(parsed.minutes()));
                }
            }
            case TODAY, SINCE_YESTERDAY_CLOSE, SINCE_YESTERDAY_OPEN -> {
                var session = kind == WindowKind.TODAY ? moves.today(now)
                        : moves.sinceYesterday(now, kind == WindowKind.SINCE_YESTERDAY_OPEN ? "open" : "close");
                start = session.start();
                end = session.end();
                note = session.message();
            }
            case RANGE -> {
                try {
                    start = OffsetDateTime.parse(parsed.rangeStart()).toInstant();
                    end = OffsetDateTime.parse(parsed.rangeEnd()).toInstant();
                    note = rangeProblem(start, end, now);
                } catch (DateTimeParseException | NullPointerException e) {
                    note = "I couldn’t work out that time window.";
                }
            }
            case PREVIOUS -> {
                if (request.contextStart() != null && request.contextEnd() != null) {
                    start = request.contextStart();
                    end = request.contextEnd();
                    note = rangeProblem(start, end, now);
                } else {
                    note = "Ask about a move first, then replay that window.";
                }
            }
            case NONE -> { }
        }
        if (note != null) {
            start = null;
            end = null;
        }
        String reply = note != null ? note + " Pick a time frame for " + ticker + "."
                : start == null ? "Which time frame for " + ticker + "?" : null;
        return ApiResponse.of(new MoveQuery(ticker, tickerName, List.of(), start, end, parsed.replay(), reply), now);
    }

    private TickerRepository.TickerMatch exactTicker(String symbol) {
        return tickers.search(symbol.toUpperCase(Locale.ROOT)).stream()
                .filter(m -> m.ticker().equalsIgnoreCase(symbol)).findFirst().orElse(null);
    }

    private static MoveQuery message(String text) {
        return new MoveQuery(null, null, List.of(), null, null, false, text);
    }

    private static String rangeProblem(Instant start, Instant end, Instant now) {
        if (!end.isAfter(start) || Duration.between(start, end).compareTo(MAX_WINDOW) > 0) {
            return "That window must be up to " + MAX_WINDOW.toDays() + " days long.";
        }
        if (end.isAfter(now)) {
            return "That window hasn’t ended yet.";
        }
        return null;
    }

    static class ParserUnavailable extends RuntimeException {}

    static class TooManyQuestions extends RuntimeException {
        final long retryAfter;

        TooManyQuestions(long retryAfter) {
            this.retryAfter = retryAfter;
        }
    }

    @ExceptionHandler(ParserUnavailable.class)
    ProblemDetail unavailable() {
        var problem = ProblemDetail.forStatusAndDetail(HttpStatus.SERVICE_UNAVAILABLE,
                "Free-text questions are not set up on this server. Type a ticker symbol instead.");
        problem.setTitle("Questions unavailable");
        return problem;
    }

    @ExceptionHandler(ParserException.class)
    ProblemDetail parserFailed() {
        var problem = ProblemDetail.forStatusAndDetail(HttpStatus.BAD_GATEWAY,
                "I couldn’t understand that just now. Try again, or type a ticker symbol.");
        problem.setTitle("Question not understood");
        return problem;
    }

    @ExceptionHandler(TooManyQuestions.class)
    ResponseEntity<ProblemDetail> tooMany(TooManyQuestions e) {
        var problem = ProblemDetail.forStatusAndDetail(HttpStatus.TOO_MANY_REQUESTS,
                "Too many questions. Retry in " + e.retryAfter + " s, or type a ticker symbol.");
        problem.setTitle("Too many requests");
        return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                .header("Retry-After", Long.toString(e.retryAfter)).body(problem);
    }
}
