package com.eventalpha.api.moves;

import java.util.regex.Pattern;

/**
 * Headlines that only describe a price move ("Chip stocks rally", "S&P 500 slides at midday",
 * "Nvidia shares jump 5%") restate the move being explained. They are never a catalyst and are
 * never quoted as a cause; the timeline still lists them, labelled as commentary.
 */
final class MarketCommentary {

    private MarketCommentary() {}

    /** A market noun followed directly, or after one word ("S&P 500 slides"), by a verb of price movement. */
    private static final Pattern MOVE_REPORT = Pattern.compile(
            "\\b(stocks?|shares|equities|markets?|index(es)?|indices|sectors?|etfs?|s&p|nasdaq|dow|wall street|futures)"
                    + "\\s+(\\S+\\s+)?"
                    + "(rall(y|ies|ied)|surg(e|es|ed|ing)|jump(s|ed)?|soar(s|ed)?|climb(s|ed)?|gain(s|ed)?|ris(e|es|ing)|rose"
                    + "|slid(e|es)?|slump(s|ed)?|fall(s|ing)?|fell|drop(s|ped)?|plung(e|es|ed)|tumbl(e|es|ed)|sink(s)?|sank"
                    + "|rebound(s|ed)?|recover(s|ed)?|swing(s)?|retreat(s|ed)?|extend(s|ed)?|higher|lower|mixed)\\b",
            Pattern.CASE_INSENSITIVE);

    /** Market recap formats, whatever they say about why. */
    private static final Pattern RECAP = Pattern.compile(
            "\\b(stock market today|market (wrap|recap|update)|midday movers|biggest movers|markets? close|market at midday)\\b",
            Pattern.CASE_INSENSITIVE);

    static boolean isCommentary(String title) {
        return title != null && (MOVE_REPORT.matcher(title).find() || RECAP.matcher(title).find());
    }
}
