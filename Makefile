.PHONY: install dev test lint format migrate migration docker-build docker-up docker-down publish clean

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn
ALEMBIC := $(VENV)/bin/alembic
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff

install:
	python3 -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"

dev:
	$(UVICORN) app.main:app --reload --host 0.0.0.0 --port 8000

test:
	$(PYTEST)

lint:
	$(RUFF) check app tests

format:
	$(RUFF) format app tests

migrate:
	$(ALEMBIC) upgrade head

migration:
	@read -p "Migration message: " msg; \
	$(ALEMBIC) revision --autogenerate -m "$$msg"

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

publish:
	@echo "TODO: scp/deploy to audit-hq-demo.tinsu.ai (set up trong tuần 9)"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache
