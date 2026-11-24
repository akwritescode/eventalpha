package com.eventalpha.api.moves;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.ZoneId;
import java.time.ZonedDateTime;
import org.junit.jupiter.api.Test;

class ClaudeMoveQuestionParserTest {

    private static final ZonedDateTime NOW = ZonedDateTime.of(2026, 11, 24, 10, 15, 0, 0, ZoneId.of("America/New_York"));

    @Test
    void buildsAStructuredRequestWithTheQuestionAsData() {
        // build() validates ParsedQuestion's derived JSON schema against what structured outputs accept.
        var params = ClaudeMoveQuestionParser.params("claude-haiku-5-5", "why did nvda drop?", NOW).rawParams();
        assertThat(params.model().asString()).isEqualTo("claude-haiku-5-5");
        String user = params.messages().getFirst().content().asString();
        assertThat(user).startsWith("Now: Tuesday 2026-11-24T10:15:00-05:00").endsWith("<question>why did nvda drop?</question>");
        assertThat(params.outputConfig()).isPresent();
    }

    @Test
    void isUnavailableWithoutAKey() {
        assertThat(new ClaudeMoveQuestionParser("", "claude-haiku-5-5").available()).isFalse();
        assertThat(new ClaudeMoveQuestionParser("test-key", "claude-haiku-5-5").available()).isTrue();
    }
}
