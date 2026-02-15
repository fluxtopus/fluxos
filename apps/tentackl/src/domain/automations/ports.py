"""Domain ports for automation persistence."""

from __future__ import annotations

from typing import Dict, List, Optional, Protocol
from uuid import UUID

from src.database.automation_models import Automation
from src.database.task_models import Task as TaskModel


class AutomationRepositoryPort(Protocol):
    """Port for automation persistence operations."""

    async def list_automations(self, user_id: str, include_paused: bool) -> List[Automation]:
        ...

    async def get_automation(self, automation_id: UUID, user_id: str) -> Optional[Automation]:
        ...

    async def update_automation_enabled(self, automation_id: UUID, enabled: bool, next_run_at=None) -> None:
        ...

    async def delete_automation(self, automation: Automation) -> None:
        ...

    async def create_automation(self, automation: Automation) -> Automation:
        ...

    async def get_task_goals(self, task_ids: List[UUID]) -> Dict[str, str]:
        ...

    async def get_task_goal(self, task_id: UUID) -> Optional[str]:
        ...

    async def get_tasks_for_automation(self, automation_id: str, limit: int = 20) -> List[TaskModel]:
        ...

    async def get_task_for_user(self, task_id: UUID, user_id: str) -> Optional[TaskModel]:
        ...
