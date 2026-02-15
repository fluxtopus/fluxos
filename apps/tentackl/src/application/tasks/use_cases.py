"""Application use cases for task execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any, List, AsyncGenerator

from src.domain.tasks.models import Task, TaskStatus
from src.domain.tasks.ports import TaskOperationsPort


@dataclass
class TaskUseCases:
    """Application-layer orchestration for task operations.

    Routes task commands and queries through the shared task runtime.
    """

    task_ops: TaskOperationsPort

    async def create_task(
        self,
        user_id: str,
        organization_id: Optional[str],
        goal: str,
        constraints: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        auto_start: bool = True,
    ) -> Task:
        return await self.task_ops.create_task(
            user_id=user_id,
            organization_id=organization_id,
            goal=goal,
            constraints=constraints,
            metadata=metadata,
            auto_start=auto_start,
        )

    async def create_task_with_steps(
        self,
        user_id: str,
        organization_id: Optional[str],
        goal: str,
        steps: List[Dict[str, Any]],
        constraints: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Task:
        return await self.task_ops.create_task_with_steps(
            user_id=user_id,
            organization_id=organization_id,
            goal=goal,
            steps=steps,
            constraints=constraints,
            metadata=metadata,
        )

    async def get_task(self, task_id: str) -> Optional[Task]:
        return await self.task_ops.get_task(task_id)

    async def list_tasks(
        self,
        user_id: str,
        status: Optional[TaskStatus] = None,
        limit: int = 50,
    ) -> List[Task]:
        return await self.task_ops.list_tasks(
            user_id=user_id,
            status=status,
            limit=limit,
        )

    async def execute_task(
        self,
        task_id: str,
        user_id: str,
        run_to_completion: bool = False,
    ):
        return await self.task_ops.execute_task(
            task_id=task_id,
            user_id=user_id,
            run_to_completion=run_to_completion,
        )

    async def start_task(self, task_id: str, user_id: str):
        return await self.task_ops.start_task(
            task_id=task_id,
            user_id=user_id,
        )

    async def pause_task(self, task_id: str, user_id: str) -> Task:
        return await self.task_ops.pause_task(task_id, user_id)

    async def cancel_task(self, task_id: str, user_id: str) -> Task:
        return await self.task_ops.cancel_task(task_id, user_id)

    async def observe_execution(
        self,
        task_id: str,
        user_id: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        return self.task_ops.observe_execution(
            task_id=task_id,
            user_id=user_id,
        )

    async def link_conversation(self, task_id: str, conversation_id: str) -> None:
        await self.task_ops.link_conversation(
            task_id=task_id,
            conversation_id=conversation_id,
        )

    async def set_parent_task(self, task_id: str, parent_task_id: str) -> None:
        await self.task_ops.set_parent_task(
            task_id=task_id,
            parent_task_id=parent_task_id,
        )

    async def clone_task_for_trigger(
        self,
        template_task_id: str,
        trigger_event: Dict[str, Any],
    ) -> Task:
        return await self.task_ops.clone_task_for_trigger(
            template_task_id=template_task_id,
            trigger_event=trigger_event,
        )

    async def clone_and_execute_from_automation(
        self,
        automation_id: str,
        template_task_id: str,
        user_id: str,
        organization_id: Optional[str],
    ) -> Task:
        return await self.task_ops.clone_and_execute_from_automation(
            automation_id=automation_id,
            template_task_id=template_task_id,
            user_id=user_id,
            organization_id=organization_id,
        )

    async def update_task_metadata(self, task_id: str, metadata: Dict[str, Any]) -> None:
        await self.task_ops.update_task_metadata(
            task_id=task_id,
            metadata=metadata,
        )
