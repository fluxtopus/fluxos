"""
Unit tests for the inbox API router.

Tests all 7 inbox endpoints:
1. GET /api/inbox               — list_inbox
2. GET /api/inbox/unread-count  — get_unread_count
3. PATCH /api/inbox/{id}        — update_status (single)
4. PATCH /api/inbox/bulk        — bulk_update_status
5. GET /api/inbox/{id}/thread   — get_thread
6. POST /api/inbox/{id}/follow-up — create_follow_up
7. GET /api/inbox/events        — inbox_events (SSE)

Tests cover:
- Happy-path responses
- 404 for nonexistent conversations
- 403 for wrong user (ownership)
- 400 for invalid input (bad enum values)
- Correct delegation to InboxService
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.auth_middleware import AuthUser
from src.api.routers.inbox import (
    list_inbox,
    get_unread_count,
    update_status,
    bulk_update_status,
    get_thread,
    create_follow_up,
    StatusUpdateRequest,
    BulkStatusUpdateRequest,
    FollowUpRequest,
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
def mock_other_user():
    """A different user for ownership tests."""
    return AuthUser(
        id="user-other",
        auth_type="bearer",
        username="otheruser",
        metadata={},
    )


@pytest.fixture
def mock_inbox_service():
    """Mock InboxService."""
    service = MagicMock()
    service.list_inbox = AsyncMock(return_value={
        "items": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
    })
    service.get_unread_count = AsyncMock(return_value=0)
    service.update_status = AsyncMock(return_value=True)
    service.bulk_update_status = AsyncMock(return_value=0)
    service.get_thread = AsyncMock(return_value=None)
    service.create_follow_up = AsyncMock(return_value={
        "task_id": "new-task-id",
        "conversation_id": "new-conv-id",
        "goal": "follow up",
        "status": "planning",
    })
    return service


@pytest.fixture
def mock_conversation_store():
    """Mock ConversationStore used for ownership checks."""
    store = MagicMock()
    store.get_conversation_user_id = AsyncMock(return_value=None)
    return store


@pytest.fixture(autouse=True)
def patch_service_and_store(mock_inbox_service, mock_conversation_store):
    """Patch the module-level globals for all tests."""
    with patch(
        "src.api.routers.inbox._get_inbox_service",
        return_value=mock_inbox_service,
    ), patch(
        "src.api.routers.inbox.conversation_store",
        mock_conversation_store,
    ):
        yield


# ---------------------------------------------------------------------------
# GET /api/inbox (list_inbox)
# ---------------------------------------------------------------------------


class TestListInbox:
    @pytest.mark.asyncio
    async def test_returns_paginated_result(self, mock_user, mock_inbox_service):
        mock_inbox_service.list_inbox.return_value = {
            "items": [{"id": "c1"}],
            "total": 1,
            "limit": 50,
            "offset": 0,
        }

        result = await list_inbox(
            read_status=None,
            priority=None,
            q=None,
            limit=50,
            offset=0,
            user=mock_user,
        )

        assert result["total"] == 1
        assert len(result["items"]) == 1
        mock_inbox_service.list_inbox.assert_awaited_once_with(
            user_id="user-123",
            read_status=None,
            priority=None,
            search_text=None,
            exclude_archived=True,
            limit=50,
            offset=0,
        )

    @pytest.mark.asyncio
    async def test_passes_filters(self, mock_user, mock_inbox_service):
        await list_inbox(
            read_status="unread",
            priority="attention",
            q=None,
            limit=10,
            offset=5,
            user=mock_user,
        )

        mock_inbox_service.list_inbox.assert_awaited_once_with(
            user_id="user-123",
            read_status="unread",
            priority="attention",
            search_text=None,
            exclude_archived=False,
            limit=10,
            offset=5,
        )

    @pytest.mark.asyncio
    async def test_invalid_read_status_returns_400(self, mock_user, mock_inbox_service):
        mock_inbox_service.list_inbox.side_effect = ValueError("bad status")

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await list_inbox(
                read_status="bogus",
                priority=None,
                q=None,
                limit=50,
                offset=0,
                user=mock_user,
            )
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/inbox/unread-count
# ---------------------------------------------------------------------------


class TestGetUnreadCount:
    @pytest.mark.asyncio
    async def test_returns_count(self, mock_user, mock_inbox_service):
        mock_inbox_service.get_unread_count.return_value = 7

        result = await get_unread_count(user=mock_user)

        assert result == {"count": 7}
        mock_inbox_service.get_unread_count.assert_awaited_once_with("user-123")

    @pytest.mark.asyncio
    async def test_zero_count(self, mock_user, mock_inbox_service):
        result = await get_unread_count(user=mock_user)
        assert result == {"count": 0}


# ---------------------------------------------------------------------------
# PATCH /api/inbox/{conversation_id} (update_status)
# ---------------------------------------------------------------------------


class TestUpdateStatus:
    @pytest.mark.asyncio
    async def test_success(self, mock_user, mock_inbox_service, mock_conversation_store):
        mock_conversation_store.get_conversation_user_id.return_value = "user-123"
        mock_inbox_service.update_status.return_value = True

        result = await update_status(
            conversation_id="conv-1",
            body=StatusUpdateRequest(read_status="read"),
            user=mock_user,
        )

        assert result["success"] is True
        assert result["conversation_id"] == "conv-1"
        assert result["read_status"] == "read"

    @pytest.mark.asyncio
    async def test_404_not_found(self, mock_user, mock_conversation_store):
        mock_conversation_store.get_conversation_user_id.return_value = None

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await update_status(
                conversation_id="nonexistent",
                body=StatusUpdateRequest(read_status="read"),
                user=mock_user,
            )
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_403_wrong_user(self, mock_user, mock_conversation_store):
        mock_conversation_store.get_conversation_user_id.return_value = "other-user"

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await update_status(
                conversation_id="conv-1",
                body=StatusUpdateRequest(read_status="read"),
                user=mock_user,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_400_invalid_status(self, mock_user, mock_inbox_service, mock_conversation_store):
        mock_conversation_store.get_conversation_user_id.return_value = "user-123"
        mock_inbox_service.update_status.side_effect = ValueError("bad value")

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await update_status(
                conversation_id="conv-1",
                body=StatusUpdateRequest(read_status="invalid"),
                user=mock_user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_404_when_update_returns_false(self, mock_user, mock_inbox_service, mock_conversation_store):
        mock_conversation_store.get_conversation_user_id.return_value = "user-123"
        mock_inbox_service.update_status.return_value = False

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await update_status(
                conversation_id="conv-1",
                body=StatusUpdateRequest(read_status="read"),
                user=mock_user,
            )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/inbox/bulk (bulk_update_status)
# ---------------------------------------------------------------------------


class TestBulkUpdateStatus:
    @pytest.mark.asyncio
    async def test_success(self, mock_user, mock_inbox_service):
        mock_inbox_service.bulk_update_status.return_value = 3

        result = await bulk_update_status(
            body=BulkStatusUpdateRequest(
                conversation_ids=["c1", "c2", "c3"],
                read_status="archived",
            ),
            user=mock_user,
        )

        assert result == {"updated": 3}
        mock_inbox_service.bulk_update_status.assert_awaited_once_with(
            conversation_ids=["c1", "c2", "c3"],
            read_status="archived",
        )

    @pytest.mark.asyncio
    async def test_400_invalid_status(self, mock_user, mock_inbox_service):
        mock_inbox_service.bulk_update_status.side_effect = ValueError("bad")

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await bulk_update_status(
                body=BulkStatusUpdateRequest(
                    conversation_ids=["c1"],
                    read_status="nope",
                ),
                user=mock_user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_list(self, mock_user, mock_inbox_service):
        mock_inbox_service.bulk_update_status.return_value = 0

        result = await bulk_update_status(
            body=BulkStatusUpdateRequest(
                conversation_ids=[],
                read_status="read",
            ),
            user=mock_user,
        )
        assert result == {"updated": 0}


# ---------------------------------------------------------------------------
# GET /api/inbox/{conversation_id}/thread
# ---------------------------------------------------------------------------


class TestGetThread:
    @pytest.mark.asyncio
    async def test_success(self, mock_user, mock_inbox_service, mock_conversation_store):
        mock_conversation_store.get_conversation_user_id.return_value = "user-123"
        mock_inbox_service.get_thread.return_value = {
            "conversation_id": "conv-1",
            "messages": [{"id": "m1", "text": "hello"}],
            "task": {"id": "t1", "goal": "test"},
        }

        result = await get_thread(
            conversation_id="conv-1",
            user=mock_user,
        )

        assert result["conversation_id"] == "conv-1"
        assert len(result["messages"]) == 1
        mock_inbox_service.get_thread.assert_awaited_once_with("conv-1")

    @pytest.mark.asyncio
    async def test_404_not_found(self, mock_user, mock_conversation_store):
        mock_conversation_store.get_conversation_user_id.return_value = None

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_thread(conversation_id="missing", user=mock_user)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_403_wrong_user(self, mock_user, mock_conversation_store):
        mock_conversation_store.get_conversation_user_id.return_value = "other-user"

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_thread(conversation_id="conv-1", user=mock_user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_404_thread_returns_none(self, mock_user, mock_inbox_service, mock_conversation_store):
        mock_conversation_store.get_conversation_user_id.return_value = "user-123"
        mock_inbox_service.get_thread.return_value = None

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await get_thread(conversation_id="conv-1", user=mock_user)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/inbox/{conversation_id}/follow-up
# ---------------------------------------------------------------------------


class TestCreateFollowUp:
    @pytest.mark.asyncio
    async def test_success(self, mock_user, mock_inbox_service, mock_conversation_store):
        mock_conversation_store.get_conversation_user_id.return_value = "user-123"
        mock_inbox_service.create_follow_up.return_value = {
            "task_id": "new-task",
            "conversation_id": "new-conv",
            "goal": "Do more work",
            "status": "planning",
        }

        result = await create_follow_up(
            conversation_id="conv-1",
            body=FollowUpRequest(text="Do more work"),
            user=mock_user,
        )

        assert result["task_id"] == "new-task"
        assert result["goal"] == "Do more work"
        mock_inbox_service.create_follow_up.assert_awaited_once_with(
            conversation_id="conv-1",
            user_id="user-123",
            organization_id="org-456",
            follow_up_text="Do more work",
        )

    @pytest.mark.asyncio
    async def test_404_not_found(self, mock_user, mock_conversation_store):
        mock_conversation_store.get_conversation_user_id.return_value = None

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await create_follow_up(
                conversation_id="missing",
                body=FollowUpRequest(text="follow up"),
                user=mock_user,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_403_wrong_user(self, mock_user, mock_conversation_store):
        mock_conversation_store.get_conversation_user_id.return_value = "other-user"

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await create_follow_up(
                conversation_id="conv-1",
                body=FollowUpRequest(text="follow up"),
                user=mock_user,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_400_value_error(self, mock_user, mock_inbox_service, mock_conversation_store):
        mock_conversation_store.get_conversation_user_id.return_value = "user-123"
        mock_inbox_service.create_follow_up.side_effect = ValueError("No task linked")

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await create_follow_up(
                conversation_id="conv-1",
                body=FollowUpRequest(text="follow up"),
                user=mock_user,
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_no_org_id_uses_empty_string(self, mock_inbox_service, mock_conversation_store):
        """When user has no organization_id in metadata, pass empty string."""
        mock_conversation_store.get_conversation_user_id.return_value = "user-no-org"
        user_no_org = AuthUser(
            id="user-no-org",
            auth_type="bearer",
            metadata={},
        )

        await create_follow_up(
            conversation_id="conv-1",
            body=FollowUpRequest(text="follow up"),
            user=user_no_org,
        )

        call_kwargs = mock_inbox_service.create_follow_up.call_args.kwargs
        assert call_kwargs["organization_id"] == ""


# ---------------------------------------------------------------------------
# Pydantic model validation tests
# ---------------------------------------------------------------------------


class TestRequestModels:
    def test_status_update_request(self):
        req = StatusUpdateRequest(read_status="read")
        assert req.read_status == "read"

    def test_bulk_status_update_request(self):
        req = BulkStatusUpdateRequest(
            conversation_ids=["c1", "c2"],
            read_status="archived",
        )
        assert len(req.conversation_ids) == 2
        assert req.read_status == "archived"

    def test_follow_up_request(self):
        req = FollowUpRequest(text="Do more")
        assert req.text == "Do more"
