# Contributing to Oopsie

Thanks for your interest in contributing to Oopsie! This document explains how to get started.

## Getting Started

1. Fork the repository and clone your fork
2. Follow the [Quick Start](README.md#quick-start) instructions to set up your development environment
3. Create a branch for your changes (`git checkout -b my-feature`)

## Development Workflow

1. Make your changes on a feature branch
2. Add or update tests for any new or changed behavior
3. Run the full CI check locally before pushing:

   ```bash
   ruff check . && ruff format --check .
   mypy oopsie
   bandit -r oopsie -ll
   pytest -v --cov=oopsie --cov-report=term-missing --cov-fail-under=90
   ```

4. Open a pull request against `main`

## Code Style

- **Python 3.11+** with ruff (line length 88)
- **Async everywhere** — async endpoints, `AsyncSession`, `asyncpg`
- **SQLAlchemy 2.0 style** — `Mapped[]`, `mapped_column()`, `DeclarativeBase`
- **Structured logging** — `from oopsie.logging import logger; logger.info("event_name", key="value")`
- **Type annotations** — all public functions and return types should be annotated

Linting and formatting are enforced in CI. Run `ruff check . --fix && ruff format .` to auto-fix most issues.

## Testing

- Tests live in `tests/` mirroring the source structure (`tests/api/`, `tests/models/`, etc.)
- Use factory-boy factories from `tests/factories.py` for test data
- All shared fixtures are in `tests/conftest.py` — avoid creating subdirectory conftest files
- Coverage must stay at or above 90%

## Pull Request Guidelines

- Keep PRs focused — one feature or fix per PR
- Write a clear description of what changed and why
- Ensure all CI checks pass
- Add tests for new functionality

## Reporting Bugs

Open a [GitHub issue](https://github.com/jacobespersen/oopsie/issues) with:

- A clear description of the bug
- Steps to reproduce
- Expected vs actual behavior
- Python version and OS

## Feature Requests

Open a [GitHub issue](https://github.com/jacobespersen/oopsie/issues) describing:

- The problem you're trying to solve
- Your proposed solution (if any)
- Any alternatives you've considered

## License

By contributing, you agree that your contributions will be licensed under the [AGPL-3.0](LICENSE).
