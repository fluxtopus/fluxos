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

### Environment overview
Everything runs in Docker. The VM update script starts `dockerd`, copies `.env.example` to `.env` (if missing), and runs `docker compose up -d --build`. After startup, all 12 containers should be running (check with `sg docker -c "docker compose ps"`).

### Service ports (development)
| Service | URL |
|---|---|
| InkPass API | http://localhost:8004 |
| Tentacle API | http://localhost:8005 |
| Mimic API | http://localhost:8006 |
| Tentacle UI | http://localhost:3000 |
| Mimic UI | http://localhost:3001 |
| Landing page | http://localhost:3002 |
| Mailpit (email) | http://localhost:8025 |

### Docker group caveat
The `ubuntu` user is added to the `docker` group but the session may not pick it up. Use `sg docker -c "<command>"` to run Docker commands in the current shell without re-login.

### Seeding dev users
After a fresh database (first start or after `docker compose down -v`), seed users with:
```
sg docker -c "docker compose exec inkpass python scripts/seed_dev_users.py"
```
Test accounts: `admin@fluxtopus.com` / `AiosAdmin123!`, `free@example.com` / `FreeUser123!`, `plus@example.com` / `PlusUser123!`.

### Running tests
- All backend unit tests: `sg docker -c "./scripts/run-all-tests.sh --unit"` (runs in disposable Docker containers, ~3 min).
- E2E tests: `sg docker -c "./scripts/run-all-tests.sh --e2e"` (Playwright in Docker).
- Frontend tests (Tentacle UI): `sg docker -c "docker compose exec tentacle-ui npm run test -- --run"`.
- Python lint (Tentacle only has `ruff` in its image): `sg docker -c "docker compose exec tentacle ruff check src/"`.

### Known quirks
- `next lint` does not work inside frontend containers because there is no `.eslintrc` config file.
- The Tentacle UI vitest suite has 1 pre-existing test failure in `RecoveryCard.test.tsx`.
- InkPass and Mimic Docker images do not include `ruff`; linting for those services is done in CI.
