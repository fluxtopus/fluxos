"""Infrastructure adapter for automation scheduling."""

from __future__ import annotations

from typing import Optional
import uuid as uuid_mod
import structlog

from src.domain.tasks.ports import AutomationSchedulerPort
from src.domain.tasks.planning_models import ScheduleSpec
from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskStore
from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore


logger = structlog.get_logger(__name__)


class AutomationSchedulerAdapter(AutomationSchedulerPort):
    """Adapter that creates Automation rows and updates task metadata."""

    def __init__(
        self,
        pg_store: Optional[PostgresTaskStore],
        redis_store: RedisTaskStore,
    ) -> None:
        self._pg_store = pg_store
        self._redis_store = redis_store

    async def create_automation_for_task(
        self,
        task_id: str,
        user_id: str,
        organization_id: Optional[str],
        goal: str,
        schedule: ScheduleSpec,
    ) -> Optional[str]:
        if not schedule.cron and not schedule.execute_at:
            logger.warning("No cron or execute_at provided, skipping automation")
            return None

        if not self._pg_store:
            logger.warning("No PG store available, cannot create automation")
            return None

        from src.database.automation_models import Automation

        if schedule.cron:
            from src.core.cron_utils import validate_cron_string, calculate_next_run

            if not validate_cron_string(schedule.cron):
                logger.warning("Invalid cron from intent extractor, skipping automation", cron=schedule.cron)
                return None

            next_run = calculate_next_run(schedule.cron, schedule.timezone)
            if next_run.tzinfo is not None:
                import pytz

                next_run = next_run.astimezone(pytz.UTC).replace(tzinfo=None)
            automation_name = f"Recurring: {goal[:50]}{'...' if len(goal) > 50 else ''}"
        else:
            next_run = schedule.execute_at
            automation_name = f"Scheduled: {goal[:50]}{'...' if len(goal) > 50 else ''}"

        automation_id = uuid_mod.uuid4()

        async with self._pg_store.db.get_session() as session:
            new_auto = Automation(
                id=automation_id,
                name=automation_name,
                task_id=uuid_mod.UUID(task_id),
                owner_id=user_id,
                organization_id=organization_id or None,
                cron=schedule.cron,
                execute_at=schedule.execute_at,
                timezone=schedule.timezone,
                enabled=True,
                next_run_at=next_run,
            )
            session.add(new_auto)
            await session.commit()

        auto_metadata = {
            "automation_id": str(automation_id),
            "schedule_cron": schedule.cron,
            "schedule_execute_at": schedule.execute_at.isoformat() if schedule.execute_at else None,
            "schedule_timezone": schedule.timezone,
        }
        if self._pg_store:
            await self._pg_store.update_task(task_id, {"metadata": auto_metadata})
        await self._redis_store.update_task(task_id, {"metadata": auto_metadata})

        logger.info(
            "Automation created from scheduling intent",
            automation_id=str(automation_id),
            task_id=task_id,
            cron=schedule.cron,
            execute_at=str(schedule.execute_at) if schedule.execute_at else None,
            timezone=schedule.timezone,
        )

        return str(automation_id)
