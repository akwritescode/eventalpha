# 0005. The web UI is served by Vercel and calls the API directly

* Status: Accepted
* Date: 2026-11-15

## Context

The React UI is static files after a build. It could be served by Caddy on the same
Lightsail instance as the API (one origin, no CORS) or by a static host.

## Decision

Vercel builds and serves `web/` from GitHub: every push to `main` deploys, every pull request
gets a preview URL. The browser calls the API on Lightsail directly, including the
Server-Sent Events stream; the API allows the Vercel origins through CORS patterns.
Proxying `/api` through Vercel was rejected because its proxy isn't built for long-lived
streaming responses.

## Consequences

* The UI deploys from GitHub with previews and a CDN, independent of backend deploys.
* Two deploy targets: a UI change that needs a new API field ships after the API.
* The production CORS list must include the Vercel domains (`EVENTALPHA_CORS_ALLOWED_ORIGINS`).
