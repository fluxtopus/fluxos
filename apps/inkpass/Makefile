.PHONY: help up down restart logs test test-unit test-integration test-e2e migrate migrate-up migrate-down

help:
	@echo "Available commands:"
	@echo "  make up              - Start all services"
	@echo "  make down            - Stop all services"
	@echo "  make restart         - Restart all services"
	@echo "  make logs            - View logs"
	@echo "  make test            - Run all tests"
	@echo "  make test-unit       - Run unit tests"
	@echo "  make test-integration - Run integration tests"
	@echo "  make test-e2e        - Run E2E tests"
	@echo "  make migrate         - Run database migrations"
	@echo "  make migrate-up      - Run migrations up"
	@echo "  make migrate-down    - Run migrations down"

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f api

test:
	docker compose exec api python -m pytest tests/ -v

test-unit:
	docker compose exec api python -m pytest tests/unit/ -v -m unit

test-integration:
	docker compose exec api python -m pytest tests/integration/ -v -m integration

test-e2e:
	docker compose exec api python -m pytest tests/e2e/ -v -m e2e

migrate:
	docker compose exec api alembic upgrade head

migrate-up:
	docker compose exec api alembic upgrade head

migrate-down:
	docker compose exec api alembic downgrade -1


