<!-- The PR title becomes the commit on main (squash merge), so it must be a Conventional Commit:
     feat(web): add ticker filter · fix(alerts): ... · docs: ...  (see CONTRIBUTING.md) -->

## What and why

<!-- What changes, and the problem it solves. Link the issue: Closes #123 -->

## How it was tested

<!-- Commands you ran, new tests, what you checked by hand. -->

- [ ] `uv run ruff check . && uv run pytest -q`
- [ ] `cd api && ./gradlew test` (if the API changed)
- [ ] `cd web && CI=true npm run build` (if the web UI changed)
- [ ] Database changes come with an Alembic migration and `scripts/export-schema.sh`

## Screenshots

<!-- For UI changes: before / after, desktop and phone width. -->

## Notes for reviewers

<!-- Anything risky, follow-ups, or decisions you'd like a second opinion on. -->
