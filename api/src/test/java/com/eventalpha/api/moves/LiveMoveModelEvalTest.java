package com.eventalpha.api.moves;

import static org.assertj.core.api.Assertions.assertThat;

import com.eventalpha.api.moves.MoveCauses.MeasuredReturn;
import com.jayway.jsonpath.JsonPath;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.assertj.core.api.SoftAssertions;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

class LiveMoveModelEvalTest {

    private record EvalCase(String id, String ticker, Instant start, Instant end, MeasuredReturn measured,
                            List<Map<String, Object>> articles) {}

    @Test
    void pairedFixturesContainPositiveAndNegativeArticles() throws Exception {
        var evaluations = cases();
        assertThat(evaluations).isNotEmpty();
        for (var evaluation : evaluations) {
            assertThat(evaluation.measured().end()).isAfter(evaluation.measured().start());
            assertThat(evaluation.articles()).extracting(article -> article.get("explainsMove")).contains(true, false);
        }
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
        var jev = new JevClient(jevKey, jevModel, "https://api.typesafe.ai");
        var claude = new CauseSummarizer(claudeKey, claudeModel);
        System.out.printf("JEV=%s Claude=%s threshold=%.2f%n", jevModel, claudeModel, MoveCauses.THRESHOLD);

        var checks = new SoftAssertions();
        var evaluations = cases();
        for (boolean withReturn : List.of(false, true)) {
            String variant = withReturn ? "with-return" : "direction-only";
            int falsePositives = 0;
            int falseNegatives = 0;
            int missing = 0;
            for (var evaluation : evaluations) {
                var direction = evaluation.measured().direction();
                String move = MoveCauses.describeMove(evaluation.start(), evaluation.end(), direction,
                        withReturn ? evaluation.measured() : null);
                for (var article : evaluation.articles()) {
                    String text = (String) article.get("text");
                    String id = variant + "/" + evaluation.id() + "/" + article.get("id");
                    var score = jev.explainsMove(MoveCauses.judgeInput(evaluation.ticker(), move, text), direction);
                    checks.assertThat(score).as("JEV response for %s", id).isPresent();
                    if (score.isEmpty()) {
                        missing++;
                        continue;
                    }
                    double probability = score.orElseThrow();
                    boolean accepted = probability >= MoveCauses.THRESHOLD;
                    boolean expected = Boolean.TRUE.equals(article.get("explainsMove"));
                    if (accepted && !expected) falsePositives++;
                    if (!accepted && expected) falseNegatives++;
                    var reason = accepted ? claude.reason(evaluation.ticker(), move, text) : Optional.<String>empty();
                    System.out.printf("%s score=%.4f expected=%s reason=%s%n", id, probability,
                            expected, reason.orElse("(none)"));
                    if (withReturn) {
                        checks.assertThat(accepted).as("JEV verdict for %s", id).isEqualTo(expected);
                        if (expected && accepted) {
                            checks.assertThat(reason).as("Claude grounded reason for %s", id).isPresent();
                        }
                    }
                }
            }
            System.out.printf("%s falsePositives=%d falseNegatives=%d missing=%d%n",
                    variant, falsePositives, falseNegatives, missing);
        }
        checks.assertAll();
    }

    private static List<EvalCase> cases() throws Exception {
        List<Map<String, Object>> data = JsonPath.parse(Files.readString(Path.of("../evals/move_explanations.json")))
                .read("$[?(@.articleJudgments)]");
        return data.stream().map(entry -> {
            var parsed = JsonPath.parse(entry);
            var measured = new MeasuredReturn(instant(parsed.read("$.measuredReturn.start")),
                    instant(parsed.read("$.measuredReturn.end")),
                    new BigDecimal(parsed.<Number>read("$.measuredReturn.percent").toString()));
            return new EvalCase(parsed.read("$.id"), parsed.read("$.ticker"), instant(parsed.read("$.start")),
                    instant(parsed.read("$.end")), measured, parsed.read("$.articleJudgments"));
        }).toList();
    }

    private static Instant instant(String value) {
        return OffsetDateTime.parse(value).toInstant();
    }
}
