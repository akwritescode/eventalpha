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

## Handling secrets

API keys and tokens live only in git-ignored `.env` files; `.env.example` lists the names
with empty values. If you find a real credential anywhere in the repository or its history,
report it privately as above.
