SHELL := /bin/bash
PYTHON ?= python3.13
VENV := backend/.venv
BIN := $(VENV)/bin
API_PORT ?= 8105
WEB_PORT ?= 3105
DEMO_PORT ?= 6405

.DEFAULT_GOAL := help
.PHONY: help install services services-stop migrate api web demo-app seed eval test test-unit lint typecheck format build ci clean reset-data

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

$(BIN)/python:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip

install: $(BIN)/python ## Install backend, examples and web dependencies
	$(BIN)/pip install -q -e "./backend[dev,embeddings]" -e ./examples
	cd web && pnpm install --frozen-lockfile

services: ## Start ClickHouse and Postgres from local binaries (no Docker needed)
	./scripts/local-services.sh start

services-stop: ## Stop the local ClickHouse and Postgres
	./scripts/local-services.sh stop

migrate: ## Apply Postgres migrations
	cd backend && .venv/bin/alembic upgrade head

api: ## Run the API with reload on :8105
	cd backend && .venv/bin/uvicorn --factory tracebench.main:create_app --reload --port $(API_PORT)

web: ## Run the Next.js dev server on :3105
	cd web && pnpm exec next dev -p $(WEB_PORT)

demo-app: ## Run the instrumented demo apps (eval target) on :6405
	$(BIN)/uvicorn --factory demo_apps.server:create_app --port $(DEMO_PORT)

seed: ## Load a week of demo traffic, golden datasets and eval runs into a running API
	$(BIN)/python -m demo_apps.seed --api-url http://localhost:$(API_PORT)

eval: ## Run the regression gate against the demo app (needs `make demo-app`)
	$(BIN)/tracebench eval run support-agent-golden --target http://localhost:$(DEMO_PORT)/support

test: ## Run backend (unit + integration) and web tests
	cd backend && .venv/bin/pytest -q
	cd web && pnpm test

test-unit: ## Run tests that need no databases
	cd backend && .venv/bin/pytest -q tests/unit

lint: ## Lint Python and TypeScript
	$(BIN)/ruff check backend examples
	$(BIN)/ruff format --check backend examples
	cd web && pnpm lint

typecheck: ## mypy --strict and tsc --noEmit
	cd backend && .venv/bin/mypy src tests ../examples/demo_apps
	cd web && pnpm typecheck

format: ## Auto-format Python
	$(BIN)/ruff format backend examples
	$(BIN)/ruff check --fix backend examples

build: ## Production build of the web app
	cd web && pnpm build

ci: lint typecheck test build ## Everything CI runs

reset-data: ## Drop all spans, datasets and runs (keeps schema)
	for t in spans trace_summaries span_rollup_1m tool_rollup_1h; do \
	  curl -s "http://127.0.0.1:27105/?user=tracebench&password=tracebench" --data-binary "TRUNCATE TABLE tracebench.$$t"; done
	psql -h 127.0.0.1 -p 5505 -U tracebench tracebench -qc "TRUNCATE datasets, eval_runs, eval_results, dataset_items, price_versions, model_prices CASCADE"

clean: ## Remove build artifacts and caches
	rm -rf web/.next backend/.mypy_cache backend/.pytest_cache backend/.ruff_cache
