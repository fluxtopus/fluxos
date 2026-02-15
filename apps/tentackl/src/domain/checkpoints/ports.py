"""Domain ports for checkpoint operations."""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol


class CheckpointOperationsPort(Protocol):
    """Port for checkpoint operations."""

    async def list_pending(self, user_id: str) -> list[Any]:
        ...

    async def list_pending_for_task(self, task_id: str) -> list[Any]:
        ...

    async def get_checkpoint(self, task_id: str, step_id: str) -> Optional[Any]:
        ...

    async def approve_checkpoint(
        self,
        task_id: str,
        step_id: str,
        user_id: str,
        feedback: Optional[str],
        learn_preference: bool,
    ) -> Any:
        ...

    async def reject_checkpoint(
        self,
        task_id: str,
        step_id: str,
        user_id: str,
        reason: str,
        learn_preference: bool,
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
