# REVIEW: Eventing is tightly coupled to Redis pub/sub + streams with a
# REVIEW: bespoke schema (no versioning). There is little error handling
# REVIEW: or backpressure control, and publish side-effects are embedded in
# REVIEW: this module. Consider abstracting an event bus interface and
# REVIEW: formalizing event schemas/versions to avoid breaking SSE consumers.
"""
Task Event Publisher

Publishes task-specific events to Redis pub/sub for real-time
observation by SSE endpoints. This separates event publishing from
execution logic, enabling a clean event-driven architecture.

Usage:
    publisher = TaskEventPublisher(redis_url)
    await publisher.task_started(task_id, goal="Research AI trends", step_count=5)
    await publisher.step_completed(task_id, step_id, output={...})
"""

import json
import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List

import redis.asyncio as redis

from src.core.config import settings

logger = logging.getLogger(__name__)


class TaskEventType(str, Enum):
    """Task-specific event types."""

    # Task lifecycle
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_PAUSED = "task.paused"
    TASK_CANCELLED = "task.cancelled"

    # Step lifecycle
    STEP_ENQUEUED = "task.step.enqueued"
    STEP_STARTED = "task.step.started"
    STEP_COMPLETED = "task.step.completed"
    STEP_FAILED = "task.step.failed"
    STEP_SKIPPED = "task.step.skipped"

    # Checkpoints
    CHECKPOINT_CREATED = "task.checkpoint.created"
    CHECKPOINT_AUTO_APPROVED = "task.checkpoint.auto_approved"
    CHECKPOINT_APPROVED = "task.checkpoint.approved"
    CHECKPOINT_REJECTED = "task.checkpoint.rejected"

    # Observer actions
    OBSERVER_RECOVERY = "task.observer.recovery"
    OBSERVER_REPLAN = "task.observer.replan"

    # Planning lifecycle
    PLANNING_STARTED = "task.planning.started"
    PLANNING_INTENT_DETECTED = "task.planning.intent_detected"
    PLANNING_FAST_PATH = "task.planning.fast_path"
    PLANNING_SPEC_MATCH = "task.planning.spec_match"
    PLANNING_LLM_STARTED = "task.planning.llm_started"
    PLANNING_LLM_RETRY = "task.planning.llm_retry"
    PLANNING_STEPS_GENERATED = "task.planning.steps_generated"
    PLANNING_RISK_DETECTION = "task.planning.risk_detection"
    PLANNING_COMPLETED = "task.planning.completed"
    PLANNING_FAILED = "task.planning.failed"

    # Progress
    PROGRESS_UPDATE = "task.progress.update"

    # Inbox
    INBOX_MESSAGE_CREATED = "inbox.message.created"
    INBOX_STATUS_UPDATED = "inbox.status.updated"


class TaskEvent:
    """A task event to be published."""

    def __init__(
        self,
        event_type: TaskEventType,
        task_id: str,
        data: Dict[str, Any],
        step_id: Optional[str] = None,
    ):
        self.id = str(uuid.uuid4())
        self.event_type = event_type
        self.task_id = task_id
        self.step_id = step_id
        self.data = data
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize event for Redis pub/sub."""
        return {
            "id": self.id,
            "type": self.event_type.value,
            "task_id": self.task_id,
            "step_id": self.step_id,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


class TaskEventPublisher:
    """
    Publishes task events to Redis pub/sub.

    Events are published to a channel specific to each task, allowing
    SSE endpoints to subscribe and forward events to clients.

    Channel format: task:{task_id}
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        key_prefix: str = "tentackl:task",
    ):
        self.redis_url = redis_url or settings.REDIS_URL
        self.key_prefix = key_prefix
        self._redis_client: Optional[redis.Redis] = None

    async def _ensure_connection(self):
        """Ensure Redis connection is established."""
        if not self._redis_client:
            self._redis_client = await redis.from_url(
                self.redis_url,
                decode_responses=True,
            )

    async def close(self):
        """Close the Redis connection."""
        if self._redis_client:
            await self._redis_client.aclose()
            self._redis_client = None

    async def publish(
        self,
        event_type: TaskEventType,
        task_id: str,
        data: Dict[str, Any],
        step_id: Optional[str] = None,
    ) -> str:
        """
        Publish an event to the task's channel.

        Args:
            event_type: Type of task event
            task_id: ID of the task
            data: Event payload
            step_id: Optional step ID if event is step-specific

        Returns:
            str: Event ID
        """
        await self._ensure_connection()

        event = TaskEvent(
            event_type=event_type,
            task_id=task_id,
            step_id=step_id,
            data=data,
        )

        # Publish to task-specific channel
        channel = f"{self.key_prefix}:events:{task_id}"
        await self._redis_client.publish(channel, json.dumps(event.to_dict()))

        # Also store in a stream for late joiners
        stream_key = f"{self.key_prefix}:stream:{task_id}"
        await self._redis_client.xadd(
            stream_key,
            {"event": json.dumps(event.to_dict())},
            maxlen=1000,  # Keep last 1000 events per task
        )

        logger.debug(
            f"Published {event_type.value} for task {task_id}",
            extra={"event_id": event.id, "step_id": step_id},
        )

        return event.id

    # =========================================================================
    # Convenience Methods - Task Lifecycle
    # =========================================================================

    async def task_started(
        self,
        task_id: str,
        goal: str,
        step_count: int,
        user_id: str,
    ) -> str:
        """Publish task started event."""
        return await self.publish(
            TaskEventType.TASK_STARTED,
            task_id,
            {
                "goal": goal,
                "step_count": step_count,
                "user_id": user_id,
            },
        )

    async def task_completed(
        self,
        task_id: str,
        steps_completed: int,
        findings: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Publish task completed event."""
        return await self.publish(
            TaskEventType.TASK_COMPLETED,
            task_id,
            {
                "steps_completed": steps_completed,
                "findings": findings or [],
            },
        )

    async def task_failed(
        self,
        task_id: str,
        error: str,
        step_id: Optional[str] = None,
    ) -> str:
        """Publish task failed event."""
        return await self.publish(
            TaskEventType.TASK_FAILED,
            task_id,
            {"error": error},
            step_id=step_id,
        )

    # =========================================================================
    # Convenience Methods - Step Lifecycle
    # =========================================================================

    async def step_enqueued(
        self,
        task_id: str,
        step_id: str,
        step_name: str,
        agent_type: str,
    ) -> str:
        """Publish step enqueued event."""
        return await self.publish(
            TaskEventType.STEP_ENQUEUED,
            task_id,
            {
                "step_name": step_name,
                "agent_type": agent_type,
            },
            step_id=step_id,
        )

    async def step_started(
        self,
        task_id: str,
        step_id: str,
        step_name: str,
    ) -> str:
        """Publish step started event."""
        return await self.publish(
            TaskEventType.STEP_STARTED,
            task_id,
            {"step_name": step_name},
            step_id=step_id,
        )

    async def step_completed(
        self,
        task_id: str,
        step_id: str,
        step_name: str,
        output: Dict[str, Any],
        object_type: Optional[str] = None,
    ) -> str:
        """Publish step completed event."""
        data = {
            "step_name": step_name,
            "output": output,
        }
        if object_type:
            data["object_type"] = object_type
        return await self.publish(
            TaskEventType.STEP_COMPLETED,
            task_id,
            data,
            step_id=step_id,
        )

    async def step_failed(
        self,
        task_id: str,
        step_id: str,
        step_name: str,
        error: str,
    ) -> str:
        """Publish step failed event."""
        return await self.publish(
            TaskEventType.STEP_FAILED,
            task_id,
            {
                "step_name": step_name,
                "error": error,
            },
            step_id=step_id,
        )

    # =========================================================================
    # Convenience Methods - Checkpoints
    # =========================================================================

    async def checkpoint_created(
        self,
        task_id: str,
        step_id: str,
        checkpoint_name: str,
        preview: Optional[Dict[str, Any]] = None,
        risk_level: Optional[str] = None,
    ) -> str:
        """Publish checkpoint created event."""
        return await self.publish(
            TaskEventType.CHECKPOINT_CREATED,
            task_id,
            {
                "checkpoint_name": checkpoint_name,
                "preview": preview,
                "risk_level": risk_level,
            },
            step_id=step_id,
        )

    async def checkpoint_auto_approved(
        self,
        task_id: str,
        step_id: str,
        checkpoint_name: str,
        preference_id: Optional[str] = None,
    ) -> str:
        """Publish checkpoint auto-approved event."""
        return await self.publish(
            TaskEventType.CHECKPOINT_AUTO_APPROVED,
            task_id,
            {
                "checkpoint_name": checkpoint_name,
                "preference_id": preference_id,
                "message": "Checkpoint auto-approved based on your preferences",
            },
            step_id=step_id,
        )

    async def checkpoint_approved(
        self,
        task_id: str,
        step_id: str,
        checkpoint_name: str,
        feedback: Optional[str] = None,
    ) -> str:
        """Publish checkpoint approved event."""
        return await self.publish(
            TaskEventType.CHECKPOINT_APPROVED,
            task_id,
            {
                "checkpoint_name": checkpoint_name,
                "feedback": feedback,
            },
            step_id=step_id,
        )

    async def checkpoint_rejected(
        self,
        task_id: str,
        step_id: str,
        checkpoint_name: str,
        reason: str,
    ) -> str:
        """Publish checkpoint rejected event."""
        return await self.publish(
            TaskEventType.CHECKPOINT_REJECTED,
            task_id,
            {
                "checkpoint_name": checkpoint_name,
                "reason": reason,
            },
            step_id=step_id,
        )

    # =========================================================================
    # Convenience Methods - Progress
    # =========================================================================

    async def progress_update(
        self,
        task_id: str,
        steps_completed: int,
        steps_total: int,
        current_step: Optional[str] = None,
    ) -> str:
        """Publish progress update event."""
        return await self.publish(
            TaskEventType.PROGRESS_UPDATE,
            task_id,
            {
                "steps_completed": steps_completed,
                "steps_total": steps_total,
                "current_step": current_step,
                "percent": round((steps_completed / steps_total) * 100)
                if steps_total > 0
                else 0,
            },
        )

    # =========================================================================
    # Convenience Methods - Planning Lifecycle
    # =========================================================================

    async def planning_started(self, task_id: str, goal: str) -> str:
        """Publish planning started event."""
        return await self.publish(
            TaskEventType.PLANNING_STARTED,
            task_id,
            {"goal": goal},
        )

    async def planning_intent_detected(
        self, task_id: str, intent_type: str, detail: str
    ) -> str:
        """Publish planning intent detected event."""
        return await self.publish(
            TaskEventType.PLANNING_INTENT_DETECTED,
            task_id,
            {"intent_type": intent_type, "detail": detail},
        )

    async def planning_fast_path(self, task_id: str, message: str) -> str:
        """Publish fast path data retrieval event."""
        return await self.publish(
            TaskEventType.PLANNING_FAST_PATH,
            task_id,
            {"message": message},
        )

    async def planning_spec_match(
        self, task_id: str, spec_id: str, confidence: float
    ) -> str:
        """Publish spec match event."""
        return await self.publish(
            TaskEventType.PLANNING_SPEC_MATCH,
            task_id,
            {"spec_id": spec_id, "confidence": confidence},
        )

    async def planning_llm_started(self, task_id: str) -> str:
        """Publish LLM planning started event."""
        return await self.publish(
            TaskEventType.PLANNING_LLM_STARTED,
            task_id,
            {},
        )

    async def planning_llm_retry(
        self, task_id: str, attempt: int, max_retries: int, reason: str
    ) -> str:
        """Publish LLM planning retry event."""
        return await self.publish(
            TaskEventType.PLANNING_LLM_RETRY,
            task_id,
            {"attempt": attempt, "max_retries": max_retries, "reason": reason},
        )

    async def planning_steps_generated(
        self, task_id: str, step_count: int, step_names: List[str]
    ) -> str:
        """Publish steps generated event."""
        return await self.publish(
            TaskEventType.PLANNING_STEPS_GENERATED,
            task_id,
            {"step_count": step_count, "step_names": step_names},
        )

    async def planning_risk_detection(
        self, task_id: str, checkpoints_added: int
    ) -> str:
        """Publish risk detection event."""
        return await self.publish(
            TaskEventType.PLANNING_RISK_DETECTION,
            task_id,
            {"checkpoints_added": checkpoints_added},
        )

    async def planning_completed(
        self, task_id: str, step_count: int, path: str
    ) -> str:
        """Publish planning completed event."""
        return await self.publish(
            TaskEventType.PLANNING_COMPLETED,
            task_id,
            {"step_count": step_count, "path": path},
        )

    async def planning_failed(self, task_id: str, error: str) -> str:
        """Publish planning failed event."""
        return await self.publish(
            TaskEventType.PLANNING_FAILED,
            task_id,
            {"error": error},
        )

    # =========================================================================
    # Convenience Methods - Inbox Events
    # =========================================================================

    async def inbox_message_created(
        self,
        user_id: str,
        conversation_id: str,
        message_preview: str,
        priority: str,
    ) -> str:
        """
        Publish an inbox message created event to the user's inbox channel.

        Publishes to tentackl:inbox:events:{user_id} so each user gets
        their own inbox event stream.

        Args:
            user_id: The user who owns the inbox item
            conversation_id: The conversation that received a new message
            message_preview: First 200 chars of the message content
            priority: 'normal' or 'attention'

        Returns:
            str: Event ID
        """
        await self._ensure_connection()

        event = TaskEvent(
            event_type=TaskEventType.INBOX_MESSAGE_CREATED,
            task_id="",  # Not task-specific
            data={
                "conversation_id": conversation_id,
                "message_preview": message_preview[:200],
                "priority": priority,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        channel = f"tentackl:inbox:events:{user_id}"
        await self._redis_client.publish(channel, json.dumps(event.to_dict()))

        logger.debug(
            f"Published inbox.message.created for user {user_id}",
            extra={"event_id": event.id, "conversation_id": conversation_id},
        )

        return event.id

    async def inbox_status_updated(
        self,
        user_id: str,
        conversation_id: str,
        new_status: str,
    ) -> str:
        """
        Publish an inbox status updated event to the user's inbox channel.

        Publishes to tentackl:inbox:events:{user_id}.

        Args:
            user_id: The user who owns the inbox item
            conversation_id: The conversation whose status changed
            new_status: The new read status ('unread', 'read', 'archived')

        Returns:
            str: Event ID
        """
        await self._ensure_connection()

        event = TaskEvent(
            event_type=TaskEventType.INBOX_STATUS_UPDATED,
            task_id="",  # Not task-specific
            data={
                "conversation_id": conversation_id,
                "new_status": new_status,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        channel = f"tentackl:inbox:events:{user_id}"
        await self._redis_client.publish(channel, json.dumps(event.to_dict()))

        logger.debug(
            f"Published inbox.status.updated for user {user_id}",
            extra={"event_id": event.id, "conversation_id": conversation_id},
        )

        return event.id

    def get_inbox_channel(self, user_id: str) -> str:
        """Get the Redis pub/sub channel name for a user's inbox events."""
        return f"tentackl:inbox:events:{user_id}"

    # =========================================================================
    # Subscription Helpers
    # =========================================================================

    async def get_channel(self, task_id: str) -> str:
        """Get the channel name for a task."""
        return f"{self.key_prefix}:events:{task_id}"

    async def get_recent_events(
        self,
        task_id: str,
        count: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get recent events for a task from the stream.

        Useful for catching up on events when joining an in-progress execution.
        """
        await self._ensure_connection()

        stream_key = f"{self.key_prefix}:stream:{task_id}"
        entries = await self._redis_client.xrevrange(
            stream_key,
            count=count,
        )

        events = []
        for _entry_id, data in reversed(entries):
            try:
                event = json.loads(data.get("event", "{}"))
                events.append(event)
            except json.JSONDecodeError:
                continue

        return events


# Singleton for easy import
_publisher: Optional[TaskEventPublisher] = None


def get_task_event_publisher() -> TaskEventPublisher:
    """Get the singleton TaskEventPublisher instance."""
    global _publisher
    if _publisher is None:
        _publisher = TaskEventPublisher()
    return _publisher

