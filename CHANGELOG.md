# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Error ingestion API with fingerprint-based deduplication
- Web dashboard for viewing projects, errors, and team members
- Background worker for automated fix generation using Claude Code
- Google OAuth authentication with invitation-gated registration
- Multi-tenant organization support with role-based access control
- GitHub token encryption at rest (Fernet)
- API key management with hash-based storage
- Structured JSON logging with structlog
