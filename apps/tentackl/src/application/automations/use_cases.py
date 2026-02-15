"""Application use cases for user-facing automations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from datetime import datetime
import uuid

from src.database.automation_models import Automation
from src.database.task_models import Task as TaskModel
from src.domain.automations.ports import AutomationRepositoryPort


class AutomationNotFound(Exception):
    """Raised when an automation or task is not found."""


class AutomationValidationError(Exception):
    """Raised when identifiers or inputs are invalid."""


class AutomationScheduleError(Exception):
    """Raised when schedule inputs are invalid."""


def _next_run_utc_naive(cron: str, tz: str) -> datetime:
    """Calculate the next run as a UTC-naive datetime (for storage in DateTime columns)."""
    from src.core.cron_utils import calculate_next_run

    next_run = calculate_next_run(cron, tz)
    if next_run.tzinfo is not None:
        import pytz

        next_run = next_run.astimezone(pytz.UTC).replace(tzinfo=None)
    return next_run


def _calculate_duration(created_at: datetime, completed_at: Optional[datetime]) -> Optional[float]:
    if completed_at and created_at:
        return (completed_at - created_at).total_seconds()
    return None


def _extract_error_from_steps(steps: List[Dict[str, Any]]) -> Optional[str]:
    for step in steps or []:
        if step.get("status") == "failed" and step.get("error_message"):
            return step["error_message"]
    return None


def _task_to_execution_summary(task: TaskModel) -> Dict[str, Any]:
    steps = task.steps or []
    steps_completed = sum(1 for s in steps if s.get("status") in ("done", "completed"))

    return {
        "id": str(task.id),
        "status": task.status,
        "started_at": task.created_at,
        "completed_at": task.completed_at,
        "duration_seconds": _calculate_duration(task.created_at, task.completed_at),
        "error_message": _extract_error_from_steps(steps) if task.status == "failed" else None,
        "step_count": len(steps),
        "steps_completed": steps_completed,
    }


def _automation_to_summary(
    auto: Automation,
    goal: str,
    stats: Dict[str, Any],
    last_execution: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "id": str(auto.id),
        "name": auto.name,
        "task_id": str(auto.task_id),
        "goal": goal,
        "schedule_cron": auto.cron,
        "schedule_execute_at": auto.execute_at,
        "schedule_timezone": auto.timezone or "UTC",
        "schedule_enabled": auto.enabled,
        "next_scheduled_run": auto.next_run_at,
        "last_execution": last_execution,
        "stats": stats,
        "created_at": auto.created_at,
        "updated_at": auto.updated_at,
    }


@dataclass
class AutomationUseCases:
    """Application-layer orchestration for automations."""

    repository: AutomationRepositoryPort
    task_use_cases_provider: Callable[[], Awaitable[Any]]

    async def list_automations(self, user_id: str, include_paused: bool) -> Dict[str, Any]:
        rows = await self.repository.list_automations(user_id=user_id, include_paused=include_paused)

        task_ids = list({r.task_id for r in rows})
        goals_map = await self.repository.get_task_goals(task_ids)

        automations: List[Dict[str, Any]] = []
        needs_attention = 0

        for auto in rows:
            stats, last_execution, _ = await self._get_automation_stats(str(auto.id))

            if last_execution and last_execution.get("status") == "failed":
                needs_attention += 1

            goal = goals_map.get(str(auto.task_id), "Unknown")
            automations.append(_automation_to_summary(auto, goal, stats, last_execution))

        automations.sort(
            key=lambda a: (
                0 if (a.get("last_execution") and a["last_execution"].get("status") == "failed") else 1,
                0 if a.get("schedule_enabled") else 1,
            )
        )

        return {
            "automations": automations,
            "total": len(automations),
            "needs_attention": needs_attention,
        }

    async def get_automation(self, user_id: str, automation_id: str) -> Dict[str, Any]:
        automation_uuid = self._parse_uuid(automation_id)

        auto = await self.repository.get_automation(automation_uuid, user_id)
        if not auto:
            raise AutomationNotFound("Automation not found")

        goal = await self.repository.get_task_goal(auto.task_id) or "Unknown"
        stats, last_execution, recent_executions = await self._get_automation_stats(automation_id)

        detail = _automation_to_summary(auto, goal, stats, last_execution)
        detail["recent_executions"] = recent_executions
        return detail

    async def pause_automation(self, user_id: str, automation_id: str) -> Dict[str, Any]:
        automation_uuid = self._parse_uuid(automation_id)

        auto = await self.repository.get_automation(automation_uuid, user_id)
        if not auto:
            raise AutomationNotFound("Automation not found")

        await self.repository.update_automation_enabled(automation_uuid, enabled=False)

        return {"ok": True, "message": "Automation paused", "schedule_enabled": False}

    async def resume_automation(self, user_id: str, automation_id: str) -> Dict[str, Any]:
        automation_uuid = self._parse_uuid(automation_id)

        auto = await self.repository.get_automation(automation_uuid, user_id)
        if not auto:
            raise AutomationNotFound("Automation not found")

        if auto.cron:
            next_run = _next_run_utc_naive(auto.cron, auto.timezone or "UTC")
        elif auto.execute_at:
            next_run = auto.execute_at
        else:
            raise AutomationScheduleError("Automation has no schedule configured")

        await self.repository.update_automation_enabled(
            automation_uuid,
            enabled=True,
            next_run_at=next_run,
        )

        return {"ok": True, "message": "Automation resumed", "schedule_enabled": True}

    async def run_automation_now(self, user_id: str, automation_id: str) -> Dict[str, Any]:
        automation_uuid = self._parse_uuid(automation_id)

        auto = await self.repository.get_automation(automation_uuid, user_id)
        if not auto:
            raise AutomationNotFound("Automation not found")

        task_use_cases = await self.task_use_cases_provider()
        new_task = await task_use_cases.clone_and_execute_from_automation(
            automation_id=automation_id,
            template_task_id=str(auto.task_id),
            user_id=user_id,
            organization_id=auto.organization_id,
        )

        return {"ok": True, "message": "Execution started", "task_id": new_task.id}

    async def delete_automation(self, user_id: str, automation_id: str) -> None:
        automation_uuid = self._parse_uuid(automation_id)

        auto = await self.repository.get_automation(automation_uuid, user_id)
        if not auto:
            raise AutomationNotFound("Automation not found")

        await self.repository.delete_automation(auto)

    async def create_automation_from_task(
        self,
        user_id: str,
        task_id: str,
        schedule_cron: str,
        schedule_timezone: str,
        name: Optional[str],
    ) -> Dict[str, Any]:
        task_uuid = self._parse_uuid(task_id)

        from src.core.cron_utils import validate_cron_string

        if not validate_cron_string(schedule_cron):
            raise AutomationScheduleError(f"Invalid cron expression: {schedule_cron}")

        task = await self.repository.get_task_for_user(task_uuid, user_id)
        if not task:
            raise AutomationNotFound("Task not found")

        if task.status != "completed":
            raise AutomationScheduleError(
                f"Can only create automation from completed tasks. Task status: {task.status}"
            )

        automation_name = name or f"Recurring: {task.goal[:50]}..."
        next_run = _next_run_utc_naive(schedule_cron, schedule_timezone)

        new_auto = Automation(
            id=uuid.uuid4(),
            name=automation_name,
            task_id=task_uuid,
            owner_id=user_id,
            organization_id=task.organization_id,
            cron=schedule_cron,
            timezone=schedule_timezone,
            enabled=True,
            next_run_at=next_run,
        )

        new_auto = await self.repository.create_automation(new_auto)
        return await self.get_automation(user_id, str(new_auto.id))

    async def _get_automation_stats(
        self,
        automation_id: str,
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        tasks = await self.repository.get_tasks_for_automation(automation_id, limit=20)

        if not tasks:
            stats = {
                "total_runs": 0,
                "successful_runs": 0,
                "failed_runs": 0,
                "success_rate": 0.0,
                "avg_duration_seconds": None,
            }
            return stats, None, []

        total = len(tasks)
        successful = sum(1 for t in tasks if t.status == "completed")
        failed = sum(1 for t in tasks if t.status == "failed")

        durations = [
            _calculate_duration(t.created_at, t.completed_at)
            for t in tasks
            if t.completed_at
        ]
        avg_duration = sum(d for d in durations if d) / len(durations) if durations else None

        stats = {
            "total_runs": total,
            "successful_runs": successful,
            "failed_runs": failed,
            "success_rate": successful / total if total > 0 else 0.0,
            "avg_duration_seconds": avg_duration,
        }

        executions = [_task_to_execution_summary(t) for t in tasks]
        last_execution = executions[0] if executions else None

        return stats, last_execution, executions[:10]

    def _parse_uuid(self, value: str) -> uuid.UUID:
        try:
            return uuid.UUID(value)
        except ValueError as exc:
            raise AutomationValidationError("Invalid ID format") from exc
