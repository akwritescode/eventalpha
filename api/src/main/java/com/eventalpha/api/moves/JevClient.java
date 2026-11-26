package com.eventalpha.api.moves;

import java.net.http.HttpClient;
import java.time.Duration;
import java.util.Map;
import java.util.OptionalDouble;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/**
 * TypeSafe System One (JEV), the same model family that scores articles in the pipeline. Here it
 * answers one yes/no question: does this article state what caused the price move? JEV returns a
 * probability, never text (the reason itself is written by {@link CauseSummarizer}).
 */
@Component
public class JevClient {

    private static final Logger log = LoggerFactory.getLogger(JevClient.class);

    public enum Direction { UP, DOWN, UNKNOWN }

    private final RestClient http;
    private final String model;
    private final boolean enabled;

    JevClient(@Value("${eventalpha.explain.typesafe-api-key:}") String apiKey,
              @Value("${eventalpha.explain.model:jev-1.14.0}") String model,
              @Value("${eventalpha.explain.typesafe-url:https://api.typesafe.ai}") String baseUrl) {
        this.model = model;
        this.enabled = !apiKey.isBlank();
        var factory = new JdkClientHttpRequestFactory(HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build());
        factory.setReadTimeout(Duration.ofSeconds(10));
        this.http = RestClient.builder().baseUrl(baseUrl).requestFactory(factory)
                .defaultHeader("Authorization", "Bearer " + apiKey).build();
    }

    boolean available() {
        return enabled;
    }

    /** The question, with criteria; phrased so an article that only reports the move answers no. */
    static Map<String, Object> question(Direction direction) {
        String move = switch (direction) {
            case UP -> "price rise";
            case DOWN -> "price decline";
            case UNKNOWN -> "price move";
        };
        return Map.of("type", "noul",
                "instructions", "For the target ticker and time window, the article names a specific cause (a news event, economic data, policy decision, "
                        + "or company announcement) for the stock " + move + " it describes, not just the size of the move.",
                "criteria", Map.of(
                        "true", "The text says what triggered or caused the " + move + ".",
                        "false", "The text only reports that prices moved, or gives a cause only for a different ticker, period, or direction."));
    }

    /** Probability (0 to 1) that the text states the move's cause; empty when unavailable or on failure. */
    OptionalDouble explainsMove(String text, Direction direction) {
        if (!enabled) return OptionalDouble.empty();
        try {
            Map<?, ?> response = http.post().uri("/v1/systemone").contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("state", text, "model", model, "questions", Map.of("explains", question(direction))))
                    .retrieve().body(Map.class);
            if (response != null && response.get("answers") instanceof Map<?, ?> answers
                    && answers.get("explains") instanceof Map<?, ?> answer && answer.get("noul") instanceof Number p) {
                return OptionalDouble.of(p.doubleValue());
            }
            log.warn("JEV answered without a probability");
        } catch (RestClientException e) {
            log.warn("JEV request failed: {}", e.getClass().getSimpleName()); // never log the URL or headers
        }
        return OptionalDouble.empty();
    }
}
