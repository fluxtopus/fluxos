"""Infrastructure adapter for task-linked inbox conversations."""

from __future__ import annotations

from typing import Optional

import structlog

from src.domain.tasks.ports import TaskConversationPort, TaskExecutionEventBusPort
from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskStore
from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore

logger = structlog.get_logger(__name__)


class TaskConversationAdapter(TaskConversationPort):
    """Adapter for inbox conversation creation and checkpoint messages."""

    def __init__(
        self,
        pg_store: PostgresTaskStore,
        redis_store: Optional[RedisTaskStore] = None,
        event_bus: Optional[TaskExecutionEventBusPort] = None,
    ) -> None:
        self._pg_store = pg_store
        self._redis_store = redis_store
        self._event_bus = event_bus

    async def ensure_conversation(self, task_id: str, goal: str, user_id: str) -> None:
        """Create an inbox conversation linked to a task when execution starts."""
        try:
            if not self._pg_store or not self._pg_store.db:
                logger.warning(
                    "Cannot create inbox conversation: pg_store not available",
                    task_id=task_id,
                )
                return

            # Skip conversations for automation-cloned tasks to avoid inbox flood.
            try:
                plan = await self._pg_store.get_task(task_id)
            except Exception:
                plan = None
            if plan and plan.metadata and plan.metadata.get("automation_id"):
                logger.info(
                    "Skipping conversation for automation-cloned task",
                    task_id=task_id,
                    automation_id=plan.metadata.get("automation_id"),
                )
                return

            from src.database.task_models import Task as TaskModel
            from sqlalchemy import select
            import uuid as uuid_mod

            async with self._pg_store.db.get_session() as session:
                result = await session.execute(
                    select(TaskModel.conversation_id).where(
                        TaskModel.id == uuid_mod.UUID(task_id)
                    )
                )
                row = result.first()
                if row and row[0] is not None:
                    existing_conv_id = str(row[0])
                    await self._add_task_status_message(existing_conv_id, task_id, goal)
                    logger.info(
                        "Added status message to existing conversation for task",
                        task_id=task_id,
                        conversation_id=existing_conv_id,
                    )
                    return

            from src.database.conversation_store import (
                ConversationStore,
                ConversationTrigger,
            )
            from src.database.models import (
                TriggerType,
                ReadStatus,
                InboxPriority,
            )

            conversation_store = ConversationStore(self._pg_store.db)
            trigger = ConversationTrigger(
                type=TriggerType.MANUAL,
                source="task",
                details={"task_id": task_id, "goal": goal},
                conversation_source="task",
            )
            conversation = await conversation_store.start_conversation(
                workflow_id=task_id,
                root_agent_id="task_orchestrator",
                trigger=trigger,
            )

            from sqlalchemy import update as sa_update
            from src.database.models import Conversation

            async with self._pg_store.db.get_session() as session:
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

            await self._pg_store.update_task(task_id, {
                "conversation_id": conversation.id,
            })
            if self._redis_store:
                try:
                    await self._redis_store.update_task(task_id, {
                        "conversation_id": str(conversation.id),
                    })
                except Exception:
                    pass

            await self._add_task_status_message(str(conversation.id), task_id, goal)

            logger.info(
                "Created inbox conversation for task",
                task_id=task_id,
                conversation_id=str(conversation.id),
                user_id=user_id,
            )
        except Exception as e:
            logger.error(
                "Failed to create inbox conversation",
                task_id=task_id,
                error=str(e),
            )

    async def add_checkpoint_resolution_message(
        self,
        task_id: str,
        approved: bool,
        reason: str = "",
    ) -> None:
        """Add an inbox message when a checkpoint is resolved."""
        try:
            if not self._pg_store or not self._pg_store.db:
                return

            from sqlalchemy import select, update as sa_update
            from src.database.task_models import Task as TaskModel
            from src.database.models import (
                Conversation,
                ReadStatus,
                InboxPriority,
                MessageType,
                MessageDirection,
            )
            from src.database.conversation_store import (
                ConversationStore,
                MessageContent,
                MessageData,
                MessageMetadata,
            )
            import uuid as uuid_mod

            db = self._pg_store.db

            async with db.get_session() as session:
                result = await session.execute(
                    select(TaskModel.conversation_id, TaskModel.user_id).where(
                        TaskModel.id == uuid_mod.UUID(task_id)
                    )
                )
                row = result.one_or_none()

            if not row or not row.conversation_id:
                logger.debug(
                    "No inbox conversation for task, skipping checkpoint resolution message",
                    task_id=task_id,
                )
                return

            conversation_id = str(row.conversation_id)
            user_id = row.user_id

            conversation_store = ConversationStore(db)

            if approved:
                content_text = "Checkpoint approved. Resuming execution."
                priority = InboxPriority.NORMAL
            else:
                content_text = (
                    f"Checkpoint rejected: {reason}. Task stopped."
                    if reason
                    else "Checkpoint rejected. Task stopped."
                )
                priority = InboxPriority.ATTENTION

            content = MessageContent(
                role="assistant",
                text=content_text,
                data={"resolution": "approved" if approved else "rejected", "reason": reason},
            )
            metadata = MessageMetadata()
            message_data = MessageData(
                agent_id="task_orchestrator",
                message_type=MessageType.LLM_RESPONSE,
                direction=MessageDirection.OUTBOUND,
                content=content,
                metadata=metadata,
            )
            await conversation_store.add_message(
                conversation_id=conversation_id,
                message_data=message_data,
            )

            async with db.get_session() as session:
                await session.execute(
                    sa_update(Conversation)
                    .where(Conversation.id == uuid_mod.UUID(conversation_id))
                    .values(
                        read_status=ReadStatus.UNREAD,
                        priority=priority,
                    )
                )
                await session.commit()

            if user_id and self._event_bus:
                try:
                    await self._event_bus.inbox_message_created(
                        user_id=str(user_id),
                        conversation_id=conversation_id,
                        message_preview=content_text[:200],
                        priority=priority.value,
                    )
                except Exception:
                    pass

            logger.debug(
                "Added inbox checkpoint resolution message",
                task_id=task_id,
                conversation_id=conversation_id,
                approved=approved,
            )
        except Exception as e:
            logger.warning(
                "Failed to add inbox checkpoint resolution message",
                task_id=task_id,
                error=str(e),
            )

    async def link_task_to_conversation(self, task_id: str, conversation_id: str) -> None:
        """Link an existing conversation to a task."""
        if not self._pg_store or not self._pg_store.db:
            raise RuntimeError("PostgreSQL store required to link conversations")

        from src.database.task_models import Task as TaskModel
        from sqlalchemy import update as sa_update
        import uuid as uuid_mod

        async with self._pg_store.db.get_session() as session:
            await session.execute(
                sa_update(TaskModel)
                .where(TaskModel.id == uuid_mod.UUID(task_id))
                .values(conversation_id=uuid_mod.UUID(conversation_id))
            )
            await session.commit()

        if self._redis_store:
            try:
                await self._redis_store.update_task(task_id, {"conversation_id": conversation_id})
            except Exception:
                pass

    async def _add_task_status_message(
        self,
        conversation_id: str,
        task_id: str,
        goal: str,
    ) -> None:
        from src.database.conversation_store import (
            ConversationStore,
            MessageContent,
            MessageData,
            MessageMetadata,
        )
        from src.database.models import (
            MessageType,
            MessageDirection,
        )

        conversation_store = ConversationStore(self._pg_store.db)
        content = MessageContent(
            role="assistant",
            text=f"Started working on: {goal}",
        )
        metadata = MessageMetadata()
        message_data = MessageData(
            agent_id="task_orchestrator",
            message_type=MessageType.LLM_RESPONSE,
            direction=MessageDirection.OUTBOUND,
            content=content,
            metadata=metadata,
        )
        await conversation_store.add_message(
            conversation_id=conversation_id,
            message_data=message_data,
        )
