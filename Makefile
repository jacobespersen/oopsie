.PHONY: dev services web worker console setup lint test ci

export COMPOSE_PROJECT_NAME = oopsie

services:
	docker compose up -d

web:
	uvicorn oopsie.main:app --reload

worker:
	python run_worker.py

console:
	python scripts/console.py

dev: services
	honcho start

setup:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"
	.venv/bin/pre-commit install

lint:
	ruff check .
	ruff format --check .
	mypy oopsie
	bandit -r oopsie -ll

test:
	docker compose --profile test up -d
	pytest -v --cov=oopsie --cov-report=term-missing --cov-fail-under=90

ci: lint test
