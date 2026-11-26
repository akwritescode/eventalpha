package com.eventalpha.api.moves;

import static org.assertj.core.api.Assertions.assertThat;

import com.eventalpha.api.moves.MoveCauses.MeasuredReturn;
import com.jayway.jsonpath.JsonPath;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;
import org.assertj.core.api.SoftAssertions;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

/**
 * Article-level evals for the JEV question and Claude's grounded reason. Cases come from
 * evals/move_explanations.json (entries with articleJudgments) and evals/article_judgments.json.
 * The fixture checks run in CI; the live comparison only with EVENTALPHA_RUN_LIVE_MOVE_EVAL=1.
 */
class LiveMoveModelEvalTest {

    private static final List<Path> FILES = List.of(Path.of("../evals/move_explanations.json"),
            Path.of("../evals/article_judgments.json"));
    /** Scores this close to the threshold are listed as fragile even when the verdict is right. */
    private static final double NEAR_THRESHOLD = 0.15;

    private record EvalCase(String id, String ticker, Instant start, Instant end, MeasuredReturn measured,
                            List<Map<String, Object>> articles) {}

    /** Per run: JEV's score, and whether the cause would be shown (JEV accepted and Claude grounded a reason). */
    private record Outcome(String kind, boolean expected, List<Double> scores, List<Boolean> shown, Optional<String> reason) {}

    @Test
    void pairedFixturesContainPositiveAndNegativeArticles() throws Exception {
        var evaluations = cases();
        assertThat(evaluations).hasSizeGreaterThanOrEqualTo(7);
        var groupIds = new HashSet<String>();
        int articles = 0;
        for (var evaluation : evaluations) {
            assertThat(groupIds.add(evaluation.id())).as("unique case id %s", evaluation.id()).isTrue();
            assertThat(evaluation.measured().end()).isAfter(evaluation.measured().start());
            assertThat(evaluation.articles()).extracting(article -> article.get("explainsMove")).contains(true, false);
            var articleIds = new HashSet<String>();
            for (var article : evaluation.articles()) {
                String id = evaluation.id() + "/" + article.get("id");
                assertThat(articleIds.add((String) article.get("id"))).as("unique article id %s", id).isTrue();
                assertThat((String) article.get("text")).as("text of %s", id).isNotBlank();
                assertThat(article.get("explainsMove")).as("label of %s", id).isInstanceOf(Boolean.class);
                // Real events are paraphrased in our own words and must say where they come from.
                if (!Boolean.TRUE.equals(article.get("synthetic"))) {
                    assertThat(article.get("url") != null || article.get("sources") != null)
                            .as("source for non-synthetic %s", id).isTrue();
                }
                articles++;
            }
        }
        assertThat(articles).as("article judgments").isGreaterThanOrEqualTo(30);
    }

    @Test
    @EnabledIfEnvironmentVariable(named = "EVENTALPHA_RUN_LIVE_MOVE_EVAL", matches = "1")
    void comparesDirectionOnlyWithMeasuredReturnContext() throws Exception {
        String jevKey = System.getenv().getOrDefault("TYPESAFE_API_KEY", "");
        String claudeKey = System.getenv().getOrDefault("ANTHROPIC_API_KEY", "");
        assertThat(!jevKey.isBlank() && !claudeKey.isBlank())
                .as("Both model API keys must be configured for the live eval").isTrue();
        var jevModel = System.getenv().getOrDefault("EVENTALPHA_EXPLAIN_MODEL", "jev-1.14.0");
        var claudeModel = System.getenv().getOrDefault("EVENTALPHA_ASK_MODEL", "claude-haiku-5-5");
        int runs = Math.max(1, Integer.parseInt(System.getenv().getOrDefault("EVENTALPHA_LIVE_EVAL_RUNS", "1")));
        var jev = new JevClient(jevKey, jevModel, "https://api.typesafe.ai");
        var claude = new CauseSummarizer(claudeKey, claudeModel);
        System.out.printf("JEV=%s Claude=%s threshold=%.2f runs=%d%n", jevModel, claudeModel, MoveCauses.THRESHOLD, runs);

        var checks = new SoftAssertions();
        var evaluations = cases();
        for (boolean withReturn : List.of(false, true)) {
            String variant = withReturn ? "with-return" : "direction-only";
            var outcomes = new LinkedHashMap<String, Outcome>();
            int missing = 0;
            for (var evaluation : evaluations) {
                var direction = evaluation.measured().direction();
                String move = MoveCauses.describeMove(evaluation.start(), evaluation.end(), direction,
                        withReturn ? evaluation.measured() : null);
                for (var article : evaluation.articles()) {
                    String text = (String) article.get("text");
                    String id = evaluation.id() + "/" + article.get("id");
                    boolean expected = Boolean.TRUE.equals(article.get("explainsMove"));
                    var scores = new ArrayList<Double>();
                    var shown = new ArrayList<Boolean>();
                    Optional<String> firstReason = Optional.empty();
                    for (int run = 0; run < runs; run++) {
                        var score = jev.explainsMove(MoveCauses.judgeInput(evaluation.ticker(), move, text), direction);
                        checks.assertThat(score).as("JEV response for %s/%s run %d", variant, id, run + 1).isPresent();
                        if (score.isEmpty()) {
                            missing++;
                            continue;
                        }
                        scores.add(score.getAsDouble());
                        // As in MoveCauses: a cause is shown only when JEV accepts and Claude grounds a reason.
                        var reason = score.getAsDouble() >= MoveCauses.THRESHOLD
                                ? claude.reason(evaluation.ticker(), move, text) : Optional.<String>empty();
                        shown.add(reason.isPresent());
                        if (firstReason.isEmpty()) firstReason = reason;
                    }
                    var kind = (String) article.getOrDefault("kind", "unlabelled");
                    outcomes.put(id, new Outcome(kind, expected, scores, shown, firstReason));
                    if (withReturn) {
                        for (int run = 0; run < shown.size(); run++) {
                            checks.assertThat(shown.get(run))
                                    .as("shown as a cause: %s run %d (JEV %.2f)", id, run + 1, scores.get(run))
                                    .isEqualTo(expected);
                        }
                    }
                }
            }
            report(variant, outcomes, missing);
        }
        checks.assertAll();
    }

    /** JEV-level and shown-to-user results, misses by kind, and JEV scores close to the threshold. */
    private static void report(String variant, Map<String, Outcome> outcomes, int missing) {
        int truePositives = 0, falsePositives = 0, falseNegatives = 0, trueNegatives = 0, unstable = 0;
        int shownRight = 0, shownWrongYes = 0, shownWrongNo = 0, claudeDropped = 0;
        var missesByKind = new TreeMap<String, Integer>();
        var fragile = new ArrayList<String>();
        for (var entry : outcomes.entrySet()) {
            var o = entry.getValue();
            if (o.scores().isEmpty()) continue;
            double min = o.scores().stream().mapToDouble(Double::doubleValue).min().orElseThrow();
            double max = o.scores().stream().mapToDouble(Double::doubleValue).max().orElseThrow();
            long accepted = o.scores().stream().filter(p -> p >= MoveCauses.THRESHOLD).count();
            boolean flips = accepted > 0 && accepted < o.scores().size();
            if (flips) unstable++;
            for (double p : o.scores()) {
                boolean yes = p >= MoveCauses.THRESHOLD;
                if (yes && o.expected()) truePositives++;
                else if (yes) falsePositives++;
                else if (o.expected()) falseNegatives++;
                else trueNegatives++;
                if (yes != o.expected()) missesByKind.merge(o.kind(), 1, Integer::sum);
            }
            for (int run = 0; run < o.shown().size(); run++) {
                boolean yes = o.shown().get(run);
                if (yes == o.expected()) shownRight++;
                else if (yes) shownWrongYes++;
                else shownWrongNo++;
                if (o.scores().get(run) >= MoveCauses.THRESHOLD && !yes && o.expected()) claudeDropped++;
            }
            if (Math.abs(min - MoveCauses.THRESHOLD) < NEAR_THRESHOLD || Math.abs(max - MoveCauses.THRESHOLD) < NEAR_THRESHOLD) {
                fragile.add(entry.getKey());
            }
            long shownCount = o.shown().stream().filter(Boolean::booleanValue).count();
            System.out.printf("%s/%s [%s] expected=%s scores=%.2f..%.2f%s shown=%d/%d reason=%s%n", variant, entry.getKey(),
                    o.kind(), o.expected(), min, max, flips ? " FLIPS" : "", shownCount, o.shown().size(),
                    o.reason().orElse("(none)"));
        }
        double precision = truePositives + falsePositives == 0 ? 1 : (double) truePositives / (truePositives + falsePositives);
        double recall = truePositives + falseNegatives == 0 ? 1 : (double) truePositives / (truePositives + falseNegatives);
        System.out.printf("%s judgments=%d TP=%d FP=%d FN=%d TN=%d precision=%.2f recall=%.2f unstable=%d missing=%d%n",
                variant, truePositives + falsePositives + falseNegatives + trueNegatives, truePositives, falsePositives,
                falseNegatives, trueNegatives, precision, recall, unstable, missing);
        System.out.printf("%s shown to users: right=%d wrongly-shown=%d wrongly-hidden=%d (Claude dropped %d JEV-accepted true causes)%n",
                variant, shownRight, shownWrongYes, shownWrongNo, claudeDropped);
        System.out.printf("%s misses by kind: %s%n", variant, missesByKind.isEmpty() ? "none" : missesByKind);
        System.out.printf("%s within %.2f of the threshold: %s%n", variant, NEAR_THRESHOLD,
                fragile.isEmpty() ? "none" : String.join(", ", fragile));
    }

    private static List<EvalCase> cases() throws Exception {
        var out = new ArrayList<EvalCase>();
        for (Path file : FILES) {
            List<Map<String, Object>> data = JsonPath.parse(Files.readString(file)).read("$[?(@.articleJudgments)]");
            for (var entry : data) {
                var parsed = JsonPath.parse(entry);
                var measured = new MeasuredReturn(instant(parsed.read("$.measuredReturn.start")),
                        instant(parsed.read("$.measuredReturn.end")),
                        new BigDecimal(parsed.<Number>read("$.measuredReturn.percent").toString()));
                out.add(new EvalCase(parsed.read("$.id"), parsed.read("$.ticker"), instant(parsed.read("$.start")),
                        instant(parsed.read("$.end")), measured, parsed.read("$.articleJudgments")));
            }
        }
        return out;
    }

    private static Instant instant(String value) {
        return OffsetDateTime.parse(value).toInstant();
    }
}
