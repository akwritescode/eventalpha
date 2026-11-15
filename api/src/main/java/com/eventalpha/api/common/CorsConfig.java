package com.eventalpha.api.common;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Browser access from the web UI. In production the UI and API share one origin behind Caddy,
 * so this only matters locally (React dev server on :3000 calling the API on :8081).
 */
@Configuration
class CorsConfig implements WebMvcConfigurer {

    private final String[] origins;

    CorsConfig(@Value("${eventalpha.cors.allowed-origins:http://localhost:3000}") String origins) {
        this.origins = origins.split("\\s*,\\s*");
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**").allowedOrigins(origins).allowedMethods("GET").maxAge(3600);
    }
}
