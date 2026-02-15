"""Infrastructure adapter for queue-mode step dispatch."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.domain.tasks.ports import TaskStepDispatchPort
from src.domain.tasks.models import Task, TaskStep


class StepDispatcherAdapter(TaskStepDispatchPort):
    """Adapter that delegates queue dispatch to the legacy StepDispatcher."""

    async def dispatch_step(
        self,
        task_id: str,
        step: TaskStep,
        plan: Task,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        from src.infrastructure.tasks.step_dispatcher import StepDispatcher

        dispatcher = StepDispatcher(model=model) if model else StepDispatcher()
        result = await dispatcher.dispatch_step(task_id=task_id, step=step, plan=plan)

        return {
            "success": bool(getattr(result, "success", False)),
            "step_id": getattr(result, "step_id", step.id),
            "celery_task_id": getattr(result, "celery_task_id", None),
            "error": getattr(result, "error", None),
        }
