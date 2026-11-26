package com.eventalpha.api.moves;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.web.MockHttpServletRequest;

class MoveControllerTest {

    private static final OffsetDateTime START = OffsetDateTime.parse("2025-04-15T10:00:00-04:00");
    private static final OffsetDateTime END = START.plusHours(1);
    private final WebMoveSearch web = mock(WebMoveSearch.class);
    private final MoveController controller = new MoveController(mock(MoveRepository.class), web, 1);
    private final MockHttpServletRequest request = new MockHttpServletRequest();

    @Test
    void cachedAnswersBypassThePerIpLimit() {
        var cached = new WebMoveSearch.WebAnswer("Reports attributed the move to the announcement.",
                List.of(new WebMoveSearch.Source("Report", "https://example.com/report")), true);
        when(web.available()).thenReturn(true);
        when(web.search(anyString(), anyString())).thenReturn(WebMoveSearch.WebAnswer.none(true));
        when(web.cachedAnswer(anyString(), anyString()))
                .thenReturn(Optional.of(cached), Optional.empty(), Optional.empty(), Optional.of(cached));

        assertThat(controller.webSearch("SPY", START, END, request).getBody().data()).isEqualTo(cached);
        assertThat(controller.webSearch("SPY", START, END, request).getStatusCode()).isEqualTo(HttpStatus.OK);
        var limited = controller.webSearch("SPY", START, END, request);
        assertThat(limited.getStatusCode()).isEqualTo(HttpStatus.TOO_MANY_REQUESTS);
        assertThat(Long.parseLong(limited.getHeaders().getFirst("Retry-After"))).isPositive();
        assertThat(controller.webSearch("SPY", START, END, request).getBody().data()).isEqualTo(cached);
        verify(web, times(1)).search(anyString(), anyString());
    }

    @Test
    void providerFailureIsDistinctFromDisabledSearch() {
        var disabled = controller.webSearch("SPY", START, END, request);
        assertThat(disabled.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(disabled.getBody().data().available()).isFalse();

        when(web.available()).thenReturn(true);
        when(web.search(anyString(), anyString())).thenReturn(WebMoveSearch.WebAnswer.none(false));
        assertThat(controller.webSearch("SPY", START, END, request).getStatusCode())
                .isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
    }
}
