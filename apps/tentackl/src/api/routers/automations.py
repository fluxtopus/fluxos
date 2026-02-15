"""
# REVIEW:
# - Uses global database injection; composition root still relies on module-level state.
# - Automation executions are inferred from Task.metadata JSON via raw SQL text; fragile and hard to index.
# - Stores schedule times as UTC-naive datetimes; timezone handling risks drift.
API routes for user-facing automations (task-based recurring schedules).

Provides a simplified interface for managing automated task execution:
- List user's automations with health status
- View automation details and execution history
- Pause/Resume/Run Now actions
- Create automations from completed tasks

Automations reference a completed task as a template. When a schedule fires,
the template task's steps are cloned and executed immediately.
"""

from fastapi import APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import structlog

from src.application.automations import (
    AutomationNotFound,
    AutomationScheduleError,
    AutomationUseCases,
    AutomationValidationError,
)
from src.infrastructure.automations.sql_repository import SqlAutomationRepository
from src.application.tasks import TaskUseCases
from src.application.tasks.providers import get_task_use_cases as provider_get_task_use_cases
from src.interfaces.database import Database
from src.api.auth_middleware import auth_middleware, AuthUser
from src.api.error_helpers import safe_error_detail

logger = structlog.get_logger()

router = APIRouter(prefix="/api/automations", tags=["automations"])

# Component instances (initialized in app startup)
database: Optional[Database] = None
_task_use_cases_instance: Optional[TaskUseCases] = None


def get_database() -> Database:
    """Get the database instance."""
    if not database:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return database


async def _get_task_use_cases() -> TaskUseCases:
    """Get or create TaskUseCases for run-now operations."""
    global _task_use_cases_instance
    if _task_use_cases_instance is None:
        _task_use_cases_instance = await provider_get_task_use_cases()
    return _task_use_cases_instance


def get_automation_use_cases(
    db: Database = Depends(get_database),
) -> AutomationUseCases:
    """Provide application-layer automation use cases."""
    return AutomationUseCases(
        repository=SqlAutomationRepository(db),
        task_use_cases_provider=_get_task_use_cases,
    )


# === Response Models ===

class ExecutionSummary(BaseModel):
    """Summary of a single automation execution."""
    id: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    step_count: int = 0
    steps_completed: int = 0


class AutomationStats(BaseModel):
    """Statistics for an automation."""
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    success_rate: float = 0.0
    avg_duration_seconds: Optional[float] = None


class AutomationSummary(BaseModel):
    """Summary of an automation for list view."""
    id: str
    name: str
    task_id: str
    goal: str
    schedule_cron: Optional[str] = None
    schedule_execute_at: Optional[datetime] = None
    schedule_timezone: str
    schedule_enabled: bool
    next_scheduled_run: Optional[datetime] = None
    last_execution: Optional[ExecutionSummary] = None
    stats: AutomationStats
    created_at: datetime
    updated_at: datetime


class AutomationDetail(AutomationSummary):
    """Detailed automation view with execution history."""
    recent_executions: List[ExecutionSummary] = []


class AutomationListResponse(BaseModel):
    """Response for list automations endpoint."""
    automations: List[AutomationSummary]
    total: int
    needs_attention: int


class CreateFromTaskRequest(BaseModel):
    """Request to create an automation from a completed task."""
    schedule_cron: str = Field(..., description="Cron expression (e.g., '0 8 * * *' for daily at 8am)")
    schedule_timezone: str = Field(default="UTC", description="Timezone for schedule")
    name: Optional[str] = Field(default=None, description="Custom name for the automation")


# === Endpoints ===

@router.get("", response_model=AutomationListResponse)
async def list_automations(
    user: AuthUser = Depends(auth_middleware.require_permission("automations", "view")),
    include_paused: bool = Query(default=True, description="Include paused automations"),
    use_cases: AutomationUseCases = Depends(get_automation_use_cases),
):
    """
    List all automations for the current user.

    Returns automations sorted by: needs attention first, then by enabled status.
    """
    user_id = user.id

    try:
        result = await use_cases.list_automations(
            user_id=user_id,
            include_paused=include_paused,
        )
        return AutomationListResponse(**result)

    except Exception as e:
        logger.error("Failed to list automations", user_id=user_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=safe_error_detail(f"Failed to list automations: {str(e)}"))


@router.get("/{automation_id}", response_model=AutomationDetail)
async def get_automation(
    automation_id: str,
    user: AuthUser = Depends(auth_middleware.require_permission("automations", "view")),
    use_cases: AutomationUseCases = Depends(get_automation_use_cases),
):
    """
    Get detailed information about an automation including execution history.
    """
    user_id = user.id

    try:
        detail = await use_cases.get_automation(user_id=user_id, automation_id=automation_id)
        return AutomationDetail(**detail)
    except AutomationValidationError:
        raise HTTPException(status_code=400, detail="Invalid automation ID format")
    except AutomationNotFound:
        raise HTTPException(status_code=404, detail="Automation not found")
    except Exception as e:
        logger.error("Failed to get automation", automation_id=automation_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=safe_error_detail(f"Failed to get automation: {str(e)}"))


@router.post("/{automation_id}/pause", status_code=status.HTTP_200_OK)
async def pause_automation(
    automation_id: str,
    user: AuthUser = Depends(auth_middleware.require_permission("automations", "update")),
    use_cases: AutomationUseCases = Depends(get_automation_use_cases),
):
    """
    Pause an automation. It will not run until resumed.
    """
    user_id = user.id

    try:
        result = await use_cases.pause_automation(user_id=user_id, automation_id=automation_id)

        logger.info("Automation paused", automation_id=automation_id, user_id=user_id)
        return result

    except AutomationValidationError:
        raise HTTPException(status_code=400, detail="Invalid automation ID format")
    except AutomationNotFound:
        raise HTTPException(status_code=404, detail="Automation not found")
    except Exception as e:
        logger.error("Failed to pause automation", automation_id=automation_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=safe_error_detail(f"Failed to pause automation: {str(e)}"))


@router.post("/{automation_id}/resume", status_code=status.HTTP_200_OK)
async def resume_automation(
    automation_id: str,
    user: AuthUser = Depends(auth_middleware.require_permission("automations", "update")),
    use_cases: AutomationUseCases = Depends(get_automation_use_cases),
):
    """
    Resume a paused automation. Recalculates next_run_at.
    """
    user_id = user.id

    try:
        result = await use_cases.resume_automation(user_id=user_id, automation_id=automation_id)

        logger.info("Automation resumed", automation_id=automation_id, user_id=user_id)
        return result

    except AutomationValidationError:
        raise HTTPException(status_code=400, detail="Invalid automation ID format")
    except AutomationScheduleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except AutomationNotFound:
        raise HTTPException(status_code=404, detail="Automation not found")
    except Exception as e:
        logger.error("Failed to resume automation", automation_id=automation_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=safe_error_detail(f"Failed to resume automation: {str(e)}"))


@router.post("/{automation_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def run_automation_now(
    automation_id: str,
    user: AuthUser = Depends(auth_middleware.require_permission("automations", "execute")),
    use_cases: AutomationUseCases = Depends(get_automation_use_cases),
):
    """
    Trigger an immediate execution of the automation.

    Clones the template task and starts execution. Returns the new task ID.
    """
    user_id = user.id

    try:
        result = await use_cases.run_automation_now(user_id=user_id, automation_id=automation_id)

        logger.info(
            "Automation run-now triggered",
            automation_id=automation_id,
            new_task_id=result.get("task_id"),
            user_id=user_id,
        )
        return result

    except AutomationValidationError:
        raise HTTPException(status_code=400, detail="Invalid automation ID format")
    except AutomationNotFound:
        raise HTTPException(status_code=404, detail="Automation not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(str(e)))
    except Exception as e:
        logger.error("Failed to run automation", automation_id=automation_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=safe_error_detail(f"Failed to run automation: {str(e)}"))


@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_automation(
    automation_id: str,
    user: AuthUser = Depends(auth_middleware.require_permission("automations", "delete")),
    use_cases: AutomationUseCases = Depends(get_automation_use_cases),
):
    """
    Delete an automation.

    Removes the automation row. Past executions (tasks) are preserved.
    """
    user_id = user.id

    try:
        await use_cases.delete_automation(user_id=user_id, automation_id=automation_id)

        logger.info("Automation deleted", automation_id=automation_id, user_id=user_id)
        return None

    except AutomationValidationError:
        raise HTTPException(status_code=400, detail="Invalid automation ID format")
    except AutomationNotFound:
        raise HTTPException(status_code=404, detail="Automation not found")
    except Exception as e:
        logger.error("Failed to delete automation", automation_id=automation_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=safe_error_detail(f"Failed to delete automation: {str(e)}"))


@router.post("/from-task/{task_id}", response_model=AutomationDetail, status_code=status.HTTP_201_CREATED)
async def create_automation_from_task(
    task_id: str,
    request: CreateFromTaskRequest,
    user: AuthUser = Depends(auth_middleware.require_permission("automations", "create")),
    use_cases: AutomationUseCases = Depends(get_automation_use_cases),
):
    """
    Create an automation from a completed task.

    This takes a successful task and turns it into a recurring automation
    that runs on the specified schedule.
    """
    user_id = user.id

    try:
        detail = await use_cases.create_automation_from_task(
            user_id=user_id,
            task_id=task_id,
            schedule_cron=request.schedule_cron,
            schedule_timezone=request.schedule_timezone,
            name=request.name,
        )

        logger.info(
            "Automation created from task",
            automation_id=detail.get("id"),
            task_id=task_id,
            user_id=user_id,
            schedule=request.schedule_cron,
        )

        return AutomationDetail(**detail)
    except AutomationValidationError:
        raise HTTPException(status_code=400, detail="Invalid task ID format")
    except AutomationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except AutomationScheduleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as e:
        logger.error("Failed to create automation from task", task_id=task_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=safe_error_detail(f"Failed to create automation: {str(e)}"))
