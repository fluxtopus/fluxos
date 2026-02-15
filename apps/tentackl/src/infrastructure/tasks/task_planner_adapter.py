"""Infrastructure adapter for task planning operations."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.domain.tasks.ports import TaskPlannerPort
from src.infrastructure.tasks.task_planner_agent import TaskPlannerAgent


class TaskPlannerAdapter(TaskPlannerPort):
    """Adapter exposing TaskPlannerAgent through the domain port."""

    def __init__(self, agent: Optional[TaskPlannerAgent] = None) -> None:
        self._agent = agent or TaskPlannerAgent()

    async def initialize(self) -> None:
        await self._agent.initialize()

    async def cleanup(self) -> None:
        await self._agent.cleanup()

    async def start_conversation(
        self,
        workflow_id: str,
        trigger_type: Any,
        trigger_source: str,
        trigger_details: Dict[str, Any],
    ) -> Optional[str]:
        return await self._agent.start_conversation(
            workflow_id=workflow_id,
            trigger_type=trigger_type,
            trigger_source=trigger_source,
            trigger_details=trigger_details,
        )

    async def end_conversation(self, status: Any) -> bool:
        return await self._agent.end_conversation(status)

    async def generate_delegation_steps(
        self,
        goal: str,
        constraints: Optional[Dict[str, Any]] = None,
        skip_validation: bool = False,
    ) -> Any:
        return await self._agent.generate_delegation_steps(
            goal,
            constraints=constraints,
            skip_validation=skip_validation,
        )

    async def replan(
        self,
        original_plan: Any,
        failed_step: Any,
        replan_context: Any,
    ) -> Any:
        return await self._agent.replan(original_plan, failed_step, replan_context)
