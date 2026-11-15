package com.eventalpha.api.stream;

import java.util.List;
import java.util.Map;
import org.springframework.data.domain.Range;
import org.springframework.data.redis.connection.Limit;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.connection.stream.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

/**
 * Reads the Redis Stream the pipeline appends high-impact events to (see
 * src/eventalpha/event_stream.py). Entry IDs are "millis-seq" and strictly increasing, so
 * "everything after ID x" is how a reconnecting client catches up.
 */
@Component
public class EventStreamReader {

    public static final String STREAM = "eventalpha:events";
    public static final String FEED_STREAM = "eventalpha:feed";
    /** Stream names clients may ask for → Redis keys. */
    public static final Map<String, String> STREAMS = Map.of("events", STREAM, "feed", FEED_STREAM);
    /** Fields that are internal to the pipeline and never leave the API (older entries carried them). */
    private static final java.util.Set<String> INTERNAL = java.util.Set.of("model", "questions_version");

    public record StreamEvent(String id, Map<String, String> fields) {}

    private final StringRedisTemplate redis;

    EventStreamReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    /** Non-blocking read of up to {@code count} entries after {@code lastId}. */
    public List<StreamEvent> readAfter(String lastId, int count) {
        return readAfter(STREAM, lastId, count);
    }

    public List<StreamEvent> readAfter(String stream, String lastId, int count) {
        List<MapRecord<String, Object, Object>> records = redis.opsForStream().read(
                StreamReadOptions.empty().count(count), StreamOffset.create(stream, ReadOffset.from(lastId)));
        return records == null ? List.of() : records.stream().map(EventStreamReader::toEvent).toList();
    }

    /** ID of the newest entry, or "0-0" for an empty stream: the starting point for "only new events". */
    public String latestId() {
        return latestId(STREAM);
    }

    public String latestId(String stream) {
        var last = redis.opsForStream().reverseRange(stream, Range.unbounded(), Limit.limit().count(1));
        return last == null || last.isEmpty() ? "0-0" : last.getFirst().getId().getValue();
    }

    /** Up to {@code count} entries in (afterId, upToId], newest first. */
    public List<StreamEvent> between(String stream, String afterId, String upToId, int count) {
        var records = redis.opsForStream().reverseRange(stream,
                Range.of(Range.Bound.exclusive(afterId), Range.Bound.inclusive(upToId)), Limit.limit().count(count));
        return records == null ? List.of() : records.stream().map(EventStreamReader::toEvent).toList();
    }

    /** The newest {@code count} entries, newest first. */
    public List<StreamEvent> latest(String stream, int count) {
        var records = redis.opsForStream().reverseRange(stream, Range.unbounded(), Limit.limit().count(count));
        return records == null ? List.of() : records.stream().map(EventStreamReader::toEvent).toList();
    }

    static StreamEvent toEvent(MapRecord<String, Object, Object> record) {
        Map<String, String> fields = new java.util.LinkedHashMap<>();
        record.getValue().forEach((k, v) -> {
            if (!INTERNAL.contains(String.valueOf(k))) {
                fields.put(String.valueOf(k), String.valueOf(v));
            }
        });
        return new StreamEvent(record.getId().getValue(), fields);
    }
}
