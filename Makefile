.PHONY: install dev test lint format migrate migration docker-build docker-up docker-down deploy logs clean version

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn
ALEMBIC := $(VENV)/bin/alembic
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff

BUILD_SHA  := $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)
BUILD_TIME := $(shell date -u +%Y-%m-%dT%H:%M:%SZ)
APP_VERSION := $(shell cat VERSION 2>/dev/null || echo 0.0.0)

install:
	python3 -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"

dev:
	$(UVICORN) app.main:app --reload --host 0.0.0.0 --port 8000

test:
	$(PYTEST)

lint:
	$(RUFF) check app tests scripts

format:
	$(RUFF) format app tests scripts

migrate:
	$(ALEMBIC) upgrade head

migration:
	@read -p "Migration message: " msg; \
	$(ALEMBIC) revision --autogenerate -m "$$msg"

version:
	@echo "v$(APP_VERSION) · build $(BUILD_SHA) · $(BUILD_TIME)"

docker-build:
	BUILD_SHA=$(BUILD_SHA) BUILD_TIME=$(BUILD_TIME) APP_VERSION=$(APP_VERSION) \
		docker compose build

docker-up:
	BUILD_SHA=$(BUILD_SHA) BUILD_TIME=$(BUILD_TIME) APP_VERSION=$(APP_VERSION) \
		docker compose up -d

docker-down:
	docker compose down

deploy: docker-build docker-up
	@echo ""
	@echo "✓ Deployed v$(APP_VERSION) · build $(BUILD_SHA)"
	@docker compose ps

logs:
	docker compose logs -f --tail 100

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache
