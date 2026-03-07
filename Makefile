.PHONY: dev services web worker console

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
