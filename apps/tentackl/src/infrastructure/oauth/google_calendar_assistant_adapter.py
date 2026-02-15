"""Infrastructure adapter for Google calendar assistant automation management."""

from __future__ import annotations

import uuid
from datetime import timezone as dt_timezone
from typing import Any, Dict, Optional

import structlog
from sqlalchemy import and_, select, update

from src.application.tasks.providers import get_task_use_cases as provider_get_task_use_cases
from src.core.cron_utils import calculate_next_run, validate_cron_string
from src.database.automation_models import Automation
from src.domain.oauth import GoogleCalendarAssistantPort
from src.infrastructure.oauth.calendar_assistant_plan_factory import create_calendar_plan
from src.interfaces.database import Database

logger = structlog.get_logger(__name__)


class GoogleCalendarAssistantAdapter(GoogleCalendarAssistantPort):
    """Adapter handling calendar assistant scheduling persistence."""

    async def enable(
        self,
        user_id: str,
        organization_id: Optional[str],
        cron: str,
    ) -> Dict[str, Any]:
        if not validate_cron_string(cron):
            raise ValueError(f"Invalid cron expression: {cron}")

        next_run = calculate_next_run(cron, "UTC")
        if next_run.tzinfo is not None:
            next_run = next_run.astimezone(dt_timezone.utc).replace(tzinfo=None)

        automation_name = f"Calendar Assistant ({user_id})"
        db = Database()
        await db.connect()

        try:
            async with db.get_session() as session:
                existing = await session.execute(
                    select(Automation).where(
                        and_(Automation.owner_id == user_id, Automation.name == automation_name)
                    )
                )
                existing_auto = existing.scalar_one_or_none()

                if existing_auto:
                    await session.execute(
                        update(Automation)
                        .where(Automation.id == existing_auto.id)
                        .values(
                            cron=cron,
                            execute_at=None,
                            timezone="UTC",
                            enabled=True,
                            next_run_at=next_run,
                        )
                    )
                    await session.commit()

                    logger.info(
                        "Calendar assistant schedule updated",
                        user_id=user_id,
                        automation_id=str(existing_auto.id),
                        cron=cron,
                    )
                    return {
                        "success": True,
                        "user_id": user_id,
                        "enabled": True,
                        "message": f"Calendar assistant enabled successfully. It will run on schedule: {cron}",
                    }

            plan = create_calendar_plan(user_id=user_id, organization_id=organization_id)
            plan.metadata["calendar_assistant"] = True
            plan.metadata["assistant_type"] = "calendar"

            task_use_cases = await provider_get_task_use_cases()
            steps_payload = [step.to_dict() if hasattr(step, "to_dict") else step for step in plan.steps]
            template_task = await task_use_cases.create_task_with_steps(
                user_id=user_id,
                organization_id=organization_id,
                goal=plan.goal,
                steps=steps_payload,
                constraints=plan.constraints,
                metadata=plan.metadata,
            )

            async with db.get_session() as session:
                automation_id = uuid.uuid4()
                automation = Automation(
                    id=automation_id,
                    name=automation_name,
                    task_id=uuid.UUID(template_task.id),
                    owner_id=user_id,
                    organization_id=organization_id,
                    cron=cron,
                    timezone="UTC",
                    enabled=True,
                    next_run_at=next_run,
                )
                session.add(automation)
                await session.commit()

            metadata_update = {
                **(template_task.metadata or {}),
                "automation_id": str(automation_id),
                "schedule_cron": cron,
                "schedule_timezone": "UTC",
                "source": "schedule",
            }
            await task_use_cases.update_task_metadata(
                task_id=template_task.id,
                metadata=metadata_update,
            )

            logger.info(
                "Calendar assistant enabled via task automation",
                user_id=user_id,
                automation_id=str(automation_id),
                task_id=template_task.id,
                cron=cron,
            )
            return {
                "success": True,
                "user_id": user_id,
                "enabled": True,
                "message": f"Calendar assistant enabled successfully. It will run on schedule: {cron}",
            }
        finally:
            await db.disconnect()

    async def disable(self, user_id: str) -> Dict[str, Any]:
        automation_name = f"Calendar Assistant ({user_id})"
        db = Database()
        await db.connect()

        try:
            async with db.get_session() as session:
                existing = await session.execute(
                    select(Automation).where(
                        and_(Automation.owner_id == user_id, Automation.name == automation_name)
                    )
                )
                existing_auto = existing.scalar_one_or_none()

                if not existing_auto:
                    logger.warning(
                        "Calendar assistant automation not found for user",
                        user_id=user_id,
                    )
                    return {
                        "success": True,
                        "user_id": user_id,
                        "enabled": False,
                        "message": "Calendar assistant was not enabled.",
                    }

                await session.execute(
                    update(Automation)
                    .where(Automation.id == existing_auto.id)
                    .values(enabled=False, next_run_at=None)
                )
                await session.commit()

            logger.info(
                "Calendar assistant disabled via task automation",
                user_id=user_id,
                automation_id=str(existing_auto.id),
            )
            return {
                "success": True,
                "user_id": user_id,
                "enabled": False,
                "message": "Calendar assistant disabled successfully.",
            }
        finally:
            await db.disconnect()
