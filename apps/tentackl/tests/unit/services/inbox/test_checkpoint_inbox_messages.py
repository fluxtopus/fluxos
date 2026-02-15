"""Unit tests for inbox checkpoint messages (INBOX-016).

Tests that:
- StepInboxMessagingAdapter.add_checkpoint_message creates a message when a
  checkpoint is created and sets priority to ATTENTION.
- TaskConversationAdapter.add_checkpoint_resolution_message creates follow-up
  messages when checkpoints are approved or rejected.
"""

import uuid
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.tasks.step_inbox_messaging_adapter import StepInboxMessagingAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

Row = namedtuple("Row", ["conversation_id", "user_id"])


def _mock_db(conversation_id=None, user_id="user-456"):
    """Create a mock Database with a session that returns task data."""
    db = MagicMock()
    session_mock = MagicMock()

    row = Row(conversation_id=conversation_id, user_id=user_id) if conversation_id else None
    result_mock = MagicMock()
    result_mock.one_or_none.return_value = row
    session_mock.execute = AsyncMock(return_value=result_mock)
    session_mock.commit = AsyncMock()

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session_mock)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    db.get_session = MagicMock(return_value=session_cm)

    return db


def _mock_publisher():
    """Create a mock TaskEventPublisher."""
    publisher = MagicMock()
    publisher.inbox_message_created = AsyncMock(return_value="event-id")
    return publisher


# ---------------------------------------------------------------------------
# Tests: StepInboxMessagingAdapter.add_checkpoint_message (checkpoint creation)
# ---------------------------------------------------------------------------


class TestAddInboxCheckpointMessage:
    @pytest.mark.asyncio
    async def test_creates_message_on_checkpoint(self):
        """Checkpoint creation adds an inbox message with ATTENTION priority."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456")
        publisher = _mock_publisher()

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(return_value=True)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_checkpoint_message(
                task_id=str(uuid.uuid4()),
                step_id="step-1",
                step_name="Deploy to production",
                description="Deploy the application to production servers",
            )

            instance.add_message.assert_awaited_once()
            call_kwargs = instance.add_message.call_args
            msg_data = call_kwargs.kwargs.get("message_data") or call_kwargs[1].get("message_data")
            assert msg_data.content.text == "Deploy the application to production servers. Awaiting your approval."

    @pytest.mark.asyncio
    async def test_uses_step_name_when_no_description(self):
        """Falls back to step_name if step_description is empty."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456")
        publisher = _mock_publisher()

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(return_value=True)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_checkpoint_message(
                task_id=str(uuid.uuid4()),
                step_id="step-1",
                step_name="Deploy to prod",
                description="",
            )

            instance.add_message.assert_awaited_once()
            call_kwargs = instance.add_message.call_args
            msg_data = call_kwargs.kwargs.get("message_data") or call_kwargs[1].get("message_data")
            assert msg_data.content.text == "Deploy to prod. Awaiting your approval."

    @pytest.mark.asyncio
    async def test_sets_priority_attention(self):
        """Checkpoint message sets conversation priority to ATTENTION."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456")
        publisher = _mock_publisher()

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(return_value=True)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_checkpoint_message(
                task_id=str(uuid.uuid4()),
                step_id="step-1",
                step_name="Deploy",
                description="Deploy step",
            )

            # Verify that session.execute was called for the priority update
            session_cm = db.get_session.return_value
            session = session_cm.__aenter__.return_value
            # At least 2 execute calls: 1 for select, 1 for update
            assert session.execute.await_count >= 2

    @pytest.mark.asyncio
    async def test_publishes_sse_event_with_attention(self):
        """Checkpoint message publishes SSE with attention priority."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456")
        publisher = _mock_publisher()

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(return_value=True)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_checkpoint_message(
                task_id=str(uuid.uuid4()),
                step_id="step-1",
                step_name="Deploy",
                description="Deploy step",
            )

            publisher.inbox_message_created.assert_awaited_once()
            call_kwargs = publisher.inbox_message_created.call_args.kwargs
            assert call_kwargs["priority"] == "attention"
            assert call_kwargs["user_id"] == "user-456"

    @pytest.mark.asyncio
    async def test_skips_when_no_conversation_id(self):
        """Skips silently when task has no conversation_id."""
        db = _mock_db(conversation_id=None)
        publisher = _mock_publisher()

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(return_value=True)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_checkpoint_message(
                task_id=str(uuid.uuid4()),
                step_id="step-1",
                step_name="Deploy",
                description="Deploy step",
            )

            instance.add_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exception_does_not_propagate(self):
        """Exceptions in checkpoint message creation do not propagate."""
        db = _mock_db(conversation_id=uuid.uuid4(), user_id="user-456")
        publisher = _mock_publisher()

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(side_effect=RuntimeError("DB error"))

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            # Should NOT raise
            await adapter.add_checkpoint_message(
                task_id=str(uuid.uuid4()),
                step_id="step-1",
                step_name="Deploy",
                description="Deploy step",
            )

    @pytest.mark.asyncio
    async def test_content_data_has_checkpoint_fields(self):
        """Content data includes checkpoint_type, task_id, and step_id."""
        conv_id = uuid.uuid4()
        task_id = str(uuid.uuid4())
        db = _mock_db(conversation_id=conv_id, user_id="user-456")
        publisher = _mock_publisher()

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(return_value=True)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_checkpoint_message(
                task_id=task_id,
                step_id="step-1",
                step_name="Deploy",
                description="Deploy step",
            )

            call_kwargs = instance.add_message.call_args
            msg_data = call_kwargs.kwargs.get("message_data") or call_kwargs[1].get("message_data")
            assert msg_data.content.data["checkpoint_type"] == "approval"
            assert msg_data.content.data["task_id"] == task_id
            assert msg_data.content.data["step_id"] == "step-1"


# ---------------------------------------------------------------------------
# Tests: TaskConversationAdapter.add_checkpoint_resolution_message (approval/rejection)
# ---------------------------------------------------------------------------


class TestAddInboxCheckpointResolutionMessage:
    def _make_conversation_adapter(self, db, event_bus=None):
        """Create a TaskConversationAdapter with mocked dependencies."""
        pg_store = MagicMock()
        pg_store.db = db

        redis_store = MagicMock()
        redis_store._connect = AsyncMock()

        from src.infrastructure.tasks.task_conversation_adapter import TaskConversationAdapter
        return TaskConversationAdapter(
            pg_store=pg_store,
            redis_store=redis_store,
            event_bus=event_bus,
        )

    @pytest.mark.asyncio
    async def test_creates_approved_message(self):
        """Approval creates a message saying 'Checkpoint approved. Resuming execution.'"""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456")
        event_bus = MagicMock()
        event_bus.inbox_message_created = AsyncMock(return_value="event-id")
        adapter = self._make_conversation_adapter(db, event_bus=event_bus)

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(return_value=True)

            await adapter.add_checkpoint_resolution_message(
                task_id=str(uuid.uuid4()),
                approved=True,
            )

            instance.add_message.assert_awaited_once()
            call_kwargs = instance.add_message.call_args
            msg_data = call_kwargs.kwargs.get("message_data") or call_kwargs[1].get("message_data")
            assert msg_data.content.text == "Checkpoint approved. Resuming execution."
            assert msg_data.content.data["resolution"] == "approved"

    @pytest.mark.asyncio
    async def test_creates_rejected_message_with_reason(self):
        """Rejection creates a message with the reason."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456")
        event_bus = MagicMock()
        event_bus.inbox_message_created = AsyncMock(return_value="event-id")
        adapter = self._make_conversation_adapter(db, event_bus=event_bus)

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(return_value=True)

            await adapter.add_checkpoint_resolution_message(
                task_id=str(uuid.uuid4()),
                approved=False,
                reason="Too risky",
            )

            instance.add_message.assert_awaited_once()
            call_kwargs = instance.add_message.call_args
            msg_data = call_kwargs.kwargs.get("message_data") or call_kwargs[1].get("message_data")
            assert msg_data.content.text == "Checkpoint rejected: Too risky. Task stopped."
            assert msg_data.content.data["resolution"] == "rejected"

    @pytest.mark.asyncio
    async def test_creates_rejected_message_without_reason(self):
        """Rejection without reason uses generic text."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456")
        event_bus = MagicMock()
        event_bus.inbox_message_created = AsyncMock(return_value="event-id")
        adapter = self._make_conversation_adapter(db, event_bus=event_bus)

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(return_value=True)

            await adapter.add_checkpoint_resolution_message(
                task_id=str(uuid.uuid4()),
                approved=False,
                reason="",
            )

            call_kwargs = instance.add_message.call_args
            msg_data = call_kwargs.kwargs.get("message_data") or call_kwargs[1].get("message_data")
            assert msg_data.content.text == "Checkpoint rejected. Task stopped."

    @pytest.mark.asyncio
    async def test_approval_sets_priority_normal(self):
        """Approval sets priority back to NORMAL via SSE."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456")
        event_bus = MagicMock()
        event_bus.inbox_message_created = AsyncMock(return_value="event-id")
        adapter = self._make_conversation_adapter(db, event_bus=event_bus)

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(return_value=True)

            await adapter.add_checkpoint_resolution_message(
                task_id=str(uuid.uuid4()),
                approved=True,
            )

            event_bus.inbox_message_created.assert_awaited_once()
            call_kwargs = event_bus.inbox_message_created.call_args.kwargs
            assert call_kwargs["priority"] == "normal"

    @pytest.mark.asyncio
    async def test_rejection_keeps_priority_attention(self):
        """Rejection keeps priority at ATTENTION via SSE."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456")
        event_bus = MagicMock()
        event_bus.inbox_message_created = AsyncMock(return_value="event-id")
        adapter = self._make_conversation_adapter(db, event_bus=event_bus)

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(return_value=True)

            await adapter.add_checkpoint_resolution_message(
                task_id=str(uuid.uuid4()),
                approved=False,
                reason="Too risky",
            )

            event_bus.inbox_message_created.assert_awaited_once()
            call_kwargs = event_bus.inbox_message_created.call_args.kwargs
            assert call_kwargs["priority"] == "attention"

    @pytest.mark.asyncio
    async def test_skips_when_no_conversation_id(self):
        """Skips silently when task has no conversation_id."""
        db = _mock_db(conversation_id=None)
        adapter = self._make_conversation_adapter(db)

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(return_value=True)

            await adapter.add_checkpoint_resolution_message(
                task_id=str(uuid.uuid4()),
                approved=True,
            )

            instance.add_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_when_no_pg_store(self):
        """Skips silently when _pg_store is None."""
        from src.infrastructure.tasks.task_conversation_adapter import TaskConversationAdapter
        adapter = TaskConversationAdapter(pg_store=None)

        # Should NOT raise
        await adapter.add_checkpoint_resolution_message(
            task_id=str(uuid.uuid4()),
            approved=True,
        )

    @pytest.mark.asyncio
    async def test_exception_does_not_propagate(self):
        """Exceptions in resolution message creation do not propagate."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456")
        adapter = self._make_conversation_adapter(db)

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(side_effect=RuntimeError("DB error"))

            # Should NOT raise
            await adapter.add_checkpoint_resolution_message(
                task_id=str(uuid.uuid4()),
                approved=True,
            )
