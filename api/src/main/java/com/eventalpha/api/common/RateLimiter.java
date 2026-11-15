package com.eventalpha.api.common;

import java.time.Clock;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Fixed-window request counter per client key (IP). Small and dependency-free: one server,
 * in-memory state. With several API replicas this would move to Redis or the proxy.
 */
public class RateLimiter {

    static final int MAX_TRACKED_CLIENTS = 50_000;

    private record Window(long startMillis, int count) {}

    private final int limit;
    private final int maxTrackedClients;
    private final long windowMillis;
    private final Clock clock;
    private final ConcurrentHashMap<String, Window> windows = new ConcurrentHashMap<>();

    public RateLimiter(int limit, long windowMillis, Clock clock) {
        this(limit, windowMillis, clock, MAX_TRACKED_CLIENTS);
    }

    RateLimiter(int limit, long windowMillis, Clock clock, int maxTrackedClients) {
        this.limit = limit;
        this.maxTrackedClients = maxTrackedClients;
        this.windowMillis = windowMillis;
        this.clock = clock;
    }

    /** Returns 0 if the request is allowed, otherwise the seconds until the window resets. */
    public long acquire(String key) {
        long now = clock.millis();
        if (windows.size() >= maxTrackedClients && !windows.containsKey(key)) {
            windows.values().removeIf(w -> now - w.startMillis() >= windowMillis);
            if (windows.size() >= maxTrackedClients) {
                // Every tracked client is still inside its window (a flood of distinct IPs):
                // refuse new keys instead of growing the map without bound.
                return Math.max(1, windowMillis / 1000);
            }
        }
        Window w = windows.compute(key, (k, cur) ->
                cur == null || now - cur.startMillis() >= windowMillis
                        ? new Window(now, 1)
                        : new Window(cur.startMillis(), cur.count() + 1));
        if (w.count() <= limit) {
            return 0;
        }
        return Math.max(1, (w.startMillis() + windowMillis - now + 999) / 1000);
    }
}
