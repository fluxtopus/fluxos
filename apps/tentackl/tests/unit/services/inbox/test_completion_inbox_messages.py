"""Unit tests for inbox completion messages (INBOX-015).

Tests that StepInboxMessagingAdapter.add_completion_message creates summary
messages when tasks complete or fail, updates conversation status and priority.
"""

import uuid
from collections import namedtuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.tasks.step_inbox_messaging_adapter import StepInboxMessagingAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

Row = namedtuple("Row", ["conversation_id", "user_id", "goal", "accumulated_findings"])


def _mock_db(conversation_id=None, user_id="user-456", goal="Compile HN digest", findings=None):
    """Create a mock Database with a session that returns task data."""
    db = MagicMock()
    session_mock = MagicMock()

    row = (
        Row(
            conversation_id=conversation_id,
            user_id=user_id,
            goal=goal,
            accumulated_findings=findings or [],
        )
        if conversation_id
        else None
    )
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
# Tests
# ---------------------------------------------------------------------------

class TestAddInboxCompletionMessage:
    @pytest.mark.asyncio
    async def test_creates_summary_message_on_completion(self):
        """Task completion creates an inbox summary message."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456", goal="Compile HN digest")
        publisher = _mock_publisher()

        with (
            patch("src.database.conversation_store.ConversationStore") as MockConvStore,
            patch("src.infrastructure.tasks.task_summary_adapter.TaskSummaryAdapter") as MockSummary,
            patch("src.infrastructure.tasks.stores.postgres_task_store.PostgresTaskStore") as MockPgStore,
        ):
            conv_instance = MockConvStore.return_value
            conv_instance.add_message = AsyncMock(return_value=True)

            summary_instance = MockSummary.return_value
            summary_instance.generate_summary_safe = AsyncMock(
                return_value="Completed: Compile HN digest. 3/3 steps executed."
            )

            pg_instance = MockPgStore.return_value
            pg_instance.get_task = AsyncMock(return_value=None)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_completion_message(
                task_id=str(uuid.uuid4()),
                status="completed",
                steps_completed=3,
                total_steps=3,
            )

            # Verify summary was generated
            summary_instance.generate_summary_safe.assert_awaited_once()
            call_kwargs = summary_instance.generate_summary_safe.call_args.kwargs
            assert call_kwargs["goal"] == "Compile HN digest"
            assert call_kwargs["status"] == "completed"
            assert call_kwargs["steps_completed"] == 3
            assert call_kwargs["total_steps"] == 3

            # Verify message was created
            conv_instance.add_message.assert_awaited_once()
            msg_kwargs = conv_instance.add_message.call_args.kwargs
            message_data = msg_kwargs["message_data"]
            assert message_data.content.text == "Completed: Compile HN digest. 3/3 steps executed."
            assert message_data.content.role == "assistant"
            assert message_data.content.data["summary_type"] == "outcome"
            assert message_data.content.data["steps_completed"] == 3
            assert message_data.content.data["total_steps"] == 3
            assert message_data.agent_id == "task_orchestrator"

    @pytest.mark.asyncio
    async def test_creates_summary_message_on_failure(self):
        """Task failure creates a failure summary message with error."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456", goal="Deploy app")
        publisher = _mock_publisher()

        with (
            patch("src.database.conversation_store.ConversationStore") as MockConvStore,
            patch("src.infrastructure.tasks.task_summary_adapter.TaskSummaryAdapter") as MockSummary,
            patch("src.infrastructure.tasks.stores.postgres_task_store.PostgresTaskStore") as MockPgStore,
        ):
            conv_instance = MockConvStore.return_value
            conv_instance.add_message = AsyncMock(return_value=True)

            summary_instance = MockSummary.return_value
            summary_instance.generate_summary_safe = AsyncMock(
                return_value="Failed: Deploy app. Error: API rate limited. 2/4 steps completed before failure."
            )

            pg_instance = MockPgStore.return_value
            pg_instance.get_task = AsyncMock(return_value=None)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_completion_message(
                task_id=str(uuid.uuid4()),
                status="failed",
                steps_completed=2,
                total_steps=4,
                error="API rate limited",
            )

            # Verify summary included error
            call_kwargs = summary_instance.generate_summary_safe.call_args.kwargs
            assert call_kwargs["error"] == "API rate limited"
            assert call_kwargs["status"] == "failed"

            # Verify message content_data has failure type
            msg_kwargs = conv_instance.add_message.call_args.kwargs
            message_data = msg_kwargs["message_data"]
            assert message_data.content.data["summary_type"] == "failure"

    @pytest.mark.asyncio
    async def test_sets_priority_attention_on_failure(self):
        """Failed tasks set conversation priority to ATTENTION."""
        from src.database.models import InboxPriority, ConversationStatus, ReadStatus

        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456")
        publisher = _mock_publisher()

        with (
            patch("src.database.conversation_store.ConversationStore") as MockConvStore,
            patch("src.infrastructure.tasks.task_summary_adapter.TaskSummaryAdapter") as MockSummary,
            patch("src.infrastructure.tasks.stores.postgres_task_store.PostgresTaskStore") as MockPgStore,
        ):
            conv_instance = MockConvStore.return_value
            conv_instance.add_message = AsyncMock(return_value=True)

            summary_instance = MockSummary.return_value
            summary_instance.generate_summary_safe = AsyncMock(return_value="Failed.")

            pg_instance = MockPgStore.return_value
            pg_instance.get_task = AsyncMock(return_value=None)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_completion_message(
                task_id=str(uuid.uuid4()),
                status="failed",
                steps_completed=1,
                total_steps=3,
                error="Timeout",
            )

            # Check the sa_update call for priority=ATTENTION and status=FAILED
            # The second get_session() call (for the update) should have execute called
            # with the update statement
            session_mock = db.get_session.return_value.__aenter__.return_value
            # Find the execute call that includes the update (second call)
            calls = session_mock.execute.call_args_list
            assert len(calls) >= 2  # first=select, second=update

    @pytest.mark.asyncio
    async def test_sets_priority_normal_on_completion(self):
        """Completed tasks set conversation priority to NORMAL."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456")
        publisher = _mock_publisher()

        with (
            patch("src.database.conversation_store.ConversationStore") as MockConvStore,
            patch("src.infrastructure.tasks.task_summary_adapter.TaskSummaryAdapter") as MockSummary,
            patch("src.infrastructure.tasks.stores.postgres_task_store.PostgresTaskStore") as MockPgStore,
        ):
            conv_instance = MockConvStore.return_value
            conv_instance.add_message = AsyncMock(return_value=True)

            summary_instance = MockSummary.return_value
            summary_instance.generate_summary_safe = AsyncMock(return_value="Done.")

            pg_instance = MockPgStore.return_value
            pg_instance.get_task = AsyncMock(return_value=None)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_completion_message(
                task_id=str(uuid.uuid4()),
                status="completed",
                steps_completed=3,
                total_steps=3,
            )

            # Verify session execute was called for update
            session_mock = db.get_session.return_value.__aenter__.return_value
            calls = session_mock.execute.call_args_list
            assert len(calls) >= 2

    @pytest.mark.asyncio
    async def test_updates_conversation_status_completed(self):
        """Completed tasks set conversation status to COMPLETED."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456")
        publisher = _mock_publisher()

        with (
            patch("src.database.conversation_store.ConversationStore") as MockConvStore,
            patch("src.infrastructure.tasks.task_summary_adapter.TaskSummaryAdapter") as MockSummary,
            patch("src.infrastructure.tasks.stores.postgres_task_store.PostgresTaskStore") as MockPgStore,
        ):
            conv_instance = MockConvStore.return_value
            conv_instance.add_message = AsyncMock(return_value=True)

            summary_instance = MockSummary.return_value
            summary_instance.generate_summary_safe = AsyncMock(return_value="Done.")

            pg_instance = MockPgStore.return_value
            pg_instance.get_task = AsyncMock(return_value=None)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_completion_message(
                task_id=str(uuid.uuid4()),
                status="completed",
                steps_completed=3,
                total_steps=3,
            )

            # Session should have committed after the update
            session_mock = db.get_session.return_value.__aenter__.return_value
            session_mock.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_publishes_sse_event_with_correct_priority(self):
        """SSE event is published with priority matching task status."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-789")
        publisher = _mock_publisher()

        with (
            patch("src.database.conversation_store.ConversationStore") as MockConvStore,
            patch("src.infrastructure.tasks.task_summary_adapter.TaskSummaryAdapter") as MockSummary,
            patch("src.infrastructure.tasks.stores.postgres_task_store.PostgresTaskStore") as MockPgStore,
        ):
            conv_instance = MockConvStore.return_value
            conv_instance.add_message = AsyncMock(return_value=True)

            summary_instance = MockSummary.return_value
            summary_instance.generate_summary_safe = AsyncMock(return_value="Failed: timeout")

            pg_instance = MockPgStore.return_value
            pg_instance.get_task = AsyncMock(return_value=None)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_completion_message(
                task_id=str(uuid.uuid4()),
                status="failed",
                steps_completed=1,
                total_steps=3,
                error="Timeout",
            )

            publisher.inbox_message_created.assert_awaited_once_with(
                user_id="user-789",
                conversation_id=str(conv_id),
                message_preview="Failed: timeout",
                priority="attention",
            )

    @pytest.mark.asyncio
    async def test_publishes_sse_normal_priority_on_success(self):
        """SSE event for completed task uses 'normal' priority."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-789")
        publisher = _mock_publisher()

        with (
            patch("src.database.conversation_store.ConversationStore") as MockConvStore,
            patch("src.infrastructure.tasks.task_summary_adapter.TaskSummaryAdapter") as MockSummary,
            patch("src.infrastructure.tasks.stores.postgres_task_store.PostgresTaskStore") as MockPgStore,
        ):
            conv_instance = MockConvStore.return_value
            conv_instance.add_message = AsyncMock(return_value=True)

            summary_instance = MockSummary.return_value
            summary_instance.generate_summary_safe = AsyncMock(return_value="Completed: task done.")

            pg_instance = MockPgStore.return_value
            pg_instance.get_task = AsyncMock(return_value=None)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_completion_message(
                task_id=str(uuid.uuid4()),
                status="completed",
                steps_completed=3,
                total_steps=3,
            )

            publisher.inbox_message_created.assert_awaited_once_with(
                user_id="user-789",
                conversation_id=str(conv_id),
                message_preview="Completed: task done.",
                priority="normal",
            )

    @pytest.mark.asyncio
    async def test_skips_when_no_conversation_id(self):
        """If task has no conversation_id, completion message is skipped."""
        db = _mock_db(conversation_id=None, user_id="user-456")
        publisher = _mock_publisher()

        with (
            patch("src.database.conversation_store.ConversationStore") as MockConvStore,
            patch("src.infrastructure.tasks.task_summary_adapter.TaskSummaryAdapter") as MockSummary,
        ):
            conv_instance = MockConvStore.return_value
            conv_instance.add_message = AsyncMock(return_value=True)

            summary_instance = MockSummary.return_value
            summary_instance.generate_summary_safe = AsyncMock(return_value="Done.")

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_completion_message(
                task_id=str(uuid.uuid4()),
                status="completed",
                steps_completed=3,
                total_steps=3,
            )

            conv_instance.add_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exception_does_not_propagate(self):
        """Any exception in inbox completion message creation is caught."""
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
        await adapter.add_completion_message(
            task_id=str(uuid.uuid4()),
            status="completed",
            steps_completed=3,
            total_steps=3,
        )

    @pytest.mark.asyncio
    async def test_sse_failure_does_not_propagate(self):
        """If SSE publish fails, message creation still succeeds."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456")
        publisher = _mock_publisher()
        publisher.inbox_message_created = AsyncMock(side_effect=RuntimeError("Redis down"))

        with (
            patch("src.database.conversation_store.ConversationStore") as MockConvStore,
            patch("src.infrastructure.tasks.task_summary_adapter.TaskSummaryAdapter") as MockSummary,
            patch("src.infrastructure.tasks.stores.postgres_task_store.PostgresTaskStore") as MockPgStore,
        ):
            conv_instance = MockConvStore.return_value
            conv_instance.add_message = AsyncMock(return_value=True)

            summary_instance = MockSummary.return_value
            summary_instance.generate_summary_safe = AsyncMock(return_value="Done.")

            pg_instance = MockPgStore.return_value
            pg_instance.get_task = AsyncMock(return_value=None)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            # Should not raise despite SSE failure
            await adapter.add_completion_message(
                task_id=str(uuid.uuid4()),
                status="completed",
                steps_completed=3,
                total_steps=3,
            )

            # Message was still created despite SSE failure
            conv_instance.add_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_completion_data_includes_step_outputs(self):
        """Completion message data includes step_outputs when key_outputs exist."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456", goal="Analyze image")
        publisher = _mock_publisher()

        mock_task = MagicMock()
        mock_step = MagicMock()
        mock_step.status = MagicMock()
        mock_step.status.value = "done"
        mock_step.name = "describe"
        mock_step.id = "step-1"
        mock_step.outputs = {"result": "A photo of a sunset."}
        mock_task.steps = [mock_step]

        with (
            patch("src.database.conversation_store.ConversationStore") as MockConvStore,
            patch("src.infrastructure.tasks.task_summary_adapter.TaskSummaryAdapter") as MockSummary,
            patch("src.infrastructure.tasks.stores.postgres_task_store.PostgresTaskStore") as MockPgStore,
        ):
            conv_instance = MockConvStore.return_value
            conv_instance.add_message = AsyncMock(return_value=True)

            summary_instance = MockSummary.return_value
            summary_instance.generate_summary_safe = AsyncMock(return_value="A photo of a sunset.")

            pg_instance = MockPgStore.return_value
            pg_instance.get_task = AsyncMock(return_value=mock_task)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_completion_message(
                task_id=str(uuid.uuid4()),
                status="completed",
                steps_completed=1,
                total_steps=1,
            )

            msg_kwargs = conv_instance.add_message.call_args.kwargs
            message_data = msg_kwargs["message_data"]
            assert message_data.content.data["step_outputs"] == {"describe": {"result": "A photo of a sunset."}}
            assert message_data.content.data["summary_type"] == "outcome"

    @pytest.mark.asyncio
    async def test_completion_data_includes_findings(self):
        """Completion message data includes findings when present."""
        conv_id = uuid.uuid4()
        findings = [{"type": "insight", "text": "Important finding"}]
        db = _mock_db(conversation_id=conv_id, user_id="user-456", findings=findings)
        publisher = _mock_publisher()

        with (
            patch("src.database.conversation_store.ConversationStore") as MockConvStore,
            patch("src.infrastructure.tasks.task_summary_adapter.TaskSummaryAdapter") as MockSummary,
            patch("src.infrastructure.tasks.stores.postgres_task_store.PostgresTaskStore") as MockPgStore,
        ):
            conv_instance = MockConvStore.return_value
            conv_instance.add_message = AsyncMock(return_value=True)

            summary_instance = MockSummary.return_value
            summary_instance.generate_summary_safe = AsyncMock(return_value="Done.")

            pg_instance = MockPgStore.return_value
            pg_instance.get_task = AsyncMock(return_value=None)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_completion_message(
                task_id=str(uuid.uuid4()),
                status="completed",
                steps_completed=3,
                total_steps=3,
            )

            msg_kwargs = conv_instance.add_message.call_args.kwargs
            message_data = msg_kwargs["message_data"]
            assert message_data.content.data["findings"] == findings

    @pytest.mark.asyncio
    async def test_completion_data_omits_empty_outputs(self):
        """Completion data does not include step_outputs or findings when empty."""
        conv_id = uuid.uuid4()
        db = _mock_db(conversation_id=conv_id, user_id="user-456")
        publisher = _mock_publisher()

        with (
            patch("src.database.conversation_store.ConversationStore") as MockConvStore,
            patch("src.infrastructure.tasks.task_summary_adapter.TaskSummaryAdapter") as MockSummary,
            patch("src.infrastructure.tasks.stores.postgres_task_store.PostgresTaskStore") as MockPgStore,
        ):
            conv_instance = MockConvStore.return_value
            conv_instance.add_message = AsyncMock(return_value=True)

            summary_instance = MockSummary.return_value
            summary_instance.generate_summary_safe = AsyncMock(return_value="Done.")

            pg_instance = MockPgStore.return_value
            pg_instance.get_task = AsyncMock(return_value=None)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_completion_message(
                task_id=str(uuid.uuid4()),
                status="completed",
                steps_completed=3,
                total_steps=3,
            )

            msg_kwargs = conv_instance.add_message.call_args.kwargs
            message_data = msg_kwargs["message_data"]
            assert "step_outputs" not in message_data.content.data
            assert "findings" not in message_data.content.data

    @pytest.mark.asyncio
    async def test_passes_findings_to_summary_service(self):
        """Accumulated findings from the task are passed to the summary service."""
        conv_id = uuid.uuid4()
        findings = [{"type": "insight", "text": "Top story has 500 points"}]
        db = _mock_db(conversation_id=conv_id, user_id="user-456", findings=findings)
        publisher = _mock_publisher()

        with (
            patch("src.database.conversation_store.ConversationStore") as MockConvStore,
            patch("src.infrastructure.tasks.task_summary_adapter.TaskSummaryAdapter") as MockSummary,
            patch("src.infrastructure.tasks.stores.postgres_task_store.PostgresTaskStore") as MockPgStore,
        ):
            conv_instance = MockConvStore.return_value
            conv_instance.add_message = AsyncMock(return_value=True)

            summary_instance = MockSummary.return_value
            summary_instance.generate_summary_safe = AsyncMock(return_value="Done.")

            pg_instance = MockPgStore.return_value
            pg_instance.get_task = AsyncMock(return_value=None)

            adapter = StepInboxMessagingAdapter(db=db, publisher=publisher)
            await adapter.add_completion_message(
                task_id=str(uuid.uuid4()),
                status="completed",
                steps_completed=3,
                total_steps=3,
            )

            call_kwargs = summary_instance.generate_summary_safe.call_args.kwargs
            assert call_kwargs["findings"] == findings
