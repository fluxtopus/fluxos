#!/bin/bash
# Health check script for inkPass service
# Verifies all components are running and accessible

set -e

BASE_URL="${INKPASS_URL:-http://localhost:8002}"

echo "================================"
echo "inkPass Health Check"
echo "================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Function to check endpoint
check_endpoint() {
    local name=$1
    local url=$2
    local expected_status=${3:-200}

    echo -n "Checking $name... "

    status=$(curl -s -o /dev/null -w "%{http_code}" "$url")

    if [ "$status" -eq "$expected_status" ]; then
        echo -e "${GREEN}✓ OK${NC} (HTTP $status)"
        return 0
    else
        echo -e "${RED}✗ FAILED${NC} (HTTP $status, expected $expected_status)"
        return 1
    fi
}

# Function to check service
check_service() {
    local name=$1
    local service=$2

    echo -n "Checking $name... "

    if docker compose ps | grep -q "$service.*Up"; then
        echo -e "${GREEN}✓ Running${NC}"
        return 0
    else
        echo -e "${RED}✗ Not Running${NC}"
        return 1
    fi
}

failures=0

# Check Docker services
echo -e "${BLUE}Docker Services:${NC}"
check_service "PostgreSQL" "db" || ((failures++))
check_service "Redis" "redis" || ((failures++))
check_service "API" "api" || ((failures++))
echo ""

# Check API endpoints
echo -e "${BLUE}API Endpoints:${NC}"
check_endpoint "Health" "$BASE_URL/health" 200 || ((failures++))
check_endpoint "Root" "$BASE_URL/" 200 || ((failures++))
check_endpoint "API Docs" "$BASE_URL/docs" 200 || ((failures++))
echo ""

# Check database connection
echo -e "${BLUE}Database Connection:${NC}"
echo -n "Checking PostgreSQL connection... "
if docker compose exec -T db pg_isready -U inkpass > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Connected${NC}"
else
    echo -e "${RED}✗ Failed${NC}"
    ((failures++))
fi

echo -n "Checking Redis connection... "
if docker compose exec -T redis redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Connected${NC}"
else
    echo -e "${RED}✗ Failed${NC}"
    ((failures++))
fi
echo ""

# Check API health details
echo -e "${BLUE}API Health Details:${NC}"
health_response=$(curl -s "$BASE_URL/health")
echo "$health_response" | jq '.'
echo ""

# Test API functionality
echo -e "${BLUE}API Functionality Tests:${NC}"

# Test 1: Register a test user
echo -n "Testing user registration... "
test_email="healthcheck_$(date +%s)@example.com"
register_response=$(curl -s -X POST "$BASE_URL/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$test_email\",
    \"password\": \"Test123!@#\",
    \"organization_name\": \"Health Check Org\"
  }")

if echo "$register_response" | jq -e '.user_id' > /dev/null 2>&1; then
    echo -e "${GREEN}✓ OK${NC}"
    user_id=$(echo "$register_response" | jq -r '.user_id')
else
    echo -e "${RED}✗ FAILED${NC}"
    echo "Response: $register_response"
    ((failures++))
fi

# Test 2: Login with test user
echo -n "Testing user login... "
login_response=$(curl -s -X POST "$BASE_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$test_email\",
    \"password\": \"Test123!@#\"
  }")

if echo "$login_response" | jq -e '.access_token' > /dev/null 2>&1; then
    echo -e "${GREEN}✓ OK${NC}"
    access_token=$(echo "$login_response" | jq -r '.access_token')
else
    echo -e "${RED}✗ FAILED${NC}"
    echo "Response: $login_response"
    ((failures++))
fi

# Test 3: Get current user with token
if [ ! -z "$access_token" ]; then
    echo -n "Testing token authentication... "
    me_response=$(curl -s "$BASE_URL/api/v1/auth/me" \
      -H "Authorization: Bearer $access_token")

    if echo "$me_response" | jq -e '.email' > /dev/null 2>&1; then
        echo -e "${GREEN}✓ OK${NC}"
    else
        echo -e "${RED}✗ FAILED${NC}"
        echo "Response: $me_response"
        ((failures++))
    fi

    # Test 4: Permission check
    echo -n "Testing permission check... "
    perm_response=$(curl -s -X POST "$BASE_URL/api/v1/auth/check?resource=test&action=read" \
      -H "Authorization: Bearer $access_token")

    if echo "$perm_response" | jq -e '.has_permission' > /dev/null 2>&1; then
        echo -e "${GREEN}✓ OK${NC}"
    else
        echo -e "${RED}✗ FAILED${NC}"
        echo "Response: $perm_response"
        ((failures++))
    fi
fi

echo ""

# Summary
echo "================================"
if [ $failures -eq 0 ]; then
    echo -e "${GREEN}All checks passed!${NC}"
    echo "inkPass is healthy and fully functional."
    exit 0
else
    echo -e "${RED}$failures check(s) failed!${NC}"
    echo "Please review the errors above."
    exit 1
fi
