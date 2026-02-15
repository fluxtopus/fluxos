"""Domain models for task planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import structlog


logger = structlog.get_logger(__name__)


class IntentType(str, Enum):
    """Types of user intent detected by IntentExtractorAgent."""

    DATA_RETRIEVAL = "data_retrieval"
    WORKFLOW = "workflow"
    SCHEDULING = "scheduling"


@dataclass
class ScheduleSpec:
    """Normalized schedule specification."""

    cron: Optional[str] = None
    timezone: str = "UTC"
    execute_at: Optional[datetime] = None
    execute_at_raw: Optional[str] = None


@dataclass
class PlanningIntent:
    """Structured intent extracted from a goal."""

    intent_type: str = IntentType.WORKFLOW.value
    has_schedule: bool = False
    schedule: Optional[ScheduleSpec] = None
    data_query: Optional[Dict[str, Any]] = None
    workflow_steps: List[str] = field(default_factory=list)
    rephrased_intent: Optional[str] = None
    one_shot_goal: Optional[str] = None

    @classmethod
    def from_intent_dict(cls, intent: Optional[Dict[str, Any]]) -> Optional["PlanningIntent"]:
        if not intent:
            return None

        schedule_spec = None
        schedule = intent.get("schedule") or {}
        if schedule:
            execute_at = schedule.get("execute_at")
            schedule_spec = ScheduleSpec(
                cron=schedule.get("cron"),
                timezone=schedule.get("timezone", "UTC"),
                execute_at=execute_at if isinstance(execute_at, datetime) else None,
                execute_at_raw=execute_at if isinstance(execute_at, str) else None,
            )

        return cls(
            intent_type=intent.get("intent_type", IntentType.WORKFLOW.value),
            has_schedule=bool(intent.get("has_schedule", False)),
            schedule=schedule_spec,
            data_query=intent.get("data_query"),
            workflow_steps=intent.get("workflow_steps") or [],
            rephrased_intent=intent.get("rephrased_intent"),
            one_shot_goal=intent.get("one_shot_goal"),
        )

    def to_dict(self) -> Dict[str, Any]:
        schedule_dict = None
        if self.schedule:
            schedule_dict = {
                "cron": self.schedule.cron,
                "timezone": self.schedule.timezone,
                "execute_at": (
                    self.schedule.execute_at.isoformat()
                    if self.schedule.execute_at
                    else self.schedule.execute_at_raw
                ),
            }
        return {
            "intent_type": self.intent_type,
            "has_schedule": self.has_schedule,
            "schedule": schedule_dict,
            "data_query": self.data_query,
            "workflow_steps": self.workflow_steps,
            "rephrased_intent": self.rephrased_intent,
            "one_shot_goal": self.one_shot_goal,
        }


@dataclass
class DataQuery:
    """Structured query parameters extracted from natural language."""

    object_type: str
    date_range: Optional[Dict[str, str]] = None
    search_text: Optional[str] = None
    where: Optional[Dict[str, Any]] = None
    limit: int = 100
    order_by: Optional[str] = None
    order_desc: bool = True

    @classmethod
    def from_intent(cls, data_query: Optional[Dict[str, Any]]) -> Optional["DataQuery"]:
        if not data_query:
            return None

        if not data_query.get("object_type"):
            logger.warning("DataQuery missing object_type", data_query=data_query)
            return None

        return cls(
            object_type=data_query["object_type"],
            date_range=data_query.get("date_range"),
            search_text=data_query.get("search_text"),
            where=data_query.get("where"),
            limit=data_query.get("limit", 100),
            order_by=data_query.get("order_by"),
        )

    def build_where_clause(self) -> Optional[Dict[str, Any]]:
        where = self.where.copy() if self.where else {}

        if self.date_range:
            start = self.date_range.get("start")
            end = self.date_range.get("end")

            if start and end:
                time_field = "start" if self.object_type == "event" else "created_at"
                where[time_field] = {"$gte": start, "$lte": end}

        return where if where else None


@dataclass
class FastPathResult:
    """Result of a fast path data retrieval query."""

    success: bool
    data: List[Dict[str, Any]] = field(default_factory=list)
    total_count: int = 0
    query_time_ms: int = 0
    intent_time_ms: int = 0
    object_type: Optional[str] = None
    error: Optional[str] = None

    @property
    def total_time_ms(self) -> int:
        return self.intent_time_ms + self.query_time_ms

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "total_count": self.total_count,
            "query_time_ms": self.query_time_ms,
            "intent_time_ms": self.intent_time_ms,
            "total_time_ms": self.total_time_ms,
            "object_type": self.object_type,
            "error": self.error,
        }


def is_fast_path_eligible(intent_info: Optional[Union[PlanningIntent, Dict[str, Any]]]) -> bool:
    """Check if an intent is eligible for fast path processing."""
    if not intent_info:
        return False

    if isinstance(intent_info, PlanningIntent):
        intent_type = intent_info.intent_type
        data_query = intent_info.data_query
        workflow_steps = intent_info.workflow_steps
    else:
        intent_type = intent_info.get("intent_type")
        data_query = intent_info.get("data_query")
        workflow_steps = intent_info.get("workflow_steps", [])

    if intent_type != IntentType.DATA_RETRIEVAL.value:
        return False

    if not data_query:
        return False

    if not data_query.get("object_type"):
        return False

    complex_verbs = ["summarize", "analyze", "compare", "create", "research", "generate"]
    for step in workflow_steps or []:
        for verb in complex_verbs:
            if verb in step.lower():
                logger.debug(
                    "Fast path rejected due to complex verb in workflow_steps",
                    step=step,
                    verb=verb,
                )
                return False

    logger.debug(
        "Fast path eligible",
        intent_type=intent_type,
        object_type=data_query.get("object_type"),
    )
    return True


def compute_date_range(
    date_description: Optional[str] = None,
    reference_date: Optional[date] = None,
) -> Optional[Dict[str, str]]:
    """Compute ISO8601 date range from natural language description."""
    if not date_description:
        return None

    ref = reference_date or date.today()
    description = date_description.lower().strip()

    if description in ("today", "now"):
        start = datetime.combine(ref, datetime.min.time())
        end = datetime.combine(ref, datetime.max.time())
    elif description == "yesterday":
        yesterday = ref - timedelta(days=1)
        start = datetime.combine(yesterday, datetime.min.time())
        end = datetime.combine(yesterday, datetime.max.time())
    elif description == "tomorrow":
        tomorrow = ref + timedelta(days=1)
        start = datetime.combine(tomorrow, datetime.min.time())
        end = datetime.combine(tomorrow, datetime.max.time())
    elif description in ("this week", "week"):
        start_of_week = ref - timedelta(days=ref.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        start = datetime.combine(start_of_week, datetime.min.time())
        end = datetime.combine(end_of_week, datetime.max.time())
    elif description in ("last week", "past week"):
        end_of_last_week = ref - timedelta(days=ref.weekday() + 1)
        start_of_last_week = end_of_last_week - timedelta(days=6)
        start = datetime.combine(start_of_last_week, datetime.min.time())
        end = datetime.combine(end_of_last_week, datetime.max.time())
    elif description in ("this month", "month"):
        start = datetime(ref.year, ref.month, 1)
        if ref.month == 12:
            end = datetime(ref.year + 1, 1, 1) - timedelta(seconds=1)
        else:
            end = datetime(ref.year, ref.month + 1, 1) - timedelta(seconds=1)
    else:
        return None

    return {"start": start.isoformat() + "Z", "end": end.isoformat() + "Z"}
