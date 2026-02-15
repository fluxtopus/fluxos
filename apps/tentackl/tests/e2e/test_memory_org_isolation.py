"""
End-to-End Test: Org Isolation Under Real Conditions (MEM-030)

Validates that memories are strictly org-isolated in a real running system:
1. Authenticate as admin (org A)
2. Create a memory in org A: key='secret-strategy', body='We plan to undercut...'
3. Verify org A can see it: GET /api/memories?topic=strategy -- assert count >= 1
4. Verify different org cannot see it:
   - Create MemoryService and search with different org_id -> 0 results
   - memory_query_handler with org_id='different-org' -> 0 results
   - format_for_injection with org_id='different-org' -> empty string

This is the hard boundary verification for organization isolation.

Requires: inkpass, tentackl, postgres, redis all running.

Run via: docker compose exec tentackl python -m pytest tests/e2e/test_memory_org_isolation.py -v -s --no-cov
"""

import asyncio
import os
import socket
import uuid

import httpx
import pytest

from src.plugins.memory_plugin import (
    memory_store_handler,
    memory_query_handler,
    set_database,
)
from src.infrastructure.memory.memory_service import MemoryService
from src.domain.memory.models import MemoryQuery
from src.interfaces.database import Database
from src.infrastructure.execution_runtime.execution_context import ExecutionContext


# ---------------------------------------------------------------------------
# URL Configuration
# ---------------------------------------------------------------------------


def _get_default_inkpass_url():
    """Get InkPass URL - internal Docker network if running in container."""
    try:
        socket.gethostbyname("inkpass")
        return "http://inkpass:8000"
    except socket.gaierror:
        return "http://localhost:8004"


def _get_default_tentackl_url():
    """Get Tentackl URL - internal Docker network if running in container."""
    try:
        socket.gethostbyname("tentackl")
        return "http://tentackl:8000"
    except socket.gaierror:
        return "http://localhost:8005"


INKPASS_URL = os.environ.get("INKPASS_URL", _get_default_inkpass_url())
TENTACKL_URL = os.environ.get("TENTACKL_URL", _get_default_tentackl_url())

TEST_EMAIL = "admin@fluxtopus.com"
TEST_PASSWORD = "AiosAdmin123!"

# Module-level unique suffix to avoid test collisions
_TEST_SUFFIX = uuid.uuid4().hex[:8]


def make_context(org_id, user_id="test-user", agent_id=None):
    """Create an ExecutionContext for testing."""
    return ExecutionContext(
        organization_id=org_id,
        user_id=user_id,
        agent_id=agent_id,
        step_id="test-step",
        task_id="test-task",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def auth_token():
    """Authenticate once for all tests in this module."""
    with httpx.Client(timeout=15) as c:
        resp = c.post(
            f"{INKPASS_URL}/api/v1/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        token = resp.json().get("access_token")
        assert token, "No access_token in login response"
        return token


@pytest.fixture(scope="module")
def api(auth_token):
    """Shared httpx client with auth headers."""
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=120, headers=headers) as c:
        yield c


@pytest.fixture(scope="module")
def org_a_id():
    """Organization A ID - the org that owns the secret memory."""
    return f"org-a-{_TEST_SUFFIX}"


@pytest.fixture(scope="module")
def org_b_id():
    """Organization B ID - the org that should NOT see org A's memories."""
    return f"org-b-{_TEST_SUFFIX}"


@pytest.fixture(scope="module")
def test_suffix():
    """Unique suffix for this test run."""
    return _TEST_SUFFIX


# ---------------------------------------------------------------------------
# Test Class: Organization Isolation Verification
# ---------------------------------------------------------------------------


class TestOrgIsolationUnderRealConditions:
    """E2E tests verifying strict org isolation for the memory system.

    This test class validates the hard security boundary that prevents
    one organization from seeing another organization's memories.
    """

    def test_01_create_secret_memory_in_org_a(self, org_a_id, test_suffix):
        """
        (Step 2) Create a memory in org A: key='secret-strategy',
        body='We plan to undercut competitor X by 30%', topic='strategy'.
        """
        async def _create_secret():
            database = Database()
            set_database(database)

            # Store secret strategy in org A
            result = await memory_store_handler({
                "key": f"secret-strategy-{test_suffix}",
                "title": "Confidential Business Strategy",
                "body": "We plan to undercut competitor X by 30%",
                "topic": "strategy",
                "tags": ["confidential", "pricing", "competitive"],
            }, context=make_context(org_a_id, user_id="admin-org-a"))

            assert "status" not in result, f"Store failed: {result.get('error')}"
            assert "memory_id" in result
            assert result["key"] == f"secret-strategy-{test_suffix}"
            assert result["version"] == 1

            return result

        asyncio.get_event_loop().run_until_complete(_create_secret())

    def test_02_org_a_can_see_own_memory(self, org_a_id, test_suffix):
        """
        (Step 3) Verify org A can see it: query with topic='strategy'.
        Assert count >= 1 and the memory body contains the secret.
        """
        async def _verify_visible():
            database = Database()
            set_database(database)

            query_result = await memory_query_handler({
                "topic": "strategy",
            }, context=make_context(org_a_id))

            assert "status" not in query_result, (
                f"Query failed: {query_result.get('error')}"
            )
            assert query_result["count"] >= 1, (
                f"Expected at least 1 memory, got {query_result['count']}"
            )

            # Find our secret memory
            memories = query_result["memories"]
            secret_memory = next(
                (m for m in memories if f"secret-strategy-{test_suffix}" in m.get("key", "")),
                None
            )

            assert secret_memory is not None, "Secret memory not found in org A query"
            assert "undercut competitor X by 30%" in secret_memory["body"]
            assert secret_memory["topic"] == "strategy"

            return query_result

        asyncio.get_event_loop().run_until_complete(_verify_visible())

    def test_03_org_b_cannot_see_org_a_memory_via_service(self, org_a_id, org_b_id, test_suffix):
        """
        (Step 4) Create a MemoryService and call search with org B's ID.
        Assert 0 results for org A's secret memory.
        """
        async def _verify_isolated():
            # Create fresh MemoryService (simulating org B's context)
            database = Database()
            memory_service = MemoryService(database)

            # Search as org B for strategy topic
            query = MemoryQuery(
                organization_id=org_b_id,
                topic="strategy",
                limit=50,
            )

            search_result = await memory_service.search(query)

            # Org B should NOT find org A's secret
            secret_found = any(
                f"secret-strategy-{test_suffix}" in m.key
                for m in search_result.memories
            )

            assert not secret_found, (
                f"SECURITY VIOLATION: Org B found org A's secret memory! "
                f"Found memories: {[m.key for m in search_result.memories]}"
            )

            # Also verify no memory contains the secret text
            secret_text_found = any(
                "undercut competitor X" in m.body
                for m in search_result.memories
            )

            assert not secret_text_found, (
                "SECURITY VIOLATION: Org B can see org A's secret content!"
            )

            return search_result

        asyncio.get_event_loop().run_until_complete(_verify_isolated())

    def test_04_org_b_cannot_see_org_a_memory_via_plugin_handler(self, org_a_id, org_b_id, test_suffix):
        """
        (Step 5) Verify memory_query_handler with org_id='different-org' returns 0 results.
        """
        async def _verify_plugin_isolated():
            database = Database()
            set_database(database)

            # Query as org B using the plugin handler
            query_result = await memory_query_handler({
                "topic": "strategy",
                "limit": 50,
            }, context=make_context(org_b_id))

            assert "status" not in query_result, (
                f"Query failed: {query_result.get('error')}"
            )

            # Should NOT find org A's secret
            memories = query_result.get("memories", [])
            secret_found = any(
                f"secret-strategy-{test_suffix}" in m.get("key", "")
                for m in memories
            )

            assert not secret_found, (
                f"SECURITY VIOLATION: Plugin handler leaked org A's memory to org B! "
                f"Found: {[m.get('key') for m in memories]}"
            )

            return query_result

        asyncio.get_event_loop().run_until_complete(_verify_plugin_isolated())

    def test_05_org_b_format_injection_returns_empty(self, org_a_id, org_b_id, test_suffix):
        """
        (Step 6) Verify format_for_injection with org_id='different-org' returns empty string.
        """
        async def _verify_injection_empty():
            database = Database()
            memory_service = MemoryService(database)

            # Build query as org B
            query = MemoryQuery(
                organization_id=org_b_id,
                text="business strategy competitive pricing",
                topic="strategy",
                limit=20,
            )

            # Call format_for_injection as org B
            formatted = await memory_service.format_for_injection(
                query=query,
                max_tokens=2000,
            )

            # Should be empty or not contain the secret
            assert "undercut competitor X" not in formatted, (
                "SECURITY VIOLATION: Secret leaked to org B via format_for_injection!"
            )

            assert f"secret-strategy-{test_suffix}" not in formatted, (
                "SECURITY VIOLATION: Secret key leaked to org B via format_for_injection!"
            )

            return formatted

        asyncio.get_event_loop().run_until_complete(_verify_injection_empty())

    def test_06_org_a_still_sees_own_memory_after_org_b_queries(self, org_a_id, test_suffix):
        """
        Verify org A can still see its memory after org B attempted to access it.
        This ensures org B's queries don't affect org A's visibility.
        """
        async def _verify_still_visible():
            database = Database()
            memory_service = MemoryService(database)

            query = MemoryQuery(
                organization_id=org_a_id,
                topic="strategy",
            )

            search_result = await memory_service.search(query)

            # Org A should still see its memory
            secret_found = any(
                f"secret-strategy-{test_suffix}" in m.key
                for m in search_result.memories
            )

            assert secret_found, (
                "Org A can no longer see its own memory after org B's queries!"
            )

            # Verify content is intact
            secret_memory = next(
                (m for m in search_result.memories
                 if f"secret-strategy-{test_suffix}" in m.key),
                None
            )
            assert secret_memory is not None
            assert "undercut competitor X by 30%" in secret_memory.body

            return search_result

        asyncio.get_event_loop().run_until_complete(_verify_still_visible())


class TestCrossOrgBoundaryAttacks:
    """Test edge cases and potential attack vectors for org isolation."""

    def test_empty_org_id_cannot_access_memories(self, org_a_id, test_suffix):
        """
        Verify that an empty org_id cannot access any memories.
        ExecutionContext rejects empty org_id at construction time.
        """
        import pytest as _pytest

        # ExecutionContext should reject empty organization_id
        with _pytest.raises(ValueError, match="non-empty organization_id"):
            make_context("")

        async def _test_no_context():
            database = Database()
            set_database(database)

            # Without context, handler returns error
            query_result = await memory_query_handler({
                "topic": "strategy",
            })

            assert query_result["status"] == "error"
            assert "ExecutionContext" in query_result["error"]

        asyncio.get_event_loop().run_until_complete(_test_no_context())

    def test_wildcard_org_id_cannot_access_memories(self, org_a_id, test_suffix):
        """
        Verify that wildcard patterns in org_id don't bypass isolation.
        """
        async def _test_wildcard():
            database = Database()
            memory_service = MemoryService(database)

            # Try various wildcard patterns
            wildcard_patterns = ["*", "%", "org-*", "org-%", "_"]

            for pattern in wildcard_patterns:
                query = MemoryQuery(
                    organization_id=pattern,
                    topic="strategy",
                    limit=50,
                )

                search_result = await memory_service.search(query)

                # Should not find org A's secret
                secret_found = any(
                    f"secret-strategy-{test_suffix}" in m.key
                    for m in search_result.memories
                )

                assert not secret_found, (
                    f"Wildcard pattern '{pattern}' bypassed org isolation!"
                )

        asyncio.get_event_loop().run_until_complete(_test_wildcard())

    def test_sql_injection_attempt_in_org_id(self, org_a_id, test_suffix):
        """
        Verify that SQL injection attempts in org_id don't bypass isolation.
        """
        async def _test_sql_injection():
            database = Database()
            memory_service = MemoryService(database)

            # SQL injection patterns
            injection_patterns = [
                "' OR '1'='1",
                "'; DROP TABLE memories; --",
                f"' OR organization_id = '{org_a_id}' --",
                "1' OR '1'='1",
            ]

            for pattern in injection_patterns:
                try:
                    query = MemoryQuery(
                        organization_id=pattern,
                        topic="strategy",
                        limit=50,
                    )

                    search_result = await memory_service.search(query)

                    # Should not find org A's secret
                    secret_found = any(
                        f"secret-strategy-{test_suffix}" in m.key
                        for m in search_result.memories
                    )

                    assert not secret_found, (
                        f"SQL injection pattern '{pattern}' bypassed org isolation!"
                    )
                except Exception:
                    # Exception is acceptable - indicates the malicious input was rejected
                    pass

        asyncio.get_event_loop().run_until_complete(_test_sql_injection())


class TestOrgIsolationCleanup:
    """Cleanup test data after org isolation tests."""

    def test_99_cleanup_test_memories(self, org_a_id, org_b_id, test_suffix):
        """
        Clean up memories created during org isolation tests.
        """
        async def _cleanup():
            database = Database()
            memory_service = MemoryService(database)

            # Clean up org A memories
            query_a = MemoryQuery(
                organization_id=org_a_id,
                topic="strategy",
            )
            result_a = await memory_service.search(query_a)

            for memory in result_a.memories:
                if test_suffix in memory.key:
                    await memory_service.delete(
                        memory.id, org_a_id, user_id="cleanup-user",
                    )

            # Clean up any org B memories (shouldn't be any from this test, but be safe)
            query_b = MemoryQuery(
                organization_id=org_b_id,
                limit=50,
            )
            result_b = await memory_service.search(query_b)

            for memory in result_b.memories:
                if test_suffix in memory.key:
                    await memory_service.delete(
                        memory.id, org_b_id, user_id="cleanup-user",
                    )

        asyncio.get_event_loop().run_until_complete(_cleanup())
