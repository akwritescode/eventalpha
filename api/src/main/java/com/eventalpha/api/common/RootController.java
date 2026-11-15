package com.eventalpha.api.common;

import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

/** The bare host (and "/docs/") lands on the API docs instead of a 404 error page. */
@Hidden
@Controller
class RootController {

    @GetMapping({"/", "/docs/"})
    String root() {
        return "redirect:/docs";
    }
}
