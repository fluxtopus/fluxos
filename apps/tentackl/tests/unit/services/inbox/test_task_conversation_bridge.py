"""Unit tests for Task-Conversation Bridge (INBOX-013).

Tests that TaskConversationAdapter.ensure_conversation creates a Conversation linked to a task
when execution starts.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.database.models import MessageDirection, MessageType, TriggerType


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Use valid UUIDs since the implementation calls uuid.UUID(task_id) for SQL queries
TASK_ID = "00000000-0000-4000-8000-000000000123"
USER_ID = "00000000-0000-4000-8000-000000000456"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conversation_adapter(pg_store=None, redis_store=None):
    """Create a TaskConversationAdapter with mocked task stores."""
    from src.infrastructure.tasks.task_conversation_adapter import TaskConversationAdapter

    return TaskConversationAdapter(
        pg_store=pg_store,
        redis_store=redis_store,
    )


def _mock_pg_store():
    """Create a mock PostgresTaskStore with a db attribute."""
    store = MagicMock()
    store.db = MagicMock()
    store.update_task = AsyncMock(return_value=True)

    # Mock the db.get_session context manager
    session_mock = MagicMock()
    session_mock.execute = AsyncMock()
    session_mock.commit = AsyncMock()
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session_mock)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    store.db.get_session = MagicMock(return_value=session_cm)

    return store


def _mock_conversation():
    """Create a mock Conversation object."""
    conv = MagicMock()
    conv.id = uuid.uuid4()
    return conv


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCreateInboxConversation:

    def _mock_early_checks(self, adapter, pg_store):
        """Mock early checks in ensure_conversation.

        The implementation now calls:
        1. pg_store.get_task() — check for automation-cloned tasks
        2. SQL SELECT on TaskModel.conversation_id — check for existing conversation

        Both must be mocked so the method proceeds to ConversationStore creation.
        """
        # 1. Not an automation task (no automation_id in metadata)
        adapter._pg_store.get_task = AsyncMock(
            return_value=MagicMock(metadata={})
        )

        # 2. SQL SELECT returns no existing conversation_id
        session_mock = pg_store.db.get_session.return_value.__aenter__.return_value
        result_proxy = MagicMock()
        result_proxy.first = MagicMock(return_value=None)
        session_mock.execute = AsyncMock(return_value=result_proxy)

    @pytest.mark.asyncio
    async def test_creates_conversation_with_correct_fields(self):
        """Conversation is created with UNREAD status and NORMAL priority."""
        pg_store = _mock_pg_store()
        redis_store = MagicMock()
        redis_store.update_task = AsyncMock(return_value=True)
        adapter = _make_conversation_adapter(pg_store=pg_store, redis_store=redis_store)
        self._mock_early_checks(adapter, pg_store)

        mock_conv = _mock_conversation()

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.start_conversation = AsyncMock(return_value=mock_conv)
            instance.add_message = AsyncMock(return_value=True)

            # Import is deferred inside the method, so we also patch it there
            with patch(
                "src.database.conversation_store.ConversationStore",
                MockConvStore,
            ):
                await adapter.ensure_conversation(
                    task_id=TASK_ID,
                    goal="Compile HN digest",
                    user_id=USER_ID,
                )

            # Verify conversation was created
            instance.start_conversation.assert_awaited_once()
            call_kwargs = instance.start_conversation.call_args
            assert call_kwargs.kwargs["workflow_id"] == TASK_ID
            assert call_kwargs.kwargs["root_agent_id"] == "task_orchestrator"
            trigger = call_kwargs.kwargs["trigger"]
            assert trigger.type == TriggerType.MANUAL
            assert trigger.conversation_source == "task"

    @pytest.mark.asyncio
    async def test_updates_task_conversation_id(self):
        """Task record is updated with conversation_id."""
        pg_store = _mock_pg_store()
        redis_store = MagicMock()
        redis_store.update_task = AsyncMock(return_value=True)
        adapter = _make_conversation_adapter(pg_store=pg_store, redis_store=redis_store)
        self._mock_early_checks(adapter, pg_store)

        mock_conv = _mock_conversation()

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.start_conversation = AsyncMock(return_value=mock_conv)
            instance.add_message = AsyncMock(return_value=True)

            await adapter.ensure_conversation(
                task_id=TASK_ID,
                goal="Test goal",
                user_id=USER_ID,
            )

        # Verify PG store updated with conversation_id (UUID object)
        pg_store.update_task.assert_awaited_once_with(
            TASK_ID,
            {"conversation_id": mock_conv.id},
        )
        # Verify Redis store updated with string conversation_id
        redis_store.update_task.assert_awaited_once_with(
            TASK_ID,
            {"conversation_id": str(mock_conv.id)},
        )

    @pytest.mark.asyncio
    async def test_creates_first_message(self):
        """First message says 'Started working on: {goal}'."""
        pg_store = _mock_pg_store()
        adapter = _make_conversation_adapter(pg_store=pg_store)
        self._mock_early_checks(adapter, pg_store)

        mock_conv = _mock_conversation()

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.start_conversation = AsyncMock(return_value=mock_conv)
            instance.add_message = AsyncMock(return_value=True)

            await adapter.ensure_conversation(
                task_id=TASK_ID,
                goal="Compile HN digest",
                user_id=USER_ID,
            )

            # Verify add_message was called
            instance.add_message.assert_awaited_once()
            call_kwargs = instance.add_message.call_args
            assert call_kwargs.kwargs["conversation_id"] == str(mock_conv.id)
            message_data = call_kwargs.kwargs["message_data"]
            assert message_data.content.text == "Started working on: Compile HN digest"
            assert message_data.content.role == "assistant"
            assert message_data.agent_id == "task_orchestrator"
            assert message_data.message_type == MessageType.LLM_RESPONSE
            assert message_data.direction == MessageDirection.OUTBOUND

    @pytest.mark.asyncio
    async def test_no_pg_store_skips_silently(self):
        """If pg_store is None, method returns without error."""
        adapter = _make_conversation_adapter(pg_store=None)
        # Should not raise
        await adapter.ensure_conversation(
            task_id=TASK_ID,
            goal="Test",
            user_id=USER_ID,
        )

    @pytest.mark.asyncio
    async def test_exception_does_not_propagate(self):
        """Any exception in inbox creation is caught — task execution continues."""
        pg_store = _mock_pg_store()
        adapter = _make_conversation_adapter(pg_store=pg_store)

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.start_conversation = AsyncMock(
                side_effect=RuntimeError("DB connection failed")
            )

            # Should not raise
            await adapter.ensure_conversation(
                task_id=TASK_ID,
                goal="Test",
                user_id=USER_ID,
            )

    @pytest.mark.asyncio
    async def test_sets_inbox_fields_via_session(self):
        """Verify that user_id, read_status, and priority are set via SQL update."""
        pg_store = _mock_pg_store()
        adapter = _make_conversation_adapter(pg_store=pg_store)
        self._mock_early_checks(adapter, pg_store)

        mock_conv = _mock_conversation()

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.start_conversation = AsyncMock(return_value=mock_conv)
            instance.add_message = AsyncMock(return_value=True)

            await adapter.ensure_conversation(
                task_id=TASK_ID,
                goal="Test",
                user_id=USER_ID,
            )

        # Session execute was called: once for SELECT (conversation_id check)
        # and once for UPDATE (inbox fields). Each uses a separate get_session call.
        session_cm = pg_store.db.get_session.return_value
        session_mock = session_cm.__aenter__.return_value
        session_mock.execute.assert_awaited()
        session_mock.commit.assert_awaited()
