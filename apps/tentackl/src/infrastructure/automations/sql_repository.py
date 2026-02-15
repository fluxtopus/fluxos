"""SQLAlchemy repository for automations."""

from __future__ import annotations

from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, select, text, update

from src.database.automation_models import Automation
from src.database.task_models import Task as TaskModel
from src.domain.automations.ports import AutomationRepositoryPort
from src.interfaces.database import Database


class SqlAutomationRepository(AutomationRepositoryPort):
    """SQLAlchemy-backed automation repository."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def list_automations(self, user_id: str, include_paused: bool) -> List[Automation]:
        async with self._database.get_session() as session:
            query = select(Automation).where(Automation.owner_id == user_id)
            if not include_paused:
                query = query.where(Automation.enabled == True)  # noqa: E712
            result = await session.execute(query.order_by(Automation.updated_at.desc()))
            return result.scalars().all()

    async def get_automation(self, automation_id: UUID, user_id: str) -> Optional[Automation]:
        async with self._database.get_session() as session:
            result = await session.execute(
                select(Automation).where(
                    and_(Automation.id == automation_id, Automation.owner_id == user_id)
                )
            )
            return result.scalar_one_or_none()

    async def update_automation_enabled(self, automation_id: UUID, enabled: bool, next_run_at=None) -> None:
        async with self._database.get_session() as session:
            values = {"enabled": enabled}
            if next_run_at is not None:
                values["next_run_at"] = next_run_at
            await session.execute(
                update(Automation).where(Automation.id == automation_id).values(**values)
            )
            await session.commit()

    async def delete_automation(self, automation: Automation) -> None:
        async with self._database.get_session() as session:
            await session.delete(automation)
            await session.commit()

    async def create_automation(self, automation: Automation) -> Automation:
        async with self._database.get_session() as session:
            session.add(automation)
            await session.commit()
            await session.refresh(automation)
            return automation

    async def get_task_goals(self, task_ids: List[UUID]) -> Dict[str, str]:
        if not task_ids:
            return {}
        async with self._database.get_session() as session:
            result = await session.execute(
                select(TaskModel.id, TaskModel.goal).where(TaskModel.id.in_(task_ids))
            )
            return {str(tid): goal or "Unknown" for tid, goal in result}

    async def get_task_goal(self, task_id: UUID) -> Optional[str]:
        async with self._database.get_session() as session:
            result = await session.execute(
                select(TaskModel.goal).where(TaskModel.id == task_id)
            )
            return result.scalar_one_or_none()

    async def get_tasks_for_automation(self, automation_id: str, limit: int = 20) -> List[TaskModel]:
        async with self._database.get_session() as session:
            result = await session.execute(
                select(TaskModel)
                .where(text("metadata->>'automation_id' = :aid").bindparams(aid=automation_id))
                .order_by(TaskModel.created_at.desc())
                .limit(limit)
            )
            return result.scalars().all()

    async def get_task_for_user(self, task_id: UUID, user_id: str) -> Optional[TaskModel]:
        async with self._database.get_session() as session:
            result = await session.execute(
                select(TaskModel).where(and_(TaskModel.id == task_id, TaskModel.user_id == user_id))
            )
            return result.scalar_one_or_none()
