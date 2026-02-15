"""Infrastructure adapter for task persistence across PG and Redis."""

from __future__ import annotations

from typing import Any, Dict, Optional
import uuid

from src.domain.tasks.ports import TaskPersistencePort
from src.domain.tasks.models import Task
from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskStore
from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore


class TaskPersistenceAdapter(TaskPersistencePort):
    """Adapter that applies task mutations to PG (primary) and Redis cache."""

    def __init__(
        self,
        pg_store: Optional[PostgresTaskStore],
        redis_store: RedisTaskStore,
    ) -> None:
        self._pg_store = pg_store
        self._redis_store = redis_store

    async def create_task(self, task: Task) -> None:
        if self._pg_store:
            await self._pg_store.create_task(task)
        await self._redis_store.create_task(task)

    async def get_task(self, task_id: str) -> Optional[Task]:
        if self._pg_store:
            task = await self._pg_store.get_task(task_id)
            if task:
                return task
        return await self._redis_store.get_task(task_id)

    async def update_task(self, task_id: str, updates: Dict[str, Any]) -> None:
        pg_updates = dict(updates)
        parent_task_id = pg_updates.get("parent_task_id")
        if parent_task_id and isinstance(parent_task_id, str):
            pg_updates["parent_task_id"] = uuid.UUID(parent_task_id)

        if self._pg_store:
            await self._pg_store.update_task(task_id, pg_updates)
        await self._redis_store.update_task(task_id, updates)

    async def update_task_metadata(self, task_id: str, metadata: Dict[str, Any]) -> None:
        await self.update_task(task_id, {"metadata": metadata})

    async def set_parent_task(self, task_id: str, parent_task_id: str) -> None:
        await self.update_task(task_id, {"parent_task_id": parent_task_id})
