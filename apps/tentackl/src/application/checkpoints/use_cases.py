"""Application use cases for checkpoint operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.domain.checkpoints import (
    CheckpointDecision,
    CheckpointOperationsPort,
    CheckpointResponse,
    CheckpointState,
)


class CheckpointNotFound(Exception):
    """Raised when a checkpoint is not found."""


class CheckpointValidationError(Exception):
    """Raised when checkpoint inputs are invalid."""


@dataclass
class CheckpointUseCases:
    """Application-layer orchestration for checkpoint operations."""

    checkpoint_ops: CheckpointOperationsPort

    async def list_pending(self, user_id: str) -> list[CheckpointState]:
        return await self.checkpoint_ops.list_pending(user_id)

    async def list_pending_for_task(self, task_id: str) -> list[CheckpointState]:
        return await self.checkpoint_ops.list_pending_for_task(task_id)

    async def get_checkpoint(self, task_id: str, step_id: str) -> CheckpointState:
        checkpoint = await self.checkpoint_ops.get_checkpoint(task_id, step_id)
        if not checkpoint:
            raise CheckpointNotFound()
        return checkpoint

    async def approve_checkpoint(
        self,
        task_id: str,
        step_id: str,
        user_id: str,
        feedback: Optional[str] = None,
        learn_preference: bool = True,
    ) -> CheckpointState:
        return await self.checkpoint_ops.approve_checkpoint(
            task_id=task_id,
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
    ) -> CheckpointState:
        return await self.checkpoint_ops.reject_checkpoint(
            task_id=task_id,
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
        decision: str,
        feedback: Optional[str],
        inputs: Optional[Dict[str, Any]],
        modified_inputs: Optional[Dict[str, Any]],
        selected_alternative: Optional[int],
        answers: Optional[Dict[str, str]],
        learn_preference: bool,
    ) -> CheckpointState:
        try:
            decision_enum = CheckpointDecision(decision)
        except ValueError as exc:
            raise CheckpointValidationError(
                f"Invalid decision: {decision}. Must be 'approved' or 'rejected'"
            ) from exc

        response = CheckpointResponse(
            decision=decision_enum,
            feedback=feedback,
            inputs=inputs,
            modified_inputs=modified_inputs,
            selected_alternative=selected_alternative,
            answers=answers,
        )

        return await self.checkpoint_ops.resolve_checkpoint(
            task_id=task_id,
            step_id=step_id,
            user_id=user_id,
            response=response,
            learn_preference=learn_preference,
        )
