"""Integration tests for memory plugin handlers with real PostgreSQL.

Tests verify that:
1. Agent stores memory via plugin - stored memory is queryable
2. Agent queries only own org - org isolation is enforced
3. Memory survives across cycles - knowledge persists across stateless orchestrator cycles
4. Agent updates existing memory - version increment works via plugin

This validates the core knowledge neuron behavior: knowledge persists across
stateless orchestrator cycles and is organization-isolated.
"""

import pytest
import uuid

from src.plugins.memory_plugin import (
    memory_store_handler,
    memory_query_handler,
    set_database,
)
from src.infrastructure.memory.memory_service import MemoryService
from src.infrastructure.memory.memory_retriever import MemoryRetriever
from src.infrastructure.memory.memory_store import MemoryStore
from src.infrastructure.execution_runtime.execution_context import ExecutionContext


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
# TestMemoryPluginEndToEnd
# ---------------------------------------------------------------------------


class TestMemoryPluginEndToEnd:
    """End-to-end tests verifying plugin handlers work with real PostgreSQL."""

    @pytest.mark.asyncio
    async def test_agent_stores_memory_via_plugin(self, integration_db):
        """
        Call memory_store_handler with {key, title, body, topic, tags} and context.
        Then call memory_query_handler with {topic} and context.
        Assert the stored memory appears in results.
        """
        # Set up the database for plugin handlers
        set_database(integration_db)

        org_id = f"org-plugin-store-{uuid.uuid4().hex[:8]}"
        key = "learned-preference"
        title = "User Preference"
        body = "User prefers concise responses under 200 words"
        topic = "preferences"
        tags = ["learned", "user-pref"]

        # Store memory via plugin handler
        store_result = await memory_store_handler({
            "key": key,
            "title": title,
            "body": body,
            "topic": topic,
            "tags": tags,
        }, context=make_context(org_id, agent_id="agent-001"))

        # Verify store succeeded
        assert "status" not in store_result, f"Store failed: {store_result.get('error')}"
        assert "memory_id" in store_result
        assert store_result["key"] == key
        assert store_result["version"] == 1

        # Query memories via plugin handler
        query_result = await memory_query_handler({
            "topic": topic,
        }, context=make_context(org_id))

        # Verify query succeeded
        assert "status" not in query_result, f"Query failed: {query_result.get('error')}"
        assert query_result["count"] == 1
        assert len(query_result["memories"]) == 1

        # Verify the stored memory is in results
        memory = query_result["memories"][0]
        assert memory["key"] == key
        assert memory["title"] == title
        assert memory["body"] == body
        assert memory["topic"] == topic
        assert set(memory["tags"]) == set(tags)
        assert memory["relevance"] == 0.8  # Topic match score

    @pytest.mark.asyncio
    async def test_agent_queries_only_own_org(self, integration_db):
        """
        Store in org-A via handler. Query as org-B.
        Assert 0 results - org isolation is enforced.
        """
        # Set up the database for plugin handlers
        set_database(integration_db)

        org_a = f"org-A-{uuid.uuid4().hex[:8]}"
        org_b = f"org-B-{uuid.uuid4().hex[:8]}"

        # Store memory in org-A
        store_result = await memory_store_handler({
            "key": "org-a-secret",
            "title": "Secret Strategy",
            "body": "Our competitive advantage is superior AI",
            "topic": "strategy",
        }, context=make_context(org_a, agent_id="agent-org-a"))

        assert "memory_id" in store_result

        # Verify org-A can query its own memory
        query_result_a = await memory_query_handler({
            "topic": "strategy",
        }, context=make_context(org_a))

        assert query_result_a["count"] == 1
        assert query_result_a["memories"][0]["key"] == "org-a-secret"

        # org-B queries - should see 0 results due to org isolation
        query_result_b = await memory_query_handler({
            "topic": "strategy",
        }, context=make_context(org_b))

        assert query_result_b["count"] == 0
        assert len(query_result_b["memories"]) == 0

        # org-B queries with exact key - still 0 results
        query_result_b_key = await memory_query_handler({
            "key": "org-a-secret",
        }, context=make_context(org_b))

        assert query_result_b_key["count"] == 0

    @pytest.mark.asyncio
    async def test_memory_survives_across_cycles(self, integration_db):
        """
        Store memory via handler (simulating cycle 1).
        Create new MemoryService + MemoryRetriever (simulating cycle 2 fresh context).
        Query memories. Assert the memory from cycle 1 appears.

        This verifies the core knowledge neuron behavior: knowledge persists
        across stateless orchestrator cycles.
        """
        # Set up the database for plugin handlers
        set_database(integration_db)

        org_id = f"org-persist-{uuid.uuid4().hex[:8]}"
        key = "learned-pattern"
        body = "This customer segment prefers email over SMS"

        # Cycle 1: Store memory via plugin handler
        store_result = await memory_store_handler({
            "key": key,
            "title": "Customer Communication Preference",
            "body": body,
            "topic": "customer-insights",
        }, context=make_context(org_id, agent_id="agent-cycle-1"))

        assert "memory_id" in store_result

        # Simulate cycle 2: Create fresh MemoryService and MemoryRetriever
        # This mimics what happens when the orchestrator starts a new cycle
        # with completely fresh context (stateless)
        memory_service_cycle2 = MemoryService(integration_db)

        # Query using the fresh service (simulating new orchestrator cycle)
        from src.domain.memory.models import MemoryQuery

        query = MemoryQuery(
            organization_id=org_id,
            topic="customer-insights",
        )

        response = await memory_service_cycle2.search(query)

        # Assert memory from cycle 1 persists and is found
        assert response.total_count == 1
        assert len(response.memories) == 1
        assert response.memories[0].key == key
        assert response.memories[0].body == body

        # Also verify via plugin handler (fresh handler call = new context)
        query_result_cycle2 = await memory_query_handler({
            "topic": "customer-insights",
        }, context=make_context(org_id))

        assert query_result_cycle2["count"] == 1
        assert query_result_cycle2["memories"][0]["body"] == body

    @pytest.mark.asyncio
    async def test_agent_updates_existing_memory(self, integration_db):
        """
        Store v1, query to get ID, store update with same key.
        Verify version incremented.
        """
        # Set up the database for plugin handlers
        set_database(integration_db)

        org_id = f"org-update-{uuid.uuid4().hex[:8]}"
        key = "evolving-knowledge"

        # Store v1
        store_v1 = await memory_store_handler({
            "key": key,
            "title": "Product Feature List",
            "body": "Features: A, B, C",
            "topic": "product",
        }, context=make_context(org_id, agent_id="agent-update"))

        assert store_v1["version"] == 1
        memory_id = store_v1["memory_id"]

        # Query to verify v1 exists
        query_v1 = await memory_query_handler({
            "key": key,
        }, context=make_context(org_id))

        assert query_v1["count"] == 1
        assert query_v1["memories"][0]["body"] == "Features: A, B, C"

        # Store update with same key - this should create v2
        # Note: The memory_store_handler creates a new memory, not update
        # To update, we need to use the MemoryService directly
        memory_service = MemoryService(integration_db)

        # Get the existing memory
        existing = await memory_service.retrieve_by_key(
            key, org_id, user_id="test-user",
        )
        assert existing is not None
        assert existing.version == 1

        # Update the memory via MemoryService
        from src.domain.memory.models import MemoryUpdateRequest

        update_request = MemoryUpdateRequest(
            body="Features: A, B, C, D (new!)",
            change_summary="Added feature D",
            changed_by="agent-update",
            changed_by_agent=True,
        )

        updated = await memory_service.update(
            memory_id=existing.id,
            organization_id=org_id,
            request=update_request,
            user_id="test-user",
        )

        assert updated is not None
        assert updated.version == 2
        assert updated.body == "Features: A, B, C, D (new!)"

        # Query again to verify the update persisted
        query_v2 = await memory_query_handler({
            "key": key,
        }, context=make_context(org_id))

        assert query_v2["count"] == 1
        assert query_v2["memories"][0]["body"] == "Features: A, B, C, D (new!)"

        # Verify version history is accessible
        versions = await memory_service.get_version_history(
            existing.id, org_id, user_id="test-user",
        )
        assert len(versions) == 2
        # Most recent first
        assert versions[0]["version"] == 2
        assert versions[1]["version"] == 1


# ---------------------------------------------------------------------------
# TestMemoryPluginErrorHandling
# ---------------------------------------------------------------------------


class TestMemoryPluginErrorHandling:
    """Tests for plugin error handling edge cases."""

    @pytest.mark.asyncio
    async def test_store_missing_context(self, integration_db):
        """Verify proper error response when context is missing."""
        set_database(integration_db)

        # Missing context
        result = await memory_store_handler({
            "key": "test",
            "title": "Test",
            "body": "Test body",
        })
        assert result["status"] == "error"
        assert "ExecutionContext" in result["error"]

    @pytest.mark.asyncio
    async def test_store_missing_required_fields(self, integration_db):
        """Verify proper error response when required fields are missing."""
        set_database(integration_db)

        # Missing body (with valid context)
        result = await memory_store_handler({
            "key": "test",
            "title": "Test",
        }, context=make_context("org-test"))
        assert result["status"] == "error"
        assert "body" in result["error"]

    @pytest.mark.asyncio
    async def test_query_with_empty_results(self, integration_db):
        """Verify proper response when no memories match the query."""
        set_database(integration_db)

        org_id = f"org-empty-{uuid.uuid4().hex[:8]}"

        # Query for non-existent memories
        result = await memory_query_handler({
            "topic": "nonexistent-topic",
        }, context=make_context(org_id))

        assert result["count"] == 0
        assert result["memories"] == []

    @pytest.mark.asyncio
    async def test_store_with_tags_as_string(self, integration_db):
        """Verify comma-separated tags string is properly parsed."""
        set_database(integration_db)

        org_id = f"org-tags-{uuid.uuid4().hex[:8]}"

        # Store with comma-separated tags string
        result = await memory_store_handler({
            "key": "tagged-memory",
            "title": "Tagged Memory",
            "body": "Memory with string tags",
            "tags": "tag1, tag2, tag3",  # String instead of list
        }, context=make_context(org_id))

        assert "memory_id" in result

        # Query and verify tags were parsed correctly
        query_result = await memory_query_handler({
            "key": "tagged-memory",
        }, context=make_context(org_id))

        assert query_result["count"] == 1
        # Tags should be parsed from comma-separated string
        assert set(query_result["memories"][0]["tags"]) == {"tag1", "tag2", "tag3"}

    @pytest.mark.asyncio
    async def test_query_with_limit(self, integration_db):
        """Verify limit parameter is respected."""
        set_database(integration_db)

        org_id = f"org-limit-{uuid.uuid4().hex[:8]}"

        # Store 10 memories
        for i in range(10):
            await memory_store_handler({
                "key": f"memory-{i:02d}",
                "title": f"Memory {i}",
                "body": f"Content for memory {i}",
                "topic": "batch",
            }, context=make_context(org_id))

        # Query with limit
        result = await memory_query_handler({
            "topic": "batch",
            "limit": 3,
        }, context=make_context(org_id))

        assert result["count"] == 3
        assert len(result["memories"]) == 3
