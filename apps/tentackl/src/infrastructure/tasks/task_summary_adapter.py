"""Infrastructure adapter for task summary generation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.domain.tasks.ports import TaskSummaryPort
from src.infrastructure.inbox.summary_service import SummaryGenerationService


class TaskSummaryAdapter(TaskSummaryPort):
    """Adapter exposing inbox summary generation through a task-focused port."""

    def __init__(self, summary_service: Optional[SummaryGenerationService] = None) -> None:
        self._summary_service = summary_service or SummaryGenerationService()

    async def generate_summary_safe(
        self,
        goal: str,
        status: str,
        steps_completed: int,
        total_steps: int,
        key_outputs: Dict[str, Any],
        findings: List[Any],
        error: Optional[str] = None,
    ) -> str:
        return await self._summary_service.generate_summary_safe(
            goal=goal,
            status=status,
            steps_completed=steps_completed,
            total_steps=total_steps,
            key_outputs=key_outputs,
            findings=findings,
            error=error,
        )
