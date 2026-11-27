package com.eventalpha.api.moves;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;

final class MoveBenchmarks {

    private static final Map<String, String> SECTORS = loadSectors();

    private MoveBenchmarks() {}

    static List<String> forTicker(String ticker) {
        String sector = SECTORS.get(ticker.replace('.', '-'));
        return sector == null ? List.of("SPY") : List.of("SPY", sector);
    }

    private static Map<String, String> loadSectors() {
        var groups = new Properties();
        try (var input = MoveBenchmarks.class.getResourceAsStream("/move-sector-etfs.properties")) {
            groups.load(input);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        var sectors = new HashMap<String, String>();
        groups.forEach((etf, tickers) -> {
            for (String ticker : tickers.toString().split(",")) {
                sectors.put(ticker, etf.toString());
            }
        });
        return Map.copyOf(sectors);
    }
}
