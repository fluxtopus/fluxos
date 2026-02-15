"""Infrastructure adapter for step-level inbox messaging."""

from __future__ import annotations

from typing import Any, Dict, Optional
import structlog

from src.domain.tasks.ports import StepInboxMessagingPort

logger = structlog.get_logger(__name__)


class StepInboxMessagingAdapter(StepInboxMessagingPort):
    """Sends inbox messages for step lifecycle events.

    Takes a database connection and event publisher in the constructor.
    All methods are best-effort — they never raise on failure, so inbox
    issues cannot block task execution.
    """

    def __init__(self, db: Any, publisher: Any, summary_service: Any = None) -> None:
        self._db = db
        self._publisher = publisher
        self._summary_service = summary_service

    async def add_step_message(
        self,
        task_id: str,
        step_name: str,
        event_type: str,
        text: str,
        data: Dict[str, Any],
    ) -> None:
        try:
            from sqlalchemy import select
            from src.database.task_models import Task as TaskModel
            from src.database.models import (
                ReadStatus,
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

            async with self._db.get_session() as session:
                result = await session.execute(
                    select(TaskModel.conversation_id, TaskModel.user_id).where(
                        TaskModel.id == uuid_mod.UUID(task_id)
                    )
                )
                row = result.one_or_none()

            if not row or not row.conversation_id:
                logger.debug(
                    "No inbox conversation for task, skipping step message",
                    task_id=task_id,
                )
                return

            conversation_id = str(row.conversation_id)
            user_id = row.user_id

            conversation_store = ConversationStore(self._db)

            content = MessageContent(role="assistant", text=text, data=data)
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

            await conversation_store.update_read_status(
                conversation_id=conversation_id,
                read_status=ReadStatus.UNREAD,
            )

            if user_id and self._publisher:
                try:
                    await self._publisher.inbox_message_created(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        message_preview=text[:200],
                        priority="normal",
                    )
                except Exception:
                    pass

            logger.debug(
                "Added inbox step message",
                task_id=task_id,
                conversation_id=conversation_id,
                event_type=event_type,
            )
        except Exception as e:
            logger.warning(
                "Failed to add inbox step message",
                task_id=task_id,
                error=str(e),
            )

    async def add_checkpoint_message(
        self,
        task_id: str,
        step_id: str,
        step_name: str,
        description: str,
    ) -> None:
        try:
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

            async with self._db.get_session() as session:
                result = await session.execute(
                    select(TaskModel.conversation_id, TaskModel.user_id).where(
                        TaskModel.id == uuid_mod.UUID(task_id)
                    )
                )
                row = result.one_or_none()

            if not row or not row.conversation_id:
                logger.debug(
                    "No inbox conversation for task, skipping checkpoint message",
                    task_id=task_id,
                )
                return

            conversation_id = str(row.conversation_id)
            user_id = row.user_id

            conversation_store = ConversationStore(self._db)

            checkpoint_desc = description or step_name
            content_text = f"{checkpoint_desc}. Awaiting your approval."
            content_data = {
                "checkpoint_type": "approval",
                "task_id": task_id,
                "step_id": step_id,
            }

            content = MessageContent(
                role="assistant",
                text=content_text,
                data=content_data,
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

            async with self._db.get_session() as session:
                await session.execute(
                    sa_update(Conversation)
                    .where(Conversation.id == uuid_mod.UUID(conversation_id))
                    .values(
                        read_status=ReadStatus.UNREAD,
                        priority=InboxPriority.ATTENTION,
                    )
                )
                await session.commit()

            if user_id and self._publisher:
                try:
                    await self._publisher.inbox_message_created(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        message_preview=content_text[:200],
                        priority="attention",
                    )
                except Exception:
                    pass

            logger.debug(
                "Added inbox checkpoint message",
                task_id=task_id,
                conversation_id=conversation_id,
                step_id=step_id,
            )
        except Exception as e:
            logger.warning(
                "Failed to add inbox checkpoint message",
                task_id=task_id,
                error=str(e),
            )

    async def add_completion_message(
        self,
        task_id: str,
        status: str,
        steps_completed: int,
        total_steps: int,
        error: Optional[str] = None,
    ) -> None:
        try:
            from sqlalchemy import select, update as sa_update
            from src.database.task_models import Task as TaskModel
            from src.database.models import (
                Conversation,
                ConversationStatus,
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
            from src.infrastructure.tasks.task_summary_adapter import TaskSummaryAdapter
            import uuid as uuid_mod

            async with self._db.get_session() as session:
                result = await session.execute(
                    select(
                        TaskModel.conversation_id,
                        TaskModel.user_id,
                        TaskModel.goal,
                        TaskModel.accumulated_findings,
                    ).where(TaskModel.id == uuid_mod.UUID(task_id))
                )
                row = result.one_or_none()

            if not row or not row.conversation_id:
                logger.debug(
                    "No inbox conversation for task, skipping completion message",
                    task_id=task_id,
                )
                return

            conversation_id = str(row.conversation_id)
            user_id = row.user_id
            goal = row.goal or "Unknown task"
            findings = row.accumulated_findings or []

            key_outputs: Dict[str, Any] = {}
            try:
                from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskStore
                pg_store = PostgresTaskStore(self._db)
                task_data = await pg_store.get_task(task_id)
                if task_data and task_data.steps:
                    for step in task_data.steps:
                        if step.status and step.status.value == "done" and step.outputs:
                            key_outputs[step.name or step.id] = step.outputs
            except Exception:
                pass

            summary_adapter = TaskSummaryAdapter(summary_service=self._summary_service)
            summary_text = await summary_adapter.generate_summary_safe(
                goal=goal,
                status=status,
                steps_completed=steps_completed,
                total_steps=total_steps,
                key_outputs=key_outputs,
                findings=findings,
                error=error,
            )

            conversation_store = ConversationStore(self._db)

            summary_type = "outcome" if status == "completed" else "failure"
            completion_data = {
                "summary_type": summary_type,
                "steps_completed": steps_completed,
                "total_steps": total_steps,
            }
            if key_outputs:
                completion_data["step_outputs"] = key_outputs
            if findings:
                completion_data["findings"] = findings
            content = MessageContent(
                role="assistant",
                text=summary_text,
                data=completion_data,
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

            priority = InboxPriority.ATTENTION if status == "failed" else InboxPriority.NORMAL
            conv_status = ConversationStatus.COMPLETED if status == "completed" else ConversationStatus.FAILED

            async with self._db.get_session() as session:
                await session.execute(
                    sa_update(Conversation)
                    .where(Conversation.id == uuid_mod.UUID(conversation_id))
                    .values(
                        read_status=ReadStatus.UNREAD,
                        priority=priority,
                        status=conv_status,
                    )
                )
                await session.commit()

            if user_id and self._publisher:
                try:
                    await self._publisher.inbox_message_created(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        message_preview=summary_text[:200],
                        priority=priority.value,
                    )
                except Exception:
                    pass

            logger.info(
                "Added inbox completion message",
                task_id=task_id,
                conversation_id=conversation_id,
                status=status,
                summary_type=summary_type,
            )
        except Exception as e:
            logger.warning(
                "Failed to add inbox completion message",
                task_id=task_id,
                error=str(e),
            )
