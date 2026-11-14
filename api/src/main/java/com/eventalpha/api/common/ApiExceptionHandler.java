package com.eventalpha.api.common;

import jakarta.validation.ConstraintViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

/** RFC 9457 problem details for bad parameters instead of stack traces. */
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler({ConstraintViolationException.class, HandlerMethodValidationException.class,
            IllegalArgumentException.class})
    ProblemDetail badRequest(Exception e) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, e.getMessage());
        problem.setTitle("Invalid request");
        return problem;
    }
}
