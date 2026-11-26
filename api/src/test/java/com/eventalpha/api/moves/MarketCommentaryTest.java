package com.eventalpha.api.moves;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class MarketCommentaryTest {

    @Test
    void headlinesThatOnlyReportAMoveAreCommentary() {
        for (String title : new String[] {
                "Chip stocks rally as semiconductor ETF jumps 4% at midday",
                "S&P 500 slides 2.39% at midday as AI selling deepens",
                "Nvidia shares jump 5% in afternoon trading",
                "Stock Market Today: Dow erases losses to end positive",
                "Tech sector rebounds after morning sell-off",
                "Midday movers: HP surges, Nutanix slumps"}) {
            assertThat(MarketCommentary.isCommentary(title)).as(title).isTrue();
        }
    }

    @Test
    void companyNewsIsNotCommentaryEvenWhenItMentionsShares() {
        for (String title : new String[] {
                "NVIDIA 8-K on H20 export licensing and expected charges",
                "Acme to repurchase up to $1 billion of shares as revenue rises",
                "Lupin Receives Approval from U.S. FDA for Sitagliptin and Metformin Tablets",
                "AI API Market worth $166.70 billion by 2031"}) {
            assertThat(MarketCommentary.isCommentary(title)).as(title).isFalse();
        }
    }
}
