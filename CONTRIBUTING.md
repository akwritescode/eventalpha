# Contributing

## Setup

```bash
make setup     # git hooks (core.hooksPath .githooks), uv sync, npm ci, .env from .env.example
make help      # every task: up, down, lint, test, check, ...
```

The pre-commit hook runs `.pre-commit-config.yaml` on staged files: ruff (lint and format),
gitleaks (secrets), whitespace and YAML/JSON checks. `uv run pre-commit run --all-files`
runs it on everything. Editor settings are in `.editorconfig`.

Running the stack locally is covered in the [README](README.md#running-locally).

The web UI builds with Node 22 (CI and Vercel). Change `web/package-lock.json` with Node 22's
npm (`nvm use` reads `web/.nvmrc`): a newer npm can write a lockfile that Node 22's `npm ci`
rejects as out of sync.

## Commit messages: Conventional Commits

Every commit follows [Conventional Commits 1.0](https://www.conventionalcommits.org/en/v1.0.0/):

```
<type>(<scope>): <description>

<optional body: what changed and why, wrapped at ~100 columns>

<optional footer: BREAKING CHANGE: ..., Refs #12>
```

| Type | Use for |
|---|---|
| `feat` | a new capability (a DAG, an endpoint, a UI feature) |
| `fix` | a bug fix |
| `docs` | documentation only |
| `refactor` | code change that neither fixes a bug nor adds a feature |
| `perf` | performance |
| `test` | tests only |
| `build` | build system, Docker images, dependencies |
| `ci` | GitHub Actions |
| `style` | formatting only |
| `chore` | maintenance that fits nothing above |
| `revert` | reverting an earlier commit |

Rules the hooks and CI enforce:

* The scope is optional, lowercase: `feat(web)`, `fix(alerts)`, `docs(readme)`. Common
  scopes: `api`, `web`, `dags`, `signals`, `news`, `sec`, `macro`, `alerts`, `deploy`, `deps`.
* The description is imperative and starts lowercase ("add", not "Added"/"Add"), with no
  trailing period. Aim for a header of at most 72 characters; 100 is the hard limit (it
  leaves room for Dependabot's grouped-update titles).
* A blank line separates the header from the body.
* A breaking change adds `!` after the type/scope (`feat(api)!: ...`) and a
  `BREAKING CHANGE:` footer.

Examples:

```
feat(news): tag news items with the companies they name
fix(maintenance): pass the metadata DB URL to airflow db clean
docs(web): document running and exploring the web UI locally
```

## How it's enforced

* `.githooks/commit-msg` rejects a non-conforming message when you commit.
* `.githooks/pre-push` checks every commit you're about to push.
* CI (`commits` job) checks every commit in a push or pull request, so skipping the hooks
  with `--no-verify` still fails the build.

All three run `scripts/check-commit-msg.sh`. To fix a message that's already committed:
`git commit --amend` for the last commit, `git rebase -i` and `reword` for older ones.

## Before you push

```bash
make check     # ruff, ruff format, mypy, Python tests with coverage, API tests, web tests and build
```

CI runs the same, plus gitleaks over the pushed commits and a check that
`docker/requirements-airflow.txt` matches `pyproject.toml`. Python coverage must stay at or
above the floor in `pyproject.toml`; Postgres-backed tests (`tests/test_db.py`) and the API
tests use Testcontainers, so Docker must be running.
