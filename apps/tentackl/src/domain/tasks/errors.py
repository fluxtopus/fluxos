"""Domain-level task errors."""

from __future__ import annotations

from typing import Optional

from src.domain.tasks.models import TaskException, TaskStatus


class InvalidTransitionError(TaskException):
    """Raised when an invalid state transition is attempted."""

    def __init__(
        self,
        task_id: str,
        current_status: TaskStatus,
        target_status: TaskStatus,
        message: Optional[str] = None,
    ) -> None:
        self.task_id = task_id
        self.current_status = current_status
        self.target_status = target_status
        self.message = message or (
            f"Invalid transition from {current_status.value} to {target_status.value}"
        )
        super().__init__(self.message)
