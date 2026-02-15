"""Infrastructure adapter for task execution events."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.domain.tasks.ports import TaskExecutionEventBusPort
from src.infrastructure.tasks.event_publisher import (
    TaskEventPublisher,
    get_task_event_publisher,
)


class TaskExecutionEventBusAdapter(TaskExecutionEventBusPort):
    """Adapter exposing TaskEventPublisher through a domain port."""

    def __init__(self, publisher: Optional[TaskEventPublisher] = None) -> None:
        self._publisher = publisher or get_task_event_publisher()

    async def task_started(
        self,
        task_id: str,
        goal: str,
        step_count: int,
        user_id: str,
    ) -> str:
        return await self._publisher.task_started(
            task_id=task_id,
            goal=goal,
            step_count=step_count,
            user_id=user_id,
        )

    async def checkpoint_created(
        self,
        task_id: str,
        step_id: str,
        checkpoint_name: str,
        preview: Dict[str, Any],
    ) -> str:
        return await self._publisher.checkpoint_created(
            task_id=task_id,
            step_id=step_id,
            checkpoint_name=checkpoint_name,
            preview=preview,
        )

    async def checkpoint_auto_approved(
        self,
        task_id: str,
        step_id: str,
        checkpoint_name: str,
    ) -> str:
        return await self._publisher.checkpoint_auto_approved(
            task_id=task_id,
            step_id=step_id,
            checkpoint_name=checkpoint_name,
        )

    async def inbox_message_created(
        self,
        user_id: str,
        conversation_id: str,
        message_preview: str,
        priority: str,
    ) -> str:
        return await self._publisher.inbox_message_created(
            user_id=user_id,
            conversation_id=conversation_id,
            message_preview=message_preview,
            priority=priority,
        )
