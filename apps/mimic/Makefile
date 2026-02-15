.PHONY: help setup dev build test clean migrate

help:
	@echo "Mimic Notification Service - Makefile"
	@echo ""
	@echo "Available commands:"
	@echo "  make setup     - Set up development environment"
	@echo "  make dev       - Start development servers"
	@echo "  make build     - Build Docker images"
	@echo "  make test      - Run tests"
	@echo "  make migrate   - Run database migrations"
	@echo "  make clean     - Clean up containers and volumes"

setup:
	docker compose up -d db
	sleep 5
	docker compose exec api alembic upgrade head

dev:
	docker compose up

build:
	docker compose build

test:
	docker compose exec api pytest tests/ -v

migrate:
	docker compose exec api alembic upgrade head

clean:
	docker compose down -v

