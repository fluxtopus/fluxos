# REVIEW: Store performs fetch-then-update without explicit locking, and mixes
# REVIEW: status handling between strings and enums. get_task swallows DB errors
# REVIEW: and returns None, which can hide schema issues. Consider explicit
# REVIEW: transactions/locking and stricter error surfacing.
"""
PostgreSQL-based implementation of TaskInterface.

Provides persistent storage for delegation plans with full ACID guarantees.
PostgreSQL is the SINGLE SOURCE OF TRUTH for task state. Redis is used only
as a read-through cache.

All state transitions must go through the TaskStateMachine, which uses
the transition_status_atomic method for row-level locking.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy import select, delete, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.interfaces.database import Database
from src.domain.tasks.models import (
    TaskInterface,
    Task,
    Finding,
    TaskStatus,
    TaskNotFoundError,
    StepNotFoundError,
)
from src.database.task_models import (
    Task as TaskModel,
    TaskEvent,
)
from src.infrastructure.tasks.stores.task_mapper import (
    model_payload_from_task,
    normalize_task_updates,
    serialize_task_status,
    task_from_model,
)


logger = structlog.get_logger()


class PostgresTaskStore(TaskInterface):
    """
    PostgreSQL-based plan store for persistent delegation plan storage.

    Provides:
    - ACID transactions for plan updates
    - Complex queries across plans
    - Full version history
    - Event audit trail
    """

    def __init__(self, database: Database):
        """
        Initialize PostgreSQL plan store.

        Args:
            database: Database instance for session management
        """
        self.db = database

    def _model_to_document(self, model: Task) -> Task:
        """Convert SQLAlchemy model to Task."""
        return task_from_model(model)

    def _document_to_model(self, doc: Task) -> TaskModel:
        """Convert Task to SQLAlchemy model."""
        return TaskModel(**model_payload_from_task(doc))

    async def _record_event(
        self,
        session: AsyncSession,
        task_id: str,
        event_type: str,
        event_data: Dict[str, Any] = None,
        metadata: Dict[str, Any] = None,
    ) -> None:
        """Record a task event for audit trail."""
        event = TaskEvent(
            task_id=uuid.UUID(task_id),
            event_type=event_type,
            event_data=event_data or {},
            extra_metadata=metadata or {},
        )
        session.add(event)

    async def create_task(self, task: Task) -> str:
        """Create a new task."""
        async with self.db.get_session() as session:
            model = self._document_to_model(task)
            session.add(model)

            # Record creation event
            await self._record_event(
                session,
                task.id,
                "task.created",
                event_data={
                    "goal": task.goal,
                    "step_count": len(task.steps),
                    "user_id": task.user_id,
                },
            )

            await session.commit()

            logger.info(
                "Created task in PostgreSQL",
                task_id=task.id,
                user_id=task.user_id,
            )

            return task.id

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        try:
            async with self.db.get_session() as session:
                result = await session.execute(
                    select(TaskModel).where(
                        TaskModel.id == uuid.UUID(task_id)
                    )
                )
                model = result.scalar_one_or_none()

                if not model:
                    return None

                return self._model_to_document(model)
        except Exception as e:
            # Table might not exist yet or other DB issues
            # Return None to allow fallback to Redis
            logger.debug("PostgreSQL get_task failed", task_id=task_id, error=str(e))
            return None

    async def update_task(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """Update a task with partial updates."""
        async with self.db.get_session() as session:
            result = await session.execute(
                select(TaskModel).where(
                    TaskModel.id == uuid.UUID(task_id)
                )
            )
            model = result.scalar_one_or_none()

            if not model:
                raise TaskNotFoundError(f"Task not found: {task_id}")

            old_status = model.status

            # Apply updates
            for key, value in normalize_task_updates(updates).items():
                if hasattr(model, key):
                    setattr(model, key, value)

            model.updated_at = datetime.utcnow()
            model.version += 1

            # Record update event
            await self._record_event(
                session,
                task_id,
                "task.updated",
                event_data={
                    "updated_fields": list(updates.keys()),
                    "version": model.version,
                    "status_changed": model.status != old_status,
                },
            )

            # Record status change if applicable
            if model.status != old_status:
                old_status_str = old_status.value if hasattr(old_status, 'value') else str(old_status)
                new_status_str = model.status.value if hasattr(model.status, 'value') else str(model.status)
                await self._record_event(
                    session,
                    task_id,
                    f"task.status.{new_status_str}",
                    event_data={
                        "old_status": old_status_str,
                        "new_status": new_status_str,
                    },
                )

            await session.commit()

            logger.debug(
                "Updated task",
                task_id=task_id,
                updates=list(updates.keys()),
                version=model.version,
            )

            return True

    async def transition_status_atomic(
        self,
        task_id: str,
        new_status: TaskStatus,
        additional_updates: Optional[Dict[str, Any]] = None,
    ) -> Task:
        """
        Atomically transition task status with row-level locking.

        This method uses SELECT FOR UPDATE to ensure no race conditions
        when multiple processes try to update the same task.

        Args:
            task_id: The task ID to update
            new_status: The new status to set
            additional_updates: Optional additional fields to update

        Returns:
            The updated Task object

        Raises:
            TaskNotFoundError: If task doesn't exist
        """
        async with self.db.get_session() as session:
            # Lock the row with FOR UPDATE to prevent concurrent modifications
            from sqlalchemy import text
            result = await session.execute(
                select(TaskModel)
                .where(TaskModel.id == uuid.UUID(task_id))
                .with_for_update()
            )
            model = result.scalar_one_or_none()

            if not model:
                raise TaskNotFoundError(f"Task not found: {task_id}")

            old_status = model.status

            # Update status
            model.status = serialize_task_status(new_status)
            model.updated_at = datetime.utcnow()
            model.version += 1

            # Apply additional updates
            if additional_updates:
                for key, value in normalize_task_updates(additional_updates).items():
                    if hasattr(model, key):
                        setattr(model, key, value)

            # Record status change event
            old_status_str = old_status.value if hasattr(old_status, 'value') else str(old_status)
            new_status_str = new_status.value if hasattr(new_status, 'value') else str(new_status)
            await self._record_event(
                session,
                task_id,
                f"task.status.{new_status_str}",
                event_data={
                    "old_status": old_status_str,
                    "new_status": new_status_str,
                    "version": model.version,
                },
            )

            await session.commit()

            logger.info(
                "Task status transitioned atomically",
                task_id=task_id,
                old_status=old_status_str,
                new_status=new_status_str,
                version=model.version,
            )

            return self._model_to_document(model)

    async def get_task_for_update(self, task_id: str) -> Optional[Task]:
        """
        Get a task with a row lock for safe updates.

        Use this when you need to read-modify-write atomically.
        The lock is held until the transaction commits.

        Note: This requires being called within a transaction context.
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(TaskModel)
                .where(TaskModel.id == uuid.UUID(task_id))
                .with_for_update()
            )
            model = result.scalar_one_or_none()

            if not model:
                return None

            return self._model_to_document(model)

    async def update_step(
        self, task_id: str, step_id: str, updates: Dict[str, Any]
    ) -> bool:
        """Update a specific step in a task."""
        async with self.db.get_session() as session:
            result = await session.execute(
                select(TaskModel).where(
                    TaskModel.id == uuid.UUID(task_id)
                )
            )
            model = result.scalar_one_or_none()

            if not model:
                raise TaskNotFoundError(f"Task not found: {task_id}")

            # Find and update the step
            steps = model.steps or []
            step_found = False

            for i, step_dict in enumerate(steps):
                if step_dict.get("id") == step_id:
                    step_found = True

                    for key, value in updates.items():
                        if key in ("started_at", "completed_at") and value:
                            step_dict[key] = value.isoformat() if isinstance(value, datetime) else value
                        else:
                            step_dict[key] = value

                    steps[i] = step_dict
                    break

            if not step_found:
                raise StepNotFoundError(f"Step not found: {step_id}")

            # Assign a new list to trigger SQLAlchemy change detection for JSON columns
            model.steps = list(steps)
            model.updated_at = datetime.utcnow()
            model.version += 1

            # Explicitly mark the column as modified (belt and suspenders)
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(model, 'steps')

            # Record step update event
            await self._record_event(
                session,
                task_id,
                f"step.{updates.get('status', 'updated')}",
                event_data={
                    "step_id": step_id,
                    "updated_fields": list(updates.keys()),
                },
            )

            await session.commit()

            logger.debug(
                "Updated task step",
                task_id=task_id,
                step_id=step_id,
                updates=list(updates.keys()),
            )

            return True

    async def add_finding(self, task_id: str, finding: Finding) -> bool:
        """Add a finding to the task's accumulated findings."""
        async with self.db.get_session() as session:
            result = await session.execute(
                select(TaskModel).where(
                    TaskModel.id == uuid.UUID(task_id)
                )
            )
            model = result.scalar_one_or_none()

            if not model:
                raise TaskNotFoundError(f"Task not found: {task_id}")

            findings = model.accumulated_findings or []
            findings.append(finding.to_dict())
            model.accumulated_findings = findings
            model.updated_at = datetime.utcnow()
            model.version += 1

            # Record finding event
            await self._record_event(
                session,
                task_id,
                "finding.added",
                event_data={
                    "finding_id": finding.id,
                    "finding_type": finding.type,
                    "step_id": finding.step_id,
                },
            )

            await session.commit()

            logger.debug(
                "Added finding to task",
                task_id=task_id,
                finding_id=finding.id,
            )

            return True

    async def get_tasks_by_user(
        self,
        user_id: str,
        status: Optional[TaskStatus] = None,
        limit: int = 100,
    ) -> List[Task]:
        """Get tasks for a user, optionally filtered by status."""
        async with self.db.get_session() as session:
            query = select(TaskModel).where(
                TaskModel.user_id == user_id
            )

            if status:
                query = query.where(
                    TaskModel.status == serialize_task_status(status)
                )

            query = query.order_by(TaskModel.created_at.desc()).limit(limit)

            result = await session.execute(query)
            models = result.scalars().all()

            return [self._model_to_document(m) for m in models]

    async def get_task_history(self, task_id: str, limit: int = 10) -> List[Task]:
        """Get version history for a task (via parent chain)."""
        history = []
        current_id = task_id

        while current_id and len(history) < limit:
            task = await self.get_task(current_id)
            if task:
                history.append(task)
                current_id = task.parent_task_id
            else:
                break

        return history

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        async with self.db.get_session() as session:
            result = await session.execute(
                delete(TaskModel).where(
                    TaskModel.id == uuid.UUID(task_id)
                )
            )

            await session.commit()

            if result.rowcount > 0:
                logger.info("Deleted task", task_id=task_id)
                return True

            return False

    async def health_check(self) -> bool:
        """Check if the plan store is healthy."""
        try:
            async with self.db.get_session() as session:
                from sqlalchemy import text
                await session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error("PostgreSQL plan store health check failed", error=str(e))
            return False

    # Additional query methods specific to PostgreSQL

    async def get_plans_by_organization(
        self,
        organization_id: str,
        status: Optional[TaskStatus] = None,
        limit: int = 100,
    ) -> List[Task]:
        """Get plans for an organization."""
        async with self.db.get_session() as session:
            query = select(TaskModel).where(
                TaskModel.organization_id == organization_id
            )

            if status:
                query = query.where(
                    TaskModel.status == serialize_task_status(status)
                )

            query = query.order_by(TaskModel.created_at.desc()).limit(limit)

            result = await session.execute(query)
            models = result.scalars().all()

            return [self._model_to_document(m) for m in models]

    async def get_task_events(
        self,
        task_id: str,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get events for a task."""
        async with self.db.get_session() as session:
            query = select(TaskEvent).where(
                TaskEvent.task_id == uuid.UUID(task_id)
            )

            if event_type:
                query = query.where(TaskEvent.event_type == event_type)

            query = query.order_by(TaskEvent.created_at.desc()).limit(limit)

            result = await session.execute(query)
            events = result.scalars().all()

            return [
                {
                    "id": str(e.id),
                    "event_type": e.event_type,
                    "event_data": e.event_data,
                    "metadata": e.extra_metadata,
                    "created_at": e.created_at.isoformat(),
                }
                for e in events
            ]

    async def get_plans_with_pending_checkpoints(
        self, limit: int = 100
    ) -> List[Task]:
        """Get plans waiting at checkpoints."""
        async with self.db.get_session() as session:
            query = (
                select(TaskModel)
                .where(TaskModel.status == serialize_task_status(TaskStatus.CHECKPOINT))
                .order_by(TaskModel.updated_at.desc())
                .limit(limit)
            )

            result = await session.execute(query)
            models = result.scalars().all()

            return [self._model_to_document(m) for m in models]

    async def get_stale_executing_plans(
        self, stale_minutes: int = 30, limit: int = 100
    ) -> List[Task]:
        """Get plans stuck in executing state."""
        cutoff = datetime.utcnow() - timedelta(minutes=stale_minutes)

        async with self.db.get_session() as session:
            query = (
                select(TaskModel)
                .where(
                    and_(
                        TaskModel.status == serialize_task_status(TaskStatus.EXECUTING),
                        TaskModel.updated_at < cutoff,
                    )
                )
                .order_by(TaskModel.updated_at.asc())
                .limit(limit)
            )

            result = await session.execute(query)
            models = result.scalars().all()

            return [self._model_to_document(m) for m in models]

    async def get_plan_stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Get plan statistics."""
        async with self.db.get_session() as session:
            base_query = select(
                TaskModel.status,
                func.count(TaskModel.id).label("count"),
            )

            if user_id:
                base_query = base_query.where(TaskModel.user_id == user_id)

            base_query = base_query.group_by(TaskModel.status)

            result = await session.execute(base_query)
            status_counts = {str(row.status): row.count for row in result}

            # Total count
            total_query = select(func.count(TaskModel.id))
            if user_id:
                total_query = total_query.where(TaskModel.user_id == user_id)

            total_result = await session.execute(total_query)
            total = total_result.scalar() or 0

            return {
                "total": total,
                "by_status": status_counts,
            }

    async def cleanup_old_tasks(
        self,
        retention_days: int = 30,
        status: Optional[TaskStatus] = None,
    ) -> int:
        """Clean up old tasks beyond retention period."""
        cutoff = datetime.utcnow() - timedelta(days=retention_days)

        async with self.db.get_session() as session:
            query = delete(TaskModel).where(
                TaskModel.created_at < cutoff
            )

            if status:
                query = query.where(
                    TaskModel.status == serialize_task_status(status)
                )

            result = await session.execute(query)
            await session.commit()

            logger.info(
                "Cleaned up old tasks",
                retention_days=retention_days,
                cleaned_count=result.rowcount,
            )

            return result.rowcount

    async def get_stuck_planning_tasks(self, timeout_minutes: int = 5) -> List[Task]:
        """Find tasks stuck in PLANNING status older than timeout_minutes."""
        try:
            cutoff = datetime.utcnow() - timedelta(minutes=timeout_minutes)
            async with self.db.get_session() as session:
                result = await session.execute(
                    select(TaskModel).where(
                        and_(
                            TaskModel.status == "planning",
                            TaskModel.created_at < cutoff,
                        )
                    )
                )
                models = result.scalars().all()
                return [self._model_to_document(m) for m in models]
        except Exception as e:
            logger.warning("Failed to query stuck planning tasks", error=str(e))
            return []
