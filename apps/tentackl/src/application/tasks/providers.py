"""Shared providers for task and checkpoint use cases."""

from __future__ import annotations

from typing import Optional
import structlog

from src.application.tasks import TaskUseCases
from src.application.tasks.runtime import TaskRuntime
from src.application.checkpoints import CheckpointUseCases
from src.infrastructure.checkpoints.task_runtime_checkpoint_adapter import (
    TaskRuntimeCheckpointAdapter,
)


logger = structlog.get_logger(__name__)

_task_runtime: Optional[TaskRuntime] = None
_task_use_cases: Optional[TaskUseCases] = None
_checkpoint_use_cases: Optional[CheckpointUseCases] = None


async def get_task_runtime() -> TaskRuntime:
    """Get the shared task runtime instance."""
    global _task_runtime
    if _task_runtime is None:
        _task_runtime = TaskRuntime()
        await _task_runtime.initialize()
        logger.info("Task runtime initialized")
    return _task_runtime


async def get_task_use_cases() -> TaskUseCases:
    """Get shared task use cases bound to the task runtime."""
    global _task_use_cases
    if _task_use_cases is None:
        runtime = await get_task_runtime()
        _task_use_cases = TaskUseCases(task_ops=runtime)
    return _task_use_cases


async def get_checkpoint_use_cases() -> CheckpointUseCases:
    """Get shared checkpoint use cases bound to the task runtime."""
    global _checkpoint_use_cases
    if _checkpoint_use_cases is None:
        runtime = await get_task_runtime()
        _checkpoint_use_cases = CheckpointUseCases(
            checkpoint_ops=TaskRuntimeCheckpointAdapter(runtime),
        )
    return _checkpoint_use_cases


async def shutdown_task_runtime() -> None:
    """Shutdown shared task runtime and clear singleton instances."""
    global _task_runtime, _task_use_cases, _checkpoint_use_cases
    if _task_runtime is not None:
        await _task_runtime.cleanup()
        logger.info("Task runtime cleaned up")
    _task_runtime = None
    _task_use_cases = None
    _checkpoint_use_cases = None
