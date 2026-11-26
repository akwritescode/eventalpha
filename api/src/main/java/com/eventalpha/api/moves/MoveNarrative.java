package com.eventalpha.api.moves;

import com.eventalpha.api.moves.MoveRepository.Catalyst;
import com.eventalpha.api.moves.MoveRepository.SectorMove;
import com.eventalpha.api.moves.MoveRepository.SectorMovers;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

/**
 * Writes the "What we found" summary from evidence and the price path:
 * <ol>
 *   <li>a verified company catalyst in the window wins;</li>
 *   <li>else an economic release in the window, or one shortly before it when prices had not reacted
 *       yet (an 08:30 release before the open), is named as the likely driver of the move, and a drop
 *       that reversed is described as such;</li>
 *   <li>else the latest release up to a day before the window: the window's move is described as a
 *       continuation or a reversal of the move that followed it;</li>
 *   <li>else only the shape of the price path.</li>
 * </ol>
 * Before releases: an article JEV judged (title + body, probability >= 0.6) to explain the move is
 * quoted as a possible cause, with the reason Claude summarized from it. Articles that merely describe
 * price moves are never promoted on their title alone (MarketCommentary).
 */
final class MoveNarrative {

    private MoveNarrative() {}

    private static final ZoneId NEW_YORK = ZoneId.of("America/New_York");
    /** Moves smaller than this (percent) count as "little changed" and don't make a dip or a spike. */
    static final BigDecimal THRESHOLD = new BigDecimal("0.30");
    private static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("h:mm a", Locale.US).withZone(NEW_YORK);
    private static final DateTimeFormatter DAY = DateTimeFormatter.ofPattern("MMM d", Locale.US).withZone(NEW_YORK);

    /** A released economic report: its short name ("PCE", "FOMC decision") and release time. */
    record Release(String name, Instant at, boolean high) {}

    /** One minute candle: when it started and its close. */
    record Candle(Instant startedAt, BigDecimal close) {}

    record Input(String ticker, Instant start, Instant end, List<Catalyst> catalysts, List<MoveCauses.Cause> causes,
                 BigDecimal startPrice, List<Candle> path, List<Release> releases,
                 BigDecimal priceBeforeLatestRelease, SectorMovers sectors, boolean index) {}

    /** The window's path from its start price: total move, low/high and when, and whether it reversed. */
    private record Shape(BigDecimal total, Instant lowAt, Instant highAt, boolean dip, boolean spike,
                         BigDecimal dipPct, BigDecimal spikePct, BigDecimal fromLow, BigDecimal fromHigh) {}

    static String summarize(Input in) {
        String sectors = in.index() ? sectorSentence(in.sectors()) : "";
        if (!in.catalysts().isEmpty()) {
            return join("Plausible catalyst — " + in.catalysts().getFirst().summary()
                    + ". The timing supports a possible link.", sectors);
        }
        if (!in.causes().isEmpty()) {
            var cause = in.causes().getFirst();
            String moved = in.path().isEmpty() || in.startPrice() == null || in.startPrice().signum() <= 0 ? ""
                    : moveWords(pct(in.startPrice(), in.path().getLast().close()));
            String because = "possibly due to " + cause.reason() + " (per “" + cause.title() + "”, JEV "
                    + String.format(Locale.US, "%.2f", cause.probability()) + ").";
            return join(moved.isEmpty() ? "P" + because.substring(1) : in.ticker() + " " + moved + " in this window, " + because,
                    sectors);
        }
        var inside = group(in.releases().stream().filter(r -> !r.at().isBefore(in.start()) && !r.at().isAfter(in.end()))
                .toList(), true);
        var before = group(in.releases().stream().filter(r -> r.at().isBefore(in.start())).toList(), false);

        if (in.path().isEmpty() || in.startPrice() == null || in.startPrice().signum() <= 0) {
            var near = inside != null ? inside : before;
            return join("No verified catalyst found for this move."
                    + (near == null ? "" : " Economic releases near this window: " + label(near, in.start()) + "."), sectors);
        }
        var shape = shape(in.startPrice(), in.path());
        var driver = inside;
        BigDecimal pre = null;
        if (driver == null && before != null && in.priceBeforeLatestRelease() != null
                && in.priceBeforeLatestRelease().signum() > 0) {
            pre = pct(in.priceBeforeLatestRelease(), in.startPrice());
            if (pre.abs().compareTo(THRESHOLD) < 0) {
                driver = before; // prices hadn't reacted before the window, e.g. an 08:30 release before the open
            }
        }
        String text;
        if (driver != null) {
            text = drivenBy(in.ticker(), driver, shape, in.start());
        } else if (before != null && pre != null) {
            text = afterEarlierRelease(in.ticker(), before, pre, shape, in.start());
        } else {
            text = priceOnly(in.ticker(), shape);
        }
        return join(text, sectors);
    }

    private static String drivenBy(String ticker, List<Release> releases, Shape s, Instant windowStart) {
        String what = label(releases, windowStart);
        Instant at = releases.getFirst().at();
        if (s.dip() && s.lowAt().isAfter(at)) {
            return ticker + " fell " + unsigned(s.dipPct()) + " after " + what + ", bottoming at " + TIME.format(s.lowAt()) + ", then reversed, rising "
                    + unsigned(s.fromLow()) + " off the low to end " + signed(s.total()) + " for the window. "
                    + "EventAlpha found no news behind the rebound.";
        }
        if (s.spike() && s.highAt().isAfter(at)) {
            return ticker + " rose " + unsigned(s.spikePct()) + " after " + what + ", peaking at " + TIME.format(s.highAt())
                    + ", then reversed, falling " + unsigned(s.fromHigh()) + " off the high to end " + signed(s.total())
                    + " for the window. EventAlpha found no news behind the pullback.";
        }
        if (s.total().abs().compareTo(THRESHOLD) < 0) {
            return ticker + " was little changed (" + signed(s.total()) + ") after " + what + ".";
        }
        return ticker + " " + (s.total().signum() > 0 ? "rose " : "fell ") + unsigned(s.total()) + " after " + what
                + ", the likely driver: no company news in EventAlpha's sources.";
    }

    private static String afterEarlierRelease(String ticker, List<Release> releases, BigDecimal pre, Shape s,
                                              Instant windowStart) {
        String what = label(releases, windowStart);
        String earlier = ticker + " had " + (pre.signum() < 0 ? "fallen " : "risen ") + unsigned(pre) + " after " + what
                + " before this window";
        if (s.total().abs().compareTo(THRESHOLD) < 0) {
            return "No news in EventAlpha's sources during this window. " + earlier + ", then held roughly steady ("
                    + signed(s.total()) + ").";
        }
        boolean reversal = s.total().signum() != pre.signum();
        if (reversal) {
            boolean up = s.total().signum() > 0;
            String turn = up && s.dip() ? ", slipped to a " + TIME.format(s.lowAt()) + " low"
                    : !up && s.spike() ? ", pushed to a " + TIME.format(s.highAt()) + " high" : "";
            return "No news in EventAlpha's sources during this window. " + earlier + turn + ", then reversed, "
                    + (up ? "rising " : "falling ") + unsigned(s.total()) + ": likely "
                    + (up ? "dip buying after the release-driven sell-off." : "profit-taking after the release-driven rally.");
        }
        return ticker + " " + (s.total().signum() > 0 ? "rose " : "fell ") + unsigned(s.total())
                + " in this window, extending the " + (pre.signum() < 0 ? "decline" : "rise") + " of " + unsigned(pre)
                + " that followed " + what + ". No other news in EventAlpha's sources.";
    }

    private static String moveWords(BigDecimal total) {
        if (total.abs().compareTo(THRESHOLD) < 0) return "was little changed (" + signed(total) + ")";
        return (total.signum() > 0 ? "rose " : "fell ") + unsigned(total);
    }

    private static String priceOnly(String ticker, Shape s) {
        if (s.dip()) {
            return ticker + " fell " + unsigned(s.dipPct()) + " to a " + TIME.format(s.lowAt()) + " low, then reversed to end "
                    + signed(s.total()) + " for the window. No verified catalyst found in EventAlpha's sources.";
        }
        if (s.spike()) {
            return ticker + " rose " + unsigned(s.spikePct()) + " to a " + TIME.format(s.highAt()) + " high, then reversed to end "
                    + signed(s.total()) + " for the window. No verified catalyst found in EventAlpha's sources.";
        }
        return "No verified catalyst found for this move.";
    }

    private static Shape shape(BigDecimal start, List<Candle> path) {
        var low = path.stream().min(Comparator.comparing(Candle::close).thenComparing(Candle::startedAt)).orElseThrow();
        var high = path.stream().max(Comparator.comparing(Candle::close).thenComparing(Candle::startedAt,
                Comparator.reverseOrder())).orElseThrow();
        var last = path.getLast();
        var total = pct(start, last.close());
        var dipPct = pct(start, low.close());
        var spikePct = pct(start, high.close());
        var fromLow = pct(low.close(), last.close());
        var fromHigh = pct(high.close(), last.close());
        boolean dip = dipPct.compareTo(THRESHOLD.negate()) <= 0 && fromLow.compareTo(THRESHOLD) >= 0 && low != last;
        boolean spike = spikePct.compareTo(THRESHOLD) >= 0 && fromHigh.compareTo(THRESHOLD.negate()) <= 0 && high != last;
        return new Shape(total, low.startedAt(), high.startedAt(), dip, spike, dipPct, spikePct, fromLow, fromHigh);
    }

    /** Releases at the same instant, preferring high-importance ones: the earliest group inside the window or the latest before it. */
    private static List<Release> group(List<Release> releases, boolean earliest) {
        if (releases.isEmpty()) return null;
        var at = earliest ? releases.stream().map(Release::at).min(Comparator.naturalOrder()).orElseThrow()
                : releases.stream().map(Release::at).max(Comparator.naturalOrder()).orElseThrow();
        var same = releases.stream().filter(r -> r.at().equals(at)).toList();
        var high = same.stream().filter(Release::high).toList();
        return high.isEmpty() ? same : high;
    }

    /** "the 8:30 AM GDP and PCE releases", "the Nov 24, 2:00 PM FOMC decision". */
    static String label(List<Release> releases, Instant windowStart) {
        var at = releases.getFirst().at();
        String when = (DAY.format(at).equals(DAY.format(windowStart)) ? "" : DAY.format(at) + ", ") + TIME.format(at);
        var names = releases.stream().map(Release::name).distinct().toList();
        String joined = names.size() == 1 ? names.getFirst()
                : String.join(", ", names.subList(0, names.size() - 1)) + " and " + names.getLast();
        boolean noun = names.size() == 1 && (joined.endsWith("decision") || joined.endsWith("report"));
        return "the " + when + " " + joined + (noun ? "" : names.size() == 1 ? " release" : " releases");
    }

    private static String sectorSentence(SectorMovers sectors) {
        if (sectors == null) return "";
        var parts = new ArrayList<String>();
        if (!sectors.gainers().isEmpty()) parts.add("Leading sectors: " + list(sectors.gainers()));
        if (!sectors.decliners().isEmpty()) parts.add((parts.isEmpty() ? "Lagging" : "lagging") + ": " + list(sectors.decliners()));
        return parts.isEmpty() ? "" : String.join("; ", parts) + ".";
    }

    private static String list(List<SectorMove> moves) {
        return moves.stream().map(m -> m.sector() + " " + signed(m.price().returnPercent()))
                .collect(Collectors.joining(", "));
    }

    private static String join(String first, String second) {
        return second.isBlank() ? first : first + " " + second;
    }

    static BigDecimal pct(BigDecimal from, BigDecimal to) {
        return to.subtract(from).movePointRight(2).divide(from, 4, RoundingMode.HALF_UP);
    }

    static String signed(BigDecimal pct) {
        var r = pct.setScale(1, RoundingMode.HALF_UP);
        return (r.signum() > 0 ? "+" : r.signum() < 0 ? "-" : "") + r.abs().toPlainString() + "%";
    }

    static String unsigned(BigDecimal pct) {
        return pct.abs().setScale(1, RoundingMode.HALF_UP).toPlainString() + "%";
    }
}
