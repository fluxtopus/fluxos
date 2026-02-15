SHELL := /bin/bash

.PHONY: help dev stop logs test-all
.DEFAULT_GOAL := help

help: ## Show targets
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

dev: ## Start local stack
	@docker compose up -d --build

stop: ## Stop local stack
	@docker compose down

logs: ## Follow logs
	@docker compose logs -f

test-all: ## Run repo test script
	@./scripts/run-all-tests.sh
