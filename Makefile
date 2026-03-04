.PHONY: dev services web worker

services:
	docker compose up -d

web:
	uvicorn oopsie.main:app --reload

worker:
	python run_worker.py

dev: services
	honcho start
