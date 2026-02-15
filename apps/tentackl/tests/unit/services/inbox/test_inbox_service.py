"""Unit tests for InboxService."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.database.models import InboxPriority, ReadStatus
from src.infrastructure.inbox.inbox_service import InboxService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_store():
    store = MagicMock()
    store.get_inbox_conversations = AsyncMock(return_value=[])
    store.get_unread_count = AsyncMock(return_value=0)
    store.update_read_status = AsyncMock(return_value=True)
    store.bulk_update_read_status = AsyncMock(return_value=0)
    store.get_inbox_thread = AsyncMock(return_value=None)
    return store


@pytest.fixture
def mock_summary():
    return MagicMock()


@pytest.fixture
def service(mock_store, mock_summary):
    return InboxService(
        conversation_store=mock_store,
        summary_service=mock_summary,
    )


# ---------------------------------------------------------------------------
# list_inbox
# ---------------------------------------------------------------------------

class TestListInbox:
    @pytest.mark.asyncio
    async def test_returns_correct_structure(self, service, mock_store):
        result = await service.list_inbox("user-1")
        assert result == {"items": [], "total": 0, "limit": 50, "offset": 0}
        mock_store.get_inbox_conversations.assert_awaited_once_with(
            user_id="user-1",
            read_status=None,
            priority=None,
            search_text=None,
            exclude_archived=False,
            limit=50,
            offset=0,
        )

    @pytest.mark.asyncio
    async def test_passes_read_status_filter(self, service, mock_store):
        await service.list_inbox("u", read_status="unread")
        mock_store.get_inbox_conversations.assert_awaited_once()
        call_kwargs = mock_store.get_inbox_conversations.call_args.kwargs
        assert call_kwargs["read_status"] == ReadStatus.UNREAD

    @pytest.mark.asyncio
    async def test_passes_priority_filter(self, service, mock_store):
        await service.list_inbox("u", priority="attention")
        call_kwargs = mock_store.get_inbox_conversations.call_args.kwargs
        assert call_kwargs["priority"] == InboxPriority.ATTENTION

    @pytest.mark.asyncio
    async def test_custom_limit_offset(self, service, mock_store):
        result = await service.list_inbox("u", limit=10, offset=20)
        assert result["limit"] == 10
        assert result["offset"] == 20

    @pytest.mark.asyncio
    async def test_invalid_read_status_raises(self, service):
        with pytest.raises(ValueError):
            await service.list_inbox("u", read_status="bogus")

    @pytest.mark.asyncio
    async def test_invalid_priority_raises(self, service):
        with pytest.raises(ValueError):
            await service.list_inbox("u", priority="bogus")


# ---------------------------------------------------------------------------
# get_unread_count
# ---------------------------------------------------------------------------

class TestGetUnreadCount:
    @pytest.mark.asyncio
    async def test_delegates_to_store(self, service, mock_store):
        mock_store.get_unread_count.return_value = 5
        count = await service.get_unread_count("user-1")
        assert count == 5
        mock_store.get_unread_count.assert_awaited_once_with("user-1")


# ---------------------------------------------------------------------------
# update_status
# ---------------------------------------------------------------------------

class TestUpdateStatus:
    @pytest.mark.asyncio
    async def test_valid_status(self, service, mock_store):
        result = await service.update_status("conv-id", "read")
        assert result is True
        mock_store.update_read_status.assert_awaited_once_with(
            "conv-id", ReadStatus.READ
        )

    @pytest.mark.asyncio
    async def test_all_valid_values(self, service, mock_store):
        for val in ("unread", "read", "archived"):
            await service.update_status("cid", val)

    @pytest.mark.asyncio
    async def test_invalid_status_raises(self, service):
        with pytest.raises(ValueError):
            await service.update_status("cid", "invalid")


# ---------------------------------------------------------------------------
# bulk_update_status
# ---------------------------------------------------------------------------

class TestBulkUpdateStatus:
    @pytest.mark.asyncio
    async def test_delegates(self, service, mock_store):
        mock_store.bulk_update_read_status.return_value = 3
        count = await service.bulk_update_status(
            ["c1", "c2", "c3"], "archived"
        )
        assert count == 3
        mock_store.bulk_update_read_status.assert_awaited_once_with(
            ["c1", "c2", "c3"], ReadStatus.ARCHIVED
        )

    @pytest.mark.asyncio
    async def test_empty_list(self, service, mock_store):
        count = await service.bulk_update_status([], "read")
        assert count == 0

    @pytest.mark.asyncio
    async def test_invalid_status_raises(self, service):
        with pytest.raises(ValueError):
            await service.bulk_update_status(["c1"], "nope")


# ---------------------------------------------------------------------------
# get_thread
# ---------------------------------------------------------------------------

class TestGetThread:
    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self, service, mock_store):
        result = await service.get_thread("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delegates_to_store(self, service, mock_store):
        mock_store.get_inbox_thread.return_value = {
            "conversation_id": "c1",
            "messages": [],
        }
        result = await service.get_thread("c1")
        assert result["conversation_id"] == "c1"
        mock_store.get_inbox_thread.assert_awaited_once_with("c1")


# ---------------------------------------------------------------------------
# create_follow_up
# ---------------------------------------------------------------------------

class TestCreateFollowUp:
    @pytest.mark.asyncio
    async def test_raises_if_conversation_not_found(self, service, mock_store):
        mock_store.get_inbox_thread.return_value = None
        with pytest.raises(ValueError, match="not found"):
            await service.create_follow_up(
                "missing-conv", "user-1", "org-1", "Do more"
            )

    @pytest.mark.asyncio
    async def test_raises_if_no_task_linked(self, service, mock_store):
        mock_store.get_inbox_thread.return_value = {
            "conversation_id": "c1",
            "task": None,
            "messages": [],
        }
        with pytest.raises(ValueError, match="No task linked"):
            await service.create_follow_up(
                "c1", "user-1", "org-1", "Do more"
            )
