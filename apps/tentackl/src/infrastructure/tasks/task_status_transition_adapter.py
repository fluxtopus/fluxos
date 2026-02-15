"""Infrastructure adapter for task status transitions."""

from __future__ import annotations

from typing import Dict, Optional, Any

from src.domain.tasks.ports import TaskStatusTransitionPort
from src.domain.tasks.models import Task, TaskStatus
from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskStore
from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore
from src.infrastructure.tasks.runtime_components import TaskStateMachine


class TaskStatusTransitionAdapter(TaskStatusTransitionPort):
    """Adapter that uses TaskStateMachine with a fallback to direct updates."""

    def __init__(
        self,
        state_machine: Optional[TaskStateMachine],
        pg_store: Optional[PostgresTaskStore],
        redis_store: RedisTaskStore,
    ) -> None:
        self._state_machine = state_machine
        self._pg_store = pg_store
        self._redis_store = redis_store

    async def transition(
        self,
        task_id: str,
        new_status: TaskStatus,
        additional_updates: Optional[Dict[str, Any]] = None,
    ) -> Task:
        if self._state_machine:
            return await self._state_machine.transition(task_id, new_status, additional_updates)

        updates: Dict[str, Any] = {"status": new_status.value}
        if additional_updates:
            updates.update(additional_updates)

        if self._pg_store:
            await self._pg_store.update_task(task_id, updates)
        await self._redis_store.update_task(task_id, updates)

        if self._pg_store:
            task = await self._pg_store.get_task(task_id)
            if task:
                return task
        task = await self._redis_store.get_task(task_id)
        if task:
            return task
        raise RuntimeError(f"Task not found after status update: {task_id}")
