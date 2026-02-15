"""Infrastructure adapter for task query/read patterns."""

from __future__ import annotations

from typing import List, Optional

from src.domain.tasks.ports import TaskQueryPort
from src.domain.tasks.models import Task, TaskStatus
from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskStore
from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore


class TaskQueryAdapter(TaskQueryPort):
    """Adapter that encapsulates PG-primary and Redis-hot-path reads."""

    def __init__(
        self,
        pg_store: Optional[PostgresTaskStore],
        redis_store: RedisTaskStore,
    ) -> None:
        self._pg_store = pg_store
        self._redis_store = redis_store

    async def get_task(self, task_id: str) -> Optional[Task]:
        if self._pg_store:
            task = await self._pg_store.get_task(task_id)
            if task:
                return task
        return await self._redis_store.get_task(task_id)

    async def get_task_for_execution(self, task_id: str) -> Optional[Task]:
        task = await self._redis_store.get_task(task_id)
        if task:
            return task
        if self._pg_store:
            return await self._pg_store.get_task(task_id)
        return None

    async def get_tasks_by_user(
        self,
        user_id: str,
        status: Optional[TaskStatus] = None,
        limit: int = 50,
    ) -> List[Task]:
        if self._pg_store:
            tasks = await self._pg_store.get_tasks_by_user(
                user_id=user_id,
                status=status,
                limit=limit,
            )
            if tasks:
                return tasks
        return await self._redis_store.get_tasks_by_user(
            user_id=user_id,
            status=status,
            limit=limit,
        )

    async def get_stuck_planning_tasks(
        self,
        timeout_minutes: int = 5,
    ) -> List[Task]:
        if not self._pg_store:
            return []
        return await self._pg_store.get_stuck_planning_tasks(
            timeout_minutes=timeout_minutes
        )
