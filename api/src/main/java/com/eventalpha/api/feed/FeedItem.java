package com.eventalpha.api.feed;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * One card in the Market Intelligence Stream. `type` decides which optional block is set:
 * sec/news → classification fields, macro → {@link Macro}, signal → {@link Signal}.
 */
public record FeedItem(
        String id,
        String type, // sec | news | macro | signal
        String label, // "SEC · 8-K", "NEWS · PR NEWSWIRE", "MACRO · CPI", "TRADING SIGNAL"
        Instant occurredAt,
        boolean timeKnown, // false when only the date is known (some FRED release dates)
        String title,
        String summary,
        String url,
        String sourceLine,
        List<String> tickers,
        Classification classification,
        List<Fact> facts,
        Macro macro,
        Signal signal) {

    public record Classification(String sentiment, double score, Double confidence, double pBullish, double pBearish,
                                 double pNeutral, double materiality, double companySpecific,
                                 Map<String, Double> events) {}  // model identifiers stay internal

    /** A labelled fact extracted from the source (8-K items, form, company, filed time ...). */
    public record Fact(String label, String value) {}

    public record MacroRow(String label, String unit, Double forecast, Double actual, Double prior, Double surprise) {}

    public record Macro(String release, String importance, List<MacroRow> rows, String verdict, String verdictTone,
                        String note) {}

    public record Contributor(String title, String url, List<String> tickers, String sentiment, Double score) {}

    public record Signal(String signalType, Double score, Double confidence, List<Contributor> contributors,
                         int contributingEvents, Map<String, Object> components) {}
}
