package com.eventalpha.api.common;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Browser access from the web UI, which is served from another origin: Vercel in production
 * (the browser calls this API directly, including the SSE stream), the React dev server locally.
 * Entries are origin patterns, so `https://eventalpha-*.vercel.app` admits Vercel preview builds.
 * Read-only API, no cookies: GET only, no credentials.
 */
@Configuration
class CorsConfig implements WebMvcConfigurer {

    private final String[] origins;

    CorsConfig(@Value("${eventalpha.cors.allowed-origins:http://localhost:3000}") String origins) {
        this.origins = origins.split("\\s*,\\s*");
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**").allowedOriginPatterns(origins).allowedMethods("GET").maxAge(3600);
    }
}
