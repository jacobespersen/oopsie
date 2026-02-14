# Oopsie - AI-Powered Error Fix Service

## Project Overview

Oopsie is a self-hosted service that receives error reports from applications, tracks their frequency, and automatically generates fix PRs using Claude Code when errors exceed a configured threshold.

**Core value proposition:** Wake up to AI-generated fix PRs ready for review, keeping your codebase relatively error-free without dedicated bug-fix time.

## Tech Stack

- **Language:** Python
- **Web framework:** FastAPI
- **Database:** PostgreSQL
- **Background jobs:** Simple asyncio worker polling the DB (no Celery needed at this scale)
- **AI agent:** Claude Code CLI in headless mode
- **Git operations:** GitPython or subprocess calls to git
- **GitHub integration:** `gh` CLI or GitHub API via PyGithub

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Your App       │────▶│  Oopsie API     │────▶│  PostgreSQL     │
│  (sends errors) │     │  (FastAPI)      │     │  (stores errors)│
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                        ┌─────────────────┐     ┌─────────────────┐
                        │  GitHub         │◀────│  Worker         │
                        │  (PR created)   │     │  (runs Claude)  │
                        └─────────────────┘     └─────────────────┘
```

## Database Schema

### Tables

**projects**
- id (uuid, primary key)
- name (string)
- github_repo_url (string) - e.g., "https://github.com/tonsser/backend"
- github_token (string, encrypted) - PAT with repo access
- default_branch (string, default: "main")
- error_threshold (integer, default: 10) - number of occurrences before attempting fix
- api_key (string) - for authenticating error reports
- created_at (timestamp)
- updated_at (timestamp)

**errors**
- id (uuid, primary key)
- project_id (uuid, foreign key)
- error_class (string) - e.g., "NoMethodError"
- message (string) - e.g., "undefined method 'full_name' for nil:NilClass"
- stack_trace (text)
- fingerprint (string, indexed) - hash of error_class + message + first app frame, for deduplication
- occurrence_count (integer, default: 1)
- first_seen_at (timestamp)
- last_seen_at (timestamp)
- status (enum: "open", "fix_attempted", "fix_merged", "ignored")
- created_at (timestamp)
- updated_at (timestamp)

**fix_attempts**
- id (uuid, primary key)
- error_id (uuid, foreign key)
- status (enum: "pending", "running", "success", "failed")
- branch_name (string, nullable)
- pr_url (string, nullable)
- claude_output (text, nullable) - raw output from Claude Code
- started_at (timestamp, nullable)
- completed_at (timestamp, nullable)
- created_at (timestamp)

## API Endpoints

### Error Ingestion

```
POST /api/v1/errors
Headers:
  Authorization: Bearer <project_api_key>
Body:
{
  "error_class": "NoMethodError",
  "message": "undefined method 'full_name' for nil:NilClass",
  "stack_trace": "app/models/user.rb:42:in `display_name'\napp/controllers/users_controller.rb:15:in `show'\n..."
}
```

This endpoint:
1. Validates the API key, identifies the project
2. Generates a fingerprint from error_class + message + first app frame
3. Upserts the error: if fingerprint exists, increment count and update last_seen_at; otherwise create new
4. Returns 202 Accepted

### Dashboard (minimal for v1)

```
GET /api/v1/projects/{project_id}/errors
GET /api/v1/projects/{project_id}/errors/{error_id}
GET /api/v1/projects/{project_id}/fix-attempts
```

### Project Management

```
POST /api/v1/projects - Create a new project
GET /api/v1/projects/{project_id} - Get project details
PATCH /api/v1/projects/{project_id} - Update settings (threshold, etc.)
POST /api/v1/projects/{project_id}/regenerate-api-key - Generate new API key
```

## Background Worker

A simple async worker that runs continuously:

```python
async def worker_loop():
    while True:
        # Find errors that:
        # - Have status "open"
        # - Have occurrence_count >= project.error_threshold
        # - Have no pending/running fix_attempts
        
        errors_to_fix = await get_errors_ready_for_fix()
        
        for error in errors_to_fix:
            await attempt_fix(error)
        
        await asyncio.sleep(60)  # Check every minute
```

## Fix Pipeline (Core Logic)

```python
import tempfile
import subprocess
from pathlib import Path

async def attempt_fix(error: Error):
    project = error.project
    
    # 1. Create fix_attempt record
    fix_attempt = await create_fix_attempt(error_id=error.id, status="running")
    
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 2. Clone the repo
            repo_url = inject_token(project.github_repo_url, project.github_token)
            subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, tmp_dir],
                check=True
            )
            
            # 3. Create a branch
            branch_name = f"oopsie/fix-{error.id[:8]}"
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=tmp_dir,
                check=True
            )
            
            # 4. Run Claude Code
            prompt = f"""Fix this error:
{error.error_class}: {error.message}

Stack trace:
{error.stack_trace}

Find the relevant files, understand the issue, and implement a fix.
Do not add any unrelated changes."""

            result = subprocess.run(
                [
                    "claude", "-p", prompt,
                    "--allowedTools", "Read,Write,Edit,Bash(git diff)",
                    "--permission-mode", "acceptEdits",
                    "--output-format", "json"
                ],
                cwd=tmp_dir,
                capture_output=True,
                text=True
            )
            
            # 5. Check if any files changed
            diff_result = subprocess.run(
                ["git", "diff", "--stat"],
                cwd=tmp_dir,
                capture_output=True,
                text=True
            )
            
            if not diff_result.stdout.strip():
                # No changes made
                await update_fix_attempt(
                    fix_attempt.id,
                    status="failed",
                    claude_output=result.stdout
                )
                return
            
            # 6. Commit and push
            subprocess.run(["git", "add", "-A"], cwd=tmp_dir, check=True)
            subprocess.run(
                ["git", "commit", "-m", f"Fix {error.error_class}: {error.message[:50]}"],
                cwd=tmp_dir,
                check=True
            )
            subprocess.run(
                ["git", "push", "-u", "origin", branch_name],
                cwd=tmp_dir,
                check=True
            )
            
            # 7. Create PR using gh CLI
            pr_body = f"""## Automated fix by Oopsie

**Error:** {error.error_class}
**Message:** {error.message}
**Occurrences:** {error.occurrence_count}
**First seen:** {error.first_seen_at}
**Last seen:** {error.last_seen_at}

### Stack trace
```
{error.stack_trace}
```

---
*This PR was automatically generated by [Oopsie](https://github.com/yourname/oopsie)*
"""
            
            pr_result = subprocess.run(
                [
                    "gh", "pr", "create",
                    "--title", f"[Oopsie] Fix {error.error_class}: {error.message[:50]}",
                    "--body", pr_body,
                    "--base", project.default_branch,
                    "--head", branch_name
                ],
                cwd=tmp_dir,
                capture_output=True,
                text=True,
                env={**os.environ, "GH_TOKEN": project.github_token}
            )
            
            pr_url = pr_result.stdout.strip()
            
            # 8. Update records
            await update_fix_attempt(
                fix_attempt.id,
                status="success",
                branch_name=branch_name,
                pr_url=pr_url,
                claude_output=result.stdout
            )
            await update_error(error.id, status="fix_attempted")
            
    except Exception as e:
        await update_fix_attempt(
            fix_attempt.id,
            status="failed",
            claude_output=str(e)
        )
```

## Project Structure

```
oopsie/
├── pyproject.toml
├── README.md
├── alembic/                    # Database migrations
│   └── versions/
├── oopsie/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # Settings via pydantic-settings
│   ├── database.py             # SQLAlchemy setup
│   ├── models/
│   │   ├── __init__.py
│   │   ├── project.py
│   │   ├── error.py
│   │   └── fix_attempt.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py             # Dependency injection (db session, auth)
│   │   ├── errors.py           # Error ingestion endpoint
│   │   └── projects.py         # Project management endpoints
│   ├── worker/
│   │   ├── __init__.py
│   │   └── fix_worker.py       # Background worker
│   ├── services/
│   │   ├── __init__.py
│   │   ├── error_service.py    # Error deduplication logic
│   │   ├── fix_service.py      # Claude Code + Git + PR logic
│   │   └── github_service.py   # GitHub API helpers
│   └── utils/
│       ├── __init__.py
│       ├── fingerprint.py      # Error fingerprinting
│       └── encryption.py       # Token encryption
├── tests/
│   ├── __init__.py
│   ├── test_api/
│   └── test_services/
└── docker-compose.yml          # Postgres for local dev
```

## Implementation Phases

### Phase 1: Fix Pipeline (prove it works)

Create a standalone script that:
1. Takes an error payload from a JSON file
2. Clones a repo
3. Runs Claude Code
4. Creates a branch, commits, pushes, opens PR

Test this manually with a real error from your Rails app to validate the approach.

Files to create:
- `oopsie/services/fix_service.py`
- `scripts/test_fix.py` (temporary test script)

### Phase 2: Error Ingestion API

Set up FastAPI with the error ingestion endpoint:
1. Database models and migrations
2. POST /api/v1/errors endpoint
3. Fingerprinting and deduplication logic

Files to create:
- `oopsie/main.py`
- `oopsie/database.py`
- `oopsie/config.py`
- `oopsie/models/*.py`
- `oopsie/api/errors.py`
- `oopsie/services/error_service.py`
- `oopsie/utils/fingerprint.py`
- `alembic/` setup

### Phase 3: Background Worker

Connect the fix pipeline to the database:
1. Worker loop that polls for errors above threshold
2. Queue management (don't run multiple fixes simultaneously)
3. Status tracking

Files to create:
- `oopsie/worker/fix_worker.py`

### Phase 4: Project Management

Add multi-project support:
1. Project CRUD endpoints
2. API key authentication
3. Token encryption for stored GitHub tokens

Files to create:
- `oopsie/api/projects.py`
- `oopsie/utils/encryption.py`

### Phase 5: Minimal Dashboard

Simple web UI showing:
- Errors above threshold
- Fix attempt status
- Links to PRs

This could be a simple Jinja2 template or a separate frontend.

## Configuration

Environment variables:
```
DATABASE_URL=postgresql://user:pass@localhost:5432/mend
ENCRYPTION_KEY=<generated-key-for-token-encryption>
ANTHROPIC_API_KEY=<for-claude-code>
```

## SDK (Future)

A simple Python/Ruby SDK for reporting errors:

```python
# Python
from oopsie import Oopsie

oopsie = Oopsie(api_key="your-project-api-key")

try:
    do_something()
except Exception as e:
    oopsie.report(e)
    raise
```

```ruby
# Ruby
require 'oopsie'

Oopsie.configure do |config|
  config.api_key = 'your-project-api-key'
end

# In your Rails app
class ApplicationController < ActionController::Base
  rescue_from StandardError do |e|
    Oopsie.report(e)
    raise
  end
end
```

## Notes

- Error threshold default is 10 occurrences before attempting a fix
- Expected volume: ~140 errors/day based on current New Relic data
- Clone repos fresh each time (simple, clean, acceptable latency for overnight runs)
- Use `--depth 1` for shallow clones to speed things up
- Single worker process is fine for v1 (no need for distributed job queue)

## Getting Started

```bash
# Create the project
mkdir oopsie && cd oopsie

# Set up Python environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install fastapi uvicorn sqlalchemy asyncpg alembic pydantic-settings

# Start with Phase 1 - create the fix service and test it manually
```
