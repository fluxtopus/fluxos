# Repository Guidelines

## Project Structure & Module Organization
This repository is a monorepo for Fluxtopus services, UIs, and SDKs.

- `apps/`: deployable backend services (`tentacle`, `inkpass`, `mimic`), each with `src/`, `tests/`, and migrations.
- `frontends/`: Next.js/React apps (`tentacle-ui`, `mimic-ui`, `fluxos-landing`).
- `packages/`: shared SDKs/libraries (Python and TypeScript).
- `scripts/`: repo automation (notably `run-all-tests.sh` and package publish scripts).
- `docs/architecture/`: architecture decisions and guardrails.

For Tentacle changes, preserve DDD layering in `apps/tentacle/src/{domain,application,infrastructure,api}`.

## Build, Test, and Development Commands
From repository root:

- `cp .env.example .env && make dev`: start local stack with Docker Compose.
- `make logs`: follow service logs.
- `make stop`: stop local stack.
- `make test-all`: run Docker-based monorepo tests (`./scripts/run-all-tests.sh`).
- `./scripts/run-all-tests.sh --unit`: backend unit tests only.
- `./scripts/run-all-tests.sh --e2e`: Playwright E2E (currently `frontends/fluxos-landing`).
- `make build-python-packages`: build Python packages in `packages/` via `uv`.

Frontend examples:
- `cd frontends/tentacle-ui && npm run dev`
- `cd frontends/tentacle-ui && npm run test`

## Coding Style & Naming Conventions
- Python: 4-space indentation, `snake_case` modules/functions, `PascalCase` classes, and type hints for new/edited code.
- Tests: use `test_*.py`, `Test*`, and `test_*` naming (enforced in service `pytest.ini` files).
- Python package tooling uses `ruff`/`mypy` (and in some packages `black`) with `line-length = 100`.
- Frontend: React components in `PascalCase` files (for example `DeliveryDashboard.tsx`), utility/state modules in `camelCase`.

## Testing Guidelines
- Backends use `pytest` with strict markers and coverage reporting against `src`.
- Add or update tests whenever behavior changes; include unit coverage first, then integration/E2E if flow-level behavior changes.
- For focused backend checks, run service-specific pytest commands via Docker Compose before opening a PR.

## Commit & Pull Request Guidelines
- Follow the existing commit style: short, imperative subject lines; optional scoped prefixes where useful (for example `fix(ci): ...`).
- Keep commits focused by concern (service/UI/package).
- Branch naming rule: never prefix branch names with `codex/` or any other harness/provider label.
- Use `.github/pull_request_template.md`: include **What**, **Why**, **How to test**, and complete checklist items.
- PR messaging rule: do not include links or references to Claude, Codex, or any other AI provider/harness in PR titles, descriptions, or comments.
- Never commit secrets (`.env`, API keys, private keys). Update docs when behavior or setup changes.

## Cursor Cloud specific instructions

### Services overview

The entire dev stack (12 containers) is Docker-based. See `docker-compose.yml` for the full service graph. Key services and ports:

| Service | Port | Health endpoint |
|---|---|---|
| InkPass API | 8004 | `GET /health` |
| Tentacle API | 8005 | `GET /api/health` |
| Mimic API | 8006 | `GET /health` |
| Tentacle UI | 3000 | — |
| Mimic UI | 3001 | — |
| Landing page | 3002 | — |
| Mailpit (email) | 8025 (UI), 1025 (SMTP) | — |

### Starting the stack

```bash
cp .env.example .env   # only needed once
make dev               # docker compose up -d --build
```

After services are healthy, seed dev users:

```bash
docker compose exec inkpass python scripts/seed_dev_users.py
```

Test accounts (seeded): `admin@fluxtopus.com` / `AiosAdmin123!`, `free@example.com` / `FreeUser123!`, `plus@example.com` / `PlusUser123!`.

### Running tests

- **Unit tests**: `./scripts/run-all-tests.sh --unit` — runs Tentacle, InkPass, and Mimic unit tests in ephemeral Docker containers.
- **E2E tests**: `./scripts/run-all-tests.sh --e2e` — runs Playwright tests for `fluxos-landing` in Docker.
- **All tests**: `make test-all` (or `./scripts/run-all-tests.sh`).

### Gotchas

- Docker Compose creates `node_modules` and `.next` directories owned by root inside frontend volume mounts. If running Playwright E2E tests outside Docker (i.e., the test script's Docker container), you may need to `sudo chown -R $(id -u):$(id -g)` those directories first.
- The `run-all-tests.sh --e2e` script runs the Playwright container with `-u "$(id -u):$(id -g)"`, so host directory permissions must allow the mapped user to write.
- Frontend linting: each frontend has `npm run lint` (uses ESLint / `next lint`).
- Backend linting is handled per-service via `ruff` (check configs in each `apps/*/` directory).
