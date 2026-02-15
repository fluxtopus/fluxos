"""Integration tests for Task-Conversation Bridge (INBOX-018).

Verifies the full flow of inbox conversation creation, message
generation, and query operations using a real PostgreSQL database
via the integration_db fixture (isolated schema per test).
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, update as sa_update

from src.database.conversation_store import (
    ConversationStore,
    ConversationTrigger,
    MessageContent,
    MessageData,
    MessageMetadata,
)
from src.database.models import (
    Conversation,
    ConversationStatus,
    InboxPriority,
    MessageDirection,
    MessageType,
    ReadStatus,
    TriggerType,
)
from src.database.task_models import Task as TaskModel
from src.domain.tasks.models import Task, TaskStatus, TaskStep, StepStatus
from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_task_with_steps(
    pg_store: PostgresTaskStore,
    user_id: str = "test-user",
    goal: str = "Test task goal",
    num_steps: int = 2,
    organization_id: str = "test-org",
) -> Task:
    """Create and persist a task with N steps."""
    steps = [
        TaskStep(
            id=f"step-{i}",
            name=f"Step {i}",
            description=f"Do step {i}",
            agent_type="test_tool",
            status=StepStatus.PENDING,
        )
        for i in range(num_steps)
    ]
    task = Task(
        user_id=user_id,
        organization_id=organization_id,
        goal=goal,
        steps=steps,
    )
    await pg_store.create_task(task)
    return task


async def _create_inbox_conversation(
    db,
    pg_store: PostgresTaskStore,
    task: Task,
    user_id: str = "test-user",
) -> str:
    """Replicate the _create_inbox_conversation flow from TaskService.

    Returns the conversation_id as a string.
    """
    conversation_store = ConversationStore(db)

    trigger = ConversationTrigger(
        type=TriggerType.MANUAL,
        source="task",
        details={"task_id": task.id, "goal": task.goal},
        conversation_source="task",
    )
    conversation = await conversation_store.start_conversation(
        workflow_id=task.id,
        root_agent_id="task_orchestrator",
        trigger=trigger,
    )

    # Set inbox fields
    async with db.get_session() as session:
        await session.execute(
            sa_update(Conversation)
            .where(Conversation.id == conversation.id)
            .values(
                user_id=user_id,
                read_status=ReadStatus.UNREAD,
                priority=InboxPriority.NORMAL,
            )
        )
        await session.commit()

    # Link task → conversation
    await pg_store.update_task(task.id, {
        "conversation_id": conversation.id,
    })

    # Add the first "Started working on" message
    msg = MessageData(
        agent_id="task_orchestrator",
        message_type=MessageType.LLM_RESPONSE,
        direction=MessageDirection.OUTBOUND,
        content=MessageContent(
            role="assistant",
            text=f"Started working on: {task.goal}",
        ),
        metadata=MessageMetadata(),
    )
    await conversation_store.add_message(str(conversation.id), msg)

    return str(conversation.id)


async def _add_step_message(
    db,
    conversation_id: str,
    step_name: str,
    step_index: int,
    succeeded: bool = True,
) -> None:
    """Add a step completion/failure message to the conversation."""
    store = ConversationStore(db)
    status_word = "completed" if succeeded else "failed"
    msg = MessageData(
        agent_id="task_orchestrator",
        message_type=MessageType.LLM_RESPONSE,
        direction=MessageDirection.OUTBOUND,
        content=MessageContent(
            role="assistant",
            text=f"Step {step_index + 1} '{step_name}' {status_word}.",
        ),
        metadata=MessageMetadata(),
    )
    await store.add_message(conversation_id, msg)

    # Mark as unread again
    async with db.get_session() as session:
        await session.execute(
            sa_update(Conversation)
            .where(Conversation.id == uuid.UUID(conversation_id))
            .values(read_status=ReadStatus.UNREAD)
        )
        await session.commit()


async def _add_completion_message(
    db,
    conversation_id: str,
    goal: str,
    succeeded: bool = True,
    total_steps: int = 2,
) -> None:
    """Add a task completion/failure summary message."""
    store = ConversationStore(db)
    if succeeded:
        text = f"Completed: {goal}. {total_steps}/{total_steps} steps executed."
    else:
        text = f"Failed: {goal}. Some steps did not complete."

    msg = MessageData(
        agent_id="task_orchestrator",
        message_type=MessageType.LLM_RESPONSE,
        direction=MessageDirection.OUTBOUND,
        content=MessageContent(
            role="assistant",
            text=text,
            data={"summary_type": "outcome" if succeeded else "failure"},
        ),
        metadata=MessageMetadata(),
    )
    await store.add_message(conversation_id, msg)

    # Update conversation status + priority
    async with db.get_session() as session:
        await session.execute(
            sa_update(Conversation)
            .where(Conversation.id == uuid.UUID(conversation_id))
            .values(
                read_status=ReadStatus.UNREAD,
                priority=InboxPriority.ATTENTION if not succeeded else InboxPriority.NORMAL,
                status=ConversationStatus.COMPLETED if succeeded else ConversationStatus.FAILED,
            )
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
class TestTaskConversationBridge:
    """Integration tests for the task → inbox conversation bridge."""

    async def test_conversation_created_with_correct_user_and_status(
        self, integration_db
    ):
        """(1-2) Creating a task and starting execution creates a Conversation
        with read_status=UNREAD and the correct user_id."""
        pg_store = PostgresTaskStore(integration_db)
        task = await _create_task_with_steps(pg_store, user_id="alice")

        conv_id = await _create_inbox_conversation(
            integration_db, pg_store, task, user_id="alice"
        )

        # Verify conversation fields
        async with integration_db.get_session() as session:
            result = await session.execute(
                select(Conversation).where(
                    Conversation.id == uuid.UUID(conv_id)
                )
            )
            conv = result.scalar_one()
            assert conv.user_id == "alice"
            assert conv.read_status == ReadStatus.UNREAD
            assert conv.priority == InboxPriority.NORMAL

    async def test_task_has_conversation_id_set(self, integration_db):
        """(4) After inbox creation the Task record has conversation_id set."""
        pg_store = PostgresTaskStore(integration_db)
        task = await _create_task_with_steps(pg_store)

        conv_id = await _create_inbox_conversation(
            integration_db, pg_store, task
        )

        # Read back via raw model
        async with integration_db.get_session() as session:
            result = await session.execute(
                select(TaskModel).where(TaskModel.id == uuid.UUID(task.id))
            )
            model = result.scalar_one()
            assert model.conversation_id is not None
            assert str(model.conversation_id) == conv_id

    async def test_step_completion_creates_messages(self, integration_db):
        """(5) Step completion creates messages in the conversation."""
        pg_store = PostgresTaskStore(integration_db)
        task = await _create_task_with_steps(pg_store, num_steps=2)

        conv_id = await _create_inbox_conversation(
            integration_db, pg_store, task
        )

        # Simulate step completions
        await _add_step_message(integration_db, conv_id, "Step 0", 0)
        await _add_step_message(integration_db, conv_id, "Step 1", 1)

        # Verify messages: 1 start + 2 step completions = 3
        store = ConversationStore(integration_db)
        messages = await store.get_messages(conv_id)
        assert len(messages) == 3

        texts = [m.content_text for m in messages]
        assert any("Started working on" in t for t in texts)
        assert any("Step 1 'Step 0' completed" in t for t in texts)
        assert any("Step 2 'Step 1' completed" in t for t in texts)

    async def test_task_completion_creates_summary_message(
        self, integration_db
    ):
        """(6) Task completion creates a summary message."""
        pg_store = PostgresTaskStore(integration_db)
        task = await _create_task_with_steps(pg_store, goal="Research AI trends")

        conv_id = await _create_inbox_conversation(
            integration_db, pg_store, task
        )

        # Add step + completion messages
        await _add_step_message(integration_db, conv_id, "Step 0", 0)
        await _add_completion_message(
            integration_db, conv_id, task.goal, succeeded=True, total_steps=2
        )

        store = ConversationStore(integration_db)
        messages = await store.get_messages(conv_id)
        # 1 start + 1 step + 1 completion = 3
        assert len(messages) == 3

        completion_msg = messages[-1]
        assert "Completed: Research AI trends" in completion_msg.content_text
        assert completion_msg.content_data.get("summary_type") == "outcome"

    async def test_failure_sets_attention_priority(self, integration_db):
        """Task failure sets priority=ATTENTION on the conversation."""
        pg_store = PostgresTaskStore(integration_db)
        task = await _create_task_with_steps(pg_store, goal="Failing task")

        conv_id = await _create_inbox_conversation(
            integration_db, pg_store, task
        )

        await _add_completion_message(
            integration_db, conv_id, task.goal, succeeded=False
        )

        async with integration_db.get_session() as session:
            result = await session.execute(
                select(Conversation).where(
                    Conversation.id == uuid.UUID(conv_id)
                )
            )
            conv = result.scalar_one()
            assert conv.priority == InboxPriority.ATTENTION
            assert conv.status == ConversationStatus.FAILED

    async def test_get_inbox_returns_conversation(self, integration_db):
        """(7) GET /api/inbox (via ConversationStore) returns the item with
        correct preview text."""
        pg_store = PostgresTaskStore(integration_db)
        task = await _create_task_with_steps(
            pg_store, user_id="bob", goal="Analyze data"
        )

        conv_id = await _create_inbox_conversation(
            integration_db, pg_store, task, user_id="bob"
        )

        store = ConversationStore(integration_db)
        items = await store.get_inbox_conversations(user_id="bob")

        assert len(items) == 1
        item = items[0]
        assert item["conversation_id"] == conv_id
        assert item["read_status"] == "unread"
        assert item["priority"] == "normal"
        assert item["last_message_text"] is not None
        assert "Started working on: Analyze data" in item["last_message_text"]
        assert item["task_goal"] == "Analyze data"
        assert item["task_id"] == task.id

    async def test_get_unread_count_returns_correct_value(
        self, integration_db
    ):
        """(8) get_unread_count returns 1 for a single unread conversation."""
        pg_store = PostgresTaskStore(integration_db)
        task = await _create_task_with_steps(pg_store, user_id="charlie")

        await _create_inbox_conversation(
            integration_db, pg_store, task, user_id="charlie"
        )

        store = ConversationStore(integration_db)
        count = await store.get_unread_count("charlie")
        assert count == 1

    async def test_unread_count_zero_for_read_conversations(
        self, integration_db
    ):
        """After marking as READ, unread count should be 0."""
        pg_store = PostgresTaskStore(integration_db)
        task = await _create_task_with_steps(pg_store, user_id="dave")

        conv_id = await _create_inbox_conversation(
            integration_db, pg_store, task, user_id="dave"
        )

        store = ConversationStore(integration_db)

        # Mark as read
        updated = await store.update_read_status(conv_id, ReadStatus.READ)
        assert updated is True

        count = await store.get_unread_count("dave")
        assert count == 0

    async def test_inbox_thread_returns_messages_and_task(
        self, integration_db
    ):
        """get_inbox_thread returns all messages + linked task data."""
        pg_store = PostgresTaskStore(integration_db)
        task = await _create_task_with_steps(
            pg_store, user_id="eve", goal="Build report"
        )

        conv_id = await _create_inbox_conversation(
            integration_db, pg_store, task, user_id="eve"
        )

        await _add_step_message(integration_db, conv_id, "Step 0", 0)
        await _add_completion_message(
            integration_db, conv_id, task.goal, succeeded=True
        )

        store = ConversationStore(integration_db)
        thread = await store.get_inbox_thread(conv_id)

        assert thread is not None
        assert thread["conversation_id"] == conv_id
        assert thread["read_status"] == "unread"
        assert thread["priority"] == "normal"

        # Task data
        assert thread["task"] is not None
        assert thread["task"]["id"] == task.id
        assert thread["task"]["goal"] == "Build report"

        # Messages: 1 start + 1 step + 1 completion = 3
        assert len(thread["messages"]) == 3
        assert thread["messages"][0]["role"] == "assistant"

    async def test_multiple_users_isolated_inboxes(self, integration_db):
        """Each user only sees their own inbox items."""
        pg_store = PostgresTaskStore(integration_db)

        # Create tasks for two users
        task_a = await _create_task_with_steps(
            pg_store, user_id="user-a", goal="Task for A"
        )
        task_b = await _create_task_with_steps(
            pg_store, user_id="user-b", goal="Task for B"
        )

        await _create_inbox_conversation(
            integration_db, pg_store, task_a, user_id="user-a"
        )
        await _create_inbox_conversation(
            integration_db, pg_store, task_b, user_id="user-b"
        )

        store = ConversationStore(integration_db)

        items_a = await store.get_inbox_conversations(user_id="user-a")
        items_b = await store.get_inbox_conversations(user_id="user-b")

        assert len(items_a) == 1
        assert items_a[0]["task_goal"] == "Task for A"

        assert len(items_b) == 1
        assert items_b[0]["task_goal"] == "Task for B"

        # Cross-check: counts
        assert await store.get_unread_count("user-a") == 1
        assert await store.get_unread_count("user-b") == 1

    async def test_bulk_update_read_status(self, integration_db):
        """bulk_update_read_status marks multiple conversations as read."""
        pg_store = PostgresTaskStore(integration_db)
        store = ConversationStore(integration_db)

        conv_ids = []
        for i in range(3):
            task = await _create_task_with_steps(
                pg_store, user_id="frank", goal=f"Task {i}"
            )
            cid = await _create_inbox_conversation(
                integration_db, pg_store, task, user_id="frank"
            )
            conv_ids.append(cid)

        # All 3 should be unread
        assert await store.get_unread_count("frank") == 3

        # Bulk mark first 2 as read
        updated = await store.bulk_update_read_status(
            conv_ids[:2], ReadStatus.READ
        )
        assert updated == 2

        assert await store.get_unread_count("frank") == 1

    async def test_inbox_filter_by_read_status(self, integration_db):
        """Filtering by read_status returns only matching conversations."""
        pg_store = PostgresTaskStore(integration_db)
        store = ConversationStore(integration_db)

        # Create 2 conversations
        task1 = await _create_task_with_steps(
            pg_store, user_id="grace", goal="Task 1"
        )
        task2 = await _create_task_with_steps(
            pg_store, user_id="grace", goal="Task 2"
        )

        cid1 = await _create_inbox_conversation(
            integration_db, pg_store, task1, user_id="grace"
        )
        await _create_inbox_conversation(
            integration_db, pg_store, task2, user_id="grace"
        )

        # Mark first as read
        await store.update_read_status(cid1, ReadStatus.READ)

        # Query unread only
        unread = await store.get_inbox_conversations(
            user_id="grace", read_status=ReadStatus.UNREAD
        )
        assert len(unread) == 1
        assert unread[0]["task_goal"] == "Task 2"

        # Query read only
        read = await store.get_inbox_conversations(
            user_id="grace", read_status=ReadStatus.READ
        )
        assert len(read) == 1
        assert read[0]["task_goal"] == "Task 1"

    async def test_conversation_not_visible_without_read_status(
        self, integration_db
    ):
        """Regular conversations (no read_status) do NOT appear in inbox."""
        pg_store = PostgresTaskStore(integration_db)
        store = ConversationStore(integration_db)

        # Create a regular (non-inbox) conversation
        trigger = ConversationTrigger(
            type=TriggerType.WEBHOOK,
            source="workflow",
            details={},
            conversation_source="workflow",
        )
        await store.start_conversation(
            workflow_id=str(uuid.uuid4()),
            root_agent_id="some_agent",
            trigger=trigger,
        )

        # Also create an inbox conversation
        task = await _create_task_with_steps(pg_store, user_id="heidi")
        await _create_inbox_conversation(
            integration_db, pg_store, task, user_id="heidi"
        )

        items = await store.get_inbox_conversations(user_id="heidi")
        assert len(items) == 1  # Only the inbox conversation
