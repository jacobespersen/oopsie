.PHONY: dev services web worker console

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
