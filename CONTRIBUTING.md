# Contributing

## Setup

```bash
git config core.hooksPath .githooks   # once per clone: enables the shared Git hooks
uv sync                               # Python (pipeline, DAGs)
cd web && npm ci                      # web UI
```

Running the stack locally is covered in the [README](README.md#running-locally).

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
uv run ruff check . && uv run pytest -q          # Python
(cd api && ./gradlew test)                        # API (needs Docker for Testcontainers)
(cd web && CI=true npm run build)                 # web UI: lint warnings fail the build
```
