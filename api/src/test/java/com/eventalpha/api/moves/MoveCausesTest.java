package com.eventalpha.api.moves;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.contains;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.eventalpha.api.moves.JevClient.Direction;
import com.eventalpha.api.moves.MoveCauses.Candidate;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.OptionalDouble;
import java.util.concurrent.ConcurrentHashMap;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

class MoveCausesTest {

    private final JevClient jev = mock(JevClient.class);
    private final CauseSummarizer summarizer = mock(CauseSummarizer.class);
    private final Map<String, String> cache = new ConcurrentHashMap<>();
    private MoveCauses causes;

    private static final Instant START = Instant.parse("2026-11-25T17:00:00Z");
    private static final Instant END = Instant.parse("2026-11-25T19:00:00Z");

    private static final Candidate RALLY = new Candidate("article:1", "Chip stocks rally at midday",
            "Shares rebounded after the Commerce Department delayed the chip tariffs.", "h1");

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setUp() {
        var redis = mock(StringRedisTemplate.class);
        ValueOperations<String, String> ops = mock(ValueOperations.class);
        when(redis.opsForValue()).thenReturn(ops);
        when(ops.get(anyString())).thenAnswer(i -> cache.get(i.<String>getArgument(0)));
        org.mockito.Mockito.doAnswer(i -> cache.put(i.getArgument(0), i.getArgument(1)))
                .when(ops).set(anyString(), anyString(), any(Duration.class));
        when(jev.available()).thenReturn(true);
        causes = new MoveCauses(jev, summarizer, redis);
    }

    @Test
    void titleAndBodyGoToJevAndOnlyAtLeastPointSixCounts() {
        when(jev.explainsMove(contains("delayed the chip tariffs"), any())).thenReturn(OptionalDouble.of(0.59));
        assertThat(causes.judge("SPY", START, END, Direction.UP, List.of(RALLY))).isEmpty();
        verify(summarizer, never()).reason(anyString(), anyString(), anyString());

        cache.clear();
        when(jev.explainsMove(anyString(), any())).thenReturn(OptionalDouble.of(0.6));
        when(summarizer.reason(anyString(), anyString(), anyString()))
                .thenReturn(Optional.of("the Commerce Department delaying the chip tariffs"));
        assertThat(causes.judge("SPY", START, END, Direction.UP, List.of(RALLY))).singleElement().satisfies(c -> {
            assertThat(c.reason()).isEqualTo("the Commerce Department delaying the chip tariffs");
            assertThat(c.probability()).isEqualTo(0.6);
        });
    }

    @Test
    void aPositiveScoreWithoutAnExtractedCauseAbstains() {
        when(jev.explainsMove(anyString(), any())).thenReturn(OptionalDouble.of(0.9));
        when(summarizer.reason(anyString(), anyString(), anyString())).thenReturn(Optional.empty());
        assertThat(causes.judge("SPY", START, END, Direction.UP, List.of(RALLY))).isEmpty();
        assertThat(cache).isEmpty();
    }

    @Test
    void verdictsAreCachedButFailuresAreRetried() {
        when(jev.explainsMove(anyString(), any())).thenReturn(OptionalDouble.empty());
        assertThat(causes.judge("SPY", START, END, Direction.UP, List.of(RALLY))).isEmpty();
        assertThat(cache).isEmpty();

        when(jev.explainsMove(anyString(), any())).thenReturn(OptionalDouble.of(0.8));
        when(summarizer.reason(anyString(), anyString(), anyString())).thenReturn(Optional.of("delayed tariffs"));
        causes.judge("SPY", START, END, Direction.UP, List.of(RALLY));
        causes.judge("SPY", START, END, Direction.UP, List.of(RALLY));
        verify(jev, org.mockito.Mockito.times(2)).explainsMove(anyString(), any()); // the failure + one real call
        causes.judge("NVDA", START, END, Direction.UP, List.of(RALLY));
        causes.judge("SPY", START.plusSeconds(60), END, Direction.UP, List.of(RALLY));
        assertThat(cache).hasSize(3);
    }

    @Test
    void jevQuestionNamesTheDirectionAndSaysWhatCountsAsNo() {
        var q = JevClient.question(Direction.DOWN);
        assertThat(q.get("type")).isEqualTo("noul");
        assertThat((String) q.get("instructions")).contains("price decline").contains("not just the size of the move");
        assertThat(q.get("criteria")).asString().contains("only reports that prices moved");
    }
}
