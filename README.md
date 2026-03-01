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

5. Start Postgres (optional for the health check; required for the API and worker):

   ```bash
   docker compose up -d
   ```

   Compose starts two databases: **postgres** (dev, port 5433) and **postgres-test** (port 5434). The test DB is ephemeral and has the schema applied automatically by the **migrate-test** service on every `up`.

6. Apply database migrations for the **development** DB (requires postgres and dev dependencies):

   ```bash
   pip install -e ".[dev]"
   alembic upgrade head
   ```

7. Run the API:

   ```bash
   uvicorn oopsie.main:app --reload
   ```

8. Open [http://localhost:8000](http://localhost:8000) for the health check, or [http://localhost:8000/docs](http://localhost:8000/docs) for the interactive API docs.

## Development dependencies

Dev dependencies (Ruff, pytest, httpx) are optional. To install them:

```bash
pip install -e ".[dev]"
```

## Linting

Run [Ruff](https://docs.astral.sh/ruff/) (requires dev dependencies to be installed):

```bash
ruff check .
```

## Testing

Tests use a **separate test database** (not the development one). With Docker Compose, use the **postgres-test** service (port 5434). Copy `.env.example` to `.env`; it sets `TEST_DATABASE_URL` to `localhost:5434/oopsie_test` so pytest uses the test DB. The test DB is recreated and migrated on every `docker compose up`.

Run tests (requires dev dependencies to be installed):

```bash
pytest
```

## Design and implementation phases

See [oopsie-implementation-plan.md](oopsie-implementation-plan.md) for the full architecture, database schema, API design, and phased implementation plan.
