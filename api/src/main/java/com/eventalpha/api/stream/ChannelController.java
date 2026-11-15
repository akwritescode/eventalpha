package com.eventalpha.api.stream;

import com.eventalpha.api.common.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * What the Telegram channel carries, for visitors who haven't joined. A private channel's invite
 * link shows no messages, so the web UI previews them from what was actually posted: each
 * signal's stored message, and the high-impact events the relay delivered (formatted exactly as
 * it sent them).
 */
@RestController
@RequestMapping("/api/v1/channel")
class ChannelController {

    record Post(String id, String kind, Instant postedAt, String html) {}

    record Preview(String channelName, List<Post> posts) {}

    private final JdbcClient jdbc;
    private final EventStreamReader reader;
    private final StringRedisTemplate redis;
    private final String channelName;

    ChannelController(JdbcClient jdbc, EventStreamReader reader, StringRedisTemplate redis,
                      @Value("${eventalpha.telegram.channel-name:EventAlpha Alerts}") String channelName) {
        this.jdbc = jdbc;
        this.reader = reader;
        this.redis = redis;
        this.channelName = channelName;
    }

    /** Events the Telegram relay actually delivered: after its starting point, up to its last delivery. */
    private List<EventStreamReader.StreamEvent> deliveredEvents(int limit) {
        String since = redis.opsForValue().get(TelegramRelay.SINCE_KEY);
        if (since == null || !Boolean.TRUE.equals(redis.hasKey(EventStreamReader.STREAM))) {
            return List.of(); // relay never ran: nothing was posted
        }
        var group = redis.opsForStream().groups(EventStreamReader.STREAM).stream()
                .filter(g -> TelegramRelay.GROUP.equals(g.groupName())).findFirst();
        if (group.isEmpty() || group.get().lastDeliveredId().equals(since)) {
            return List.of();
        }
        return reader.between(EventStreamReader.STREAM, since, group.get().lastDeliveredId(), limit);
    }

    @Operation(summary = "Recent posts of the Telegram alerts channel (signals and high-impact events), newest first")
    @GetMapping("/preview")
    ApiResponse<Preview> preview(@RequestParam(defaultValue = "20") @Min(1) @Max(50) int limit) {
        List<Post> posts = new ArrayList<>(jdbc.sql("""
                        SELECT signal_type, session_date, generated_at, message FROM signals
                        WHERE message IS NOT NULL ORDER BY generated_at DESC LIMIT :limit""")
                .param("limit", limit)
                .query((rs, i) -> new Post("signal:" + rs.getString("signal_type") + ":" + rs.getString("session_date"),
                        "signal", rs.getObject("generated_at", OffsetDateTime.class).toInstant(), rs.getString("message")))
                .list());
        for (var e : deliveredEvents(limit)) {
            long millis = Long.parseLong(e.id().split("-")[0]); // stream IDs start with the publish time
            posts.add(new Post("event:" + e.id(), "event", Instant.ofEpochMilli(millis), TelegramRelay.format(e.fields())));
        }
        posts.sort(Comparator.comparing(Post::postedAt).reversed());
        List<Post> page = posts.size() > limit ? posts.subList(0, limit) : posts;
        return ApiResponse.of(new Preview(channelName, page), page.isEmpty() ? null : page.getFirst().postedAt());
    }
}
