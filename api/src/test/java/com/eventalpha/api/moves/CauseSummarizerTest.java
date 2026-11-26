package com.eventalpha.api.moves;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class CauseSummarizerTest {

    @Test
    void onlyKeepsReasonsWithAnExcerptInTheArticle() {
        var reason = new CauseSummarizer.CauseReason("the tariff delay", "Tariffs were delayed.");
        assertThat(CauseSummarizer.supportedReason(reason, "Chip stocks rose. Tariffs were delayed."))
                .contains("the tariff delay");
        assertThat(CauseSummarizer.supportedReason(reason, "Chip stocks rose.")).isEmpty();
    }

    @Test
    void matchesAcrossWhitespaceAndTypographicQuoteDifferences() {
        var reason = new CauseSummarizer.CauseReason("the tariff delay", "The agency's statement said \"tariffs were delayed.\"");
        assertThat(CauseSummarizer.supportedReason(reason, "The agency’s statement\n said “tariffs\u00a0were delayed.”"))
                .contains("the tariff delay");
        assertThat(CauseSummarizer.supportedReason(reason, "The agency’s statement said “tariffs were cancelled.”"))
                .isEmpty();
        assertThat(CauseSummarizer.supportedReason(new CauseSummarizer.CauseReason("the tariff delay", "\u00a0"),
                "Chip stocks rose.")).isEmpty();
    }

    @Test
    void buildsAStructuredRequestWithTheArticleAsData() {
        // build() validates CauseReason's derived JSON schema against what structured outputs accept.
        var params = CauseSummarizer.params("claude-haiku-5-5", "SPY", "rose", "Chip stocks rally. Tariffs delayed.").rawParams();
        String user = params.messages().getFirst().content().asString();
        assertThat(user).isEqualTo("Move: SPY rose\n<article>Chip stocks rally. Tariffs delayed.</article>");
        assertThat(params.outputConfig()).isPresent();
        assertThat(new CauseSummarizer("", "claude-haiku-5-5").available()).isFalse();
    }
}
