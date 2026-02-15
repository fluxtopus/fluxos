"""Checkpoint adapter backed by TaskRuntime-compatible methods."""

from __future__ import annotations

from typing import Any, Optional, Protocol

from src.domain.checkpoints.ports import CheckpointOperationsPort


class TaskCheckpointRuntime(Protocol):
    async def list_pending_checkpoints(self, user_id: str) -> list[Any]:
        ...

    async def list_pending_checkpoints_for_task(self, task_id: str) -> list[Any]:
        ...

    async def get_checkpoint(self, task_id: str, step_id: str) -> Optional[Any]:
        ...

    async def approve_checkpoint(
        self,
        plan_id: str,
        step_id: str,
        user_id: str,
        feedback: Optional[str] = None,
        learn_preference: bool = True,
    ) -> Any:
        ...

    async def reject_checkpoint(
        self,
        plan_id: str,
        step_id: str,
        user_id: str,
        reason: str = "",
        learn_preference: bool = True,
    ) -> Any:
        ...

    async def resolve_checkpoint(
        self,
        task_id: str,
        step_id: str,
        user_id: str,
        response: Any,
        learn_preference: bool,
    ) -> Any:
        ...


class TaskRuntimeCheckpointAdapter(CheckpointOperationsPort):
    """Adapter exposing checkpoint operations from the shared task runtime."""

    def __init__(self, runtime: TaskCheckpointRuntime) -> None:
        self._runtime = runtime

    async def list_pending(self, user_id: str) -> list[Any]:
        return await self._runtime.list_pending_checkpoints(user_id)

    async def list_pending_for_task(self, task_id: str) -> list[Any]:
        return await self._runtime.list_pending_checkpoints_for_task(task_id)

    async def get_checkpoint(self, task_id: str, step_id: str) -> Optional[Any]:
        return await self._runtime.get_checkpoint(task_id, step_id)

    async def approve_checkpoint(
        self,
        task_id: str,
        step_id: str,
        user_id: str,
        feedback: Optional[str] = None,
        learn_preference: bool = True,
    ) -> Any:
        return await self._runtime.approve_checkpoint(
            plan_id=task_id,
            step_id=step_id,
            user_id=user_id,
            feedback=feedback,
            learn_preference=learn_preference,
        )

    async def reject_checkpoint(
        self,
        task_id: str,
        step_id: str,
        user_id: str,
        reason: str,
        learn_preference: bool = True,
    ) -> Any:
        return await self._runtime.reject_checkpoint(
            plan_id=task_id,
            step_id=step_id,
            user_id=user_id,
            reason=reason,
            learn_preference=learn_preference,
        )

    async def resolve_checkpoint(
        self,
        task_id: str,
        step_id: str,
        user_id: str,
        response: Any,
        learn_preference: bool,
    ) -> Any:
        return await self._runtime.resolve_checkpoint(
            task_id=task_id,
            step_id=step_id,
            user_id=user_id,
            response=response,
            learn_preference=learn_preference,
        )
