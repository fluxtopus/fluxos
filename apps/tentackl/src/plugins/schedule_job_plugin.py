"""
Schedule Job Plugin - Schedule tasks for future or recurring execution.

Creates Automation records that the ``check_automations`` Celery Beat task
polls every 2 minutes.  Supports one-time (execute_at) and recurring (cron)
schedules.
"""

import uuid
import structlog
from datetime import datetime
from typing import Any, Dict

from dateutil.parser import isoparse

logger = structlog.get_logger(__name__)


async def schedule_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """
    Schedule a job for future or recurring execution.

    Creates an ``Automation`` record pointing at the current task as a
    template.  When ``check_automations`` fires, the template task's steps
    are cloned and executed.

    If this step is running inside a cloned task (i.e. triggered by an
    automation), it returns early to avoid creating duplicate automations.

    Inputs:
        plan_id: string (required) - ID of the task to use as template
        step_id: string (required) - ID of this step
        user_id: string (required) - User ID for the scheduled job
        organization_id: string (optional) - Organization ID
        execute_at: string (optional) - ISO datetime for one-time execution
        cron: string (optional) - Cron expression for recurring
        timezone: string (optional) - Timezone (default: UTC)
        name: string (optional) - Human-readable name
        _task_metadata: dict (optional) - Injected by step_dispatcher

    Returns:
        {
            job_id: string - Automation ID,
            scheduled_time: string - Next execution time,
            schedule_type: string - one_time or recurring,
            status: string - scheduled, skipped, or error
        }
    """
    # 1. Skip if this is a cloned execution from an automation
    metadata = inputs.get("_task_metadata") or {}
    if metadata.get("automation_id"):
        logger.info(
            "Skipping schedule_job in cloned task",
            automation_id=metadata["automation_id"],
        )
        return {
            "job_id": metadata["automation_id"],
            "scheduled_time": "n/a",
            "schedule_type": "skipped",
            "status": "skipped",
            "note": "Already running from automation",
        }

    # 2. Validate required inputs
    plan_id = inputs.get("plan_id")
    step_id = inputs.get("step_id")
    user_id = inputs.get("user_id")

    if not plan_id:
        return {"error": "plan_id is required", "status": "error"}
    if not step_id:
        return {"error": "step_id is required", "status": "error"}
    if not user_id:
        return {"error": "user_id is required", "status": "error"}

    cron_expr = inputs.get("cron")
    execute_at_raw = inputs.get("execute_at")
    timezone = inputs.get("timezone", "UTC")
    organization_id = inputs.get("organization_id")

    if not cron_expr and not execute_at_raw:
        return {
            "error": "Either execute_at (for one-time) or cron (for recurring) is required",
            "status": "error",
        }

    # 3. Parse and validate schedule parameters
    parsed_execute_at = None
    if execute_at_raw and not cron_expr:
        try:
            parsed_execute_at = isoparse(execute_at_raw)
            # Strip tzinfo for naive DateTime storage (UTC assumed)
            if parsed_execute_at.tzinfo is not None:
                import pytz
                parsed_execute_at = parsed_execute_at.astimezone(pytz.UTC).replace(tzinfo=None)
        except (ValueError, TypeError) as e:
            return {"error": f"Invalid execute_at format: {e}", "status": "error"}

    if cron_expr:
        from src.core.cron_utils import validate_cron_string
        if not validate_cron_string(cron_expr):
            return {"error": f"Invalid cron expression: {cron_expr}", "status": "error"}

    # 4. Calculate next_run_at
    if cron_expr:
        from src.core.cron_utils import calculate_next_run
        next_run = calculate_next_run(cron_expr, timezone)
        if next_run.tzinfo is not None:
            import pytz
            next_run = next_run.astimezone(pytz.UTC).replace(tzinfo=None)
        schedule_type = "recurring"
    else:
        next_run = parsed_execute_at
        schedule_type = "one_time"

    # 5. Create Automation record
    try:
        from src.database.automation_models import Automation
        from src.core.tasks import get_shared_db

        db = await get_shared_db()
        name = inputs.get("name", f"Scheduled: {plan_id[:8]}")
        automation_id = uuid.uuid4()

        new_auto = Automation(
            id=automation_id,
            name=name,
            task_id=uuid.UUID(plan_id),
            owner_id=user_id,
            organization_id=organization_id,
            cron=cron_expr,
            execute_at=parsed_execute_at,
            timezone=timezone,
            enabled=True,
            next_run_at=next_run,
        )

        async with db.get_session() as session:
            session.add(new_auto)
            await session.commit()

        logger.info(
            "Automation created by schedule_job plugin",
            automation_id=str(automation_id),
            plan_id=plan_id,
            schedule_type=schedule_type,
            next_run_at=str(next_run),
        )

        return {
            "job_id": str(automation_id),
            "scheduled_time": next_run.isoformat() if next_run else "not-set",
            "schedule_type": schedule_type,
            "status": "scheduled",
            "name": name,
        }

    except Exception as e:
        logger.error("schedule_job_failed", error=str(e), plan_id=plan_id, exc_info=True)
        return {"error": f"Failed to schedule job: {str(e)}", "status": "error"}


PLUGIN_DEFINITION = {
    "name": "schedule_job",
    "description": "Schedule tasks for future or recurring execution",
    "handler": schedule_handler,
    "inputs_schema": {
        "plan_id": {"type": "string", "required": True, "description": "Plan ID to schedule"},
        "step_id": {"type": "string", "required": True, "description": "Step ID within the plan"},
        "user_id": {"type": "string", "required": True, "description": "User ID"},
        "organization_id": {"type": "string", "required": False, "description": "Organization ID"},
        "execute_at": {"type": "string", "required": False, "description": "ISO datetime for one-time"},
        "cron": {"type": "string", "required": False, "description": "Cron expression for recurring"},
        "timezone": {"type": "string", "required": False, "default": "UTC"},
        "name": {"type": "string", "required": False, "description": "Job name"},
    },
    "outputs_schema": {
        "job_id": {"type": "string", "description": "Automation ID"},
        "scheduled_time": {"type": "string", "description": "Next execution time"},
        "schedule_type": {"type": "string", "description": "one_time, recurring, or skipped"},
        "status": {"type": "string", "description": "scheduled, skipped, or error"},
    },
    "category": "scheduling",
}
