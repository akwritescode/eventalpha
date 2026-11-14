package com.eventalpha.api.stream;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;
import org.junit.jupiter.api.Test;

class TelegramRelayFormatTest {

    @Test
    void formatsAndEscapes() {
        String text = TelegramRelay.format(Map.of(
                "sentiment", "bearish", "sentiment_score", "-0.850", "materiality", "2.80",
                "tickers", "AAON", "form_type", "8-K", "title", "AAON <cuts> guidance",
                "events", "guidance_lowered,earnings_results", "url", "https://example.com/2"));
        assertThat(text).startsWith("🔴 <b>AAON</b> · 8-K")
                .contains("AAON &lt;cuts&gt; guidance")
                .contains("bearish (-0.850) · materiality 2.80")
                .contains("guidance_lowered, earnings_results")
                .endsWith("<a href=\"https://example.com/2\">source</a>");
    }
}
