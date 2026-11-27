package com.eventalpha.api.moves;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.OffsetDateTime;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.web.MockHttpServletRequest;

class MoveControllerTest {

    private static final OffsetDateTime START = OffsetDateTime.parse("2025-04-15T10:00:00-04:00");
    private static final OffsetDateTime END = START.plusHours(1);
    private final WebMoveSearch web = mock(WebMoveSearch.class);
    private final MoveRepository repo = mock(MoveRepository.class);
    private final MoveController controller = new MoveController(repo, web, 1);
    private final MockHttpServletRequest request = new MockHttpServletRequest();

    @Test
    void cachedAnswersBypassThePerIpLimit() {
        var cached = new WebMoveSearch.WebAnswer("Reports attributed the move to the announcement.",
                List.of(new WebMoveSearch.Source("Report", "https://example.com/report")), true);
        when(web.available()).thenReturn(true);
        when(web.search(anyString(), anyString())).thenReturn(WebMoveSearch.WebAnswer.none(true));
        when(web.cachedAnswer(anyString(), anyString()))
                .thenReturn(Optional.of(cached), Optional.empty(), Optional.empty(), Optional.of(cached));

        assertThat(controller.webSearch("SPY", START, END, false, request).getBody().data()).isEqualTo(cached);
        assertThat(controller.webSearch("SPY", START, END, false, request).getStatusCode()).isEqualTo(HttpStatus.OK);
        var limited = controller.webSearch("SPY", START, END, false, request);
        assertThat(limited.getStatusCode()).isEqualTo(HttpStatus.TOO_MANY_REQUESTS);
        assertThat(Long.parseLong(limited.getHeaders().getFirst("Retry-After"))).isPositive();
        assertThat(controller.webSearch("SPY", START, END, false, request).getBody().data()).isEqualTo(cached);
        verify(web, times(1)).search(anyString(), anyString());
    }

    @Test
    void providerFailureIsDistinctFromDisabledSearch() {
        var disabled = controller.webSearch("SPY", START, END, false, request);
        assertThat(disabled.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(disabled.getBody().data().available()).isFalse();

        when(web.available()).thenReturn(true);
        when(web.search(anyString(), anyString())).thenReturn(WebMoveSearch.WebAnswer.none(false));
        assertThat(controller.webSearch("SPY", START, END, false, request).getStatusCode())
                .isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
    }

    @Test
    void expandsOnlyAfterAnEmptyInWindowSearchAndKeepsTheArticleAnchor() {
        Instant floor = START.minusDays(3).toInstant();
        Instant published = START.minusHours(2).toInstant();
        var report = new WebMoveSearch.WebAnswer("Coverage attributed the move to guidance.",
                List.of(new WebMoveSearch.Source("Report", "https://example.com/report")), true, published, null);
        var comparison = new MoveRepository.ReturnComparison(published, List.of());
        when(web.available()).thenReturn(true);
        when(repo.canLookBack(org.mockito.ArgumentMatchers.eq("TSLA"), org.mockito.ArgumentMatchers.eq(START.toInstant()),
                org.mockito.ArgumentMatchers.eq(END.toInstant()), org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.eq(Optional.empty()))).thenReturn(true);
        when(repo.lookbackFloor(START.toInstant())).thenReturn(floor);
        when(repo.returnsSince(org.mockito.ArgumentMatchers.eq("TSLA"), org.mockito.ArgumentMatchers.eq(published),
                org.mockito.ArgumentMatchers.eq(END.toInstant()), org.mockito.ArgumentMatchers.any())).thenReturn(comparison);
        when(web.search(anyString(), org.mockito.ArgumentMatchers.contains("(inclusive)")))
                .thenReturn(WebMoveSearch.WebAnswer.none(true));
        when(web.search(anyString(), org.mockito.ArgumentMatchers.contains("(end exclusive)"))).thenReturn(report);

        var result = controller.webSearch("TSLA", START, END, false, request).getBody().data();
        assertThat(result.comparison()).isEqualTo(comparison);
        var order = org.mockito.Mockito.inOrder(web);
        order.verify(web).search(anyString(), org.mockito.ArgumentMatchers.contains(START.toInstant() + " through " + END.toInstant()));
        order.verify(web).search(anyString(), org.mockito.ArgumentMatchers.contains(floor + " through " + START.toInstant()));
    }

    @Test
    void inWindowOnlyRejectsAnEarlierArticleAndDoesNotExpand() {
        when(web.available()).thenReturn(true);
        when(repo.canLookBack(org.mockito.ArgumentMatchers.eq("TSLA"), org.mockito.ArgumentMatchers.eq(START.toInstant()),
                org.mockito.ArgumentMatchers.eq(END.toInstant()), org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.eq(Optional.empty()))).thenReturn(true);
        when(web.search(anyString(), anyString())).thenReturn(new WebMoveSearch.WebAnswer("Earlier coverage.",
                List.of(new WebMoveSearch.Source("Report", "https://example.com/report")), true,
                START.minusSeconds(1).toInstant(), null));

        assertThat(controller.webSearch("TSLA", START, END, true, request).getBody().data().answer()).isNull();
        verify(web, times(1)).search(anyString(), org.mockito.ArgumentMatchers.contains("(inclusive)"));
    }
}
