# Tentackl

Tentackl is the task orchestration backend for **Tasks**, **Inbox (Flux)**, **Plugins**, **DB-based Agents**, and **Integrations/Triggers**.

> Workflow YAML specs are deprecated. Durable execution is task-driven.

## Fast Start (Standalone, 5 minutes)

This path runs Tentackl without InkPass or Mimic.

### 1. Prerequisites

- Docker
- Docker Compose

### 2. Configure env

```bash
cp .env.standalone.example .env.standalone
```

Edit `.env.standalone` and set at minimum:

- `TENTACKL_SECRET_KEY`
- `SECRET_KEY`
- One LLM key: `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` or `OPENROUTER_API_KEY`

### 3. Start services

```bash
docker compose -f docker-compose.standalone.yml --env-file .env.standalone up -d --build
```

### 4. Verify

```bash
curl -H "X-API-Key: tk_dev_key" http://localhost:8000/api/health
```

Open:

- API docs: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

### 5. Create your first task

```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -H "X-API-Key: tk_dev_key" \
  -d '{"input":"Research the top 3 OSS observability stacks and summarize tradeoffs.","org_id":"dev","workspace":"default"}'
```

## What It Does

- Manages task lifecycle: plan, execute, pause, resume, rerun, cancel
- Orchestrates agent execution with checkpoints and preference learning
- Powers Flux inbox interactions (inbound/outbound messaging for tasks)
- Handles integration triggers and OAuth-backed external providers
- Exposes FastAPI endpoints consumed by `tentackl-ui`

## Architecture (DDD)

Tentackl follows layered DDD boundaries:

- `src/domain`: entities, value objects, ports
- `src/application`: use cases and orchestration logic
- `src/infrastructure`: adapters (Postgres, Redis, OAuth, events, external services)
- `src/api`: HTTP transport/adapters

Main bounded contexts:

- `tasks`
- `inbox` (Flux)
- `integrations` and `triggers`
- `auth` and `oauth`
- `memory`, `capabilities`, `workspace`, `allowed_hosts`, `events`, `notifications`

## Common Commands

```bash
# Full non-e2e backend regression (main compose stack)
docker compose run --rm tentackl python -m pytest -q --ignore=tests/e2e

# Architecture guardrails
docker compose run --rm tentackl python -m pytest -q tests/architecture

# OpenAPI smoke
docker compose run --rm tentackl python -c "from fastapi.testclient import TestClient; from src.api.app import app; r=TestClient(app).get('/openapi.json'); print(r.status_code)"

# Stop standalone stack
docker compose -f docker-compose.standalone.yml --env-file .env.standalone down -v
```

## Project Layout

```text
apps/tentackl/
├── src/
│   ├── domain/
│   ├── application/
│   ├── infrastructure/
│   ├── api/
│   ├── agents/
│   ├── plugins/
│   └── core/
├── tests/
└── alembic/
```

## Documentation

- Architecture guardrails: `docs/architecture/Architecture-Guardrails.md`
