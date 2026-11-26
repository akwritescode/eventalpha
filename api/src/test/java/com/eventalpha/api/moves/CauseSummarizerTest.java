package com.eventalpha.api.moves;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class CauseSummarizerTest {

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
