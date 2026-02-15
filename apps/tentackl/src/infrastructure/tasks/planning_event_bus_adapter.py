"""Infrastructure adapter for planning events."""

from __future__ import annotations

from typing import List

from src.domain.tasks.ports import PlanningEventBusPort
from src.infrastructure.tasks.event_publisher import (
    TaskEventPublisher,
    get_task_event_publisher,
)


class PlanningEventBusAdapter(PlanningEventBusPort):
    """Adapter that forwards planning events to TaskEventPublisher."""

    def __init__(self, publisher: TaskEventPublisher | None = None) -> None:
        self._publisher = publisher or get_task_event_publisher()

    async def planning_started(self, task_id: str, goal: str) -> str:
        return await self._publisher.planning_started(task_id, goal)

    async def planning_intent_detected(self, task_id: str, intent: str, detail: str) -> str:
        return await self._publisher.planning_intent_detected(task_id, intent, detail)

    async def planning_fast_path(self, task_id: str, message: str) -> str:
        return await self._publisher.planning_fast_path(task_id, message)

    async def planning_llm_started(self, task_id: str) -> str:
        return await self._publisher.planning_llm_started(task_id)

    async def planning_llm_retry(
        self,
        task_id: str,
        attempt: int,
        max_retries: int,
        reason: str,
    ) -> str:
        return await self._publisher.planning_llm_retry(task_id, attempt, max_retries, reason)

    async def planning_steps_generated(self, task_id: str, step_count: int, step_names: List[str]) -> str:
        return await self._publisher.planning_steps_generated(task_id, step_count, step_names)

    async def planning_risk_detection(self, task_id: str, checkpoints_added: int) -> str:
        return await self._publisher.planning_risk_detection(task_id, checkpoints_added)

    async def planning_completed(self, task_id: str, step_count: int, source: str) -> str:
        return await self._publisher.planning_completed(task_id, step_count, source)

    async def planning_failed(self, task_id: str, error: str) -> str:
        return await self._publisher.planning_failed(task_id, error)
