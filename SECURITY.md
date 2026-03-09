# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Oopsie, please report it responsibly. **Do not open a public GitHub issue.**

Email: **jacobespersen@gmail.com**

Please include:

- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

I will respond as soon as possible. We will work with you to understand the issue and coordinate a fix before any public disclosure.

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest  | Yes       |

## Security Practices

- GitHub tokens are encrypted at rest using Fernet symmetric encryption
- API keys are stored as irreversible hashes (SHA-256)
- Authentication uses JWT tokens with expiration and a revocation deny list
- Web sessions use secure, HTTP-only cookies
- All database queries use parameterized statements via SQLAlchemy ORM
- Dependencies are audited in CI via `pip-audit` and `bandit`
