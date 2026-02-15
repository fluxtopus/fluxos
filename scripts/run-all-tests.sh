#!/usr/bin/env bash
#
# Monorepo Test Suite
#
# This script runs all tests with minimal manual interaction:
# 1. Unit tests (mocked, no external dependencies)
# 2. E2E tests with Playwright (marketing site)
#
# Usage:
#   ./scripts/run-all-tests.sh              # Run all tests
#   ./scripts/run-all-tests.sh --unit       # Unit tests only
#   ./scripts/run-all-tests.sh --integration # Integration tests only
#   ./scripts/run-all-tests.sh --e2e        # E2E tests only
#   ./scripts/run-all-tests.sh --quick      # Skip slow tests
#
# Environment variables (optional):
#   STRIPE_SECRET_KEY - Stripe test mode key (sk_test_xxx)
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# Counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# Parse arguments
RUN_UNIT=true
RUN_E2E=true
QUICK_MODE=false

for arg in "$@"; do
    case $arg in
        --unit)
            RUN_INTEGRATION=false
            RUN_E2E=false
            ;;
        --e2e)
            RUN_UNIT=false
            ;;
        --quick)
            QUICK_MODE=true
            ;;
        --help)
            echo "Usage: $0 [--unit|--e2e] [--quick]"
            exit 0
            ;;
    esac
done

# Print banner
echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                MONOREPO TEST SUITE                            ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check environment
echo -e "${YELLOW}Checking environment...${NC}"

check_env() {
    local var_name=$1
    local required=$2
    if [ -z "${!var_name}" ]; then
        if [ "$required" = "true" ]; then
            echo -e "  ${RED}✗${NC} $var_name not set (required)"
            return 1
        else
            echo -e "  ${YELLOW}○${NC} $var_name not set (optional)"
            return 0
        fi
    else
        echo -e "  ${GREEN}✓${NC} $var_name configured"
        return 0
    fi
}

# Check required tools
command -v docker >/dev/null 2>&1 || { echo -e "${RED}Docker is required but not installed.${NC}"; exit 1; }

echo ""
echo "Environment variables:"
check_env "STRIPE_SECRET_KEY" false

echo ""

# ============================================================================
# Unit Tests
# ============================================================================

if [ "$RUN_UNIT" = true ]; then
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}Running Unit Tests${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    run_py_unit() {
        local name=$1
        local path=$2
        local test_network=""
        local redis_container=""
        local postgres_container=""
        local env_args=()
        if [ ! -d "$path" ]; then
            echo -e "${YELLOW}○${NC} $name skipped (missing $path)"
            TESTS_SKIPPED=$((TESTS_SKIPPED + 1))
            return 0
        fi
        if [ ! -f "$path/requirements.txt" ]; then
            echo -e "${YELLOW}○${NC} $name skipped (no requirements.txt)"
            TESTS_SKIPPED=$((TESTS_SKIPPED + 1))
            return 0
        fi
        if [ ! -d "$path/tests" ]; then
            echo -e "${YELLOW}○${NC} $name skipped (no tests/)"
            TESTS_SKIPPED=$((TESTS_SKIPPED + 1))
            return 0
        fi
        if [ ! -d "$path/tests/unit" ]; then
            echo -e "${YELLOW}○${NC} $name skipped (no tests/unit)"
            TESTS_SKIPPED=$((TESTS_SKIPPED + 1))
            return 0
        fi

        echo -e "${BLUE}Running $name unit tests...${NC}"

        # Some test suites expect service hostnames (e.g., `redis`, `postgres`) to be reachable.
        # Provide minimal sidecars when needed.
        if [ "$name" = "Tentackl" ]; then
            test_network="unit-${path//\//-}"
            redis_container="${test_network}-redis"
            postgres_container="${test_network}-postgres"
            docker network create "$test_network" >/dev/null 2>&1 || true
            docker rm -f "$redis_container" >/dev/null 2>&1 || true
            docker run -d --name "$redis_container" --network "$test_network" --network-alias redis redis:7-alpine >/dev/null

            docker rm -f "$postgres_container" >/dev/null 2>&1 || true
            docker run -d \
                --name "$postgres_container" \
                --network "$test_network" \
                --network-alias postgres \
                -e POSTGRES_USER=tentackl \
                -e POSTGRES_PASSWORD=tentackl_pass \
                -e POSTGRES_DB=tentackl_db \
                pgvector/pgvector:pg16 >/dev/null

            # Postgres may briefly restart during initdb; require a successful psql round-trip.
            # Avoid bash brace-expansion so this works even if braceexpand is disabled via shell config.
            for i in $(seq 1 90); do
                if docker exec "$postgres_container" pg_isready -U tentackl -d postgres >/dev/null 2>&1 \
                    && docker exec "$postgres_container" psql -U tentackl -d postgres -c "SELECT 1" >/dev/null 2>&1; then
                    break
                fi
                sleep 1
            done
            if ! docker exec "$postgres_container" psql -U tentackl -d postgres -c "SELECT 1" >/dev/null 2>&1; then
                echo -e "${RED}✗${NC} Tentackl Postgres sidecar did not become ready"
                docker logs --tail=80 "$postgres_container" || true
                docker rm -f "$redis_container" >/dev/null 2>&1 || true
                docker rm -f "$postgres_container" >/dev/null 2>&1 || true
                docker network rm "$test_network" >/dev/null 2>&1 || true
                return 1
            fi

            # Ensure the requested DB exists (race-free across images/entrypoints).
            tentackl_db_exists="$(
                docker exec "$postgres_container" psql -U tentackl -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='tentackl_db'" 2>/dev/null \
                | tr -d '[:space:]' \
                || true
            )"
            if [ "$tentackl_db_exists" != "1" ]; then
                docker exec "$postgres_container" psql -U tentackl -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE tentackl_db;" >/dev/null
            fi

            # Wait for the requested DB to be available and enable pgvector.
            for i in $(seq 1 30); do
                if docker exec "$postgres_container" psql -U tentackl -d tentackl_db -c "SELECT 1" >/dev/null 2>&1; then
                    break
                fi
                sleep 1
            done
            if ! docker exec "$postgres_container" psql -U tentackl -d tentackl_db -c "SELECT 1" >/dev/null 2>&1; then
                echo -e "${RED}✗${NC} Tentackl Postgres sidecar DB 'tentackl_db' did not become available"
                docker logs --tail=80 "$postgres_container" || true
                docker rm -f "$redis_container" >/dev/null 2>&1 || true
                docker rm -f "$postgres_container" >/dev/null 2>&1 || true
                docker network rm "$test_network" >/dev/null 2>&1 || true
                return 1
            fi

            # Ensure pgvector extension exists (some models rely on it).
            for i in $(seq 1 30); do
                if docker exec "$postgres_container" psql -U tentackl -d tentackl_db -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null 2>&1; then
                    break
                fi
                sleep 1
            done
            if ! docker exec "$postgres_container" psql -U tentackl -d tentackl_db -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null 2>&1; then
                echo -e "${RED}✗${NC} Tentackl Postgres sidecar could not enable pgvector"
                docker logs --tail=80 "$postgres_container" || true
                docker rm -f "$redis_container" >/dev/null 2>&1 || true
                docker rm -f "$postgres_container" >/dev/null 2>&1 || true
                docker network rm "$test_network" >/dev/null 2>&1 || true
                return 1
            fi

            env_args+=(
                -e DATABASE_URL="postgresql://tentackl:tentackl_pass@postgres:5432/tentackl_db"
                -e REDIS_URL="redis://redis:6379/0"
            )
        fi

        if [ "$name" = "InkPass" ]; then
            test_network="unit-${path//\//-}"
            postgres_container="${test_network}-postgres"
            docker network create "$test_network" >/dev/null 2>&1 || true
            docker rm -f "$postgres_container" >/dev/null 2>&1 || true
            docker run -d \
                --name "$postgres_container" \
                --network "$test_network" \
                --network-alias postgres \
                -e POSTGRES_USER=postgres \
                -e POSTGRES_PASSWORD=postgres_master_pass \
                -e POSTGRES_DB=inkpass \
                pgvector/pgvector:pg16 >/dev/null

            # Postgres may briefly restart during initdb; require a successful psql round-trip.
            # Avoid bash brace-expansion so this works even if braceexpand is disabled via shell config.
            for i in $(seq 1 90); do
                if docker exec "$postgres_container" pg_isready -U postgres -d postgres >/dev/null 2>&1 \
                    && docker exec "$postgres_container" psql -U postgres -d postgres -c "SELECT 1" >/dev/null 2>&1; then
                    break
                fi
                sleep 1
            done
            if ! docker exec "$postgres_container" psql -U postgres -d postgres -c "SELECT 1" >/dev/null 2>&1; then
                echo -e "${RED}✗${NC} InkPass Postgres sidecar did not become ready"
                docker logs --tail=80 "$postgres_container" || true
                docker rm -f "$postgres_container" >/dev/null 2>&1 || true
                docker network rm "$test_network" >/dev/null 2>&1 || true
                return 1
            fi

            # Ensure the requested DB exists (race-free across images/entrypoints).
            inkpass_db_exists="$(
                docker exec "$postgres_container" psql -U postgres -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='inkpass'" 2>/dev/null \
                | tr -d '[:space:]' \
                || true
            )"
            if [ "$inkpass_db_exists" != "1" ]; then
                docker exec "$postgres_container" psql -U postgres -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE inkpass;" >/dev/null
            fi

            # Wait for the requested DB to be available and enable pgvector.
            for i in $(seq 1 30); do
                if docker exec "$postgres_container" psql -U postgres -d inkpass -c "SELECT 1" >/dev/null 2>&1; then
                    break
                fi
                sleep 1
            done
            if ! docker exec "$postgres_container" psql -U postgres -d inkpass -c "SELECT 1" >/dev/null 2>&1; then
                echo -e "${RED}✗${NC} InkPass Postgres sidecar DB 'inkpass' did not become available"
                docker logs --tail=50 "$postgres_container" || true
                docker rm -f "$postgres_container" >/dev/null 2>&1 || true
                docker network rm "$test_network" >/dev/null 2>&1 || true
                return 1
            fi

            for i in $(seq 1 30); do
                if docker exec "$postgres_container" psql -U postgres -d inkpass -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null 2>&1; then
                    break
                fi
                sleep 1
            done
            if ! docker exec "$postgres_container" psql -U postgres -d inkpass -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null 2>&1; then
                echo -e "${RED}✗${NC} InkPass Postgres sidecar could not enable pgvector"
                docker logs --tail=50 "$postgres_container" || true
                docker rm -f "$postgres_container" >/dev/null 2>&1 || true
                docker network rm "$test_network" >/dev/null 2>&1 || true
                return 1
            fi

            env_args+=(
                -e APP_ENV="test"
                -e DATABASE_URL="postgresql://postgres:postgres_master_pass@postgres:5432/inkpass"
                -e TEST_DATABASE_URL="postgresql://postgres:postgres_master_pass@postgres:5432/inkpass"
                -e SECRET_KEY="test-secret-key"
                -e JWT_SECRET_KEY="test-jwt-secret-key"
                -e ENCRYPTION_KEY="test-encryption-key"
            )
        fi

        if [ "$name" = "Mimic" ]; then
            # Mimic unit tests override DB dependencies to use an in-memory SQLite engine.
            # Ensure the app doesn't touch the configured DB on startup.
            env_args+=(
                -e APP_ENV="test"
            )
        fi

        local network_args=()
        if [ -n "$test_network" ]; then
            network_args+=(--network "$test_network")
        fi

        if docker run --rm \
            "${network_args[@]}" \
            "${env_args[@]}" \
            -e PYTHONDONTWRITEBYTECODE=1 \
            -e HYPOTHESIS_STORAGE_DIRECTORY=/tmp/hypothesis \
            -v "$PROJECT_ROOT:/repo" \
            -w "/repo/$path" \
            python:3.11-slim \
            bash -lc "DEBIAN_FRONTEND=noninteractive apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq gcc >/dev/null && pip install -q -r requirements.txt pytest pytest-asyncio && python -m pytest tests/unit -v --tb=short --no-cov -p no:cacheprovider"; then
            echo -e "${GREEN}✓ $name unit tests passed${NC}"
            TESTS_PASSED=$((TESTS_PASSED + 1))
        else
            echo -e "${RED}✗ $name unit tests failed${NC}"
            TESTS_FAILED=$((TESTS_FAILED + 1))
        fi

        if [ -n "$redis_container" ]; then
            docker rm -f "$redis_container" >/dev/null 2>&1 || true
        fi
        if [ -n "$postgres_container" ]; then
            docker rm -f "$postgres_container" >/dev/null 2>&1 || true
        fi
        if [ -n "$test_network" ]; then
            docker network rm "$test_network" >/dev/null 2>&1 || true
        fi
    }

    run_py_unit "Tentackl" "apps/tentackl"
    run_py_unit "InkPass" "apps/inkpass"
    run_py_unit "Mimic" "apps/mimic"
    echo ""
fi

# ============================================================================
# E2E Tests (Playwright)
# ============================================================================

if [ "$RUN_E2E" = true ]; then
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}Running E2E Tests (Playwright)${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    # Docker-only E2E runner (no host Node/npm required).
    # Match Playwright version pinned by frontends/aios-landing/package-lock.json.
    PLAYWRIGHT_IMAGE="mcr.microsoft.com/playwright:v1.58.2-jammy"
    PLAYWRIGHT_ARGS=()
    if [ "$QUICK_MODE" = true ]; then
        PLAYWRIGHT_ARGS+=(--project=chromium --retries=0)
    fi

    if docker run --rm --ipc=host \
        -u "$(id -u):$(id -g)" \
        -e CI=true \
        -e HOME=/tmp \
        -v "$PROJECT_ROOT:/repo" \
        -w "/repo/frontends/aios-landing" \
        "$PLAYWRIGHT_IMAGE" \
        bash -lc "npm ci --silent && npx playwright test ${PLAYWRIGHT_ARGS[*]}"; then
        echo -e "${GREEN}✓ E2E tests passed${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo -e "${RED}✗ E2E tests failed${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi

    echo ""
fi

# ============================================================================
# Summary
# ============================================================================

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Test Summary${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${GREEN}Passed:${NC}  $TESTS_PASSED"
echo -e "  ${RED}Failed:${NC}  $TESTS_FAILED"
echo -e "  ${YELLOW}Skipped:${NC} $TESTS_SKIPPED"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                    ALL TESTS PASSED!                          ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    exit 0
else
    echo -e "${RED}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║                    SOME TESTS FAILED                          ║${NC}"
    echo -e "${RED}╚═══════════════════════════════════════════════════════════════╝${NC}"
    exit 1
fi
