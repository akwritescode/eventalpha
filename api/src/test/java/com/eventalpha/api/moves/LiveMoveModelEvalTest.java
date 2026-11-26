package com.eventalpha.api.moves;

import static org.assertj.core.api.Assertions.assertThat;

import com.eventalpha.api.moves.JevClient.Direction;
import com.jayway.jsonpath.JsonPath;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.assertj.core.api.SoftAssertions;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

@EnabledIfEnvironmentVariable(named = "EVENTALPHA_RUN_LIVE_MOVE_EVAL", matches = "1")
class LiveMoveModelEvalTest {

    @Test
    void judgesRecapsAndExplicitAttributionUsingProductionPrompts() throws Exception {
        String jevKey = System.getenv().getOrDefault("TYPESAFE_API_KEY", "");
        String claudeKey = System.getenv().getOrDefault("ANTHROPIC_API_KEY", "");
        assertThat(!jevKey.isBlank() && !claudeKey.isBlank())
                .as("Both model API keys must be configured for the live eval").isTrue();
        var jevModel = System.getenv().getOrDefault("EVENTALPHA_EXPLAIN_MODEL", "jev-1.14.0");
        var claudeModel = System.getenv().getOrDefault("EVENTALPHA_ASK_MODEL", "claude-haiku-5-5");
        var jev = new JevClient(jevKey, jevModel, "https://api.typesafe.ai");
        var claude = new CauseSummarizer(claudeKey, claudeModel);
        System.out.printf("JEV=%s Claude=%s threshold=%.2f%n", jevModel, claudeModel, MoveCauses.THRESHOLD);

        List<Map<String, Object>> cases = JsonPath.parse(Files.readString(Path.of("../evals/move_explanations.json")))
                .read("$[?(@.articleJudgments)]");
        assertThat(cases).isNotEmpty();
        var checks = new SoftAssertions();
        for (var evaluation : cases) {
            var parsed = JsonPath.parse(evaluation);
            String ticker = parsed.read("$.ticker");
            String start = parsed.read("$.start");
            String end = parsed.read("$.end");
            String move = MoveCauses.describeMove(OffsetDateTime.parse(start).toInstant(),
                    OffsetDateTime.parse(end).toInstant(), Direction.UP);
            List<Map<String, Object>> judgments = parsed.read("$.articleJudgments");
            for (var article : judgments) {
                String text = (String) article.get("text");
                var score = jev.explainsMove(MoveCauses.judgeInput(ticker, move, text), Direction.UP);
                checks.assertThat(score).as("JEV response for %s", article.get("id")).isPresent();
                if (score.isEmpty()) continue;
                double probability = score.orElseThrow();
                boolean accepted = probability >= MoveCauses.THRESHOLD;
                var reason = accepted ? claude.reason(ticker, move, text) : Optional.<String>empty();
                System.out.printf("%s/%s score=%.4f reason=%s%n", evaluation.get("id"), article.get("id"),
                        probability, reason.orElse("(none)"));
                checks.assertThat(accepted).as("JEV verdict for %s", article.get("id"))
                        .isEqualTo(article.get("explainsMove"));
                if (accepted) checks.assertThat(reason).as("Claude grounded reason for %s", article.get("id")).isPresent();
            }
        }
        checks.assertAll();
    }
}
