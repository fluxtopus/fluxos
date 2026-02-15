"""Infrastructure adapter for task scheduling."""

from __future__ import annotations

from src.domain.tasks.ports import TaskSchedulerPort
from src.infrastructure.tasks.scheduling import schedule_ready_nodes


class TaskSchedulerAdapter(TaskSchedulerPort):
    """Adapter for scheduling ready task steps."""

    async def schedule_ready_nodes(self, task_id: str) -> int:
        return await schedule_ready_nodes(task_id)
