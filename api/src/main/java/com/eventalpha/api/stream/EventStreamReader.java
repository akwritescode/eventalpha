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

    public record StreamEvent(String id, Map<String, String> fields) {}

    private final StringRedisTemplate redis;

    EventStreamReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    /** Non-blocking read of up to {@code count} entries after {@code lastId}. */
    public List<StreamEvent> readAfter(String lastId, int count) {
        List<MapRecord<String, Object, Object>> records = redis.opsForStream().read(
                StreamReadOptions.empty().count(count), StreamOffset.create(STREAM, ReadOffset.from(lastId)));
        return records == null ? List.of() : records.stream().map(EventStreamReader::toEvent).toList();
    }

    /** ID of the newest entry, or "0-0" for an empty stream: the starting point for "only new events". */
    public String latestId() {
        var last = redis.opsForStream().reverseRange(STREAM, Range.unbounded(), Limit.limit().count(1));
        return last == null || last.isEmpty() ? "0-0" : last.getFirst().getId().getValue();
    }

    static StreamEvent toEvent(MapRecord<String, Object, Object> record) {
        Map<String, String> fields = new java.util.LinkedHashMap<>();
        record.getValue().forEach((k, v) -> fields.put(String.valueOf(k), String.valueOf(v)));
        return new StreamEvent(record.getId().getValue(), fields);
    }
}
