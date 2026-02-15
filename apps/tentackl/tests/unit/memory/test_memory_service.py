"""Unit tests for MemoryService facade composition.

Tests that MemoryService properly delegates to its internal components:
- MemoryStore for PostgreSQL persistence
- MemoryRetriever for query routing and scoring
- MemoryInjector for prompt formatting
- MemoryLogger for structured logging
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.database.memory_models import Memory, MemoryVersion
from src.domain.memory.models import (
    MemoryCreateRequest,
    MemoryQuery,
    MemoryResult,
    MemorySearchResponse,
    MemoryUpdateRequest,
    MemoryScopeEnum,
    RetrievalEvidence,
    MemoryNotFoundError,
)
from src.infrastructure.memory.memory_service import MemoryService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_database():
    """Mock Database instance."""
    database = MagicMock()

    # Make get_session return an async context manager
    async_context = AsyncMock()
    async_context.__aenter__ = AsyncMock(return_value=AsyncMock())
    async_context.__aexit__ = AsyncMock(return_value=None)

    database.get_session = MagicMock(return_value=async_context)

    return database


@pytest.fixture
def sample_memory_id():
    """Sample memory UUID."""
    return uuid.uuid4()


@pytest.fixture
def sample_memory(sample_memory_id):
    """Sample Memory ORM object."""
    return Memory(
        id=sample_memory_id,
        organization_id="org-test",
        key="test-key",
        title="Test Memory",
        scope="organization",
        scope_value=None,
        topic="testing",
        tags=["unit", "test"],
        content_type="text",
        current_version=1,
        status="active",
        created_by_user_id="user-123",
        created_by_agent_id=None,
        extra_metadata={"priority": "high"},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def sample_version(sample_memory_id):
    """Sample MemoryVersion ORM object."""
    return MemoryVersion(
        id=uuid.uuid4(),
        memory_id=sample_memory_id,
        version=1,
        body="This is the test memory body content.",
        extended_data={"format": "markdown"},
        change_summary="Initial version",
        changed_by="user-123",
        changed_by_agent=False,
        created_at=datetime.utcnow(),
    )


@pytest.fixture
def sample_memory_result(sample_memory_id):
    """Sample MemoryResult dataclass."""
    return MemoryResult(
        id=str(sample_memory_id),
        key="test-key",
        title="Test Memory",
        body="This is the test memory body content.",
        scope="organization",
        topic="testing",
        tags=["unit", "test"],
        version=1,
        extended_data={"format": "markdown"},
        metadata={"priority": "high"},
        evidence=RetrievalEvidence(
            match_type="exact_key",
            relevance_score=1.0,
            filters_applied=["key"],
            retrieval_time_ms=5,
        ),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def sample_search_response(sample_memory_result):
    """Sample MemorySearchResponse."""
    return MemorySearchResponse(
        memories=[sample_memory_result],
        total_count=1,
        retrieval_path=["route:exact_key=test-key"],
        query_time_ms=10,
    )


# ---------------------------------------------------------------------------
# TestMemoryServiceStore
# ---------------------------------------------------------------------------


class TestMemoryServiceStore:
    """Tests for MemoryService.store() method."""

    @pytest.mark.asyncio
    async def test_store_delegates_to_store(self, mock_database, sample_memory, sample_version):
        """Test store() delegates to MemoryStore.create()."""
        with patch("src.infrastructure.memory.memory_service.MemoryStore") as MockStore:
            mock_store_instance = AsyncMock()
            mock_store_instance.create.return_value = sample_memory
            mock_store_instance.get_current_version.return_value = sample_version
            MockStore.return_value = mock_store_instance

            service = MemoryService(mock_database)
            request = MemoryCreateRequest(
                organization_id="org-test",
                key="test-key",
                title="Test Memory",
                body="This is the body",
            )

            await service.store(request)

            # Verify MemoryStore was instantiated and create was called
            MockStore.assert_called_once_with(mock_database)
            mock_store_instance.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_returns_memory_result(self, mock_database, sample_memory, sample_version):
        """Test store() returns a MemoryResult dataclass."""
        with patch("src.infrastructure.memory.memory_service.MemoryStore") as MockStore:
            mock_store_instance = AsyncMock()
            mock_store_instance.create.return_value = sample_memory
            mock_store_instance.get_current_version.return_value = sample_version
            MockStore.return_value = mock_store_instance

            service = MemoryService(mock_database)
            request = MemoryCreateRequest(
                organization_id="org-test",
                key="test-key",
                title="Test Memory",
                body="This is the body",
            )

            result = await service.store(request)

            assert isinstance(result, MemoryResult)
            assert result.key == "test-key"
            assert result.title == "Test Memory"
            assert result.body == sample_version.body

    @pytest.mark.asyncio
    async def test_store_logs_operation(self, mock_database, sample_memory, sample_version):
        """Test store() logs the store operation."""
        with patch("src.infrastructure.memory.memory_service.MemoryStore") as MockStore, \
             patch("src.infrastructure.memory.memory_service.MemoryLogger") as MockLogger:
            mock_store_instance = AsyncMock()
            mock_store_instance.create.return_value = sample_memory
            mock_store_instance.get_current_version.return_value = sample_version
            MockStore.return_value = mock_store_instance

            mock_logger_instance = MagicMock()
            MockLogger.return_value = mock_logger_instance

            service = MemoryService(mock_database)
            request = MemoryCreateRequest(
                organization_id="org-test",
                key="test-key",
                title="Test Memory",
                body="This is the body",
            )

            await service.store(request)

            mock_logger_instance.log_store.assert_called_once_with(
                organization_id="org-test",
                key="test-key",
                scope="organization",
                created_by_agent=False,
            )

    @pytest.mark.asyncio
    async def test_store_with_agent_creator(self, mock_database, sample_memory, sample_version):
        """Test store() correctly logs when created by agent."""
        sample_memory.created_by_agent_id = "agent-123"

        with patch("src.infrastructure.memory.memory_service.MemoryStore") as MockStore, \
             patch("src.infrastructure.memory.memory_service.MemoryLogger") as MockLogger:
            mock_store_instance = AsyncMock()
            mock_store_instance.create.return_value = sample_memory
            mock_store_instance.get_current_version.return_value = sample_version
            MockStore.return_value = mock_store_instance

            mock_logger_instance = MagicMock()
            MockLogger.return_value = mock_logger_instance

            service = MemoryService(mock_database)
            request = MemoryCreateRequest(
                organization_id="org-test",
                key="test-key",
                title="Test Memory",
                body="This is the body",
                created_by_agent_id="agent-123",
            )

            await service.store(request)

            mock_logger_instance.log_store.assert_called_once_with(
                organization_id="org-test",
                key="test-key",
                scope="organization",
                created_by_agent=True,
            )


# ---------------------------------------------------------------------------
# TestMemoryServiceSearch
# ---------------------------------------------------------------------------


class TestMemoryServiceSearch:
    """Tests for MemoryService.search() method."""

    @pytest.mark.asyncio
    async def test_search_delegates_to_retriever(self, mock_database, sample_search_response):
        """Test search() delegates to MemoryRetriever.search()."""
        with patch("src.infrastructure.memory.memory_service.MemoryStore") as MockStore, \
             patch("src.infrastructure.memory.memory_service.MemoryRetriever") as MockRetriever:
            mock_store_instance = AsyncMock()
            MockStore.return_value = mock_store_instance

            mock_retriever_instance = AsyncMock()
            mock_retriever_instance.search.return_value = sample_search_response
            MockRetriever.return_value = mock_retriever_instance

            service = MemoryService(mock_database)
            query = MemoryQuery(organization_id="org-test", topic="testing")

            await service.search(query)

            # Verify MemoryRetriever was created and search was called
            mock_retriever_instance.search.assert_called_once_with(query)

    @pytest.mark.asyncio
    async def test_search_returns_search_response(self, mock_database, sample_search_response):
        """Test search() returns MemorySearchResponse."""
        with patch("src.infrastructure.memory.memory_service.MemoryStore") as MockStore, \
             patch("src.infrastructure.memory.memory_service.MemoryRetriever") as MockRetriever:
            mock_store_instance = AsyncMock()
            MockStore.return_value = mock_store_instance

            mock_retriever_instance = AsyncMock()
            mock_retriever_instance.search.return_value = sample_search_response
            MockRetriever.return_value = mock_retriever_instance

            service = MemoryService(mock_database)
            query = MemoryQuery(organization_id="org-test")

            result = await service.search(query)

            assert isinstance(result, MemorySearchResponse)
            assert result.total_count == 1
            assert len(result.memories) == 1


# ---------------------------------------------------------------------------
# TestMemoryServiceInject
# ---------------------------------------------------------------------------


class TestMemoryServiceInject:
    """Tests for MemoryService.format_for_injection() method."""

    @pytest.mark.asyncio
    async def test_format_for_injection_calls_search_then_format(
        self, mock_database, sample_search_response
    ):
        """Test format_for_injection() calls search then format."""
        with patch("src.infrastructure.memory.memory_service.MemoryStore") as MockStore, \
             patch("src.infrastructure.memory.memory_service.MemoryRetriever") as MockRetriever, \
             patch("src.infrastructure.memory.memory_service.MemoryInjector") as MockInjector, \
             patch("src.infrastructure.memory.memory_service.MemoryLogger") as MockLogger:
            mock_store_instance = AsyncMock()
            MockStore.return_value = mock_store_instance

            mock_retriever_instance = AsyncMock()
            mock_retriever_instance.search.return_value = sample_search_response
            MockRetriever.return_value = mock_retriever_instance

            mock_injector_instance = MagicMock()
            mock_injector_instance.format_for_prompt.return_value = "<memories>...</memories>"
            mock_injector_instance.estimate_tokens.return_value = 50
            MockInjector.return_value = mock_injector_instance

            mock_logger_instance = MagicMock()
            MockLogger.return_value = mock_logger_instance

            service = MemoryService(mock_database)
            query = MemoryQuery(organization_id="org-test")

            result = await service.format_for_injection(query, max_tokens=2000)

            # Verify search was called
            mock_retriever_instance.search.assert_called_once_with(query)
            # Verify format_for_prompt was called with memories
            mock_injector_instance.format_for_prompt.assert_called()
            # Verify result is formatted string
            assert result == "<memories>...</memories>"

    @pytest.mark.asyncio
    async def test_format_respects_token_budget(
        self, mock_database, sample_search_response
    ):
        """Test format_for_injection() passes max_tokens to injector."""
        with patch("src.infrastructure.memory.memory_service.MemoryStore") as MockStore, \
             patch("src.infrastructure.memory.memory_service.MemoryRetriever") as MockRetriever, \
             patch("src.infrastructure.memory.memory_service.MemoryInjector") as MockInjector, \
             patch("src.infrastructure.memory.memory_service.MemoryLogger") as MockLogger:
            mock_store_instance = AsyncMock()
            MockStore.return_value = mock_store_instance

            mock_retriever_instance = AsyncMock()
            mock_retriever_instance.search.return_value = sample_search_response
            MockRetriever.return_value = mock_retriever_instance

            mock_injector_instance = MagicMock()
            mock_injector_instance.format_for_prompt.return_value = "<memories>...</memories>"
            mock_injector_instance.estimate_tokens.return_value = 100
            MockInjector.return_value = mock_injector_instance

            mock_logger_instance = MagicMock()
            MockLogger.return_value = mock_logger_instance

            service = MemoryService(mock_database)
            query = MemoryQuery(organization_id="org-test")

            await service.format_for_injection(query, max_tokens=500)

            # Verify format_for_prompt was called
            # MemoryService calls format_for_prompt twice: once with max_tokens,
            # once with max_tokens=100000 for truncation check
            # Check that the first call (the main one) used our max_tokens
            all_calls = mock_injector_instance.format_for_prompt.call_args_list
            assert len(all_calls) >= 1
            first_call = all_calls[0]
            # First call should have max_tokens=500
            assert first_call.args[1] == 500 or first_call.kwargs.get("max_tokens") == 500

    @pytest.mark.asyncio
    async def test_format_logs_injection(
        self, mock_database, sample_search_response
    ):
        """Test format_for_injection() logs the injection."""
        with patch("src.infrastructure.memory.memory_service.MemoryStore") as MockStore, \
             patch("src.infrastructure.memory.memory_service.MemoryRetriever") as MockRetriever, \
             patch("src.infrastructure.memory.memory_service.MemoryInjector") as MockInjector, \
             patch("src.infrastructure.memory.memory_service.MemoryLogger") as MockLogger:
            mock_store_instance = AsyncMock()
            MockStore.return_value = mock_store_instance

            mock_retriever_instance = AsyncMock()
            mock_retriever_instance.search.return_value = sample_search_response
            MockRetriever.return_value = mock_retriever_instance

            mock_injector_instance = MagicMock()
            mock_injector_instance.format_for_prompt.return_value = "<memories>...</memories>"
            mock_injector_instance.estimate_tokens.return_value = 50
            MockInjector.return_value = mock_injector_instance

            mock_logger_instance = MagicMock()
            MockLogger.return_value = mock_logger_instance

            service = MemoryService(mock_database)
            query = MemoryQuery(organization_id="org-test")

            await service.format_for_injection(query, max_tokens=2000)

            # Verify log_injection was called
            mock_logger_instance.log_injection.assert_called_once()
            call_kwargs = mock_logger_instance.log_injection.call_args.kwargs
            assert "memory_count" in call_kwargs
            assert "injected_tokens" in call_kwargs
            assert "max_tokens" in call_kwargs

    @pytest.mark.asyncio
    async def test_format_returns_empty_for_no_memories(self, mock_database):
        """Test format_for_injection() returns empty string when no memories."""
        empty_response = MemorySearchResponse(
            memories=[],
            total_count=0,
            retrieval_path=["route:org_scan"],
            query_time_ms=5,
        )

        with patch("src.infrastructure.memory.memory_service.MemoryStore") as MockStore, \
             patch("src.infrastructure.memory.memory_service.MemoryRetriever") as MockRetriever:
            mock_store_instance = AsyncMock()
            MockStore.return_value = mock_store_instance

            mock_retriever_instance = AsyncMock()
            mock_retriever_instance.search.return_value = empty_response
            MockRetriever.return_value = mock_retriever_instance

            service = MemoryService(mock_database)
            query = MemoryQuery(organization_id="org-test")

            result = await service.format_for_injection(query, max_tokens=2000)

            assert result == ""


# ---------------------------------------------------------------------------
# TestMemoryServiceRetrieve
# ---------------------------------------------------------------------------


class TestMemoryServiceRetrieve:
    """Tests for MemoryService.retrieve() method."""

    @pytest.mark.asyncio
    async def test_retrieve_by_id(self, mock_database, sample_memory, sample_version):
        """Test retrieve() returns memory by ID."""
        with patch("src.infrastructure.memory.memory_service.MemoryStore") as MockStore:
            mock_store_instance = AsyncMock()
            mock_store_instance.get_by_id.return_value = sample_memory
            mock_store_instance.check_permission.return_value = True
            mock_store_instance.get_current_version.return_value = sample_version
            MockStore.return_value = mock_store_instance

            service = MemoryService(mock_database)
            result = await service.retrieve(
                str(sample_memory.id), "org-test", user_id="user-123",
            )

            mock_store_instance.get_by_id.assert_called_once_with(
                str(sample_memory.id), "org-test"
            )
            assert isinstance(result, MemoryResult)
            assert result.key == "test-key"

    @pytest.mark.asyncio
    async def test_retrieve_returns_none_for_missing(self, mock_database):
        """Test retrieve() returns None when memory not found."""
        with patch("src.infrastructure.memory.memory_service.MemoryStore") as MockStore:
            mock_store_instance = AsyncMock()
            mock_store_instance.get_by_id.return_value = None
            MockStore.return_value = mock_store_instance

            service = MemoryService(mock_database)
            result = await service.retrieve(
                "nonexistent-id", "org-test", user_id="user-123",
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_retrieve_by_key(self, mock_database, sample_memory, sample_version):
        """Test retrieve_by_key() returns memory by key."""
        with patch("src.infrastructure.memory.memory_service.MemoryStore") as MockStore:
            mock_store_instance = AsyncMock()
            mock_store_instance.get_by_key.return_value = sample_memory
            mock_store_instance.check_permission.return_value = True
            mock_store_instance.get_current_version.return_value = sample_version
            MockStore.return_value = mock_store_instance

            service = MemoryService(mock_database)
            result = await service.retrieve_by_key(
                "test-key", "org-test", user_id="user-123",
            )

            mock_store_instance.get_by_key.assert_called_once_with("test-key", "org-test")
            assert isinstance(result, MemoryResult)
            assert result.key == "test-key"

    @pytest.mark.asyncio
    async def test_retrieve_by_key_returns_none_for_missing(self, mock_database):
        """Test retrieve_by_key() returns None when key not found."""
        with patch("src.infrastructure.memory.memory_service.MemoryStore") as MockStore:
            mock_store_instance = AsyncMock()
            mock_store_instance.get_by_key.return_value = None
            MockStore.return_value = mock_store_instance

            service = MemoryService(mock_database)
            result = await service.retrieve_by_key(
                "nonexistent-key", "org-test", user_id="user-123",
            )

            assert result is None


# ---------------------------------------------------------------------------
# TestMemoryServiceUpdate
# ---------------------------------------------------------------------------


class TestMemoryServiceUpdate:
    """Tests for MemoryService.update() method."""

    @pytest.mark.asyncio
    async def test_update_creates_new_version(self, mock_database, sample_memory):
        """Test update() creates a new version when body changes."""
        new_version = MemoryVersion(
            id=uuid.uuid4(),
            memory_id=sample_memory.id,
            version=2,
            body="Updated body content",
            extended_data={},
            change_summary="Updated content",
            changed_by="user-123",
            changed_by_agent=False,
            created_at=datetime.utcnow(),
        )

        updated_memory = Memory(
            id=sample_memory.id,
            organization_id="org-test",
            key="test-key",
            title="Test Memory",
            scope="organization",
            scope_value=None,
            topic="testing",
            tags=["unit", "test"],
            content_type="text",
            current_version=2,  # Version incremented
            status="active",
            created_by_user_id="user-123",
            created_by_agent_id=None,
            extra_metadata={"priority": "high"},
            created_at=sample_memory.created_at,
            updated_at=datetime.utcnow(),
        )

        with patch("src.infrastructure.memory.memory_service.MemoryStore") as MockStore:
            mock_store_instance = AsyncMock()
            mock_store_instance.get_by_id.side_effect = [sample_memory, updated_memory]
            mock_store_instance.check_permission.return_value = True
            mock_store_instance.update.return_value = new_version
            MockStore.return_value = mock_store_instance

            service = MemoryService(mock_database)
            request = MemoryUpdateRequest(
                body="Updated body content",
                change_summary="Updated content",
            )

            result = await service.update(
                str(sample_memory.id), "org-test", request, user_id="user-123",
            )

            mock_store_instance.update.assert_called_once()
            assert isinstance(result, MemoryResult)
            assert result.body == "Updated body content"
            assert result.version == 2

    @pytest.mark.asyncio
    async def test_update_raises_not_found(self, mock_database):
        """Test update() raises MemoryNotFoundError when memory not found."""
        with patch("src.infrastructure.memory.memory_service.MemoryStore") as MockStore:
            mock_store_instance = AsyncMock()
            mock_store_instance.get_by_id.return_value = None
            MockStore.return_value = mock_store_instance

            service = MemoryService(mock_database)
            request = MemoryUpdateRequest(body="New body")

            with pytest.raises(MemoryNotFoundError):
                await service.update(
                    "nonexistent-id", "org-test", request, user_id="user-123",
                )


# ---------------------------------------------------------------------------
# TestMemoryServiceDelete
# ---------------------------------------------------------------------------


class TestMemoryServiceDelete:
    """Tests for MemoryService.delete() method."""

    @pytest.mark.asyncio
    async def test_delete_delegates_to_store(self, mock_database, sample_memory):
        """Test delete() delegates to MemoryStore.soft_delete()."""
        with patch("src.infrastructure.memory.memory_service.MemoryStore") as MockStore:
            mock_store_instance = AsyncMock()
            mock_store_instance.get_by_id.return_value = sample_memory
            mock_store_instance.check_permission.return_value = True
            mock_store_instance.soft_delete.return_value = True
            MockStore.return_value = mock_store_instance

            service = MemoryService(mock_database)
            result = await service.delete(
                str(sample_memory.id), "org-test", user_id="user-123",
            )

            mock_store_instance.soft_delete.assert_called_once_with(
                str(sample_memory.id), "org-test",
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_delete_returns_false_for_missing(self, mock_database):
        """Test delete() returns False when memory not found."""
        with patch("src.infrastructure.memory.memory_service.MemoryStore") as MockStore:
            mock_store_instance = AsyncMock()
            mock_store_instance.get_by_id.return_value = None
            MockStore.return_value = mock_store_instance

            service = MemoryService(mock_database)
            result = await service.delete(
                "nonexistent-id", "org-test", user_id="user-123",
            )

            assert result is False


# ---------------------------------------------------------------------------
# TestMemoryServiceVersionHistory
# ---------------------------------------------------------------------------


class TestMemoryServiceVersionHistory:
    """Tests for MemoryService.get_version_history() method."""

    @pytest.mark.asyncio
    async def test_get_version_history_returns_versions(self, mock_database, sample_memory):
        """Test get_version_history() returns list of version dicts."""
        versions = [
            MemoryVersion(
                id=uuid.uuid4(),
                memory_id=sample_memory.id,
                version=2,
                body="Version 2 body",
                extended_data={},
                change_summary="Second update",
                changed_by="user-123",
                changed_by_agent=False,
                created_at=datetime.utcnow(),
            ),
            MemoryVersion(
                id=uuid.uuid4(),
                memory_id=sample_memory.id,
                version=1,
                body="Version 1 body",
                extended_data={},
                change_summary="Initial",
                changed_by="user-123",
                changed_by_agent=False,
                created_at=datetime.utcnow(),
            ),
        ]

        with patch("src.infrastructure.memory.memory_service.MemoryStore") as MockStore:
            mock_store_instance = AsyncMock()
            mock_store_instance.get_by_id.return_value = sample_memory
            mock_store_instance.check_permission.return_value = True
            mock_store_instance.get_version_history.return_value = versions
            MockStore.return_value = mock_store_instance

            service = MemoryService(mock_database)
            result = await service.get_version_history(
                str(sample_memory.id), "org-test", user_id="user-123",
            )

            assert len(result) == 2
            assert result[0]["version"] == 2
            assert result[1]["version"] == 1
            assert "body" in result[0]
            assert "change_summary" in result[0]

    @pytest.mark.asyncio
    async def test_get_version_history_returns_empty_for_missing(self, mock_database):
        """Test get_version_history() returns empty list when memory not found."""
        with patch("src.infrastructure.memory.memory_service.MemoryStore") as MockStore:
            mock_store_instance = AsyncMock()
            mock_store_instance.get_by_id.return_value = None
            MockStore.return_value = mock_store_instance

            service = MemoryService(mock_database)
            result = await service.get_version_history(
                "nonexistent-id", "org-test", user_id="user-123",
            )

            assert result == []


# ---------------------------------------------------------------------------
# TestMemoryServiceHealthCheck
# ---------------------------------------------------------------------------


class TestMemoryServiceHealthCheck:
    """Tests for MemoryService.health_check() method."""

    @pytest.mark.asyncio
    async def test_health_check_returns_true_on_success(self, mock_database):
        """Test health_check() returns True when DB is accessible."""
        with patch("src.infrastructure.memory.memory_service.MemoryLogger") as MockLogger:
            mock_logger_instance = MagicMock()
            MockLogger.return_value = mock_logger_instance

            service = MemoryService(mock_database)
            result = await service.health_check()

            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_failure(self):
        """Test health_check() returns False when DB is not accessible."""
        # Create a database that raises an exception
        mock_database = MagicMock()

        async_context = AsyncMock()
        async_context.__aenter__ = AsyncMock(side_effect=Exception("Connection failed"))
        async_context.__aexit__ = AsyncMock(return_value=None)

        mock_database.get_session = MagicMock(return_value=async_context)

        with patch("src.infrastructure.memory.memory_service.MemoryLogger") as MockLogger:
            mock_logger_instance = MagicMock()
            MockLogger.return_value = mock_logger_instance

            service = MemoryService(mock_database)
            result = await service.health_check()

            assert result is False
            mock_logger_instance.log_error.assert_called_once()
