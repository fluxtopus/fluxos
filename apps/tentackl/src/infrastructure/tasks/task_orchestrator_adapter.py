"""Infrastructure adapter for task orchestration."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.domain.tasks.ports import (
    TaskOrchestratorPort,
    TaskPlanStorePort,
    TaskObserverPort,
    TaskPlannerPort,
    TaskStepDispatchPort,
)
from src.domain.memory import MemoryOperationsPort
from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore
from src.infrastructure.tasks.task_orchestrator import TaskOrchestratorAgent
from src.infrastructure.tasks.task_plan_store_adapter import TaskPlanStoreAdapter
from src.infrastructure.tasks.task_observer_adapter import TaskObserverAdapter
from src.infrastructure.tasks.task_planner_adapter import TaskPlannerAdapter
from src.infrastructure.tasks.step_dispatcher_adapter import StepDispatcherAdapter


class TaskOrchestratorAdapter(TaskOrchestratorPort):
    """Adapter exposing TaskOrchestratorAgent through the domain port."""

    def __init__(
        self,
        plan_store: Optional[TaskPlanStorePort] = None,
        redis_store: Optional[RedisTaskStore] = None,
        execution_mode: str = "queue",
        memory_service: Optional[MemoryOperationsPort] = None,
        observer: Optional[TaskObserverPort] = None,
        planner: Optional[TaskPlannerPort] = None,
        step_dispatcher: Optional[TaskStepDispatchPort] = None,
        llm_client: Optional[Any] = None,
        agent: Optional[TaskOrchestratorAgent] = None,
    ) -> None:
        if agent is not None:
            self._agent = agent
            self._owns_observer = False
            self._owns_planner = False
            return

        if plan_store is None:
            plan_store = TaskPlanStoreAdapter(redis_store)
        self._owns_observer = observer is None
        self._owns_planner = planner is None
        observer = observer or TaskObserverAdapter(
            plan_store=plan_store,
            llm_client=llm_client,
        )
        planner = planner or TaskPlannerAdapter()
        step_dispatcher = step_dispatcher or StepDispatcherAdapter()
        self._agent = TaskOrchestratorAgent(
            plan_store=plan_store,
            execution_mode=execution_mode,
            memory_service=memory_service,
            observer=observer,
            planner=planner,
            step_dispatcher=step_dispatcher,
            llm_client=llm_client,
        )

    async def initialize(self) -> None:
        await self._agent.initialize()
        if self._owns_observer:
            await self._agent._observer.initialize()
        if self._owns_planner:
            await self._agent._planner.initialize()

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

    async def execute_cycle(self, plan_id: str) -> Dict[str, Any]:
        return await self._agent.execute_cycle(plan_id)

    async def execute_replan(self, plan_id: str, step_id: str) -> Dict[str, Any]:
        return await self._agent.execute_replan(plan_id, step_id)
