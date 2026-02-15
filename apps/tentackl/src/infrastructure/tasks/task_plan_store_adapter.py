"""Infrastructure adapter for task plan storage."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.domain.tasks.ports import TaskPlanStorePort
from src.domain.tasks.models import Task
from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore


class TaskPlanStoreAdapter(TaskPlanStorePort):
    """Adapter exposing RedisTaskStore via the plan store port."""

    def __init__(self, redis_store: Optional[RedisTaskStore] = None) -> None:
        self._store = redis_store or RedisTaskStore()

    async def _ensure_connected(self) -> None:
        is_connected = getattr(self._store, "_is_connected", False)
        if not is_connected:
            await self._store._connect()

    async def connect(self) -> None:
        await self._ensure_connected()

    async def disconnect(self) -> None:
        await self._store._disconnect()

    async def create_task(self, task: Task) -> str:
        await self._ensure_connected()
        return await self._store.create_task(task)

    async def get_task(self, task_id: str) -> Optional[Task]:
        await self._ensure_connected()
        return await self._store.get_task(task_id)

    async def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        await self._ensure_connected()
        return await self._store.update_task(task_id, updates)

    async def update_step(self, plan_id: str, step_id: str, updates: Dict[str, Any]) -> bool:
        await self._ensure_connected()
        return await self._store.update_step(plan_id, step_id, updates)

    async def add_finding(self, plan_id: str, finding: Any) -> bool:
        await self._ensure_connected()
        return await self._store.add_finding(plan_id, finding)
