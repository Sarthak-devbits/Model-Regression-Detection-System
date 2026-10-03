# Single entry point for every common task. Run `make help` to list them.
COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env

.DEFAULT_GOAL := help
.PHONY: help install up down logs ps redis-ping test lint fmt check clean

help: ## Show this list
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install Python deps and git hooks
	uv sync
	uv run pre-commit install

up: ## Start infrastructure containers and wait until healthy
	$(COMPOSE) up -d --wait

down: ## Stop containers (data volumes are kept)
	$(COMPOSE) down

logs: ## Follow container logs
	$(COMPOSE) logs -f

ps: ## List running containers and their health
	$(COMPOSE) ps

redis-ping: ## Check Redis answers
	$(COMPOSE) exec redis redis-cli ping

test: ## Run the test suite
	uv run pytest

lint: ## Lint without changing files
	uv run ruff check .
	uv run ruff format --check .

fmt: ## Auto-fix lint issues and format
	uv run ruff check --fix .
	uv run ruff format .

check: lint test ## Everything CI will run

clean: ## Remove caches
	rm -rf .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

# ---------- classifier service (Phase 1) ----------

classifier-dev: ## Run the classifier on port 8001 with auto-reload (real OpenAI)
	uv run uvicorn classifier_service.main:create_app --factory --reload --port 8001

classifier-fake: ## Same, with the offline fake LLM (no API key, no cost)
	LLM_PROVIDER=fake uv run uvicorn classifier_service.main:create_app --factory --reload --port 8001

classify: ## Send one email: make classify EMAIL="I was charged twice"
	uv run python scripts/try_classifier.py "$(EMAIL)"

build: ## Build all service images
	$(COMPOSE) build
