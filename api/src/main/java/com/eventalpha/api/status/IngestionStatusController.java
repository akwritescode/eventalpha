package com.eventalpha.api.status;

import com.eventalpha.api.common.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** Pipeline coverage from the sec_filings ledger: what landed per day and family, and what failed. */
@RestController
@RequestMapping("/api/v1/status")
class IngestionStatusController {

    private final JdbcClient jdbc;

    IngestionStatusController(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    record FamilyDay(LocalDate dateFiled, String family, int loaded, int skipped, int failed, long rows,
                     Instant lastProcessedAt) {}

    @Operation(summary = "SEC filings processed per filing date and family")
    @GetMapping("/sec")
    ApiResponse<List<FamilyDay>> sec(@RequestParam(defaultValue = "14") @Min(1) @Max(400) int days) {
        var rows = jdbc.sql("""
                        SELECT date_filed, family,
                               count(*) FILTER (WHERE status = 'loaded')  AS loaded,
                               count(*) FILTER (WHERE status = 'skipped') AS skipped,
                               count(*) FILTER (WHERE status = 'failed')  AS failed,
                               sum(rows)                                  AS rows,
                               max(processed_at)                          AS last_processed_at
                        FROM sec_filings
                        WHERE date_filed >= current_date - :days
                        GROUP BY 1, 2
                        ORDER BY 1 DESC, 2
                        """)
                .param("days", days)
                .query(FamilyDay.class)
                .list();
        Instant asOf = rows.stream().map(FamilyDay::lastProcessedAt).max(Instant::compareTo).orElse(null);
        return ApiResponse.of(rows, asOf);
    }
}
