# REVIEW: Cache store relies on ad-hoc indexes and metadata fields (org_id in
# REVIEW: metadata), and opens/closes Redis clients per call. There’s no TTL
# REVIEW: or background cleanup, so stale indexes can accumulate. Consider a
# REVIEW: shared cache layer with explicit lifecycle and index maintenance.
"""
Redis-based implementation of TaskInterface.

IMPORTANT: Redis is a READ-THROUGH CACHE only. PostgreSQL is the single
source of truth for task state.

All status transitions MUST go through the TaskStateMachine, which:
1. Updates PostgreSQL (source of truth)
2. Invalidates Redis cache

This store provides:
- Fast read access for active tasks
- Sorted set indexes for efficient queries
- Cache invalidation methods

DO NOT use update_task() for status changes - use TaskStateMachine.transition() instead.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import redis.asyncio as redis
import structlog

from src.domain.tasks.models import (
    TaskInterface,
    Task,
    Finding,
    TaskStatus,
    TaskNotFoundError,
    TaskValidationError,
)
from src.infrastructure.tasks.stores.task_mapper import (
    findings_from_storage,
    parse_step_status,
    parse_task_status,
    steps_from_storage,
)


logger = structlog.get_logger()


class RedisTaskStore(TaskInterface):
    """
    Redis-based cache for fast task access.

    IMPORTANT: This is a READ-THROUGH CACHE. PostgreSQL is the source of truth.
    All status changes must go through TaskStateMachine.transition().

    Key Structure:
    - plan:{plan_id} - Hash with plan document JSON
    - plan:user:{user_id}:plans - Sorted set of plan IDs by created_at
    - plan:status:{status} - Sorted set of plan IDs by created_at
    - plan:tree:{tree_id} - Plan ID for tree linkage

    Cache Invalidation:
    - Call invalidate(task_id) after PostgreSQL updates
    - Call invalidate_status_index(task_id, old_status) when status changes
    """

    def __init__(
        self,
        redis_url: str = None,
        db: int = 0,
        key_prefix: str = "tentackl:delegation",
        connection_pool_size: int = 10,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
    ):
        """
        Initialize Redis plan store.

        Args:
            redis_url: Redis connection URL
            db: Redis database number
            key_prefix: Prefix for all Redis keys
            connection_pool_size: Size of connection pool
            socket_timeout: Socket timeout in seconds
            socket_connect_timeout: Connection timeout in seconds
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://redis:6379/0")
        self.db = db
        self.key_prefix = key_prefix
        self.connection_pool_size = connection_pool_size
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout

        self._redis_pool = None
        self._is_connected = False

    async def _get_redis(self) -> redis.Redis:
        """Get Redis connection from pool."""
        if not self._is_connected:
            await self._connect()
        return redis.Redis(connection_pool=self._redis_pool)

    async def _connect(self) -> None:
        """Establish Redis connection pool."""
        try:
            self._redis_pool = redis.ConnectionPool.from_url(
                self.redis_url,
                db=self.db,
                max_connections=self.connection_pool_size,
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
                decode_responses=True,
            )

            # Test connection
            client = redis.Redis(connection_pool=self._redis_pool)
            await client.ping()
            await client.aclose()

            self._is_connected = True
            logger.info(
                "Connected to Redis for plan store",
                redis_url=self.redis_url,
                db=self.db,
            )

        except Exception as e:
            logger.error("Failed to connect to Redis plan store", error=str(e))
            raise

    async def _disconnect(self) -> None:
        """Close Redis connection pool."""
        if self._redis_pool:
            await self._redis_pool.disconnect()
            self._is_connected = False
            logger.info("Disconnected from Redis plan store")

    # Key generation helpers

    def _plan_key(self, plan_id: str) -> str:
        """Key for plan document."""
        return f"{self.key_prefix}:plan:{plan_id}"

    def _user_plans_key(self, user_id: str) -> str:
        """Key for user's plans index."""
        return f"{self.key_prefix}:user:{user_id}:plans"

    def _status_index_key(self, status: Any) -> str:
        """Key for status-based index."""
        return f"{self.key_prefix}:status:{parse_task_status(status).value}"

    def _tree_link_key(self, tree_id: str) -> str:
        """Key for tree-to-plan linkage."""
        return f"{self.key_prefix}:tree:{tree_id}"

    def _org_plans_key(self, org_id: str) -> str:
        """Key for organization's plans index."""
        return f"{self.key_prefix}:org:{org_id}:plans"

    def _serialize_plan(self, plan: Task) -> str:
        """Serialize plan to JSON."""
        return json.dumps(plan.to_dict())

    def _deserialize_plan(self, data: str) -> Task:
        """Deserialize plan from JSON."""
        try:
            return Task.from_dict(json.loads(data))
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            raise TaskValidationError(f"Invalid plan data: {e}")

    # Interface implementation

    async def create_task(self, task: Task) -> str:
        """Create a new task."""
        client = await self._get_redis()

        try:
            task_key = self._plan_key(task.id)
            user_key = self._user_plans_key(task.user_id)
            status_key = self._status_index_key(task.status)
            timestamp_score = task.created_at.timestamp()

            serialized = self._serialize_plan(task)

            async with client.pipeline(transaction=True) as pipe:
                # Store task document
                pipe.set(task_key, serialized)

                # Index by user
                pipe.zadd(user_key, {task.id: timestamp_score})

                # Index by status
                pipe.zadd(status_key, {task.id: timestamp_score})

                # Index by tree if linked
                if task.tree_id:
                    pipe.set(self._tree_link_key(task.tree_id), task.id)

                # Index by organization if present
                org_id = task.metadata.get("organization_id")
                if org_id:
                    pipe.zadd(self._org_plans_key(org_id), {task.id: timestamp_score})

                await pipe.execute()

            logger.info(
                "Created task",
                task_id=task.id,
                user_id=task.user_id,
                goal=task.goal[:50],
            )

            return task.id

        finally:
            await client.aclose()

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        client = await self._get_redis()

        try:
            task_key = self._plan_key(task_id)
            data = await client.get(task_key)

            if not data:
                return None

            return self._deserialize_plan(data)

        finally:
            await client.aclose()

    async def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """Update a task with partial updates."""
        client = await self._get_redis()

        try:
            task_key = self._plan_key(task_id)
            data = await client.get(task_key)

            if not data:
                raise TaskNotFoundError(f"Task not found: {task_id}")

            task = self._deserialize_plan(data)
            old_status = task.status

            # Apply updates
            for key, value in updates.items():
                if key == "status":
                    task.status = parse_task_status(value)
                elif key == "steps":
                    task.steps = steps_from_storage(value)
                elif key == "accumulated_findings":
                    task.accumulated_findings = findings_from_storage(value)
                elif hasattr(task, key):
                    setattr(task, key, value)

            task.updated_at = datetime.utcnow()
            task.version += 1

            serialized = self._serialize_plan(task)

            async with client.pipeline(transaction=True) as pipe:
                # Update task document
                pipe.set(task_key, serialized)

                # Update status index if status changed
                if task.status != old_status:
                    old_status_key = self._status_index_key(old_status)
                    new_status_key = self._status_index_key(task.status)
                    timestamp_score = task.updated_at.timestamp()

                    pipe.zrem(old_status_key, task_id)
                    pipe.zadd(new_status_key, {task_id: timestamp_score})

                await pipe.execute()

            logger.debug(
                "Updated task",
                task_id=task_id,
                updates=list(updates.keys()),
                version=task.version,
            )

            return True

        except TaskNotFoundError:
            raise
        except Exception as e:
            logger.error("Failed to update task", task_id=task_id, error=str(e))
            return False
        finally:
            await client.aclose()

    async def update_step(
        self, plan_id: str, step_id: str, updates: Dict[str, Any]
    ) -> bool:
        """Update a specific step in a plan."""
        client = await self._get_redis()

        try:
            plan_key = self._plan_key(plan_id)
            data = await client.get(plan_key)

            if not data:
                raise TaskNotFoundError(f"Plan not found: {plan_id}")

            plan = self._deserialize_plan(data)
            step = plan.get_step_by_id(step_id)

            if not step:
                from src.domain.tasks.models import StepNotFoundError
                raise StepNotFoundError(f"Step not found: {step_id}")

            # Apply updates to step
            for key, value in updates.items():
                if key == "status":
                    step.status = parse_step_status(value)
                elif key == "started_at" and isinstance(value, str):
                    step.started_at = datetime.fromisoformat(value)
                elif key == "completed_at" and isinstance(value, str):
                    step.completed_at = datetime.fromisoformat(value)
                elif hasattr(step, key):
                    setattr(step, key, value)

            plan.updated_at = datetime.utcnow()
            plan.version += 1

            serialized = self._serialize_plan(plan)
            await client.set(plan_key, serialized)

            logger.debug(
                "Updated plan step",
                plan_id=plan_id,
                step_id=step_id,
                updates=list(updates.keys()),
            )

            return True

        except (TaskNotFoundError,):
            raise
        except Exception as e:
            logger.error(
                "Failed to update step",
                plan_id=plan_id,
                step_id=step_id,
                error=str(e),
            )
            return False
        finally:
            await client.aclose()

    async def add_finding(self, plan_id: str, finding: Finding) -> bool:
        """Add a finding to the plan's accumulated findings."""
        client = await self._get_redis()

        try:
            plan_key = self._plan_key(plan_id)
            data = await client.get(plan_key)

            if not data:
                raise TaskNotFoundError(f"Plan not found: {plan_id}")

            plan = self._deserialize_plan(data)
            plan.add_finding(finding)
            plan.version += 1

            serialized = self._serialize_plan(plan)
            await client.set(plan_key, serialized)

            logger.debug(
                "Added finding to plan",
                plan_id=plan_id,
                finding_id=finding.id,
                finding_type=finding.type,
            )

            return True

        except TaskNotFoundError:
            raise
        except Exception as e:
            logger.error("Failed to add finding", plan_id=plan_id, error=str(e))
            return False
        finally:
            await client.aclose()

    async def get_tasks_by_user(
        self,
        user_id: str,
        status: Optional[TaskStatus] = None,
        limit: int = 100,
    ) -> List[Task]:
        """Get tasks for a user, optionally filtered by status."""
        client = await self._get_redis()

        try:
            user_key = self._user_plans_key(user_id)

            # Get task IDs for user (newest first)
            task_ids = await client.zrevrange(user_key, 0, limit - 1)

            tasks = []
            for task_id in task_ids:
                task = await self.get_task(task_id)
                if task:
                    if status is None or task.status == status:
                        tasks.append(task)

            return tasks[:limit]

        finally:
            await client.aclose()

    async def get_task_history(self, task_id: str, limit: int = 10) -> List[Task]:
        """
        Get version history for a task.

        Note: Redis implementation doesn't store version history by default.
        For full version history, use PostgreSQL store.
        """
        task = await self.get_task(task_id)
        if task:
            # Follow parent chain if exists
            history = [task]
            current = task

            while current.parent_task_id and len(history) < limit:
                parent = await self.get_task(current.parent_task_id)
                if parent:
                    history.append(parent)
                    current = parent
                else:
                    break

            return history

        return []

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        client = await self._get_redis()

        try:
            task_key = self._plan_key(task_id)
            data = await client.get(task_key)

            if not data:
                return False

            task = self._deserialize_plan(data)

            async with client.pipeline(transaction=True) as pipe:
                # Delete task document
                pipe.delete(task_key)

                # Remove from user index
                pipe.zrem(self._user_plans_key(task.user_id), task_id)

                # Remove from status index
                pipe.zrem(self._status_index_key(task.status), task_id)

                # Remove tree linkage
                if task.tree_id:
                    pipe.delete(self._tree_link_key(task.tree_id))

                # Remove from org index
                org_id = task.metadata.get("organization_id")
                if org_id:
                    pipe.zrem(self._org_plans_key(org_id), task_id)

                await pipe.execute()

            logger.info("Deleted task", task_id=task_id)
            return True

        except Exception as e:
            logger.error("Failed to delete task", task_id=task_id, error=str(e))
            return False
        finally:
            await client.aclose()

    async def health_check(self) -> bool:
        """Check if the plan store is healthy."""
        try:
            client = await self._get_redis()
            test_key = f"{self.key_prefix}:health"
            await client.set(test_key, "ok", ex=60)
            result = await client.get(test_key)
            await client.delete(test_key)
            await client.aclose()
            return result == "ok"
        except Exception as e:
            logger.error("Plan store health check failed", error=str(e))
            return False

    # Cache invalidation methods (called by TaskStateMachine after PG updates)

    async def invalidate(self, task_id: str) -> bool:
        """
        Invalidate the cache for a specific task.

        Call this after updating PostgreSQL to ensure cache consistency.
        The next read will fetch fresh data from PostgreSQL.

        Args:
            task_id: The task ID to invalidate

        Returns:
            True if invalidation succeeded, False otherwise
        """
        client = await self._get_redis()

        try:
            task_key = self._plan_key(task_id)
            deleted = await client.delete(task_key)

            logger.debug(
                "Invalidated task cache",
                task_id=task_id,
                was_cached=deleted > 0,
            )

            return True
        except Exception as e:
            logger.warning(
                "Failed to invalidate task cache",
                task_id=task_id,
                error=str(e),
            )
            return False
        finally:
            await client.aclose()

    async def invalidate_with_indexes(
        self,
        task_id: str,
        user_id: str,
        old_status: Optional[TaskStatus] = None,
        new_status: Optional[TaskStatus] = None,
    ) -> bool:
        """
        Invalidate task cache and update status indexes.

        Call this after a status transition to keep indexes consistent.

        Args:
            task_id: The task ID to invalidate
            user_id: The user who owns the task
            old_status: Previous status (to remove from old index)
            new_status: New status (to add to new index)

        Returns:
            True if invalidation succeeded, False otherwise
        """
        client = await self._get_redis()

        try:
            async with client.pipeline(transaction=True) as pipe:
                # Delete cached task document
                pipe.delete(self._plan_key(task_id))

                # Update status indexes if status changed
                if old_status and new_status and old_status != new_status:
                    timestamp_score = datetime.utcnow().timestamp()
                    old_status_key = self._status_index_key(old_status)
                    new_status_key = self._status_index_key(new_status)

                    pipe.zrem(old_status_key, task_id)
                    pipe.zadd(new_status_key, {task_id: timestamp_score})

                await pipe.execute()

            logger.debug(
                "Invalidated task cache with index updates",
                task_id=task_id,
                old_status=parse_task_status(old_status).value if old_status else None,
                new_status=parse_task_status(new_status).value if new_status else None,
            )

            return True
        except Exception as e:
            logger.warning(
                "Failed to invalidate task cache with indexes",
                task_id=task_id,
                error=str(e),
            )
            return False
        finally:
            await client.aclose()

    # Additional utility methods

    async def get_tasks_by_status(
        self, status: TaskStatus, limit: int = 100
    ) -> List[Task]:
        """Get tasks by status."""
        client = await self._get_redis()

        try:
            status_key = self._status_index_key(status)
            task_ids = await client.zrevrange(status_key, 0, limit - 1)

            tasks = []
            for task_id in task_ids:
                task = await self.get_task(task_id)
                if task:
                    tasks.append(task)

            return tasks

        finally:
            await client.aclose()

    async def get_task_by_tree_id(self, tree_id: str) -> Optional[Task]:
        """Get task linked to an execution tree."""
        client = await self._get_redis()

        try:
            tree_key = self._tree_link_key(tree_id)
            task_id = await client.get(tree_key)

            if task_id:
                return await self.get_task(task_id)

            return None

        finally:
            await client.aclose()

    async def get_active_tasks(self, user_id: str, limit: int = 10) -> List[Task]:
        """Get active (executing or checkpoint) tasks for a user."""
        active_statuses = [TaskStatus.EXECUTING, TaskStatus.CHECKPOINT]

        all_active = []
        for status in active_statuses:
            tasks = await self.get_tasks_by_user(user_id, status=status, limit=limit)
            all_active.extend(tasks)

        # Sort by updated_at descending
        all_active.sort(key=lambda t: t.updated_at, reverse=True)
        return all_active[:limit]

    async def cleanup_old_tasks(
        self, retention_days: int = 30, status: Optional[TaskStatus] = None
    ) -> int:
        """Clean up old tasks beyond retention period."""
        client = await self._get_redis()

        try:
            cutoff = datetime.utcnow() - timedelta(days=retention_days)
            cutoff_score = cutoff.timestamp()
            cleaned = 0

            # If status specified, only clean that status
            statuses = [status] if status else list(TaskStatus)

            for st in statuses:
                status_key = self._status_index_key(st)

                # Get old task IDs
                old_ids = await client.zrangebyscore(
                    status_key, "-inf", cutoff_score
                )

                for task_id in old_ids:
                    if await self.delete_task(task_id):
                        cleaned += 1

            logger.info(
                "Cleaned up old tasks",
                retention_days=retention_days,
                cleaned_count=cleaned,
            )

            return cleaned

        except Exception as e:
            logger.error("Failed to cleanup old tasks", error=str(e))
            return 0
        finally:
            await client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        await self._connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._disconnect()
