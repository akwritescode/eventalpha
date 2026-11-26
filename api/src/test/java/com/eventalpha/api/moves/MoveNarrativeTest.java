package com.eventalpha.api.moves;

import static org.assertj.core.api.Assertions.assertThat;

import com.eventalpha.api.moves.MoveNarrative.Candle;
import com.eventalpha.api.moves.MoveNarrative.Input;
import com.eventalpha.api.moves.MoveNarrative.Release;
import com.eventalpha.api.moves.MoveRepository.Catalyst;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;

class MoveNarrativeTest {

    private static Instant et(String time) {
        return OffsetDateTime.parse(time + "-05:00").toInstant();
    }

    private static Candle c(String time, String close) {
        return new Candle(et(time), new BigDecimal(close));
    }

    private static Input input(String start, String end, List<Catalyst> catalysts, String startPrice, List<Candle> path,
                               List<Release> releases) {
        return new Input("SPY", et(start), et(end), catalysts, List.of(), new BigDecimal(startPrice), path, releases,
                null, false);
    }

    private static final Release CPI = new Release("CPI", et("2026-11-25T10:00:00"), true);

    @Test
    void aVerifiedCatalystWinsOverReleasesAndPricePath() {
        var text = MoveNarrative.summarize(input("2026-11-25T09:30:00", "2026-11-25T11:00:00",
                List.of(new Catalyst("Acme 8-K: CEO departs", "article:1")), "100",
                List.of(c("2026-11-25T10:59:00", "95")), List.of(CPI)));
        assertThat(text).isEqualTo("Plausible catalyst — Acme 8-K: CEO departs. The timing supports a possible link.");
    }

    @Test
    void aReleaseInsideTheWindowIsCalendarContext() {
        var text = MoveNarrative.summarize(input("2026-11-25T09:30:00", "2026-11-25T11:00:00", List.of(), "100",
                List.of(c("2026-11-25T09:45:00", "100.1"), c("2026-11-25T10:30:00", "101"), c("2026-11-25T10:59:00", "101.5")),
                List.of(CPI)));
        assertThat(text).isEqualTo("No verified catalyst found for this move. Economic calendar: the 10:00 AM CPI release.");
    }

    @Test
    void aRallyThatFadesAfterAReleaseIsDescribedAsAReversal() {
        var text = MoveNarrative.summarize(input("2026-11-25T09:30:00", "2026-11-25T12:00:00", List.of(), "100",
                List.of(c("2026-11-25T10:05:00", "102"), c("2026-11-25T11:59:00", "100.5")), List.of(CPI)));
        assertThat(text).isEqualTo("SPY rose 2.0% to a 10:05 AM high, then reversed to end +0.5% for the window. "
                + "No verified catalyst found in EventAlpha's sources. Economic calendar: the 10:00 AM CPI release.");
    }

    @Test
    void anEarlierReleaseIsCalendarContext() {
        var fomc = new Release("FOMC decision", et("2026-11-24T14:00:00"), true);
        var text = MoveNarrative.summarize(input("2026-11-25T09:30:00", "2026-11-25T11:00:00", List.of(), "98",
                List.of(c("2026-11-25T10:59:00", "97")), List.of(fomc)));
        assertThat(text).isEqualTo("No verified catalyst found for this move. Economic calendar: the Nov 24, 2:00 PM FOMC decision.");
    }

    @Test
    void withoutReleasesOnlyAReversingPathIsDescribed() {
        var text = MoveNarrative.summarize(input("2026-11-25T09:30:00", "2026-11-25T12:00:00", List.of(), "100",
                List.of(c("2026-11-25T10:00:00", "98"), c("2026-11-25T11:59:00", "99.5")), List.of()));
        assertThat(text).isEqualTo("SPY fell 2.0% to a 10:00 AM low, then reversed to end -0.5% for the window. "
                + "No verified catalyst found in EventAlpha's sources.");
        assertThat(MoveNarrative.summarize(input("2026-11-25T09:30:00", "2026-11-25T12:00:00", List.of(), "100",
                List.of(c("2026-11-25T11:59:00", "100.1")), List.of())))
                .isEqualTo("No verified catalyst found for this move.");
    }

    @Test
    void releasesAtTheSameTimeAreNamedTogetherPreferringHighImportance() {
        var at = et("2026-11-25T08:30:00");
        assertThat(MoveNarrative.label(List.of(new Release("GDP", at, true), new Release("PCE", at, true)),
                et("2026-11-25T09:00:00"))).isEqualTo("the 8:30 AM GDP and PCE releases");
        assertThat(MoveNarrative.label(List.of(new Release("jobs report", at, true)), et("2026-11-25T09:00:00")))
                .isEqualTo("the 8:30 AM jobs report");
    }
}
