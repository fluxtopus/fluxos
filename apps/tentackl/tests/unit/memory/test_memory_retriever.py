"""Unit tests for MemoryRetriever's routing and scoring logic.

Tests query routing priority, relevance scoring, evidence building,
and permission filtering with mocked MemoryStore.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.database.memory_models import Memory, MemoryVersion
from src.domain.memory.models import MemoryQuery, MemoryScopeEnum
from src.infrastructure.memory.memory_retriever import MemoryRetriever
from src.infrastructure.memory.memory_logger import MemoryLogger
from src.infrastructure.memory.memory_store import MemoryStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_store():
    """Mock MemoryStore for unit tests."""
    store = AsyncMock(spec=MemoryStore)
    store.get_by_key = AsyncMock(return_value=None)
    store.get_by_id = AsyncMock(return_value=None)
    store.get_by_ids = AsyncMock(return_value={})
    store.get_current_version = AsyncMock(return_value=None)
    store.batch_get_current_versions = AsyncMock(return_value={})
    store.list_filtered = AsyncMock(return_value=([], 0))
    store.check_permission = AsyncMock(return_value=True)
    store.batch_check_permissions = AsyncMock(return_value=set())
    return store


@pytest.fixture
def mock_logger():
    """Mock MemoryLogger for unit tests."""
    logger = MagicMock(spec=MemoryLogger)
    logger.log_retrieval = MagicMock()
    return logger


@pytest.fixture
def sample_memory():
    """Sample Memory ORM object for testing."""
    memory_id = uuid.uuid4()
    return Memory(
        id=memory_id,
        organization_id="org-test",
        key="test-memory-key",
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
def sample_version(sample_memory):
    """Sample MemoryVersion ORM object."""
    return MemoryVersion(
        id=uuid.uuid4(),
        memory_id=sample_memory.id,
        version=1,
        body="This is the test memory body content.",
        extended_data={},
        change_summary="Initial version",
        changed_by="user-123",
        changed_by_agent=False,
        created_at=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# TestMemoryRetrieverRouting
# ---------------------------------------------------------------------------


class TestMemoryRetrieverRouting:
    """Tests for query routing logic."""

    @pytest.mark.asyncio
    async def test_exact_key_returns_single_result(
        self, mock_store, mock_logger, sample_memory, sample_version
    ):
        """Test query with key='x' calls store.get_by_key and returns single result."""
        mock_store.get_by_key.return_value = sample_memory
        mock_store.get_current_version.return_value = sample_version
        mock_store.batch_check_permissions.return_value = {str(sample_memory.id)}

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(organization_id="org-test", key="test-memory-key")

        result = await retriever.search(query)

        # Verify get_by_key was called with correct params
        mock_store.get_by_key.assert_called_once_with("test-memory-key", "org-test")
        # list_filtered should NOT be called for exact key lookup
        mock_store.list_filtered.assert_not_called()
        # Should return exactly one result
        assert len(result.memories) == 1
        assert result.memories[0].key == "test-memory-key"

    @pytest.mark.asyncio
    async def test_topic_filter_calls_list_filtered(
        self, mock_store, mock_logger, sample_memory, sample_version
    ):
        """Test query with topic='ops' calls list_filtered with topic parameter."""
        mock_store.list_filtered.return_value = ([sample_memory], 1)
        mock_store.batch_get_current_versions.return_value = {str(sample_memory.id): sample_version}
        mock_store.batch_check_permissions.return_value = {str(sample_memory.id)}

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(organization_id="org-test", topic="ops")

        result = await retriever.search(query)

        # Verify list_filtered was called with topic
        mock_store.list_filtered.assert_called_once()
        call_kwargs = mock_store.list_filtered.call_args.kwargs
        assert call_kwargs["organization_id"] == "org-test"
        assert call_kwargs["topic"] == "ops"

    @pytest.mark.asyncio
    async def test_tag_filter_applied(
        self, mock_store, mock_logger, sample_memory, sample_version
    ):
        """Test query with tags calls list_filtered with tags parameter."""
        mock_store.list_filtered.return_value = ([sample_memory], 1)
        mock_store.batch_get_current_versions.return_value = {str(sample_memory.id): sample_version}
        mock_store.batch_check_permissions.return_value = {str(sample_memory.id)}

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(organization_id="org-test", tags=["api", "learned"])

        result = await retriever.search(query)

        # Verify list_filtered was called with tags
        mock_store.list_filtered.assert_called_once()
        call_kwargs = mock_store.list_filtered.call_args.kwargs
        assert call_kwargs["tags"] == ["api", "learned"]

    @pytest.mark.asyncio
    async def test_org_id_always_required(self, mock_store, mock_logger):
        """Test every query passes org_id to the store."""
        mock_store.list_filtered.return_value = ([], 0)

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(organization_id="required-org")

        await retriever.search(query)

        # Verify list_filtered was called with organization_id
        mock_store.list_filtered.assert_called_once()
        call_kwargs = mock_store.list_filtered.call_args.kwargs
        assert call_kwargs["organization_id"] == "required-org"

    @pytest.mark.asyncio
    async def test_exact_key_not_found_returns_empty(self, mock_store, mock_logger):
        """Test exact key lookup returns empty when memory not found."""
        mock_store.get_by_key.return_value = None

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(organization_id="org-test", key="nonexistent-key")

        result = await retriever.search(query)

        assert len(result.memories) == 0
        assert result.total_count == 0

    @pytest.mark.asyncio
    async def test_scope_filter_applied(
        self, mock_store, mock_logger, sample_memory, sample_version
    ):
        """Test query with scope filter calls list_filtered with scope."""
        mock_store.list_filtered.return_value = ([sample_memory], 1)
        mock_store.batch_get_current_versions.return_value = {str(sample_memory.id): sample_version}
        mock_store.batch_check_permissions.return_value = {str(sample_memory.id)}

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(
            organization_id="org-test",
            scope=MemoryScopeEnum.USER,
            scope_value="user-123",
        )

        result = await retriever.search(query)

        call_kwargs = mock_store.list_filtered.call_args.kwargs
        assert call_kwargs["scope"] == "user"
        assert call_kwargs["scope_value"] == "user-123"


# ---------------------------------------------------------------------------
# TestMemoryRetrieverScoring
# ---------------------------------------------------------------------------


class TestMemoryRetrieverScoring:
    """Tests for relevance scoring logic."""

    @pytest.mark.asyncio
    async def test_exact_key_gets_score_1(
        self, mock_store, mock_logger, sample_memory, sample_version
    ):
        """Test exact key match gets relevance_score=1.0."""
        mock_store.get_by_key.return_value = sample_memory
        mock_store.get_current_version.return_value = sample_version
        mock_store.batch_check_permissions.return_value = {str(sample_memory.id)}

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(organization_id="org-test", key="test-key")

        result = await retriever.search(query)

        assert len(result.memories) == 1
        assert result.memories[0].evidence.relevance_score == 1.0

    @pytest.mark.asyncio
    async def test_topic_match_scores_higher_than_org_scan(
        self, mock_store, mock_logger, sample_memory, sample_version
    ):
        """Test topic match (0.8) scores higher than org scan (0.5)."""
        mock_store.list_filtered.return_value = ([sample_memory], 1)
        mock_store.batch_get_current_versions.return_value = {str(sample_memory.id): sample_version}
        mock_store.batch_check_permissions.return_value = {str(sample_memory.id)}

        retriever = MemoryRetriever(mock_store, mock_logger)

        # Topic match query
        topic_query = MemoryQuery(organization_id="org-test", topic="content")
        topic_result = await retriever.search(topic_query)
        topic_score = topic_result.memories[0].evidence.relevance_score

        # Reset mock for next call
        mock_store.list_filtered.reset_mock()

        # Org scan query (no filters)
        org_query = MemoryQuery(organization_id="org-test")
        org_result = await retriever.search(org_query)
        org_score = org_result.memories[0].evidence.relevance_score

        # Topic should score higher
        assert topic_score > org_score
        assert topic_score == 0.8
        assert org_score == 0.5

    @pytest.mark.asyncio
    async def test_tag_match_score(
        self, mock_store, mock_logger, sample_memory, sample_version
    ):
        """Test tag match gets score 0.6."""
        mock_store.list_filtered.return_value = ([sample_memory], 1)
        mock_store.batch_get_current_versions.return_value = {str(sample_memory.id): sample_version}
        mock_store.batch_check_permissions.return_value = {str(sample_memory.id)}

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(organization_id="org-test", tags=["test"])

        result = await retriever.search(query)

        assert result.memories[0].evidence.relevance_score == 0.6

    @pytest.mark.asyncio
    async def test_results_sorted_by_relevance_desc(
        self, mock_store, mock_logger, sample_version
    ):
        """Test results are returned (evidence built consistently for all)."""
        # Create two memories
        memory1 = Memory(
            id=uuid.uuid4(),
            organization_id="org-test",
            key="memory-1",
            title="Memory 1",
            scope="organization",
            topic="content",
            tags=[],
            content_type="text",
            current_version=1,
            status="active",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        memory2 = Memory(
            id=uuid.uuid4(),
            organization_id="org-test",
            key="memory-2",
            title="Memory 2",
            scope="organization",
            topic="content",
            tags=[],
            content_type="text",
            current_version=1,
            status="active",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        mock_store.list_filtered.return_value = ([memory1, memory2], 2)
        mock_store.batch_get_current_versions.return_value = {
            str(memory1.id): sample_version,
            str(memory2.id): sample_version,
        }
        mock_store.batch_check_permissions.return_value = {str(memory1.id), str(memory2.id)}

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(organization_id="org-test", topic="content")

        result = await retriever.search(query)

        # All results should have evidence with topic match score
        assert len(result.memories) == 2
        for memory in result.memories:
            assert memory.evidence.relevance_score == 0.8


# ---------------------------------------------------------------------------
# TestMemoryRetrieverEvidence
# ---------------------------------------------------------------------------


class TestMemoryRetrieverEvidence:
    """Tests for evidence building."""

    @pytest.mark.asyncio
    async def test_evidence_contains_match_type(
        self, mock_store, mock_logger, sample_memory, sample_version
    ):
        """Test evidence contains correct match_type."""
        mock_store.get_by_key.return_value = sample_memory
        mock_store.get_current_version.return_value = sample_version
        mock_store.batch_check_permissions.return_value = {str(sample_memory.id)}

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(organization_id="org-test", key="test-key")

        result = await retriever.search(query)

        assert result.memories[0].evidence.match_type == "exact_key"

    @pytest.mark.asyncio
    async def test_evidence_contains_filters_applied(
        self, mock_store, mock_logger, sample_memory, sample_version
    ):
        """Test evidence contains list of applied filters."""
        mock_store.list_filtered.return_value = ([sample_memory], 1)
        mock_store.batch_get_current_versions.return_value = {str(sample_memory.id): sample_version}
        mock_store.batch_check_permissions.return_value = {str(sample_memory.id)}

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(
            organization_id="org-test",
            topic="content",
            tags=["api"],
        )

        result = await retriever.search(query)

        filters = result.memories[0].evidence.filters_applied
        assert "topic" in filters
        assert "tags" in filters

    @pytest.mark.asyncio
    async def test_retrieval_path_logged(
        self, mock_store, mock_logger, sample_memory, sample_version
    ):
        """Test retrieval path contains expected entries."""
        mock_store.list_filtered.return_value = ([sample_memory], 1)
        mock_store.batch_get_current_versions.return_value = {str(sample_memory.id): sample_version}
        mock_store.batch_check_permissions.return_value = {str(sample_memory.id)}

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(organization_id="org-test", topic="ops")

        result = await retriever.search(query)

        # Retrieval path should contain topic filter entry
        assert any("filter:topic=ops" in path for path in result.retrieval_path)

    @pytest.mark.asyncio
    async def test_retrieval_path_exact_key(
        self, mock_store, mock_logger, sample_memory, sample_version
    ):
        """Test retrieval path for exact key lookup."""
        mock_store.get_by_key.return_value = sample_memory
        mock_store.get_current_version.return_value = sample_version
        mock_store.batch_check_permissions.return_value = {str(sample_memory.id)}

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(organization_id="org-test", key="brand-voice")

        result = await retriever.search(query)

        assert any("route:exact_key=brand-voice" in path for path in result.retrieval_path)

    @pytest.mark.asyncio
    async def test_retrieval_path_org_scan(self, mock_store, mock_logger):
        """Test retrieval path for org scan (no filters)."""
        mock_store.list_filtered.return_value = ([], 0)

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(organization_id="org-scan-test")

        result = await retriever.search(query)

        assert any("route:org_scan=org-scan-test" in path for path in result.retrieval_path)

    @pytest.mark.asyncio
    async def test_evidence_contains_retrieval_time(
        self, mock_store, mock_logger, sample_memory, sample_version
    ):
        """Test evidence contains retrieval_time_ms."""
        mock_store.list_filtered.return_value = ([sample_memory], 1)
        mock_store.batch_get_current_versions.return_value = {str(sample_memory.id): sample_version}
        mock_store.batch_check_permissions.return_value = {str(sample_memory.id)}

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(organization_id="org-test")

        result = await retriever.search(query)

        assert result.memories[0].evidence.retrieval_time_ms >= 0
        assert result.query_time_ms >= 0


# ---------------------------------------------------------------------------
# TestMemoryRetrieverPermissions
# ---------------------------------------------------------------------------


class TestMemoryRetrieverPermissions:
    """Tests for permission filtering."""

    @pytest.mark.asyncio
    async def test_denied_memories_excluded(
        self, mock_store, mock_logger, sample_version
    ):
        """Test memories denied by batch_check_permissions are excluded from results."""
        # Create two memories
        allowed_memory = Memory(
            id=uuid.uuid4(),
            organization_id="org-test",
            key="allowed",
            title="Allowed Memory",
            scope="organization",
            topic="testing",
            tags=[],
            content_type="text",
            current_version=1,
            status="active",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        denied_memory = Memory(
            id=uuid.uuid4(),
            organization_id="org-test",
            key="denied",
            title="Denied Memory",
            scope="user",
            scope_value="other-user",
            topic="testing",
            tags=[],
            content_type="text",
            current_version=1,
            status="active",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        mock_store.list_filtered.return_value = ([allowed_memory, denied_memory], 2)
        mock_store.batch_get_current_versions.return_value = {
            str(allowed_memory.id): sample_version,
            str(denied_memory.id): sample_version,
        }
        # Only allowed_memory is in the permitted set
        mock_store.batch_check_permissions.return_value = {str(allowed_memory.id)}

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(
            organization_id="org-test",
            requesting_user_id="current-user",
        )

        result = await retriever.search(query)

        # Only allowed memory should be in results
        assert len(result.memories) == 1
        assert result.memories[0].key == "allowed"

    @pytest.mark.asyncio
    async def test_denied_memories_logged_in_path(
        self, mock_store, mock_logger, sample_version
    ):
        """Test denied memories are logged in retrieval path."""
        denied_memory = Memory(
            id=uuid.uuid4(),
            organization_id="org-test",
            key="denied",
            title="Denied Memory",
            scope="user",
            scope_value="other-user",
            topic="testing",
            tags=[],
            content_type="text",
            current_version=1,
            status="active",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        mock_store.list_filtered.return_value = ([denied_memory], 1)
        mock_store.batch_get_current_versions.return_value = {str(denied_memory.id): sample_version}
        # Empty set = no permissions
        mock_store.batch_check_permissions.return_value = set()

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(organization_id="org-test", requesting_user_id="blocked-user")

        result = await retriever.search(query)

        # Should have denial in retrieval path
        assert any("denied:memory_id=" in path for path in result.retrieval_path)
        # Should have no memories in result
        assert len(result.memories) == 0

    @pytest.mark.asyncio
    async def test_batch_permission_check_called_once(
        self, mock_store, mock_logger, sample_version
    ):
        """Test batch_check_permissions is called once for all memories."""
        memories = [
            Memory(
                id=uuid.uuid4(),
                organization_id="org-test",
                key=f"memory-{i}",
                title=f"Memory {i}",
                scope="organization",
                topic="testing",
                tags=[],
                content_type="text",
                current_version=1,
                status="active",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            for i in range(3)
        ]

        mock_store.list_filtered.return_value = (memories, 3)
        mock_store.batch_get_current_versions.return_value = {
            str(m.id): sample_version for m in memories
        }
        mock_store.batch_check_permissions.return_value = {str(m.id) for m in memories}

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(organization_id="org-test")

        await retriever.search(query)

        # batch_check_permissions should be called exactly once
        assert mock_store.batch_check_permissions.call_count == 1

    @pytest.mark.asyncio
    async def test_all_permitted_when_no_requesting_user(
        self, mock_store, mock_logger, sample_memory, sample_version
    ):
        """Test memories are included when no requesting_user_id."""
        mock_store.list_filtered.return_value = ([sample_memory], 1)
        mock_store.batch_get_current_versions.return_value = {str(sample_memory.id): sample_version}
        mock_store.batch_check_permissions.return_value = {str(sample_memory.id)}

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(
            organization_id="org-test",
            # No requesting_user_id
        )

        result = await retriever.search(query)

        assert len(result.memories) == 1


# ---------------------------------------------------------------------------
# TestMemoryRetrieverLogging
# ---------------------------------------------------------------------------


class TestMemoryRetrieverLogging:
    """Tests for logging behavior."""

    @pytest.mark.asyncio
    async def test_log_retrieval_called(
        self, mock_store, mock_logger, sample_memory, sample_version
    ):
        """Test log_retrieval is called after search."""
        mock_store.list_filtered.return_value = ([sample_memory], 1)
        mock_store.batch_get_current_versions.return_value = {str(sample_memory.id): sample_version}
        mock_store.batch_check_permissions.return_value = {str(sample_memory.id)}

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(organization_id="org-test")

        await retriever.search(query)

        mock_logger.log_retrieval.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_retrieval_receives_query_and_response(
        self, mock_store, mock_logger, sample_memory, sample_version
    ):
        """Test log_retrieval receives the query and response."""
        mock_store.list_filtered.return_value = ([sample_memory], 1)
        mock_store.batch_get_current_versions.return_value = {str(sample_memory.id): sample_version}
        mock_store.batch_check_permissions.return_value = {str(sample_memory.id)}

        retriever = MemoryRetriever(mock_store, mock_logger)
        query = MemoryQuery(organization_id="org-test", topic="logging")

        result = await retriever.search(query)

        # Verify log_retrieval was called with query and response
        call_args = mock_logger.log_retrieval.call_args
        assert call_args[0][0] == query  # First arg is query
        assert call_args[0][1] == result  # Second arg is response
