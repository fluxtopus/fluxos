"""
Unit tests for the memory API router.

Tests all memory endpoints:
1. POST /api/memories           — create_memory
2. GET /api/memories/{id}       — get_memory
3. GET /api/memories            — search_memories
4. PUT /api/memories/{id}       — update_memory
5. DELETE /api/memories/{id}    — delete_memory
6. GET /api/memories/{id}/versions — get_memory_versions

Tests cover:
- Happy-path responses
- 404 for nonexistent memories
- 400 for missing organization_id
- Correct delegation to MemoryUseCases
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.api.auth_middleware import AuthUser
from src.api.routers.memories import (
    create_memory,
    get_memory,
    search_memories,
    update_memory,
    delete_memory,
    get_memory_versions,
    CreateMemoryRequest,
    UpdateMemoryRequest,
)
from src.domain.memory.models import (
    MemoryResult,
    MemorySearchResponse,
    RetrievalEvidence,
    MemoryNotFoundError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_user():
    """Authenticated user for tests."""
    return AuthUser(
        id="user-123",
        auth_type="bearer",
        username="testuser",
        metadata={"organization_id": "org-456"},
    )


@pytest.fixture
def mock_other_org_user():
    """User from a different organization."""
    return AuthUser(
        id="user-other",
        auth_type="bearer",
        username="otheruser",
        metadata={"organization_id": "org-other"},
    )


@pytest.fixture
def mock_no_org_user():
    """User with no organization_id in metadata."""
    return AuthUser(
        id="user-no-org",
        auth_type="bearer",
        username="noorguser",
        metadata={},
    )


@pytest.fixture
def sample_memory_result():
    """Sample MemoryResult for mocking service responses."""
    return MemoryResult(
        id="mem-123",
        key="brand-voice",
        title="Brand Voice Guidelines",
        body="Use confident but approachable tone.",
        scope="organization",
        topic="content",
        tags=["branding", "style"],
        version=1,
        extended_data={},
        metadata={},
        evidence=RetrievalEvidence(
            match_type="exact_key",
            relevance_score=1.0,
            filters_applied=[],
            retrieval_time_ms=5,
        ),
        created_at=datetime(2026, 2, 3, 10, 0, 0),
        updated_at=datetime(2026, 2, 3, 10, 0, 0),
    )


@pytest.fixture
def mock_memory_use_cases(sample_memory_result):
    """Mock MemoryUseCases."""
    service = MagicMock()
    service.store = AsyncMock(return_value=sample_memory_result)
    service.retrieve = AsyncMock(return_value=sample_memory_result)
    service.retrieve_by_key = AsyncMock(return_value=sample_memory_result)
    service.search = AsyncMock(return_value=MemorySearchResponse(
        memories=[sample_memory_result],
        total_count=1,
        retrieval_path=["filter:topic=content"],
        query_time_ms=10,
    ))
    service.update = AsyncMock(return_value=MemoryResult(
        id="mem-123",
        key="brand-voice",
        title="Updated Title",
        body="Updated body content.",
        scope="organization",
        topic="content",
        tags=["branding"],
        version=2,
        extended_data={},
        metadata={},
        evidence=RetrievalEvidence(
            match_type="exact_key",
            relevance_score=1.0,
            filters_applied=[],
            retrieval_time_ms=5,
        ),
        created_at=datetime(2026, 2, 3, 10, 0, 0),
        updated_at=datetime(2026, 2, 3, 11, 0, 0),
    ))
    service.delete = AsyncMock(return_value=True)
    service.get_version_history = AsyncMock(return_value=[
        {"version": 2, "body": "Updated body", "change_summary": "v2", "changed_by": "user-123", "changed_by_agent": False, "created_at": "2026-02-03T11:00:00"},
        {"version": 1, "body": "Original body", "change_summary": None, "changed_by": "user-123", "changed_by_agent": False, "created_at": "2026-02-03T10:00:00"},
    ])
    return service


@pytest.fixture(autouse=True)
def patch_memory_use_cases(mock_memory_use_cases):
    """Patch the module-level _get_memory_use_cases for all tests."""
    with patch(
        "src.api.routers.memories._get_memory_use_cases",
        return_value=mock_memory_use_cases,
    ):
        yield


# ---------------------------------------------------------------------------
# POST /api/memories (create_memory)
# ---------------------------------------------------------------------------


class TestCreateMemory:
    @pytest.mark.asyncio
    async def test_success(self, mock_user, mock_memory_use_cases):
        """Test successful memory creation."""
        result = await create_memory(
            request=CreateMemoryRequest(
                key="brand-voice",
                title="Brand Voice Guidelines",
                body="Use confident but approachable tone.",
                topic="content",
                tags=["branding", "style"],
            ),
            user=mock_user,
        )

        assert result.id == "mem-123"
        assert result.key == "brand-voice"
        assert result.version == 1
        mock_memory_use_cases.store.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_extracts_org_from_metadata(self, mock_user, mock_memory_use_cases):
        """Test that organization_id is extracted from user metadata."""
        await create_memory(
            request=CreateMemoryRequest(
                key="test-key",
                title="Test",
                body="Test body",
            ),
            user=mock_user,
        )

        call_args = mock_memory_use_cases.store.call_args
        create_request = call_args[0][0]
        assert create_request.organization_id == "org-456"
        assert create_request.created_by_user_id == "user-123"

    @pytest.mark.asyncio
    async def test_no_org_returns_400(self, mock_no_org_user, mock_memory_use_cases):
        """Test that missing organization_id returns 400."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await create_memory(
                request=CreateMemoryRequest(
                    key="test-key",
                    title="Test",
                    body="Test body",
                ),
                user=mock_no_org_user,
            )
        assert exc_info.value.status_code == 400
        assert "organization" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_invalid_scope_returns_400(self, mock_user, mock_memory_use_cases):
        """Test that invalid scope returns 400."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await create_memory(
                request=CreateMemoryRequest(
                    key="test-key",
                    title="Test",
                    body="Test body",
                    scope="invalid_scope",
                ),
                user=mock_user,
            )
        assert exc_info.value.status_code == 400
        assert "scope" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# GET /api/memories/{memory_id} (get_memory)
# ---------------------------------------------------------------------------


class TestGetMemory:
    @pytest.mark.asyncio
    async def test_success(self, mock_user, mock_memory_use_cases):
        """Test successful memory retrieval."""
        result = await get_memory(
            memory_id="mem-123",
            user=mock_user,
        )

        assert result.id == "mem-123"
        assert result.key == "brand-voice"
        mock_memory_use_cases.retrieve.assert_awaited_once_with(
            "mem-123", "org-456", user_id="user-123",
        )

    @pytest.mark.asyncio
    async def test_404_not_found(self, mock_user, mock_memory_use_cases):
        """Test 404 when memory doesn't exist."""
        mock_memory_use_cases.retrieve.return_value = None

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_memory(
                memory_id="nonexistent",
                user=mock_user,
            )
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_no_org_returns_400(self, mock_no_org_user, mock_memory_use_cases):
        """Test that missing organization_id returns 400."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_memory(
                memory_id="mem-123",
                user=mock_no_org_user,
            )
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/memories (search_memories)
# ---------------------------------------------------------------------------


class TestSearchMemories:
    @pytest.mark.asyncio
    async def test_returns_results(self, mock_user, mock_memory_use_cases):
        """Test successful memory search."""
        result = await search_memories(
            text=None,
            topic=None,
            tags=None,
            scope=None,
            key=None,
            limit=20,
            offset=0,
            user=mock_user,
        )

        assert result.total_count == 1
        assert len(result.memories) == 1
        assert result.memories[0].key == "brand-voice"
        mock_memory_use_cases.search.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_passes_topic_filter(self, mock_user, mock_memory_use_cases):
        """Test that topic filter is passed to service."""
        await search_memories(
            text=None,
            topic="content",
            tags=None,
            scope=None,
            key=None,
            limit=20,
            offset=0,
            user=mock_user,
        )

        call_args = mock_memory_use_cases.search.call_args
        query = call_args[0][0]
        assert query.topic == "content"

    @pytest.mark.asyncio
    async def test_passes_tag_filter(self, mock_user, mock_memory_use_cases):
        """Test that comma-separated tags are parsed and passed to service."""
        await search_memories(
            text=None,
            topic=None,
            tags="branding,style",
            scope=None,
            key=None,
            limit=20,
            offset=0,
            user=mock_user,
        )

        call_args = mock_memory_use_cases.search.call_args
        query = call_args[0][0]
        assert query.tags == ["branding", "style"]

    @pytest.mark.asyncio
    async def test_passes_key_filter(self, mock_user, mock_memory_use_cases):
        """Test that key filter is passed to service."""
        await search_memories(
            text=None,
            topic=None,
            tags=None,
            scope=None,
            key="brand-voice",
            limit=20,
            offset=0,
            user=mock_user,
        )

        call_args = mock_memory_use_cases.search.call_args
        query = call_args[0][0]
        assert query.key == "brand-voice"

    @pytest.mark.asyncio
    async def test_passes_scope_filter(self, mock_user, mock_memory_use_cases):
        """Test that scope filter is passed to service as enum."""
        await search_memories(
            text=None,
            topic=None,
            tags=None,
            scope="organization",
            key=None,
            limit=20,
            offset=0,
            user=mock_user,
        )

        call_args = mock_memory_use_cases.search.call_args
        query = call_args[0][0]
        assert query.scope.value == "organization"

    @pytest.mark.asyncio
    async def test_invalid_scope_returns_400(self, mock_user, mock_memory_use_cases):
        """Test that invalid scope returns 400."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await search_memories(
                text=None,
                topic=None,
                tags=None,
                scope="invalid_scope",
                key=None,
                limit=20,
                offset=0,
                user=mock_user,
            )
        assert exc_info.value.status_code == 400
        assert "scope" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_no_org_returns_400(self, mock_no_org_user, mock_memory_use_cases):
        """Test that missing organization_id returns 400."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await search_memories(
                text=None,
                topic=None,
                tags=None,
                scope=None,
                key=None,
                limit=20,
                offset=0,
                user=mock_no_org_user,
            )
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# PUT /api/memories/{memory_id} (update_memory)
# ---------------------------------------------------------------------------


class TestUpdateMemory:
    @pytest.mark.asyncio
    async def test_success_creates_version(self, mock_user, mock_memory_use_cases):
        """Test successful memory update creates new version."""
        result = await update_memory(
            memory_id="mem-123",
            request=UpdateMemoryRequest(
                body="Updated body content.",
                title="Updated Title",
            ),
            user=mock_user,
        )

        assert result.id == "mem-123"
        assert result.version == 2
        assert result.body == "Updated body content."
        mock_memory_use_cases.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_passes_user_as_changed_by(self, mock_user, mock_memory_use_cases):
        """Test that user_id is passed as changed_by."""
        await update_memory(
            memory_id="mem-123",
            request=UpdateMemoryRequest(body="New body"),
            user=mock_user,
        )

        call_args = mock_memory_use_cases.update.call_args
        # Args: memory_id, org_id, update_request
        update_request = call_args[0][2]
        assert update_request.changed_by == "user-123"
        assert update_request.changed_by_agent is False

    @pytest.mark.asyncio
    async def test_404_not_found(self, mock_user, mock_memory_use_cases):
        """Test 404 when memory doesn't exist."""
        mock_memory_use_cases.update.side_effect = MemoryNotFoundError("Memory not found")

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await update_memory(
                memory_id="nonexistent",
                request=UpdateMemoryRequest(body="New body"),
                user=mock_user,
            )
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_no_org_returns_400(self, mock_no_org_user, mock_memory_use_cases):
        """Test that missing organization_id returns 400."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await update_memory(
                memory_id="mem-123",
                request=UpdateMemoryRequest(body="New body"),
                user=mock_no_org_user,
            )
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# DELETE /api/memories/{memory_id} (delete_memory)
# ---------------------------------------------------------------------------


class TestDeleteMemory:
    @pytest.mark.asyncio
    async def test_success_returns_204(self, mock_user, mock_memory_use_cases):
        """Test successful deletion returns None (for 204 response)."""
        result = await delete_memory(
            memory_id="mem-123",
            user=mock_user,
        )

        # DELETE returns None for 204 No Content
        assert result is None
        mock_memory_use_cases.delete.assert_awaited_once_with(
            "mem-123", "org-456", user_id="user-123",
        )

    @pytest.mark.asyncio
    async def test_404_not_found(self, mock_user, mock_memory_use_cases):
        """Test 404 when memory doesn't exist."""
        mock_memory_use_cases.delete.return_value = False

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await delete_memory(
                memory_id="nonexistent",
                user=mock_user,
            )
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_no_org_returns_400(self, mock_no_org_user, mock_memory_use_cases):
        """Test that missing organization_id returns 400."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await delete_memory(
                memory_id="mem-123",
                user=mock_no_org_user,
            )
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/memories/{memory_id}/versions (get_memory_versions)
# ---------------------------------------------------------------------------


class TestGetVersions:
    @pytest.mark.asyncio
    async def test_returns_versions(self, mock_user, mock_memory_use_cases):
        """Test successful version history retrieval."""
        result = await get_memory_versions(
            memory_id="mem-123",
            limit=20,
            user=mock_user,
        )

        assert len(result) == 2
        assert result[0].version == 2
        assert result[1].version == 1
        mock_memory_use_cases.get_version_history.assert_awaited_once_with(
            "mem-123", "org-456", user_id="user-123", limit=20,
        )

    @pytest.mark.asyncio
    async def test_404_nonexistent(self, mock_user, mock_memory_use_cases):
        """Test 404 when memory doesn't exist."""
        mock_memory_use_cases.get_version_history.return_value = []
        mock_memory_use_cases.retrieve.return_value = None

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_memory_versions(
                memory_id="nonexistent",
                limit=20,
                user=mock_user,
            )
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_no_org_returns_400(self, mock_no_org_user, mock_memory_use_cases):
        """Test that missing organization_id returns 400."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_memory_versions(
                memory_id="mem-123",
                limit=20,
                user=mock_no_org_user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_versions_for_existing_memory(self, mock_user, mock_memory_use_cases, sample_memory_result):
        """Test returns empty list when memory exists but has no versions."""
        mock_memory_use_cases.get_version_history.return_value = []
        mock_memory_use_cases.retrieve.return_value = sample_memory_result

        result = await get_memory_versions(
            memory_id="mem-123",
            limit=20,
            user=mock_user,
        )

        # Empty list, but not 404 since memory exists
        assert result == []


# ---------------------------------------------------------------------------
# Pydantic model validation tests
# ---------------------------------------------------------------------------


class TestRequestModels:
    def test_create_memory_request(self):
        """Test CreateMemoryRequest validation."""
        req = CreateMemoryRequest(
            key="test-key",
            title="Test Title",
            body="Test body content",
            topic="testing",
            tags=["a", "b"],
        )
        assert req.key == "test-key"
        assert req.scope == "organization"  # default

    def test_create_memory_request_with_all_fields(self):
        """Test CreateMemoryRequest with all optional fields."""
        req = CreateMemoryRequest(
            key="test-key",
            title="Test Title",
            body="Test body content",
            scope="user",
            scope_value="user-123",
            topic="testing",
            tags=["a", "b"],
            content_type="markdown",
            extended_data={"custom": "data"},
            metadata={"source": "api"},
        )
        assert req.scope == "user"
        assert req.extended_data == {"custom": "data"}

    def test_update_memory_request(self):
        """Test UpdateMemoryRequest validation."""
        req = UpdateMemoryRequest(
            body="Updated body",
            change_summary="Minor fix",
        )
        assert req.body == "Updated body"
        assert req.change_summary == "Minor fix"
        assert req.title is None  # optional

    def test_update_memory_request_partial(self):
        """Test UpdateMemoryRequest with only some fields."""
        req = UpdateMemoryRequest(tags=["new", "tags"])
        assert req.tags == ["new", "tags"]
        assert req.body is None
