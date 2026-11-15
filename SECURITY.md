# Security policy

## Reporting a vulnerability

Please **don't open a public issue** for security problems. Report them privately through
GitHub: **Security → Report a vulnerability** on this repository
([private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)).

Include what you found, how to reproduce it and the impact you expect. You'll get an
acknowledgement within a few days; fixes are released as soon as they're ready, and you're
credited in the advisory unless you prefer otherwise.

## Supported versions

Only the latest release on `main` gets security fixes.

## Scope

In scope: the code in this repository (pipeline, API, web UI, deployment configuration).

Out of scope: the third-party data sources and services it calls (SEC EDGAR, BLS, FRED, the
Federal Reserve, Tradier, the classifier provider, Telegram); report those to their owners.

## Public API by design

The HTTP API is intentionally public and unauthenticated: it serves the public web UI, and
everything it returns is derived from public sources (SEC filings, official statistics,
syndicated press releases). It is read-only (GET only), so there is nothing to modify or
delete, and its database connections are opened read-only (Hikari `read-only: true`).

Protections that apply instead of authentication:

* per-IP rate limiting, and a cap on concurrent stream (SSE) connections;
* input validation on every parameter (lengths, patterns, ranges);
* CORS limited to the web UI's origins (the browser-side guard; it isn't access control);
* behind Caddy, only `/api/*`, the API docs and `/actuator/health` are reachable; other
  actuator endpoints are not exposed.

The OpenAPI docs (`/docs`) are public on purpose: the API is part of what the project shows.
If the API ever serves non-public or paid data, it gets API keys and the docs move behind
them first.

## Handling secrets

API keys and tokens live only in git-ignored `.env` files; `.env.example` lists the names
with empty values. If you find a real credential anywhere in the repository or its history,
report it privately as above.
