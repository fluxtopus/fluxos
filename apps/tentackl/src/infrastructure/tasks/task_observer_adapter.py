"""Infrastructure adapter for task observer operations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.domain.tasks.ports import TaskObserverPort, TaskPlanStorePort
from src.infrastructure.tasks.task_observer import TaskObserverAgent
from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore
from src.infrastructure.tasks.task_plan_store_adapter import TaskPlanStoreAdapter


class TaskObserverAdapter(TaskObserverPort):
    """Adapter exposing TaskObserverAgent through the domain port."""

    def __init__(
        self,
        plan_store: Optional[TaskPlanStorePort] = None,
        redis_store: Optional[RedisTaskStore] = None,
        llm_client: Optional[Any] = None,
        agent: Optional[TaskObserverAgent] = None,
    ) -> None:
        if plan_store is None:
            plan_store = TaskPlanStoreAdapter(redis_store)
        self._agent = agent or TaskObserverAgent(
            plan_store=plan_store,
            llm_client=llm_client,
        )

    async def initialize(self) -> None:
        await self._agent.initialize()

    async def cleanup(self) -> None:
        await self._agent.cleanup()

    async def observe(
        self,
        plan_id: str,
        execution_state: Optional[Dict[str, Any]] = None,
        recent_events: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        return await self._agent.observe(
            plan_id=plan_id,
            execution_state=execution_state,
            recent_events=recent_events,
        )

    async def analyze_failure(self, plan: Any, failed_step: Any) -> Any:
        return await self._agent.analyze_failure(plan, failed_step)

    async def analyze_blocked_dependencies(
        self,
        plan: Any,
        blocked_steps: List[Any],
        failed_steps: List[Any],
    ) -> Any:
        return await self._agent.analyze_blocked_dependencies(
            plan, blocked_steps, failed_steps
        )
