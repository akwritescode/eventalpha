package com.eventalpha.api.moves;

import static org.assertj.core.api.Assertions.assertThat;

import com.anthropic.models.messages.CitationsWebSearchResultLocation;
import com.anthropic.models.messages.TextBlock;
import com.anthropic.models.messages.TextCitation;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class WebMoveSearchTest {

    private static TextBlock cited(String text, String url, String title) {
        return cited(text, url, title, "…");
    }

    private static TextBlock cited(String text, String url, String title, String excerpt) {
        var location = CitationsWebSearchResultLocation.builder().citedText(excerpt).encryptedIndex("x")
                .title(title).url(url).build();
        return TextBlock.builder().text(text).citations(List.of(TextCitation.ofWebSearchResultLocation(location))).build();
    }

    @Test
    void attachesPublicationTimeOnlyWhenTheSourceSupportsIt() {
        String answer = "PUBLISHED: 2026-11-26T11:00:00-05:00\nReports attributed the rally to a delivery update.";
        String url = "https://example.com/tesla";
        assertThat(WebMoveSearch.parse(List.of(cited(answer, url, "Deliveries", "Published Nov 26, 2026 at 11:00 AM EST")))
                .publishedAt()).isEqualTo(Instant.parse("2026-11-26T16:00:00Z"));
        assertThat(WebMoveSearch.parse(List.of(cited(answer, url, "Deliveries", "Published Nov. 26 at 11 a.m. ET")))
                .publishedAt()).isEqualTo(Instant.parse("2026-11-26T16:00:00Z"));
        assertThat(WebMoveSearch.parse(List.of(cited(answer, url, "Deliveries", "Published Nov 26, 2026 at 1:00 AM EST")))
                .publishedAt()).isNull();
        var noTime = WebMoveSearch.parse(List.of(cited(answer, url, "Deliveries")));
        assertThat(noTime.publishedAt()).isNull();
        assertThat(noTime.answer()).isEqualTo("Reports attributed the rally to a delivery update.");
    }

    private static TextBlock plain(String text) {
        return TextBlock.builder().text(text).citations(List.of()).build();
    }

    @Test
    void keepsACitedAnswerWithItsSources() {
        var answer = WebMoveSearch.parse(List.of(plain("Reports said "),
                cited("chipmakers rebounded after the tariff delay.", "https://example.com/a", "Chips rebound"),
                cited(" Bond yields also eased.", "https://example.com/b", "Yields ease")));
        assertThat(answer.answer()).isEqualTo("Reports said chipmakers rebounded after the tariff delay. Bond yields also eased.");
        assertThat(answer.sources()).extracting(WebMoveSearch.Source::url)
                .containsExactly("https://example.com/a", "https://example.com/b");
    }

    @Test
    void noneOrUncitedAnswersCountAsNothingFound() {
        assertThat(WebMoveSearch.parse(List.of(plain("**NONE.** The sources describe the rebound without a trigger.")))
                .answer()).isNull();
        assertThat(WebMoveSearch.parse(List.of(cited("NONE", "https://example.com/a", "Recap"))).answer()).isNull();
        assertThat(WebMoveSearch.parse(List.of(plain("Stocks rose because of the Fed."))).answer()).isNull(); // no citation
        assertThat(WebMoveSearch.parse(List.of(cited("Stocks rose because of the Fed.", "file:///tmp/report", "Report")))
                .answer()).isNull();
    }

    @Test
    void nonethelessIsNotTheNoneSentinel() {
        String text = "Nonetheless, reports said the tariff delay drove the rebound.";
        assertThat(WebMoveSearch.parse(List.of(cited(text, "https://example.com/a", "Report"))).answer())
                .isEqualTo(text);
    }

    @Test
    void requestUsesTheBasicWebSearchToolAndTheMoveAsData() {
        var params = WebMoveSearch.params("claude-haiku-5-5", "SPY rose 2.1% between 12:00 PM and 2:00 PM ET");
        assertThat(params.tools().orElseThrow()).hasSize(1);
        assertThat(params.messages().getFirst().content().asString())
                .isEqualTo("<move>SPY rose 2.1% between 12:00 PM and 2:00 PM ET</move>");
    }
}
