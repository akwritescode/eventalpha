package com.eventalpha.api.common;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;

class RateLimiterTest {

    private final AtomicLong now = new AtomicLong(1_000_000);
    private final Clock clock = new Clock() {
        @Override public ZoneOffset getZone() { return ZoneOffset.UTC; }
        @Override public Clock withZone(java.time.ZoneId zone) { return this; }
        @Override public Instant instant() { return Instant.ofEpochMilli(now.get()); }
    };

    @Test
    void limitsPerKeyAndResetsAfterWindow() {
        var limiter = new RateLimiter(2, 60_000, clock);
        assertThat(limiter.acquire("a")).isZero();
        assertThat(limiter.acquire("a")).isZero();
        assertThat(limiter.acquire("a")).isEqualTo(60);   // third call in the window is refused
        assertThat(limiter.acquire("b")).isZero();         // other clients are unaffected

        now.addAndGet(45_000);
        assertThat(limiter.acquire("a")).isEqualTo(15);

        now.addAndGet(15_000);
        assertThat(limiter.acquire("a")).isZero();         // new window
    }

    @Test
    void trackedClientsStayCappedDuringAFloodOfNewKeys() {
        var limiter = new RateLimiter(5, 60_000, clock, 3);
        for (String k : new String[] {"a", "b", "c"}) {
            assertThat(limiter.acquire(k)).isZero();
        }
        assertThat(limiter.acquire("d")).isEqualTo(60);  // map full of active clients: new key refused
        assertThat(limiter.acquire("a")).isZero();        // known clients keep working

        now.addAndGet(60_000);                            // windows expire: room again
        assertThat(limiter.acquire("d")).isZero();
    }
}
