"""Unit tests for the memory plugin handlers.

Tests:
- memory_store_handler: validates required fields, stores memories, returns correct response
- memory_query_handler: validates org_id, queries with filters, returns ranked results
"""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.execution_runtime.execution_context import ExecutionContext
from src.domain.memory.models import (
    MemoryResult,
    MemorySearchResponse,
    RetrievalEvidence,
    MemoryScopeEnum,
)
from src.plugins.memory_plugin import (
    memory_store_handler,
    memory_query_handler,
    PLUGIN_HANDLERS,
)


# Helper to create mock MemoryResult
def create_mock_memory_result(
    id: str = None,
    key: str = "test-key",
    title: str = "Test Title",
    body: str = "Test body content",
    topic: str = None,
    tags: list = None,
    version: int = 1,
    relevance: float = 0.8,
) -> MemoryResult:
    """Create a mock MemoryResult for testing."""
    return MemoryResult(
        id=id or str(uuid.uuid4()),
        key=key,
        title=title,
        body=body,
        scope="organization",
        topic=topic,
        tags=tags or [],
        version=version,
        extended_data={},
        metadata={},
        evidence=RetrievalEvidence(
            match_type="topic",
            relevance_score=relevance,
            filters_applied=["filter:topic=test"],
            retrieval_time_ms=5,
        ),
    )


def make_context(org_id="org-123", user_id="user-456", agent_id=None):
    """Create an ExecutionContext for testing."""
    return ExecutionContext(
        organization_id=org_id,
        user_id=user_id,
        agent_id=agent_id,
        step_id="step-test",
        task_id="task-test",
    )


class TestPluginExports:
    """Tests for PLUGIN_HANDLERS dictionary."""

    def test_exports_memory_store(self):
        assert "memory_store" in PLUGIN_HANDLERS
        assert PLUGIN_HANDLERS["memory_store"] is memory_store_handler

    def test_exports_memory_query(self):
        assert "memory_query" in PLUGIN_HANDLERS
        assert PLUGIN_HANDLERS["memory_query"] is memory_query_handler


class TestMemoryStoreHandlerValidation:
    """Tests for input validation in memory_store_handler."""

    @pytest.mark.asyncio
    async def test_missing_context_returns_error(self):
        """Missing context should return an error."""
        result = await memory_store_handler({
            "key": "test-key",
            "title": "Test",
            "body": "Body",
        })
        assert result["status"] == "error"
        assert "ExecutionContext" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_key_returns_error(self):
        """Missing key should return an error."""
        ctx = make_context()
        result = await memory_store_handler({
            "title": "Test",
            "body": "Body",
        }, context=ctx)
        assert result["status"] == "error"
        assert "key" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_title_returns_error(self):
        """Missing title should return an error."""
        ctx = make_context()
        result = await memory_store_handler({
            "key": "test-key",
            "body": "Body",
        }, context=ctx)
        assert result["status"] == "error"
        assert "title" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_body_returns_error(self):
        """Missing body should return an error."""
        ctx = make_context()
        result = await memory_store_handler({
            "key": "test-key",
            "title": "Test",
        }, context=ctx)
        assert result["status"] == "error"
        assert "body" in result["error"]


class TestMemoryStoreHandlerSuccess:
    """Tests for successful memory_store_handler operations."""

    @pytest.fixture(autouse=True)
    def setup_mock_service(self):
        """Set up mocked MemoryUseCases."""
        self.mock_service = MagicMock()
        self.mock_result = create_mock_memory_result(
            id="mem-123",
            key="test-key",
            version=1,
        )
        self.mock_service.store = AsyncMock(return_value=self.mock_result)

        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            yield

    @pytest.mark.asyncio
    async def test_stores_with_required_fields(self):
        """Should successfully store memory with all required fields."""
        ctx = make_context()
        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            result = await memory_store_handler({
                "key": "test-key",
                "title": "Test Title",
                "body": "Test body content",
            }, context=ctx)

        assert "memory_id" in result
        assert result["memory_id"] == "mem-123"
        self.mock_service.store.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_memory_id_and_version(self):
        """Should return memory_id, key, and version."""
        ctx = make_context()
        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            result = await memory_store_handler({
                "key": "test-key",
                "title": "Test Title",
                "body": "Test body content",
            }, context=ctx)

        assert result["memory_id"] == "mem-123"
        assert result["key"] == "test-key"
        assert result["version"] == 1

    @pytest.mark.asyncio
    async def test_optional_scope_defaults_to_organization(self):
        """Should default scope to 'organization' when not provided."""
        ctx = make_context()
        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            await memory_store_handler({
                "key": "test-key",
                "title": "Test Title",
                "body": "Test body content",
            }, context=ctx)

        # Check the request passed to store()
        call_args = self.mock_service.store.call_args[0][0]
        assert call_args.scope == MemoryScopeEnum.ORGANIZATION

    @pytest.mark.asyncio
    async def test_accepts_user_scope(self):
        """Should accept 'user' scope."""
        ctx = make_context()
        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            await memory_store_handler({
                "key": "test-key",
                "title": "Test Title",
                "body": "Test body content",
                "scope": "user",
                "scope_value": "user-456",
            }, context=ctx)

        call_args = self.mock_service.store.call_args[0][0]
        assert call_args.scope == MemoryScopeEnum.USER
        assert call_args.scope_value == "user-456"

    @pytest.mark.asyncio
    async def test_accepts_tags_and_topic(self):
        """Should accept tags and topic parameters."""
        ctx = make_context()
        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            await memory_store_handler({
                "key": "test-key",
                "title": "Test Title",
                "body": "Test body content",
                "topic": "content",
                "tags": ["api", "learned"],
            }, context=ctx)

        call_args = self.mock_service.store.call_args[0][0]
        assert call_args.topic == "content"
        assert call_args.tags == ["api", "learned"]

    @pytest.mark.asyncio
    async def test_accepts_comma_separated_tags(self):
        """Should split comma-separated tags string into list."""
        ctx = make_context()
        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            await memory_store_handler({
                "key": "test-key",
                "title": "Test Title",
                "body": "Test body content",
                "tags": "api, learned, important",
            }, context=ctx)

        call_args = self.mock_service.store.call_args[0][0]
        assert call_args.tags == ["api", "learned", "important"]

    @pytest.mark.asyncio
    async def test_passes_agent_id_from_context(self):
        """Should pass agent_id from context to the request."""
        ctx = make_context(agent_id="agent-789")
        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            await memory_store_handler({
                "key": "test-key",
                "title": "Test Title",
                "body": "Test body content",
            }, context=ctx)

        call_args = self.mock_service.store.call_args[0][0]
        assert call_args.created_by_agent_id == "agent-789"

    @pytest.mark.asyncio
    async def test_passes_user_id_from_context(self):
        """Should pass user_id from context to the request."""
        ctx = make_context(user_id="user-456")
        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            await memory_store_handler({
                "key": "test-key",
                "title": "Test Title",
                "body": "Test body content",
            }, context=ctx)

        call_args = self.mock_service.store.call_args[0][0]
        assert call_args.created_by_user_id == "user-456"


class TestMemoryStoreHandlerErrors:
    """Tests for error handling in memory_store_handler."""

    @pytest.mark.asyncio
    async def test_handles_service_exception(self):
        """Should handle service exceptions gracefully."""
        ctx = make_context()
        mock_service = MagicMock()
        mock_service.store = AsyncMock(side_effect=Exception("DB connection failed"))

        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=mock_service,
        ):
            result = await memory_store_handler({
                "key": "test-key",
                "title": "Test Title",
                "body": "Test body content",
            }, context=ctx)

        assert result["status"] == "error"
        assert "DB connection failed" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_scope_defaults_to_organization(self):
        """Should default to organization scope if invalid scope provided."""
        ctx = make_context()
        mock_service = MagicMock()
        mock_result = create_mock_memory_result()
        mock_service.store = AsyncMock(return_value=mock_result)

        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=mock_service,
        ):
            await memory_store_handler({
                "key": "test-key",
                "title": "Test Title",
                "body": "Test body content",
                "scope": "invalid_scope",
            }, context=ctx)

        call_args = mock_service.store.call_args[0][0]
        assert call_args.scope == MemoryScopeEnum.ORGANIZATION


class TestMemoryQueryHandlerValidation:
    """Tests for input validation in memory_query_handler."""

    @pytest.mark.asyncio
    async def test_missing_context_returns_error(self):
        """Missing context should return an error."""
        result = await memory_query_handler({
            "topic": "content",
        })
        assert result["status"] == "error"
        assert "ExecutionContext" in result["error"]


class TestMemoryQueryHandlerSuccess:
    """Tests for successful memory_query_handler operations."""

    @pytest.fixture(autouse=True)
    def setup_mock_service(self):
        """Set up mocked MemoryUseCases."""
        self.mock_service = MagicMock()
        self.mock_memories = [
            create_mock_memory_result(id="mem-1", key="k1", title="First", relevance=0.9),
            create_mock_memory_result(id="mem-2", key="k2", title="Second", relevance=0.7),
        ]
        self.mock_response = MemorySearchResponse(
            memories=self.mock_memories,
            total_count=2,
            retrieval_path=["filter:topic=content"],
            query_time_ms=10,
        )
        self.mock_service.search = AsyncMock(return_value=self.mock_response)

    @pytest.mark.asyncio
    async def test_queries_with_text(self):
        """Should query with text parameter."""
        ctx = make_context()
        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            result = await memory_query_handler({
                "text": "brand voice guidelines",
            }, context=ctx)

        assert result["count"] == 2
        assert len(result["memories"]) == 2
        call_args = self.mock_service.search.call_args[0][0]
        assert call_args.text == "brand voice guidelines"

    @pytest.mark.asyncio
    async def test_queries_by_topic(self):
        """Should query by topic."""
        ctx = make_context()
        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            result = await memory_query_handler({
                "topic": "content",
            }, context=ctx)

        call_args = self.mock_service.search.call_args[0][0]
        assert call_args.topic == "content"

    @pytest.mark.asyncio
    async def test_queries_by_tags(self):
        """Should query by tags list."""
        ctx = make_context()
        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            await memory_query_handler({
                "tags": ["api", "learned"],
            }, context=ctx)

        call_args = self.mock_service.search.call_args[0][0]
        assert call_args.tags == ["api", "learned"]

    @pytest.mark.asyncio
    async def test_queries_by_comma_separated_tags(self):
        """Should split comma-separated tags string."""
        ctx = make_context()
        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            await memory_query_handler({
                "tags": "api, learned",
            }, context=ctx)

        call_args = self.mock_service.search.call_args[0][0]
        assert call_args.tags == ["api", "learned"]

    @pytest.mark.asyncio
    async def test_queries_by_key(self):
        """Should query by exact key."""
        ctx = make_context()
        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            await memory_query_handler({
                "key": "brand-voice",
            }, context=ctx)

        call_args = self.mock_service.search.call_args[0][0]
        assert call_args.key == "brand-voice"

    @pytest.mark.asyncio
    async def test_returns_ranked_results(self):
        """Should return results with relevance scores."""
        ctx = make_context()
        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            result = await memory_query_handler({
                "topic": "content",
            }, context=ctx)

        memories = result["memories"]
        assert len(memories) == 2
        assert memories[0]["relevance"] == 0.9
        assert memories[1]["relevance"] == 0.7

    @pytest.mark.asyncio
    async def test_returns_memory_fields(self):
        """Should return expected memory fields."""
        ctx = make_context()
        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            result = await memory_query_handler({}, context=ctx)

        memory = result["memories"][0]
        assert "id" in memory
        assert "key" in memory
        assert "title" in memory
        assert "body" in memory
        assert "topic" in memory
        assert "tags" in memory
        assert "relevance" in memory

    @pytest.mark.asyncio
    async def test_empty_results(self):
        """Should handle empty results correctly."""
        ctx = make_context()
        empty_response = MemorySearchResponse(
            memories=[],
            total_count=0,
            retrieval_path=["filter:topic=nonexistent"],
            query_time_ms=5,
        )
        self.mock_service.search = AsyncMock(return_value=empty_response)

        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            result = await memory_query_handler({
                "topic": "nonexistent",
            }, context=ctx)

        assert result["count"] == 0
        assert result["memories"] == []

    @pytest.mark.asyncio
    async def test_respects_limit(self):
        """Should pass limit to query."""
        ctx = make_context()
        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            await memory_query_handler({
                "limit": 10,
            }, context=ctx)

        call_args = self.mock_service.search.call_args[0][0]
        assert call_args.limit == 10

    @pytest.mark.asyncio
    async def test_limit_capped_at_50(self):
        """Should cap limit at 50."""
        ctx = make_context()
        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            await memory_query_handler({
                "limit": 100,
            }, context=ctx)

        call_args = self.mock_service.search.call_args[0][0]
        assert call_args.limit == 50

    @pytest.mark.asyncio
    async def test_default_limit_is_5(self):
        """Should default limit to 5."""
        ctx = make_context()
        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            await memory_query_handler({}, context=ctx)

        call_args = self.mock_service.search.call_args[0][0]
        assert call_args.limit == 5

    @pytest.mark.asyncio
    async def test_passes_agent_id_from_context(self):
        """Should pass agent_id from context for permission checks."""
        ctx = make_context(agent_id="agent-789")
        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            await memory_query_handler({}, context=ctx)

        call_args = self.mock_service.search.call_args[0][0]
        assert call_args.requesting_agent_id == "agent-789"

    @pytest.mark.asyncio
    async def test_passes_user_id_from_context(self):
        """Should pass user_id from context for permission checks."""
        ctx = make_context(user_id="user-456")
        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=self.mock_service,
        ):
            await memory_query_handler({}, context=ctx)

        call_args = self.mock_service.search.call_args[0][0]
        assert call_args.requesting_user_id == "user-456"


class TestMemoryQueryHandlerNoEvidence:
    """Tests for handling memories without evidence."""

    @pytest.mark.asyncio
    async def test_defaults_relevance_to_1_when_no_evidence(self):
        """Should default relevance to 1.0 when memory has no evidence."""
        ctx = make_context()
        mock_service = MagicMock()
        memory_without_evidence = MemoryResult(
            id="mem-1",
            key="k1",
            title="Title",
            body="Body",
            scope="organization",
            evidence=None,  # No evidence
        )
        mock_response = MemorySearchResponse(
            memories=[memory_without_evidence],
            total_count=1,
            retrieval_path=[],
            query_time_ms=5,
        )
        mock_service.search = AsyncMock(return_value=mock_response)

        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=mock_service,
        ):
            result = await memory_query_handler({}, context=ctx)

        assert result["memories"][0]["relevance"] == 1.0


class TestMemoryQueryHandlerErrors:
    """Tests for error handling in memory_query_handler."""

    @pytest.mark.asyncio
    async def test_handles_service_exception(self):
        """Should handle service exceptions gracefully."""
        ctx = make_context()
        mock_service = MagicMock()
        mock_service.search = AsyncMock(side_effect=Exception("Search failed"))

        with patch(
            "src.plugins.memory_plugin._get_memory_use_cases",
            new_callable=AsyncMock,
            return_value=mock_service,
        ):
            result = await memory_query_handler({}, context=ctx)

        assert result["status"] == "error"
        assert "Search failed" in result["error"]
