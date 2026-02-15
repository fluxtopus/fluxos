"""Unit tests for inbox step messages (INBOX-014).

Tests that StepInboxMessagingAdapter.add_step_message creates conversation
messages when task steps complete or fail.
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

    # Simulate the select result
    row = Row(conversation_id=conversation_id, user_id=user_id) if conversation_id else None
    result_mock = MagicMock()
    result_mock.one_or_none.return_value = row
    session_mock.execute = AsyncMock(return_value=result_mock)

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
# Tests
# ---------------------------------------------------------------------------

class TestAddInboxStepMessage:
    @pytest.mark.asyncio
    async def test_creates_message_on_step_completed(self):
        """A step completion creates an inbox message with correct content."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456")
        publisher = _mock_publisher()

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(return_value=True)
            instance.update_read_status = AsyncMock(return_value=True)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_step_message(
                task_id=str(uuid.uuid4()),
                step_name="Fetch HN data",
                event_type="completed",
                text="Fetch HN data — done.",
                data={"step_id": "step-1", "outputs": {"result": "ok"}},
            )

            # Verify message was created
            instance.add_message.assert_awaited_once()
            call_kwargs = instance.add_message.call_args
            message_data = call_kwargs.kwargs["message_data"]
            assert message_data.content.text == "Fetch HN data — done."
            assert message_data.content.role == "assistant"
            assert message_data.content.data == {"step_id": "step-1", "outputs": {"result": "ok"}}
            assert message_data.agent_id == "task_orchestrator"

    @pytest.mark.asyncio
    async def test_creates_message_on_step_failed(self):
        """A step failure creates an inbox message with error details."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456")
        publisher = _mock_publisher()

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(return_value=True)
            instance.update_read_status = AsyncMock(return_value=True)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_step_message(
                task_id=str(uuid.uuid4()),
                step_name="Deploy app",
                event_type="failed",
                text="Deploy app — failed: API rate limited",
                data={"step_id": "step-2", "error": "API rate limited"},
            )

            instance.add_message.assert_awaited_once()
            call_kwargs = instance.add_message.call_args
            message_data = call_kwargs.kwargs["message_data"]
            assert message_data.content.text == "Deploy app — failed: API rate limited"
            assert message_data.content.data["error"] == "API rate limited"

    @pytest.mark.asyncio
    async def test_updates_read_status_to_unread(self):
        """Conversation read_status is set to UNREAD after new step message."""
        from src.database.models import ReadStatus

        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456")
        publisher = _mock_publisher()

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(return_value=True)
            instance.update_read_status = AsyncMock(return_value=True)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_step_message(
                task_id=str(uuid.uuid4()),
                step_name="Test step",
                event_type="completed",
                text="Test step — done.",
                data={},
            )

            instance.update_read_status.assert_awaited_once_with(
                conversation_id=str(conv_id),
                read_status=ReadStatus.UNREAD,
            )

    @pytest.mark.asyncio
    async def test_publishes_sse_event(self):
        """SSE event is published for the user when step message is added."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-789")
        publisher = _mock_publisher()

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(return_value=True)
            instance.update_read_status = AsyncMock(return_value=True)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_step_message(
                task_id=str(uuid.uuid4()),
                step_name="Analyze data",
                event_type="completed",
                text="Analyze data — done.",
                data={},
            )

            publisher.inbox_message_created.assert_awaited_once_with(
                user_id="user-789",
                conversation_id=str(conv_id),
                message_preview="Analyze data — done.",
                priority="normal",
            )

    @pytest.mark.asyncio
    async def test_skips_when_no_conversation_id(self):
        """If task has no conversation_id, message creation is skipped."""
        db = _mock_db(conversation_id=None, user_id="user-456")
        publisher = _mock_publisher()

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(return_value=True)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_step_message(
                task_id=str(uuid.uuid4()),
                step_name="Some step",
                event_type="completed",
                text="Some step — done.",
                data={},
            )

            # add_message should NOT have been called
            instance.add_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_when_task_not_found(self):
        """If task doesn't exist in DB, message creation is skipped."""
        db = MagicMock()
        session_mock = MagicMock()
        result_mock = MagicMock()
        result_mock.one_or_none.return_value = None
        session_mock.execute = AsyncMock(return_value=result_mock)
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=session_mock)
        session_cm.__aexit__ = AsyncMock(return_value=False)
        db.get_session = MagicMock(return_value=session_cm)

        publisher = _mock_publisher()

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(return_value=True)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_step_message(
                task_id=str(uuid.uuid4()),
                step_name="Some step",
                event_type="completed",
                text="Some step — done.",
                data={},
            )

            instance.add_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exception_does_not_propagate(self):
        """Any exception in inbox message creation is caught — task continues."""
        db = MagicMock()
        session_mock = MagicMock()
        session_mock.execute = AsyncMock(side_effect=RuntimeError("DB down"))
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=session_mock)
        session_cm.__aexit__ = AsyncMock(return_value=False)
        db.get_session = MagicMock(return_value=session_cm)

        publisher = _mock_publisher()

        adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
        # Should not raise
        await adapter.add_step_message(
            task_id=str(uuid.uuid4()),
            step_name="Step",
            event_type="completed",
            text="Step — done.",
            data={},
        )

    @pytest.mark.asyncio
    async def test_sse_failure_does_not_propagate(self):
        """If SSE publish fails, message creation still succeeds."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456")
        publisher = _mock_publisher()
        publisher.inbox_message_created = AsyncMock(
            side_effect=RuntimeError("Redis down")
        )

        with patch(
            "src.database.conversation_store.ConversationStore"
        ) as MockConvStore:
            instance = MockConvStore.return_value
            instance.add_message = AsyncMock(return_value=True)
            instance.update_read_status = AsyncMock(return_value=True)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            # Should not raise despite SSE failure
            await adapter.add_step_message(
                task_id=str(uuid.uuid4()),
                step_name="Step",
                event_type="completed",
                text="Step — done.",
                data={},
            )

            # Message was still created despite SSE failure
            instance.add_message.assert_awaited_once()
