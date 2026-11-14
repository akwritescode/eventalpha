package com.eventalpha.api.common;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.time.Clock;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Per-IP limit on /api/** (health and docs are not limited). Behind Caddy the client IP comes
 * from X-Forwarded-For, which Spring applies when server.forward-headers-strategy=framework.
 */
@Component
class RateLimitFilter extends OncePerRequestFilter {

    private final RateLimiter limiter;

    RateLimitFilter(@Value("${eventalpha.rate-limit.requests-per-minute:120}") int perMinute) {
        this.limiter = new RateLimiter(perMinute, 60_000, Clock.systemUTC());
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getRequestURI().startsWith("/api/");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        long retryAfter = limiter.acquire(request.getRemoteAddr());
        if (retryAfter == 0) {
            chain.doFilter(request, response);
            return;
        }
        response.setStatus(429);
        response.setHeader("Retry-After", Long.toString(retryAfter));
        response.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
        response.getWriter().write("""
                {"type":"about:blank","title":"Too many requests","status":429,"detail":"Retry in %d s"}"""
                .formatted(retryAfter));
    }
}
