"""Infrastructure adapter for task planning persistence."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.domain.tasks.ports import TaskPlanningStorePort, TaskPersistencePort, TaskQueryPort
from src.domain.tasks.models import Task
from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskStore
from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore


class TaskPlanningStoreAdapter(TaskPlanningStorePort):
    """Adapter that updates both PG (source of truth) and Redis cache."""

    def __init__(
        self,
        pg_store: Optional[PostgresTaskStore],
        redis_store: RedisTaskStore,
        query_port: Optional[TaskQueryPort] = None,
        persistence_port: Optional[TaskPersistencePort] = None,
    ) -> None:
        self._pg_store = pg_store
        self._redis_store = redis_store
        self._query_port = query_port
        self._persistence_port = persistence_port

    async def update_task(self, task_id: str, updates: Dict[str, Any]) -> None:
        if self._persistence_port:
            await self._persistence_port.update_task(task_id, updates)
            return
        if self._pg_store:
            await self._pg_store.update_task(task_id, updates)
        await self._redis_store.update_task(task_id, updates)

    async def update_step(self, task_id: str, step_id: str, updates: Dict[str, Any]) -> None:
        if self._pg_store:
            await self._pg_store.update_step(task_id, step_id, updates)
        await self._redis_store.update_step(task_id, step_id, updates)

    async def get_task(self, task_id: str) -> Optional[Task]:
        if self._query_port:
            return await self._query_port.get_task(task_id)
        if self._pg_store:
            task = await self._pg_store.get_task(task_id)
            if task:
                return task
        return await self._redis_store.get_task(task_id)
