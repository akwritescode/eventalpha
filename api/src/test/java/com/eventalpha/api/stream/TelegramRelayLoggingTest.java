package com.eventalpha.api.stream;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.ResourceAccessException;

class TelegramRelayLoggingTest {

    private static final String TOKEN = "123456:SECRET-TOKEN";

    @Test
    void ioErrorsAreDescribedWithoutTheRequestUrl() {
        // RestClient puts the full URL, bot token included, into I/O error messages.
        var e = new ResourceAccessException("I/O error on POST request for \"https://api.telegram.org/bot"
                + TOKEN + "/sendMessage\": Connection reset", new IOException("Connection reset"));
        assertThat(e.toString()).contains(TOKEN);
        assertThat(TelegramRelay.describe(e)).isEqualTo("ResourceAccessException").doesNotContain(TOKEN);
    }

    @Test
    void httpErrorsKeepTheirStatus() {
        var e = HttpClientErrorException.create(HttpStatus.BAD_REQUEST, "Bad Request", null, null, null);
        assertThat(TelegramRelay.describe(e)).isEqualTo("BadRequest (HTTP 400)");
    }
}
