package com.eventalpha.api.moves;

import static org.assertj.core.api.Assertions.assertThat;

import com.anthropic.models.messages.CitationsWebSearchResultLocation;
import com.anthropic.models.messages.TextBlock;
import com.anthropic.models.messages.TextCitation;
import java.util.List;
import org.junit.jupiter.api.Test;

class WebMoveSearchTest {

    private static TextBlock cited(String text, String url, String title) {
        var location = CitationsWebSearchResultLocation.builder().citedText("…").encryptedIndex("x")
                .title(title).url(url).build();
        return TextBlock.builder().text(text).citations(List.of(TextCitation.ofWebSearchResultLocation(location))).build();
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
    }

    @Test
    void requestUsesTheBasicWebSearchToolAndTheMoveAsData() {
        var params = WebMoveSearch.params("claude-haiku-5-5", "SPY rose 2.1% between 12:00 PM and 2:00 PM ET");
        assertThat(params.tools().orElseThrow()).hasSize(1);
        assertThat(params.messages().getFirst().content().asString())
                .isEqualTo("<move>SPY rose 2.1% between 12:00 PM and 2:00 PM ET</move>");
    }
}
