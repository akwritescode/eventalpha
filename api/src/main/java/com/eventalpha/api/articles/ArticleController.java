package com.eventalpha.api.articles;

import com.eventalpha.api.common.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1")
class ArticleController {

    private final ArticleRepository articles;

    ArticleController(ArticleRepository articles) {
        this.articles = articles;
    }

    @Operation(summary = "Recent articles and filings, newest first, with their latest classification score")
    @GetMapping("/articles")
    ApiResponse<List<ArticleView>> list(
            @RequestParam(required = false) @Pattern(regexp = "[A-Za-z.\\-]{1,10}") String ticker,
            @RequestParam(required = false) String source,
            @RequestParam(required = false) String formType,
            @RequestParam(defaultValue = "7") @Min(1) @Max(365) int days,
            @RequestParam(defaultValue = "50") @Min(1) @Max(500) int limit) {
        var q = new ArticleRepository.Query(ticker, source, formType, null, 0, since(days), limit);
        return ApiResponse.of(articles.find(q), articles.lastIngestedAt());
    }

    @Operation(summary = "Articles where the classifier flags an event type, e.g. guidance_lowered or m_and_a")
    @GetMapping("/events")
    ApiResponse<List<ArticleView>> events(
            @RequestParam @Pattern(regexp = "[a-z_]{2,40}") String type,
            @RequestParam(defaultValue = "0.7") @DecimalMin("0") @DecimalMax("1") double minProb,
            @RequestParam(required = false) @Pattern(regexp = "[A-Za-z.\\-]{1,10}") String ticker,
            @RequestParam(defaultValue = "7") @Min(1) @Max(365) int days,
            @RequestParam(defaultValue = "50") @Min(1) @Max(500) int limit) {
        var q = new ArticleRepository.Query(ticker, null, null, type, minProb, since(days), limit);
        return ApiResponse.of(articles.find(q), articles.lastIngestedAt());
    }

    private static Instant since(int days) {
        return Instant.now().minus(Duration.ofDays(days));
    }
}
