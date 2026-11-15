package com.eventalpha.api.articles;

import java.time.Instant;
import java.util.List;
import java.util.Map;

public record ArticleView(
        long id,
        String source,
        String formType,
        String title,
        String url,
        String company,
        List<String> tickers,
        List<String> secItems,
        Instant publishedAt,
        Score score) {

    /** Null when the article hasn't been classified yet. */
    public record Score(
            String sentiment,
            double sentimentScore,
            double materiality,
            double companySpecific,
            Map<String, Double> events,
            Instant scoredAt) {}
}
