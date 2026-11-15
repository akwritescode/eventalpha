# Common tasks. `make help` lists them.
.DEFAULT_GOAL := help
JAVA_TEST = cd api && ./gradlew test --console=plain

.PHONY: help setup up down seed lint typecheck test test-python test-api test-web check

help:  ## List the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

setup:  ## Install dependencies and enable the shared Git hooks
	git config core.hooksPath .githooks
	uv sync
	cd web && npm ci
	@[ -f .env ] || { cp .env.example .env; echo "created .env: set SEC_USER_AGENT and your API keys"; }

up:  ## Start the local stack (Airflow, Postgres, Redis, API)
	docker compose up -d

down:  ## Stop the local stack (data volumes are kept)
	docker compose down

seed:  ## Load demo data into an empty local warehouse (see examples/README.md)
	docker compose exec -T warehouse-db psql -q -U eventalpha -d eventalpha < examples/demo-data.sql

lint:  ## Ruff (lint + format check) and mypy
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

typecheck:  ## mypy only
	uv run mypy

test-python:  ## Python tests with coverage (Postgres tests need Docker)
	uv run pytest -q --cov --cov-report=term-missing:skip-covered

test-api:  ## API tests (Testcontainers: needs Docker)
	$(JAVA_TEST)

test-web:  ## Web unit tests
	cd web && CI=true npm test -- --watchAll=false

test: test-python test-api test-web  ## All tests

check: lint test  ## Everything CI runs, locally
	cd web && CI=true npm run build
