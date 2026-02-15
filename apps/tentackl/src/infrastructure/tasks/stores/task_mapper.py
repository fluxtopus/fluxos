"""Shared task-domain mapping helpers for task stores."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, Mapping, Optional

from src.domain.tasks.models import Finding, StepStatus, Task, TaskStatus, TaskStep


def parse_task_status(value: Any) -> TaskStatus:
    """Normalize storage/runtime task status to domain enum."""
    if isinstance(value, TaskStatus):
        return value
    if hasattr(value, "value"):
        return TaskStatus(value.value)
    return TaskStatus(str(value))


def serialize_task_status(value: Any) -> str:
    """Normalize domain/runtime status to persisted string value."""
    if isinstance(value, TaskStatus):
        return value.value
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def parse_step_status(value: Any) -> StepStatus:
    """Normalize storage/runtime step status to domain enum."""
    if isinstance(value, StepStatus):
        return value
    if hasattr(value, "value"):
        return StepStatus(value.value)
    return StepStatus(str(value))


def _step_from_any(item: Any) -> TaskStep:
    if isinstance(item, TaskStep):
        return item
    if isinstance(item, Mapping):
        payload = dict(item)
        if "status" in payload:
            payload["status"] = parse_step_status(payload["status"]).value
        return TaskStep.from_dict(payload)
    raise ValueError(f"Unsupported step payload type: {type(item)!r}")


def _finding_from_any(item: Any) -> Finding:
    if isinstance(item, Finding):
        return item
    if isinstance(item, Mapping):
        return Finding.from_dict(dict(item))
    raise ValueError(f"Unsupported finding payload type: {type(item)!r}")


def steps_from_storage(items: Optional[Iterable[Any]]) -> list[TaskStep]:
    """Deserialize persisted steps into domain steps."""
    return [_step_from_any(item) for item in (items or [])]


def findings_from_storage(items: Optional[Iterable[Any]]) -> list[Finding]:
    """Deserialize persisted findings into domain findings."""
    return [_finding_from_any(item) for item in (items or [])]


def steps_to_storage(items: Optional[Iterable[Any]]) -> list[Dict[str, Any]]:
    """Serialize domain/runtime step values to persisted dictionaries."""
    return [_step_from_any(item).to_dict() for item in (items or [])]


def findings_to_storage(items: Optional[Iterable[Any]]) -> list[Dict[str, Any]]:
    """Serialize domain/runtime finding values to persisted dictionaries."""
    return [_finding_from_any(item).to_dict() for item in (items or [])]


def to_uuid(value: Any) -> Optional[uuid.UUID]:
    """Convert string or UUID-like values to UUID for model persistence."""
    if value in (None, ""):
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def normalize_task_updates(updates: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Normalize partial task updates to storage-ready field/value pairs.

    Returned keys use SQL model attribute names when they differ from domain.
    """
    normalized: Dict[str, Any] = {}
    for key, value in updates.items():
        if key == "status":
            normalized["status"] = serialize_task_status(value)
        elif key == "steps":
            normalized["steps"] = steps_to_storage(value)
        elif key == "accumulated_findings":
            normalized["accumulated_findings"] = findings_to_storage(value)
        elif key == "metadata":
            normalized["extra_metadata"] = value
        elif key == "parent_task_id":
            normalized["parent_task_id"] = to_uuid(value)
        elif key == "completed_at" and isinstance(value, str):
            normalized["completed_at"] = datetime.fromisoformat(value)
        else:
            normalized[key] = value
    return normalized


def task_from_model(model: Any) -> Task:
    """Create a domain task from a SQLAlchemy task row."""
    return Task(
        id=str(model.id),
        version=model.version,
        user_id=model.user_id,
        organization_id=model.organization_id,
        goal=model.goal,
        constraints=model.constraints or {},
        success_criteria=model.success_criteria or [],
        steps=steps_from_storage(model.steps),
        accumulated_findings=findings_from_storage(model.accumulated_findings),
        current_step_index=model.current_step_index,
        status=parse_task_status(model.status),
        tree_id=model.tree_id,
        parent_task_id=str(model.parent_task_id) if model.parent_task_id else None,
        metadata=model.extra_metadata or {},
        created_at=model.created_at,
        updated_at=model.updated_at,
        completed_at=model.completed_at,
    )


def model_payload_from_task(task: Task) -> Dict[str, Any]:
    """Create SQLAlchemy task model payload from a domain task."""
    return {
        "id": to_uuid(task.id),
        "user_id": task.user_id,
        "organization_id": task.organization_id,
        "goal": task.goal,
        "constraints": task.constraints,
        "success_criteria": task.success_criteria,
        "steps": steps_to_storage(task.steps),
        "accumulated_findings": findings_to_storage(task.accumulated_findings),
        "current_step_index": task.current_step_index,
        "status": serialize_task_status(task.status),
        "tree_id": task.tree_id,
        "parent_task_id": to_uuid(task.parent_task_id),
        "version": task.version,
        "extra_metadata": task.metadata,
        "source": task.metadata.get("source", "api"),
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "completed_at": task.completed_at,
    }

