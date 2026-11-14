package com.eventalpha.api.stream;

import io.swagger.v3.oas.annotations.Operation;
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * Live feed of high-impact events as Server-Sent Events. Browsers reconnect automatically and
 * send the last ID they saw in {@code Last-Event-ID}; the stream's history fills the gap.
 *
 * Each client gets a virtual thread that polls the stream (non-blocking XREAD, 1 s sleep when
 * idle) rather than a blocking XREAD, which would pin one Redis connection per client.
 */
@RestController
class EventStreamController {

    private static final Logger log = LoggerFactory.getLogger(EventStreamController.class);
    private static final Pattern STREAM_ID = Pattern.compile("\\d{1,20}-\\d{1,20}");
    private static final Duration IDLE_POLL = Duration.ofSeconds(1);
    private static final Duration KEEPALIVE = Duration.ofSeconds(15);
    private static final Duration MAX_CONNECTION = Duration.ofMinutes(30);

    private final EventStreamReader reader;
    private final int maxClients;
    private final AtomicInteger clients = new AtomicInteger();

    EventStreamController(EventStreamReader reader, @Value("${eventalpha.stream.max-clients:100}") int maxClients) {
        this.reader = reader;
        this.maxClients = maxClients;
    }

    @Operation(summary = "Server-Sent Events feed of high-impact events; resume with the Last-Event-ID header")
    @GetMapping(path = "/api/v1/stream/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    SseEmitter stream(@RequestHeader(value = "Last-Event-ID", required = false) String lastEventId) {
        if (clients.incrementAndGet() > maxClients) {
            clients.decrementAndGet();
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "too many stream clients");
        }
        String start = lastEventId != null && STREAM_ID.matcher(lastEventId).matches() ? lastEventId : reader.latestId();
        var emitter = new SseEmitter(MAX_CONNECTION.toMillis());
        var closed = new AtomicBoolean();
        Runnable close = () -> {
            if (closed.compareAndSet(false, true)) {
                clients.decrementAndGet();
            }
        };
        emitter.onCompletion(close);
        emitter.onTimeout(close);
        emitter.onError(e -> close.run());
        Thread.ofVirtual().name("sse-events").start(() -> pump(emitter, start, closed));
        return emitter;
    }

    private void pump(SseEmitter emitter, String start, AtomicBoolean closed) {
        String last = start;
        long lastSentAt = System.nanoTime();
        try {
            while (!closed.get()) {
                var events = reader.readAfter(last, 100);
                for (var e : events) {
                    emitter.send(SseEmitter.event().id(e.id()).name("event").data(e.fields(), MediaType.APPLICATION_JSON));
                    last = e.id();
                    lastSentAt = System.nanoTime();
                }
                if (events.isEmpty()) {
                    if (System.nanoTime() - lastSentAt > KEEPALIVE.toNanos()) {
                        emitter.send(SseEmitter.event().comment("keepalive")); // keeps proxies from closing idle streams
                        lastSentAt = System.nanoTime();
                    }
                    Thread.sleep(IDLE_POLL);
                }
            }
        } catch (IOException | IllegalStateException e) {
            log.debug("stream client went away: {}", e.toString()); // normal disconnect
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } catch (RuntimeException e) {
            log.warn("event stream failed", e);
            emitter.completeWithError(e);
            return;
        }
        emitter.complete();
    }
}
