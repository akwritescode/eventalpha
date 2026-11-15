package com.eventalpha.api.feed;

import com.eventalpha.api.common.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1")
class FeedController {

    private static final Set<String> TYPES = Set.of("sec", "news", "macro", "signal");

    private final FeedRepository repo;

    FeedController(FeedRepository repo) {
        this.repo = repo;
    }

    @Operation(summary = "Market Intelligence Stream: SEC filings, news, released macro data and signals, newest first. "
            + "Page with `before` = the last item's occurredAt. `ticker` limits it to one company "
            + "(its filings and news, and signals it contributed to).")
    @GetMapping("/feed")
    ApiResponse<List<FeedItem>> feed(
            @RequestParam(defaultValue = "sec,news,macro,signal") String types,
            @RequestParam(defaultValue = "7") @Min(1) @Max(60) int days,
            @RequestParam(required = false) Instant before,
            @RequestParam(defaultValue = "100") @Min(1) @Max(300) int limit,
            @RequestParam(required = false) String ticker) {
        String symbol = ticker == null || ticker.isBlank() ? null : ticker.trim().toUpperCase();
        var wanted = Set.of(types.toLowerCase().split("\\s*,\\s*"));
        if (!TYPES.containsAll(wanted)) {
            throw new IllegalArgumentException("types must be a subset of " + TYPES);
        }
        Instant end = before != null ? before : Instant.now().plusSeconds(60);
        Instant since = end.minus(Duration.ofDays(days));

        List<FeedItem> items = new ArrayList<>();
        if (wanted.contains("sec") || wanted.contains("news")) {
            items.addAll(repo.articles(since, end, limit, wanted.contains("sec"), wanted.contains("news"), symbol));
        }
        // Macro releases aren't about one company, so a ticker view leaves them out.
        if (wanted.contains("macro") && symbol == null) items.addAll(repo.macro(since, end));
        if (wanted.contains("signal")) {
            repo.signals(since, end).stream().filter(s -> symbol == null || mentions(s, symbol)).forEach(items::add);
        }
        items.sort(Comparator.comparing(FeedItem::occurredAt).reversed());
        List<FeedItem> page = items.size() > limit ? items.subList(0, limit) : items;
        Instant asOf = page.isEmpty() ? null : page.getFirst().occurredAt();
        return ApiResponse.of(page, asOf);
    }

    /** A signal belongs to a ticker view when one of its contributing events names the ticker. */
    private static boolean mentions(FeedItem item, String ticker) {
        return item.tickers().contains(ticker) || (item.signal() != null && item.signal().contributors().stream()
                .anyMatch(c -> c.tickers() != null && c.tickers().contains(ticker)));
    }
}
