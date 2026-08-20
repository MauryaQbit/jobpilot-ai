.PHONY: help install sync format format-check lint check lock-check migrate migrate-check test dashboard api

help: ## Show available targets
	@printf "Usage: make <target>\n\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

install: ## Install locked dependencies into a virtual environment
	uv sync --locked

sync: install ## Alias for install

format: ## Format Python sources with ruff
	uv run --locked ruff format .

format-check: ## Verify sources are formatted
	uv run --locked ruff format --check .

lint: ## Lint with ruff
	uv run --locked ruff check .

check: lint ## Alias for lint

lock-check: ## Verify uv.lock is up to date
	uv lock --check

migrate: ## Apply pending schema migrations
	uv run --locked alembic upgrade head

migrate-check: ## Verify migrations match the models
	uv run --locked alembic check

test: ## Run the test suite
	uv run --locked pytest -q

dashboard: ## Run the Streamlit dashboard
	uv run --locked jobpilot dashboard

api: ## Run the FastAPI HTTP API
	uv run --locked jobpilot api