# Oopsie

Oopsie is a self-hosted service that receives error reports from applications, tracks their frequency, and automatically generates fix PRs using Claude Code when errors exceed a configured threshold.

## Prerequisites

- Python 3.11+
- Docker (for local Postgres)

## Setup

1. Clone the repo and go to the project directory.

2. Create and activate a virtual environment (or use an existing one):

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # On Windows: .venv\Scripts\activate
   ```

3. Install the package in editable mode:

   ```bash
   pip install -e .
   ```

4. Copy the example env file and edit if needed:

   ```bash
   cp .env.example .env
   ```

5. Start Postgres (optional for the health check; required for Phase 2):

   ```bash
   docker compose up -d
   ```

6. Run the API:

   ```bash
   uvicorn oopsie.main:app --reload
   ```

7. Open [http://localhost:8000](http://localhost:8000) for the health check, or [http://localhost:8000/docs](http://localhost:8000/docs) for the interactive API docs.

## Design and implementation phases

See [oopsie-implementation-plan.md](oopsie-implementation-plan.md) for the full architecture, database schema, API design, and phased implementation plan.
