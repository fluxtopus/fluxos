"""Application use case for task lifecycle transitions."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.tasks.ports import (
    TaskQueryPort,
    TaskStatusTransitionPort,
    PlanCancellationPort,
)
from src.domain.tasks.models import Task, TaskStatus


@dataclass
class CancelTaskDecision:
    """Result payload for cancel flow side effects."""

    task: Task
    cancelled_while_planning: bool = False


@dataclass
class TaskLifecycleUseCase:
    """Handles pause/cancel lifecycle transitions with ownership checks."""

    query_port: TaskQueryPort
    status_transition: TaskStatusTransitionPort
    cancellation_port: PlanCancellationPort

    async def pause_plan(self, plan_id: str, user_id: str) -> Task:
        plan = await self.query_port.get_task(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")
        if plan.user_id != user_id:
            raise PermissionError(f"User {user_id} does not own plan {plan_id}")
        return await self.status_transition.transition(plan_id, TaskStatus.PAUSED)

    async def cancel_plan(self, plan_id: str, user_id: str) -> CancelTaskDecision:
        plan = await self.query_port.get_task(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")
        if plan.user_id != user_id:
            raise PermissionError(f"User {user_id} does not own plan {plan_id}")

        cancelled_while_planning = plan.status == TaskStatus.PLANNING
        if cancelled_while_planning:
            await self.cancellation_port.cancel(plan_id)

        task = await self.status_transition.transition(plan_id, TaskStatus.CANCELLED)
        return CancelTaskDecision(
            task=task,
            cancelled_while_planning=cancelled_while_planning,
        )
