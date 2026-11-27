package com.eventalpha.api.moves;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.mock.web.MockHttpServletRequest;

class LiveMoveWebEvalTest {

    private record Window(String ticker, String start, String end, String returnPercent, String lookbackFloor) {}

    @Test
    @EnabledIfEnvironmentVariable(named = "EVENTALPHA_RUN_LIVE_WEB_EVAL", matches = "1")
    void reportsCitationAndPublicationTimeCoverageThroughTheProductionSearchFlow() {
        String apiKey = System.getenv().getOrDefault("ANTHROPIC_API_KEY", "");
        assertThat(apiKey).as("Anthropic API key").isNotBlank();
        String model = System.getenv().getOrDefault("EVENTALPHA_ASK_MODEL", "claude-haiku-5-5");
        var windows = List.of(
                new Window("TSLA", "2026-11-25T16:00:00-05:00", "2026-11-26T11:30:00-05:00", null, null),
                new Window("SPY", "2026-11-25T12:00:00-05:00", "2026-11-25T14:00:00-05:00", "2.1026", "2026-11-20T00:00:00-05:00"),
                new Window("NVDA", "2026-11-23T09:30:00-05:00", "2026-11-23T16:00:00-05:00", "31.2996", "2026-11-18T00:00:00-05:00"));
        var rawAnswers = new ArrayList<WebMoveSearch.WebAnswer>();
        var displayedAnswers = new ArrayList<WebMoveSearch.WebAnswer>();
        var web = spy(new WebMoveSearch(apiKey, model, mock(StringRedisTemplate.class)));
        doAnswer(call -> {
            var answer = (WebMoveSearch.WebAnswer) call.callRealMethod();
            rawAnswers.add(answer);
            String prompt = call.getArgument(1);
            System.out.printf("Provider %s: cited=%s, supported time=%s, sources=%s%n",
                    prompt, answer.answer() != null, answer.publishedAt(), answer.sources());
            return answer;
        }).when(web).search(anyString(), anyString());

        for (var window : windows) {
            var start = OffsetDateTime.parse(window.start());
            var end = OffsetDateTime.parse(window.end());
            var repo = mock(MoveRepository.class);
            if (window.returnPercent() != null) {
                var move = new MoveRepository.PriceMove(window.ticker(), null, null,
                        new BigDecimal(window.returnPercent()), start.toInstant(), end.toInstant(), end.toInstant());
                when(repo.windowMove(anyString(), any(), any(), any())).thenReturn(Optional.of(move));
                when(repo.canLookBack(anyString(), any(), any(), any(), any())).thenReturn(true);
                when(repo.lookbackFloor(start.toInstant())).thenReturn(OffsetDateTime.parse(window.lookbackFloor()).toInstant());
            }
            var controller = new MoveController(repo, web, 1);
            var response = controller.webSearch(window.ticker(), start, end, false, new MockHttpServletRequest());
            assertThat(response.getStatusCode()).as("provider response for %s", window.ticker()).isEqualTo(HttpStatus.OK);
            var displayed = response.getBody().data();
            displayedAnswers.add(displayed);
            System.out.printf("Displayed %s: published=%s, cause=%s%n", window.ticker(), displayed.publishedAt(), displayed.answer());
        }
        System.out.printf("Model %s, %d windows and %d uncached provider calls. Cited provider answers: %d, supported times: %d. "
                        + "Displayed answers: %d, supported times: %d.%n", model, windows.size(), rawAnswers.size(),
                rawAnswers.stream().filter(a -> a.answer() != null).count(),
                rawAnswers.stream().filter(a -> a.publishedAt() != null).count(),
                displayedAnswers.stream().filter(a -> a.answer() != null).count(),
                displayedAnswers.stream().filter(a -> a.publishedAt() != null).count());
    }
}
