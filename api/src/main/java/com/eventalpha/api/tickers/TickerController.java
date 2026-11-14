package com.eventalpha.api.tickers;

import com.eventalpha.api.common.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;
import java.math.BigDecimal;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/tickers/{ticker}")
class TickerController {

    private final TickerRepository repo;

    TickerController(TickerRepository repo) {
        this.repo = repo;
    }

    @Operation(summary = "Daily sentiment for a ticker (US/Eastern days)")
    @GetMapping("/sentiment")
    ApiResponse<List<TickerRepository.SentimentDay>> sentiment(
            @PathVariable @Pattern(regexp = "[A-Za-z.\\-]{1,10}") String ticker,
            @RequestParam(defaultValue = "30") @Min(1) @Max(365) int days) {
        return ApiResponse.of(repo.sentimentByDay(ticker.toUpperCase(), days), repo.lastScoredAt());
    }

    record InsiderSummary(
            int trades,
            int openMarketBuys,
            int openMarketSells,
            BigDecimal netOpenMarketValue,
            List<TickerRepository.InsiderTrade> transactions) {}

    @Operation(summary = "Form 4 insider transactions; net value counts open-market buys (P) minus sells (S)")
    @GetMapping("/insider-trades")
    ApiResponse<InsiderSummary> insiderTrades(
            @PathVariable @Pattern(regexp = "[A-Za-z.\\-]{1,10}") String ticker,
            @RequestParam(defaultValue = "90") @Min(1) @Max(730) int days,
            @RequestParam(defaultValue = "false") boolean openMarketOnly) {
        var trades = repo.insiderTrades(ticker.toUpperCase(), days, openMarketOnly);
        BigDecimal net = BigDecimal.ZERO;
        int buys = 0;
        int sells = 0;
        for (var t : trades) {
            if (t.isDerivative() || t.shares() == null || t.price() == null) {
                continue;
            }
            switch (t.transactionCode()) {
                case "P" -> { buys++; net = net.add(t.shares().multiply(t.price())); }
                case "S" -> { sells++; net = net.subtract(t.shares().multiply(t.price())); }
                case null, default -> { }
            }
        }
        return ApiResponse.of(new InsiderSummary(trades.size(), buys, sells, net, trades), repo.lastInsiderFiling());
    }
}
