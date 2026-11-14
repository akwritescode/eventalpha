#!/usr/bin/env bash
# Regenerate the DDL the Spring API tests run against, from Alembic (the schema owner).
# Run after every new migration; CI fails if the committed file is stale.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run alembic upgrade head --sql 2>/dev/null > api/src/test/resources/db/schema.sql
echo "wrote api/src/test/resources/db/schema.sql"
