package com.eventalpha.api.common;

import java.time.Instant;

/**
 * Every response says how fresh it is: {@code dataAsOf} is the newest timestamp in the
 * underlying data (last ingest or last score), so a client can tell stale from quiet.
 */
public record ApiResponse<T>(T data, Instant dataAsOf, Instant generatedAt) {

    public static <T> ApiResponse<T> of(T data, Instant dataAsOf) {
        return new ApiResponse<>(data, dataAsOf, Instant.now());
    }
}
