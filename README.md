# Oopsie

Oopsie is a self-hosted service that receives error reports from applications, tracks their frequency, and automatically generates fix PRs using Claude Code when errors exceed a configured threshold.

## Prerequisites

- Python 3.11+
- Docker (for local Postgres)
- [Honcho](https://github.com/nickstenning/honcho) (for `make dev`)

## Setup

1. Clone the repo and go to the project directory.

2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. Install the package with dev dependencies:

   ```bash
   pip install -e ".[dev]"
   ```

4. Copy the example env file and fill in the required values:

   ```bash
   cp .env.example .env
   ```

   Generate the required secrets:

   ```bash
   # Fernet key for encrypting GitHub tokens
   python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'

   # JWT secret for session tokens (min 32 characters)
   python -c 'import secrets; print(secrets.token_urlsafe(64))'
   ```

5. Set up Google OAuth (required for login):

   - Go to [Google Cloud Console — Credentials](https://console.cloud.google.com/apis/credentials)
   - Create an **OAuth 2.0 Client ID** (application type: Web application)
   - Add `http://localhost:8000/auth/callback` as an authorized redirect URI
   - Copy the client ID and secret into your `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`

6. Start Postgres and apply migrations:

   ```bash
   docker compose up -d
   alembic upgrade head
   ```

   Compose starts two databases: **postgres** (dev, port 5433) and **postgres-test** (port 5434). The test DB schema is applied automatically by the **migrate-test** service on every `up`.

## Running

The easiest way to run the full stack (web server + background worker) is:

```bash
make dev
```

This starts Docker services, then uses [Honcho](https://github.com/nickstenning/honcho) to run the processes defined in the `Procfile`:

| Process  | Command                              |
|----------|--------------------------------------|
| `web`    | `uvicorn oopsie.main:app --reload`   |
| `worker` | `python run_worker.py`               |

You can also run individual components:

```bash
make services   # start Docker services only
make web        # API server only (http://localhost:8000)
make worker     # background worker only
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) for the interactive API docs.

## Testing

Tests use a **separate test database** on port 5434. Copy `.env.example` to `.env`; it sets `TEST_DATABASE_URL` to `localhost:5434/oopsie_test`. The test DB is recreated and migrated on every `docker compose up`.

```bash
docker compose --profile test up -d   # ensure test DB is running
pytest                                # run all tests
pytest --cov                          # with coverage (fail_under=90)
```

## Linting

```bash
ruff check .          # lint
ruff check . --fix    # lint + autofix
ruff format .         # format
mypy oopsie           # type check
```

## Design and implementation phases

See [oopsie-implementation-plan.md](oopsie-implementation-plan.md) for the full architecture, database schema, API design, and phased implementation plan.
