package com.eventalpha.api.moves;

import com.fasterxml.jackson.annotation.JsonPropertyDescription;
import java.time.ZonedDateTime;

/** Turns a free-text question about a stock move into structured search parameters. */
public interface MoveQuestionParser {

    /** False when no model is configured (no API key): only bare tickers are understood then. */
    boolean available();

    /** @throws ParserException when the model can't be reached or gives no usable answer. */
    ParsedQuestion parse(String question, ZonedDateTime nowInNewYork);

    enum WindowKind { NONE, LAST_MINUTES, TODAY, SINCE_YESTERDAY_CLOSE, SINCE_YESTERDAY_OPEN, RANGE, PREVIOUS }

    /** The model's structured answer. Every field is required by the schema; "absent" is empty or 0. */
    record ParsedQuestion(
            @JsonPropertyDescription("False if the message is not asking about a stock or its price move.")
            boolean aboutStockMove,
            @JsonPropertyDescription("Ticker symbol or company name exactly as the user refers to it, e.g. \"NVDA\" or \"Nvidia\". Empty if none.")
            String company,
            @JsonPropertyDescription("Which time window the user asks about.")
            WindowKind window,
            @JsonPropertyDescription("Window length in minutes when window is LAST_MINUTES, otherwise 0.")
            int minutes,
            @JsonPropertyDescription("Window start for RANGE as ISO-8601 with offset, e.g. 2026-11-23T14:00:00-05:00. Empty otherwise.")
            String rangeStart,
            @JsonPropertyDescription("Window end for RANGE as ISO-8601 with offset. Empty otherwise.")
            String rangeEnd,
            @JsonPropertyDescription("True if the user wants only what was known by the end of the window, without hindsight.")
            boolean replay) {}

    class ParserException extends RuntimeException {
        public ParserException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
