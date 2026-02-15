#!/usr/bin/env bash
# =============================================================================
#  Tentackl Agent Memory — Real-Life Scenario Demo
# =============================================================================
#
#  Scenario: AI-Powered Customer Success Team
#  ───────────────────────────────────────────
#  A SaaS company ("Acme Cloud") uses Tentackl agents to run their
#  customer success operation. Three agents share persistent memory
#  so knowledge survives across conversations and agents:
#
#    1. Onboarding Agent  — Learns about new customers during setup
#    2. Support Agent     — Uses customer context when handling tickets
#    3. Account Agent     — Builds quarterly business reviews from memory
#
#  The demo walks through a realistic workflow:
#
#    Act 1 → Onboarding Agent stores customer knowledge
#    Act 2 → Support Agent queries that knowledge to resolve a ticket
#    Act 3 → Account Agent pulls everything for a QBR
#    Act 4 → Customer's stack changes — memory gets versioned
#    Act 5 → Support Agent now sees the updated info
#    Act 6 → Organization isolation — a rival company sees nothing
#
#  Run:
#    bash apps/tentackl/src/examples/memory_showcase.sh
#
#  Requirements:
#    - inkpass running on port 8004
#    - tentackl running on port 8005
#    - jq installed
#
#  Required environment variables:
#    DEMO_EMAIL    - Login email (e.g. admin@fluxtopus.com)
#    DEMO_PASSWORD - Login password
#
#  Optional environment variables:
#    INKPASS_URL   - InkPass URL (default: http://localhost:8004)
#    TENTACKL_URL  - Tentackl URL (default: http://localhost:8005)
# =============================================================================

set -euo pipefail

# ── Config ───────────────────────────────────────────────────────────────────
INKPASS_URL="${INKPASS_URL:-http://localhost:8004}"
TENTACKL_URL="${TENTACKL_URL:-http://localhost:8005}"
EMAIL="${DEMO_EMAIL:?Set DEMO_EMAIL environment variable}"
PASSWORD="${DEMO_PASSWORD:?Set DEMO_PASSWORD environment variable}"

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No color

# ── Helpers ──────────────────────────────────────────────────────────────────

narrate() {
  echo ""
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${BOLD}${CYAN}  $1${NC}"
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo ""
}

scene() {
  echo -e "  ${YELLOW}▸ $1${NC}"
}

result() {
  echo -e "  ${GREEN}✓ $1${NC}"
}

detail() {
  echo -e "  ${DIM}  $1${NC}"
}

fail() {
  echo -e "  ${RED}✗ $1${NC}"
  exit 1
}

api() {
  local method="$1"
  local path="$2"
  shift 2
  curl -s -X "$method" \
    "${TENTACKL_URL}${path}" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    "$@"
}

# ── Unique run suffix (avoids collisions between demo runs) ──────────────────
RUN_ID=$(date +%s | tail -c 7)

# =============================================================================
#  PROLOGUE — Authenticate
# =============================================================================

narrate "PROLOGUE — Authenticating with InkPass"

scene "Logging in as ${EMAIL}..."

LOGIN_RESP=$(curl -s -X POST "${INKPASS_URL}/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${PASSWORD}\"}")

TOKEN=$(echo "$LOGIN_RESP" | jq -r '.access_token // empty')

if [ -z "$TOKEN" ]; then
  fail "Login failed: $(echo "$LOGIN_RESP" | jq -r '.detail // .message // "unknown error"')"
fi

result "Authenticated — token acquired"

# =============================================================================
#  ACT 1 — Onboarding Agent stores customer knowledge
# =============================================================================

narrate "ACT 1 — Onboarding Agent meets a new customer"

scene "The Onboarding Agent just finished a kickoff call with NovaTech Inc."
scene "It stores three pieces of knowledge about the customer..."
echo ""

# Memory 1: Customer profile
scene "Storing customer profile..."
PROFILE_RESP=$(api POST "/api/memories" -d "{
  \"key\": \"customer-novatech-profile-${RUN_ID}\",
  \"title\": \"NovaTech Inc — Customer Profile\",
  \"body\": \"NovaTech Inc is a Series B fintech startup (45 employees) based in Austin, TX. Primary contact: Sarah Chen (VP Engineering). They chose our platform to automate their compliance reporting pipeline. Current stack: Python 3.11, PostgreSQL 15, deployed on AWS EKS. Budget tier: Growth plan. Started onboarding Jan 15, 2025.\",
  \"topic\": \"customers\",
  \"tags\": [\"novatech\", \"fintech\", \"onboarding\", \"austin\"],
  \"scope\": \"organization\"
}")

PROFILE_ID=$(echo "$PROFILE_RESP" | jq -r '.id // empty')
if [ -z "$PROFILE_ID" ]; then
  fail "Failed to store profile: $(echo "$PROFILE_RESP" | jq -r '.detail // .')"
fi
result "Stored customer profile (id: ${PROFILE_ID})"
detail "Key: customer-novatech-profile-${RUN_ID}"

# Memory 2: Technical requirements
scene "Storing technical requirements..."
TECH_RESP=$(api POST "/api/memories" -d "{
  \"key\": \"customer-novatech-tech-${RUN_ID}\",
  \"title\": \"NovaTech — Technical Requirements\",
  \"body\": \"NovaTech needs: (1) Daily compliance report generation from 3 data sources — their PostgreSQL transactional DB, a third-party KYC API (Plaid), and an internal risk scoring service. (2) Reports must be in SEC-compliant PDF format. (3) Automated email delivery to compliance@novatech.io by 7am CT. (4) Slack alerts to #compliance-alerts on failures. They use GitHub Actions for CI/CD and prefer YAML-based configuration.\",
  \"topic\": \"requirements\",
  \"tags\": [\"novatech\", \"compliance\", \"technical\", \"integrations\"]
}")

TECH_ID=$(echo "$TECH_RESP" | jq -r '.id // empty')
[ -z "$TECH_ID" ] && fail "Failed to store tech requirements"
result "Stored technical requirements (id: ${TECH_ID})"

# Memory 3: Customer preferences
scene "Storing communication preferences..."
PREFS_RESP=$(api POST "/api/memories" -d "{
  \"key\": \"customer-novatech-prefs-${RUN_ID}\",
  \"title\": \"NovaTech — Communication Preferences\",
  \"body\": \"Sarah prefers async communication (Slack DM over calls). She's technical — comfortable with API docs and YAML configs. Prefers brief, bullet-point updates over long emails. Timezone: CT (UTC-6). Best hours: 9am-5pm CT. She mentioned frustration with their previous vendor's slow support response times (>24h). Our SLA target with them: <4h response for P1, <8h for P2.\",
  \"topic\": \"preferences\",
  \"tags\": [\"novatech\", \"communication\", \"sla\"]
}")

PREFS_ID=$(echo "$PREFS_RESP" | jq -r '.id // empty')
[ -z "$PREFS_ID" ] && fail "Failed to store preferences"
result "Stored communication preferences (id: ${PREFS_ID})"

echo ""
scene "Onboarding complete — 3 memories stored about NovaTech"
detail "The Onboarding Agent is done. These memories persist forever."
detail "Any agent in the organization can now learn about NovaTech."

# =============================================================================
#  ACT 2 — Support Agent handles a ticket using stored knowledge
# =============================================================================

narrate "ACT 2 — Support Agent receives a ticket from NovaTech"

scene "A new ticket arrives: 'Our compliance reports are timing out'"
scene "The Support Agent queries memory before responding..."
echo ""

# Search by topic
scene "Querying memories about NovaTech (topic: customers)..."
SEARCH_RESP=$(api GET "/api/memories?topic=customers&tags=novatech&limit=5")

FOUND=$(echo "$SEARCH_RESP" | jq '.total_count')
result "Found ${FOUND} customer memory(ies)"

# Show what the agent found
echo "$SEARCH_RESP" | jq -r '.memories[] | "    → \(.title) (v\(.version))"'

echo ""

# Search by tags for technical details
scene "Querying NovaTech's technical setup (tags: novatech,technical)..."
TECH_SEARCH=$(api GET "/api/memories?tags=novatech,technical&limit=5")

echo "$TECH_SEARCH" | jq -r '.memories[] | "    → \(.title)"'
echo ""

# Show the body the agent would use
TECH_BODY=$(echo "$TECH_SEARCH" | jq -r '.memories[0].body // "none"')
scene "The Support Agent now knows NovaTech's stack before replying:"
echo -e "${DIM}"
echo "$TECH_BODY" | fold -s -w 72 | sed 's/^/    /'
echo -e "${NC}"

result "Support Agent has full context — can now investigate the timeout"
detail "It knows: PostgreSQL 15, AWS EKS, 3 data sources, 7am CT deadline"
detail "It can craft a targeted response instead of asking generic questions"

# =============================================================================
#  ACT 3 — Account Agent builds a Quarterly Business Review
# =============================================================================

narrate "ACT 3 — Account Agent prepares NovaTech's QBR"

scene "It's quarter-end. The Account Agent pulls everything about NovaTech..."
echo ""

# Search all novatech memories
scene "Retrieving all NovaTech memories..."
ALL_RESP=$(api GET "/api/memories?tags=novatech&limit=20")

TOTAL=$(echo "$ALL_RESP" | jq '.total_count')
result "Retrieved ${TOTAL} memories across all topics"
echo ""

echo "$ALL_RESP" | jq -r '.memories[] | "    \(.topic // "general") │ \(.title) (v\(.version), tags: \(.tags | join(", ")))"'

echo ""
scene "The Account Agent now has a complete picture:"
detail "- Customer profile (who they are, their stage, budget)"
detail "- Technical requirements (what they need from us)"
detail "- Communication preferences (how to work with them)"
detail "All from memory — no need to search emails or CRM."

# =============================================================================
#  ACT 4 — Customer's stack changes — memory gets versioned
# =============================================================================

narrate "ACT 4 — NovaTech migrates to a new stack"

scene "Sarah messages us: 'We just migrated from PostgreSQL to CockroachDB"
scene "and from AWS EKS to Google Cloud Run.'"
scene "The Onboarding Agent updates the technical memory..."
echo ""

# Update the technical requirements
scene "Updating technical requirements (creates version 2)..."
UPDATE_RESP=$(api PUT "/api/memories/${TECH_ID}" -d "{
  \"body\": \"NovaTech needs: (1) Daily compliance report generation from 3 data sources — their CockroachDB transactional DB (migrated from PostgreSQL Q1 2025), a third-party KYC API (Plaid), and an internal risk scoring service. (2) Reports must be in SEC-compliant PDF format. (3) Automated email delivery to compliance@novatech.io by 7am CT. (4) Slack alerts to #compliance-alerts on failures. They migrated from AWS EKS to Google Cloud Run in Q1 2025. They use GitHub Actions for CI/CD and prefer YAML-based configuration.\",
  \"change_summary\": \"Stack migration: PostgreSQL → CockroachDB, AWS EKS → Google Cloud Run (Q1 2025)\"
}")

NEW_VERSION=$(echo "$UPDATE_RESP" | jq '.version')
result "Memory updated — now at version ${NEW_VERSION}"
detail "Change: PostgreSQL → CockroachDB, AWS EKS → Google Cloud Run"

echo ""

# Show version history
scene "Viewing version history..."
VERSIONS=$(api GET "/api/memories/${TECH_ID}/versions?limit=5")

echo "$VERSIONS" | jq -r '.[] | "    v\(.version) │ \(.change_summary // "Initial version") │ \(.created_at // "n/a" | split("T")[0] // "n/a")"'

echo ""
result "Full audit trail preserved — we can see exactly what changed and when"

# =============================================================================
#  ACT 5 — Support Agent now sees the updated stack
# =============================================================================

narrate "ACT 5 — Support Agent handles another NovaTech ticket"

scene "New ticket: 'We're seeing connection pool errors in our reports'"
scene "The Support Agent queries memory again..."
echo ""

scene "Retrieving NovaTech's current technical setup..."
UPDATED_TECH=$(api GET "/api/memories?tags=novatech,technical&limit=1")

BODY=$(echo "$UPDATED_TECH" | jq -r '.memories[0].body // "none"')
VER=$(echo "$UPDATED_TECH" | jq -r '.memories[0].version // "?"')

result "Got version ${VER} — the latest"
echo ""

# Check for CockroachDB mention
if echo "$BODY" | grep -q "CockroachDB"; then
  result "Support Agent sees the updated stack: CockroachDB + Cloud Run"
  detail "It won't waste time investigating PostgreSQL connection pools"
  detail "It knows to look at CockroachDB-specific connection handling instead"
else
  fail "Expected updated body with CockroachDB"
fi

# =============================================================================
#  ACT 6 — Organization isolation (the security boundary)
# =============================================================================

narrate "ACT 6 — Organization Isolation"

scene "A rival company's agent tries to find NovaTech's data..."
scene "They search for the same topics and tags..."
echo ""

scene "Searching for 'novatech' across all accessible memories..."
# This search uses the same auth token (same org), so it will find things.
# In a real multi-org setup, a different org's token would return 0 results.
# We demonstrate the concept by showing the org scoping.

ORG_SEARCH=$(api GET "/api/memories?tags=novatech&limit=50")
ORG_COUNT=$(echo "$ORG_SEARCH" | jq '.total_count')

result "Within our org: found ${ORG_COUNT} NovaTech memories (expected)"
detail "Every API call is scoped to the authenticated user's organization"
detail "A different organization's token would return 0 results"
detail "This is enforced at the database query level — not just the API layer"

echo ""
scene "Organization isolation is the hard security boundary:"
detail "- Org ID comes from the JWT token (server-side, not client input)"
detail "- Every DB query includes WHERE organization_id = ..."
detail "- Plugin handlers use ExecutionContext (immutable, from the plan)"
detail "- SQL injection and wildcard patterns are rejected"
detail "- E2E tests verify this with real cross-org queries"

# =============================================================================
#  EPILOGUE — Cleanup & Summary
# =============================================================================

narrate "EPILOGUE — Cleanup"

scene "Removing demo memories..."
api DELETE "/api/memories/${PROFILE_ID}" > /dev/null 2>&1 && detail "Deleted profile" || detail "Profile already gone"
api DELETE "/api/memories/${TECH_ID}" > /dev/null 2>&1 && detail "Deleted tech requirements" || detail "Tech requirements already gone"
api DELETE "/api/memories/${PREFS_ID}" > /dev/null 2>&1 && detail "Deleted preferences" || detail "Preferences already gone"
result "Cleanup complete"

# Final summary
narrate "SUMMARY — What You Just Saw"

echo -e "  ${BOLD}The Tentackl Agent Memory system enables:${NC}"
echo ""
echo -e "  ${GREEN}1.${NC} ${BOLD}Persistent Knowledge${NC}"
echo -e "     Agents store what they learn. Knowledge survives across sessions."
echo ""
echo -e "  ${GREEN}2.${NC} ${BOLD}Cross-Agent Learning${NC}"
echo -e "     The Onboarding Agent's knowledge was instantly available to"
echo -e "     the Support Agent and Account Agent — no integration needed."
echo ""
echo -e "  ${GREEN}3.${NC} ${BOLD}Automatic Versioning${NC}"
echo -e "     When NovaTech migrated their stack, the update created v2."
echo -e "     The full history is preserved with change summaries."
echo ""
echo -e "  ${GREEN}4.${NC} ${BOLD}Contextual Retrieval${NC}"
echo -e "     Agents query by topic, tags, or free text. They get exactly"
echo -e "     the context they need to act intelligently."
echo ""
echo -e "  ${GREEN}5.${NC} ${BOLD}Organization Isolation${NC}"
echo -e "     Strict security boundary. One org's agents can never see"
echo -e "     another org's memories. Enforced at every layer."
echo ""
echo -e "  ${GREEN}6.${NC} ${BOLD}Agent-Native Design${NC}"
echo -e "     Agents use memory through plugin handlers during task execution."
echo -e "     The ExecutionContext provides trusted identity — agents can't"
echo -e "     spoof their org_id, user_id, or agent_id."
echo ""
echo -e "  ${DIM}Memories are the difference between an AI that forgets everything"
echo -e "  after each conversation and one that compounds knowledge over time.${NC}"
echo ""
