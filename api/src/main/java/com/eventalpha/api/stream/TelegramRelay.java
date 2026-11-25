package com.eventalpha.api.stream;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.data.domain.Range;
import org.springframework.data.redis.RedisSystemException;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.PendingMessage;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.connection.stream.StreamReadOptions;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.util.HtmlUtils;

/**
 * Sends each high-impact event to Telegram exactly once per consumer group.
 *
 * Consumer-group semantics do the bookkeeping: XREADGROUP hands out entries, XACK marks
 * them sent. An entry that failed to send stays in the group's pending list and is retried
 * first on the next loop (and after a restart), so nothing is lost and nothing is re-sent
 * once acknowledged.
 */
@Component
@ConditionalOnExpression("!'${eventalpha.telegram.bot-token:}'.isBlank()")
class TelegramRelay {

    private static final Logger log = LoggerFactory.getLogger(TelegramRelay.class);
    static final String GROUP = "telegram";
    /** Stream ID the relay started after: entries up to here were never sent to the channel. */
    static final String SINCE_KEY = "eventalpha:relay:telegram:since";
    /**
     * One relay per deployment, so a fixed consumer name: a hostname-based name changes every
     * time the container is recreated and strands that consumer's unacknowledged entries.
     */
    static final String CONSUMER = "relay";
    /** Entries another consumer has held this long are taken over (left by an old consumer name). */
    static final Duration ORPHAN_IDLE = Duration.ofMinutes(1);

    private final StringRedisTemplate redis;
    private final RestClient telegram;
    private final String chatId;
    /** "[local] " etc. from ALERT_PREFIX, so a dev stack's posts are recognisable; empty in production. */
    private final String prefix;
    private final Consumer consumer;
    private volatile boolean running = true;

    TelegramRelay(StringRedisTemplate redis,
                  @Value("${eventalpha.telegram.bot-token}") String botToken,
                  @Value("${eventalpha.telegram.chat-id}") String chatId,
                  @Value("${eventalpha.telegram.prefix:}") String prefix) {
        this.redis = redis;
        this.chatId = chatId;
        this.prefix = prefix.isBlank() ? "" : HtmlUtils.htmlEscape(prefix.strip()) + " ";
        this.telegram = RestClient.builder().baseUrl("https://api.telegram.org/bot" + botToken).build();
        this.consumer = Consumer.from(GROUP, CONSUMER);
    }

    @EventListener(ApplicationReadyEvent.class)
    void start() {
        // The relay is optional: if Redis or Telegram misbehave, the read API must still start.
        // The loop retries with backoff, so a group that couldn't be created now is retried there.
        try {
            ensureGroup();
        } catch (RuntimeException e) {
            log.warn("Telegram relay: could not create consumer group yet: {}", e.toString());
        }
        Thread.ofVirtual().name("telegram-relay").start(this::loop);
        log.info("Telegram relay started as {}/{}", GROUP, consumer.getName());
    }

    @jakarta.annotation.PreDestroy
    void stop() {
        running = false;
    }

    private void ensureGroup() {
        try {
            // MKSTREAM: the stream may not exist before the first event. "$": start from now,
            // don't flood the chat with history the first time the relay runs.
            redis.execute((RedisCallback<Object>) c -> {
                c.streamCommands().xGroupCreate(EventStreamReader.STREAM.getBytes(), GROUP, ReadOffset.latest(), true);
                return null;
            });
        } catch (RedisSystemException e) {
            if (!isBusyGroup(e)) {
                throw e;
            }
        }
        // First run only: remember the starting point, so the channel preview never shows
        // events that were in the stream before the relay existed (they were never posted).
        var groups = redis.opsForStream().groups(EventStreamReader.STREAM);
        groups.stream().filter(g -> GROUP.equals(g.groupName())).findFirst()
                .ifPresent(g -> redis.opsForValue().setIfAbsent(SINCE_KEY, g.lastDeliveredId()));
    }

    /** Spring wraps the driver's error ("Error in execution"); BUSYGROUP is in the cause chain. */
    static boolean isBusyGroup(Throwable e) {
        for (Throwable t = e; t != null; t = t.getCause()) {
            if (String.valueOf(t.getMessage()).contains("BUSYGROUP")) {
                return true;
            }
        }
        return false;
    }

    private void loop() {
        Duration backoff = Duration.ofSeconds(2);
        while (running) {
            try {
                // Own pending entries first (sent before but never acked), then new ones.
                ensureGroup(); // no-op once the group exists; recovers if Redis was down at startup
                claimOrphans();
                var batch = read(ReadOffset.from("0"));
                if (batch.isEmpty()) {
                    batch = read(ReadOffset.lastConsumed());
                }
                for (var record : batch) {
                    try {
                        var event = EventStreamReader.toEvent(record).fields();
                        if (eligibleForDelivery(event)) {
                            send(event);
                        }
                    } catch (HttpClientErrorException e) {
                        if (e.getStatusCode().value() == 429) {
                            throw e; // rate limited: back off and retry this entry
                        }
                        // Any other 4xx is permanent (bad chat id, malformed message): retrying can
                        // never succeed and would block every later alert, so drop this one.
                        log.warn("Telegram rejected event {} (HTTP {}); dropping it",
                                record.getId(), e.getStatusCode().value());
                    }
                    redis.opsForStream().acknowledge(EventStreamReader.STREAM, GROUP, record.getId());
                }
                backoff = Duration.ofSeconds(2);
                if (batch.isEmpty()) {
                    Thread.sleep(Duration.ofSeconds(2));
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            } catch (RuntimeException e) {
                log.warn("Telegram relay error, retrying in {}: {}", backoff, describe(e));
                try {
                    Thread.sleep(backoff);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    return;
                }
                backoff = backoff.multipliedBy(2).compareTo(Duration.ofMinutes(5)) > 0
                        ? Duration.ofMinutes(5) : backoff.multipliedBy(2);
            }
        }
    }

    /** Take over entries pending under other consumer names (e.g. the old hostname-based ones). */
    private void claimOrphans() {
        var pending = redis.opsForStream().pending(EventStreamReader.STREAM, GROUP, Range.unbounded(), 100);
        RecordId[] orphans = pending.stream()
                .filter(p -> !CONSUMER.equals(p.getConsumerName()))
                .map(PendingMessage::getId)
                .toArray(RecordId[]::new);
        if (orphans.length > 0) {
            redis.opsForStream().claim(EventStreamReader.STREAM, GROUP, CONSUMER, ORPHAN_IDLE, orphans);
        }
    }

    /**
     * Never log the exception as is: for I/O errors its message contains the request URL, and
     * the bot token is part of that URL. Class name plus HTTP status is enough to diagnose.
     */
    static String describe(Throwable e) {
        return e instanceof RestClientResponseException r
                ? e.getClass().getSimpleName() + " (HTTP " + r.getStatusCode().value() + ")"
                : e.getClass().getSimpleName();
    }

    private List<MapRecord<String, Object, Object>> read(ReadOffset offset) {
        var records = redis.opsForStream().read(consumer, StreamReadOptions.empty().count(20),
                StreamOffset.create(EventStreamReader.STREAM, offset));
        return records == null ? List.of() : records;
    }

    private void send(Map<String, String> event) {
        telegram.post().uri("/sendMessage").contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("chat_id", chatId, "text", text(event), "parse_mode", "HTML",
                        "disable_web_page_preview", true))
                .retrieve()
                .toBodilessEntity();
    }

    /** The message as posted: the environment prefix, if any, then the formatted event. */
    String text(Map<String, String> event) {
        return prefix + format(event);
    }

    // Old queued entries predate the producer's index filter.
    static boolean eligibleForDelivery(Map<String, String> event) {
        return "1".equals(event.get("index_filtered")) && !event.getOrDefault("tickers", "").isBlank();
    }

    static String format(Map<String, String> e) {
        String icon = switch (e.getOrDefault("sentiment", "")) {
            case "bullish" -> "🟢";
            case "bearish" -> "🔴";
            default -> "⚪";
        };
        String tickers = e.getOrDefault("tickers", "");
        String events = e.getOrDefault("events", "");
        return icon + (tickers.isBlank() ? "" : " <b>" + HtmlUtils.htmlEscape(tickers) + "</b>")
                + (e.getOrDefault("form_type", "").isBlank() ? "" : " · " + HtmlUtils.htmlEscape(e.get("form_type")))
                + "\n" + HtmlUtils.htmlEscape(e.getOrDefault("title", ""))
                + "\n" + HtmlUtils.htmlEscape(e.getOrDefault("sentiment", "?")) + " (" + e.getOrDefault("sentiment_score", "?")
                + ") · materiality " + e.getOrDefault("materiality", "?")
                + (events.isBlank() ? "" : "\n" + HtmlUtils.htmlEscape(events.replace(",", ", ")))
                + "\n<a href=\"" + HtmlUtils.htmlEscape(e.getOrDefault("url", "")) + "\">source</a>";
    }
}
