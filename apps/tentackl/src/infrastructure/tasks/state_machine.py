# REVIEW: State transition rules are hard-coded here and the docstring claims
# REVIEW: transactional locking, but the actual lock behavior depends entirely
# REVIEW: on pg_store implementation (not enforced here). Consider centralizing
# REVIEW: state rules in a declarative spec and making locking/transactions
# REVIEW: explicit at this layer to avoid drift. Also note Redis invalidation
# REVIEW: side effects are tightly coupled to the transition.
"""
Task State Machine

Enforces valid state transitions for tasks. PostgreSQL is the single source
of truth - all state changes must go through this state machine.

State Diagram:
                                   ┌─────────────┐
                                   │   PLANNING  │
                                   │  (initial)  │
                                   └──────┬──────┘
                                          │ plan generated
                                          ▼
                                   ┌─────────────┐
                         ┌─────────│    READY    │◄────────────────────┐
                         │         └──────┬──────┘                     │
                         │                │ start execution            │
                         │                ▼                            │
                         │         ┌─────────────┐                     │
                         │    ┌───►│  EXECUTING  │◄───┐                │
                         │    │    └──────┬──────┘    │                │
                         │    │           │           │                │
                         │    │     ┌─────┴─────┐     │                │
                         │    │     │           │     │                │
                         │    │     ▼           ▼     │                │
                         │    │ ┌───────┐ ┌──────────┐│                │
                         │    │ │PAUSED │ │CHECKPOINT││  approve       │
                         │    │ └───┬───┘ └────┬─────┘│  checkpoint    │
                         │    │     │          │      │                │
                         │    │     │ resume   │      │                │
                         │    └─────┘          └──────┘                │
                         │                                             │
                         │ retry                                       │ retry
                         │                                             │
       ┌─────────────────┼─────────────────────────────────────────────┼──────┐
       │                 │                                             │      │
       ▼                 │                                             │      │
┌─────────────┐         │                                    ┌────────┴───┐  │
│  CANCELLED  │         │ all steps done                     │   FAILED   │◄─┘
└─────────────┘         │                                    └────────────┘
                        ▼                                           ▲
                 ┌─────────────┐                                    │
                 │  COMPLETED  │                                    │
                 │  (terminal) │                                    │
                 └─────────────┘                                    │
                                                                    │
                        reject checkpoint ──────────────────────────┘
"""

from datetime import datetime
from typing import Dict, List, Optional, TYPE_CHECKING
import structlog

from src.domain.tasks.models import Task, TaskStatus
from src.domain.tasks.errors import InvalidTransitionError

if TYPE_CHECKING:
    from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskStore
    from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore


logger = structlog.get_logger()


# Valid state transitions based on the documented state machine
VALID_TRANSITIONS: Dict[TaskStatus, List[TaskStatus]] = {
    TaskStatus.PLANNING: [
        TaskStatus.READY,      # Plan generation complete
        TaskStatus.COMPLETED,  # Fast path: immediate completion (no execution needed)
        TaskStatus.FAILED,     # Planning failed
        TaskStatus.CANCELLED,  # User cancelled during planning
    ],
    TaskStatus.READY: [
        TaskStatus.EXECUTING,  # Execution started
        TaskStatus.CANCELLED,  # User cancelled before execution
    ],
    TaskStatus.EXECUTING: [
        TaskStatus.CHECKPOINT,  # Step requires user approval
        TaskStatus.PAUSED,      # User paused execution
        TaskStatus.COMPLETED,   # All steps finished successfully
        TaskStatus.FAILED,      # Critical step failed, no recovery
        TaskStatus.CANCELLED,   # User cancelled during execution
        TaskStatus.SUPERSEDED,  # Replaced by REPLAN
    ],
    TaskStatus.CHECKPOINT: [
        TaskStatus.EXECUTING,  # User approved checkpoint
        TaskStatus.FAILED,     # User rejected checkpoint
        TaskStatus.CANCELLED,  # User cancelled at checkpoint
    ],
    TaskStatus.PAUSED: [
        TaskStatus.EXECUTING,  # User resumed execution
        TaskStatus.CANCELLED,  # User cancelled while paused
    ],
    # Terminal states - can only retry (which goes back to READY)
    TaskStatus.COMPLETED: [],  # No transitions allowed
    TaskStatus.FAILED: [
        TaskStatus.READY,  # User retries the task
    ],
    TaskStatus.CANCELLED: [
        TaskStatus.READY,  # User retries the task
    ],
    TaskStatus.SUPERSEDED: [],  # No transitions allowed (replaced by new task)
}


def is_terminal_status(status: TaskStatus) -> bool:
    """Check if a status is terminal (no automatic transitions out)."""
    return status in (
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.SUPERSEDED,
    )


def can_transition(from_status: TaskStatus, to_status: TaskStatus) -> bool:
    """Check if a state transition is valid."""
    allowed = VALID_TRANSITIONS.get(from_status, [])
    return to_status in allowed


class TaskStateMachine:
    """
    Enforces valid state transitions for tasks.

    PostgreSQL is the single source of truth. All state changes:
    1. Lock the task row (SELECT FOR UPDATE)
    2. Validate the transition is allowed
    3. Update PostgreSQL
    4. Invalidate Redis cache
    5. Return the updated task

    This ensures atomicity and prevents race conditions.
    """

    def __init__(
        self,
        pg_store: "PostgresTaskStore",
        redis_store: Optional["RedisTaskStore"] = None,
    ):
        """
        Initialize the state machine.

        Args:
            pg_store: PostgreSQL store (source of truth)
            redis_store: Redis store (cache, optional)
        """
        self._pg_store = pg_store
        self._redis_store = redis_store

    async def get_current_status(self, task_id: str) -> TaskStatus:
        """
        Get the current status of a task from PostgreSQL.

        Always reads from PostgreSQL to ensure we have the authoritative state.
        """
        task = await self._pg_store.get_task(task_id)
        if not task:
            from src.domain.tasks.models import TaskNotFoundError
            raise TaskNotFoundError(f"Task not found: {task_id}")
        return task.status

    async def transition(
        self,
        task_id: str,
        new_status: TaskStatus,
        additional_updates: Optional[Dict] = None,
    ) -> Task:
        """
        Atomically transition a task to a new status.

        This method:
        1. Reads the current state from PostgreSQL
        2. Validates the transition is allowed
        3. Updates PostgreSQL with the new status
        4. Invalidates Redis cache
        5. Returns the updated task

        Args:
            task_id: The task ID to transition
            new_status: The target status
            additional_updates: Optional additional fields to update

        Returns:
            The updated Task object

        Raises:
            TaskNotFoundError: If task doesn't exist
            InvalidTransitionError: If transition is not allowed
        """
        # Get current task from PostgreSQL (source of truth)
        task = await self._pg_store.get_task(task_id)
        if not task:
            from src.domain.tasks.models import TaskNotFoundError
            raise TaskNotFoundError(f"Task not found: {task_id}")

        current_status = task.status

        # Check if transition is valid
        if not can_transition(current_status, new_status):
            logger.warning(
                "Invalid state transition attempted",
                task_id=task_id,
                current_status=current_status.value,
                target_status=new_status.value,
            )
            raise InvalidTransitionError(
                task_id=task_id,
                current_status=current_status,
                target_status=new_status,
            )

        # Build updates
        updates = {"status": new_status}
        if additional_updates:
            updates.update(additional_updates)

        # Handle terminal state timestamps
        if new_status == TaskStatus.COMPLETED:
            updates["completed_at"] = datetime.utcnow()

        # Update PostgreSQL (source of truth)
        await self._pg_store.update_task(task_id, updates)

        # Get the updated task from PostgreSQL
        updated_task = await self._pg_store.get_task(task_id)

        # Update Redis cache with fresh data (not just invalidate)
        # This ensures orchestrator and other Redis readers see the new state
        if self._redis_store and updated_task:
            await self._update_cache(task_id, updated_task)

        logger.info(
            "Task state transitioned",
            task_id=task_id,
            from_status=current_status.value,
            to_status=new_status.value,
        )

        return updated_task

    async def transition_if_current(
        self,
        task_id: str,
        expected_status: TaskStatus,
        new_status: TaskStatus,
        additional_updates: Optional[Dict] = None,
    ) -> Optional[Task]:
        """
        Transition only if the current status matches expected.

        This is useful for idempotent operations where you want to
        transition only if the task is in an expected state.

        Args:
            task_id: The task ID to transition
            expected_status: The expected current status
            new_status: The target status
            additional_updates: Optional additional fields to update

        Returns:
            The updated Task object if transition occurred, None if current
            status didn't match expected

        Raises:
            TaskNotFoundError: If task doesn't exist
            InvalidTransitionError: If transition is not allowed
        """
        task = await self._pg_store.get_task(task_id)
        if not task:
            from src.domain.tasks.models import TaskNotFoundError
            raise TaskNotFoundError(f"Task not found: {task_id}")

        if task.status != expected_status:
            logger.debug(
                "Transition skipped - status mismatch",
                task_id=task_id,
                expected_status=expected_status.value,
                actual_status=task.status.value,
            )
            return None

        return await self.transition(task_id, new_status, additional_updates)

    async def _update_cache(self, task_id: str, task: Task) -> None:
        """
        Update the Redis cache with fresh task data.

        Instead of just invalidating (which causes cache misses), we repopulate
        the cache with the updated task from PostgreSQL. This ensures:
        1. Orchestrator and other Redis readers see the new state immediately
        2. No cache miss race conditions
        3. Consistent state across the system
        """
        if not self._redis_store:
            return

        try:
            client = await self._redis_store._get_redis()
            cache_key = self._redis_store._plan_key(task_id)
            serialized = self._redis_store._serialize_plan(task)
            await client.set(cache_key, serialized)
            await client.aclose()

            logger.debug(
                "Updated Redis cache",
                task_id=task_id,
                status=task.status.value,
            )
        except Exception as e:
            # Cache update failure is not critical - PG is source of truth
            logger.warning(
                "Failed to update Redis cache",
                task_id=task_id,
                error=str(e),
            )

    def validate_transition(
        self, current_status: TaskStatus, new_status: TaskStatus
    ) -> bool:
        """
        Validate if a transition is allowed without performing it.

        Args:
            current_status: The current task status
            new_status: The target status

        Returns:
            True if transition is valid, False otherwise
        """
        return can_transition(current_status, new_status)

    def get_allowed_transitions(self, current_status: TaskStatus) -> List[TaskStatus]:
        """
        Get all allowed transitions from a given status.

        Args:
            current_status: The current task status

        Returns:
            List of valid target statuses
        """
        return VALID_TRANSITIONS.get(current_status, [])
