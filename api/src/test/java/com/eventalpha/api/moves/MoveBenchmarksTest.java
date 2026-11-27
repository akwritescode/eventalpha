package com.eventalpha.api.moves;

import static org.assertj.core.api.Assertions.assertThat;

import com.jayway.jsonpath.JsonPath;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;

class MoveBenchmarksTest {

    @Test
    void allCurrentSp500MembersHaveASectorEtf() throws Exception {
        List<String> members = JsonPath.read(Files.readString(Path.of("../config/index_members.json")), "$.indexes.sp500.symbols");
        assertThat(members).isNotEmpty();
        assertThat(members.stream().filter(ticker -> MoveBenchmarks.forTicker(ticker).size() == 1).toList())
                .as("S&P 500 members missing a sector ETF in move-sector-etfs.properties")
                .isEmpty();
    }
}
