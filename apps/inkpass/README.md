# InkPass

Authentication and authorization service (FastAPI) used by this monorepo.

## Features

- Multi-organization management
- User and group management
- ABAC (Attribute-Based Access Control) permission system
- API key management
- Email/Password authentication
- Two-Factor Authentication (2FA) with TOTP
- One-Time Passwords (OTP) for password reset
- Role and permission templates

## Quick Start

Run everything from the monorepo root:

```bash
docker compose up -d --build
```

Access:
- API: `http://localhost:8004`
- API docs: `http://localhost:8004/docs`
- Health: `http://localhost:8004/health`

InkPass initializes its database schema on startup (Alembic).

## Development

```bash
./scripts/run-all-tests.sh --unit
```

## Client Library

See `packages/inkpass-sdk-python/README.md`.
