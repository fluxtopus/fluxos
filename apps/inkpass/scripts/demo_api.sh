#!/bin/bash
# Demo script for testing inkPass API
# This script demonstrates the complete authentication and authorization flow

set -e  # Exit on error

BASE_URL="http://localhost:8002"
EMAIL="demo@example.com"
PASSWORD="DemoPassword123!"
ORG_NAME="Demo Organization"

echo "================================"
echo "inkPass API Demo Script"
echo "================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Health Check
echo -e "${BLUE}Step 1: Health Check${NC}"
echo "GET $BASE_URL/health"
curl -s "$BASE_URL/health" | jq '.'
echo ""

# Step 2: Register User
echo -e "${BLUE}Step 2: Register User${NC}"
echo "POST $BASE_URL/api/v1/auth/register"
REGISTER_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$EMAIL\",
    \"password\": \"$PASSWORD\",
    \"organization_name\": \"$ORG_NAME\"
  }")

echo "$REGISTER_RESPONSE" | jq '.'
USER_ID=$(echo "$REGISTER_RESPONSE" | jq -r '.user_id')
ORG_ID=$(echo "$REGISTER_RESPONSE" | jq -r '.organization_id')
echo -e "${GREEN}✓ User created: $USER_ID${NC}"
echo -e "${GREEN}✓ Organization created: $ORG_ID${NC}"
echo ""

# Step 3: Login
echo -e "${BLUE}Step 3: Login${NC}"
echo "POST $BASE_URL/api/v1/auth/login"
LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$EMAIL\",
    \"password\": \"$PASSWORD\"
  }")

echo "$LOGIN_RESPONSE" | jq '.'
ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token')
REFRESH_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.refresh_token')
echo -e "${GREEN}✓ Login successful${NC}"
echo -e "${YELLOW}Access Token: ${ACCESS_TOKEN:0:20}...${NC}"
echo ""

# Step 4: Get Current User
echo -e "${BLUE}Step 4: Get Current User${NC}"
echo "GET $BASE_URL/api/v1/auth/me"
curl -s "$BASE_URL/api/v1/auth/me" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq '.'
echo -e "${GREEN}✓ User info retrieved${NC}"
echo ""

# Step 5: List Organizations
echo -e "${BLUE}Step 5: List Organizations${NC}"
echo "GET $BASE_URL/api/v1/organizations"
curl -s "$BASE_URL/api/v1/organizations" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq '.'
echo -e "${GREEN}✓ Organizations listed${NC}"
echo ""

# Step 6: Create a Group
echo -e "${BLUE}Step 6: Create a Group${NC}"
echo "POST $BASE_URL/api/v1/groups"
GROUP_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/groups" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"Admins\",
    \"description\": \"Administrator group\"
  }")

echo "$GROUP_RESPONSE" | jq '.'
GROUP_ID=$(echo "$GROUP_RESPONSE" | jq -r '.id')
echo -e "${GREEN}✓ Group created: $GROUP_ID${NC}"
echo ""

# Step 7: Create a Permission
echo -e "${BLUE}Step 7: Create a Permission${NC}"
echo "POST $BASE_URL/api/v1/permissions"
PERMISSION_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/permissions" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"resource\": \"workflows\",
    \"action\": \"create\",
    \"conditions\": {}
  }")

echo "$PERMISSION_RESPONSE" | jq '.'
PERMISSION_ID=$(echo "$PERMISSION_RESPONSE" | jq -r '.id')
echo -e "${GREEN}✓ Permission created: $PERMISSION_ID${NC}"
echo ""

# Step 8: Assign Permission to Group
echo -e "${BLUE}Step 8: Assign Permission to Group${NC}"
echo "POST $BASE_URL/api/v1/permissions/$PERMISSION_ID/groups"
curl -s -X POST "$BASE_URL/api/v1/permissions/$PERMISSION_ID/groups" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"group_id\": \"$GROUP_ID\"
  }" | jq '.'
echo -e "${GREEN}✓ Permission assigned to group${NC}"
echo ""

# Step 9: Add User to Group
echo -e "${BLUE}Step 9: Add User to Group${NC}"
echo "POST $BASE_URL/api/v1/groups/$GROUP_ID/users"
curl -s -X POST "$BASE_URL/api/v1/groups/$GROUP_ID/users" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"user_id\": \"$USER_ID\"
  }" | jq '.'
echo -e "${GREEN}✓ User added to group${NC}"
echo ""

# Step 10: Check Permission
echo -e "${BLUE}Step 10: Check Permission${NC}"
echo "POST $BASE_URL/api/v1/auth/check?resource=workflows&action=create"
PERMISSION_CHECK=$(curl -s -X POST "$BASE_URL/api/v1/auth/check?resource=workflows&action=create" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

echo "$PERMISSION_CHECK" | jq '.'
HAS_PERMISSION=$(echo "$PERMISSION_CHECK" | jq -r '.has_permission')
if [ "$HAS_PERMISSION" = "true" ]; then
  echo -e "${GREEN}✓ User has permission to create workflows${NC}"
else
  echo -e "${YELLOW}⚠ User does NOT have permission${NC}"
fi
echo ""

# Step 11: Create API Key
echo -e "${BLUE}Step 11: Create API Key${NC}"
echo "POST $BASE_URL/api/v1/api-keys"
API_KEY_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/api-keys" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"Demo API Key\",
    \"scopes\": [\"read\", \"write\"]
  }")

echo "$API_KEY_RESPONSE" | jq '.'
API_KEY=$(echo "$API_KEY_RESPONSE" | jq -r '.key')
echo -e "${GREEN}✓ API Key created${NC}"
echo -e "${YELLOW}API Key: ${API_KEY:0:20}...${NC}"
echo ""

# Step 12: Test API Key Authentication
echo -e "${BLUE}Step 12: Test API Key Authentication${NC}"
echo "GET $BASE_URL/api/v1/auth/me (using API key)"
curl -s "$BASE_URL/api/v1/auth/me" \
  -H "X-API-Key: $API_KEY" | jq '.'
echo -e "${GREEN}✓ API Key authentication successful${NC}"
echo ""

# Summary
echo "================================"
echo -e "${GREEN}Demo Completed Successfully!${NC}"
echo "================================"
echo ""
echo "Summary:"
echo "  User ID: $USER_ID"
echo "  Organization ID: $ORG_ID"
echo "  Group ID: $GROUP_ID"
echo "  Permission ID: $PERMISSION_ID"
echo "  Access Token: ${ACCESS_TOKEN:0:20}..."
echo "  API Key: ${API_KEY:0:20}..."
echo ""
echo "You can now use these credentials to test the API further!"
echo ""
