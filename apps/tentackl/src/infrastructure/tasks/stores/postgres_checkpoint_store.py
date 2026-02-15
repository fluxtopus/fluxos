# REVIEW: Store maintains its own mapping between status strings and enums,
# REVIEW: which risks divergence from other checkpoint logic. Also uses a
# REVIEW: fetch-then-update pattern without explicit locking, so concurrent
# REVIEW: updates may overwrite each other.
"""
PostgreSQL-based checkpoint storage for persistence.

Provides durable storage for checkpoints with full ACID guarantees.
Uses the CheckpointApproval model for audit trail and complex queries.
"""

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy import select, update, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.interfaces.database import Database
from src.database.task_models import CheckpointApproval
from src.domain.checkpoints import CheckpointDecision, CheckpointState


logger = structlog.get_logger()


# Mapping between CheckpointDecision and status strings
# Database uses VARCHAR, not enum
DECISION_TO_STATUS = {
    CheckpointDecision.PENDING: "pending",
    CheckpointDecision.APPROVED: "approved",
    CheckpointDecision.REJECTED: "rejected",
    CheckpointDecision.AUTO_APPROVED: "auto_approved",
    CheckpointDecision.EXPIRED: "timeout",
}

STATUS_TO_DECISION = {v: k for k, v in DECISION_TO_STATUS.items()}


class PostgresCheckpointStore:
    """
    PostgreSQL-based checkpoint storage for persistence.

    Provides:
    - ACID transactions for checkpoint updates
    - Complex queries (by user, by plan, by status)
    - Full audit trail
    - Timeout tracking
    """

    def __init__(self, database: Database):
        """
        Initialize PostgreSQL checkpoint store.

        Args:
            database: Database instance for session management
        """
        self.db = database

    def _model_to_state(self, model: CheckpointApproval) -> CheckpointState:
        """Convert SQLAlchemy model to CheckpointState."""
        # Map status to decision
        decision = STATUS_TO_DECISION.get(
            model.status, CheckpointDecision.PENDING
        )

        return CheckpointState(
            plan_id=str(model.task_id),
            step_id=model.step_id,
            checkpoint_name=model.checkpoint_name,
            description=model.checkpoint_description or "",
            decision=decision,
            preview_data=model.preview_data or {},
            created_at=model.requested_at,
            decided_at=model.resolved_at,
            decided_by=model.user_id if model.resolved_at else None,
            auto_approved=model.auto_approved,
            preference_used=str(model.preference_id) if model.preference_id else None,
            feedback=model.feedback,
            expires_at=model.timeout_at,
        )

    def _state_to_model(
        self, state: CheckpointState, user_id: str
    ) -> CheckpointApproval:
        """Convert CheckpointState to SQLAlchemy model."""
        status = DECISION_TO_STATUS.get(state.decision, "pending")

        return CheckpointApproval(
            id=uuid.uuid4(),
            task_id=uuid.UUID(state.plan_id),
            step_id=state.step_id,
            user_id=user_id,
            checkpoint_name=state.checkpoint_name,
            checkpoint_description=state.description,
            preview_data=state.preview_data,
            status=status,
            auto_approved=state.auto_approved,
            preference_id=uuid.UUID(state.preference_used) if state.preference_used else None,
            feedback=state.feedback,
            requested_at=state.created_at,
            resolved_at=state.decided_at,
            timeout_at=state.expires_at,
        )

    async def create_checkpoint(
        self, checkpoint: CheckpointState, user_id: str
    ) -> str:
        """
        Save checkpoint to CheckpointApproval table.

        Args:
            checkpoint: CheckpointState to save
            user_id: User ID who owns this checkpoint

        Returns:
            ID of created checkpoint record
        """
        async with self.db.get_session() as session:
            model = self._state_to_model(checkpoint, user_id)
            session.add(model)
            await session.commit()

            logger.info(
                "Created checkpoint in PostgreSQL",
                checkpoint_id=str(model.id),
                plan_id=checkpoint.plan_id,
                step_id=checkpoint.step_id,
            )

            return str(model.id)

    async def get_checkpoint(
        self, plan_id: str, step_id: str
    ) -> Optional[CheckpointState]:
        """
        Get checkpoint from database.

        Args:
            plan_id: Plan ID
            step_id: Step ID

        Returns:
            CheckpointState if found, None otherwise
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(CheckpointApproval).where(
                    and_(
                        CheckpointApproval.task_id == uuid.UUID(plan_id),
                        CheckpointApproval.step_id == step_id,
                    )
                ).order_by(CheckpointApproval.requested_at.desc())
            )
            # Use scalars().first() since there may be multiple checkpoints
            # for the same step (e.g., original + replan), we want the most recent
            model = result.scalars().first()

            if not model:
                return None

            return self._model_to_state(model)

    async def update_checkpoint(
        self, plan_id: str, step_id: str, updates: Dict[str, Any]
    ) -> bool:
        """
        Update checkpoint in database.

        Args:
            plan_id: Plan ID
            step_id: Step ID
            updates: Dictionary of fields to update

        Returns:
            True if updated, False if not found
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(CheckpointApproval).where(
                    and_(
                        CheckpointApproval.task_id == uuid.UUID(plan_id),
                        CheckpointApproval.step_id == step_id,
                    )
                ).order_by(CheckpointApproval.requested_at.desc())
            )
            # Use scalars().first() since there may be multiple checkpoints
            # for the same step (e.g., original + replan), we want the most recent
            model = result.scalars().first()

            if not model:
                return False

            # Map CheckpointState fields to model fields
            field_mapping = {
                "decision": "status",
                "decided_at": "resolved_at",
                "feedback": "feedback",
                "auto_approved": "auto_approved",
                "preference_used": "preference_id",
            }

            for state_field, value in updates.items():
                model_field = field_mapping.get(state_field, state_field)

                if model_field == "status" and isinstance(value, CheckpointDecision):
                    value = DECISION_TO_STATUS.get(value, "pending")
                elif model_field == "preference_id" and value:
                    value = uuid.UUID(value) if isinstance(value, str) else value

                if hasattr(model, model_field):
                    setattr(model, model_field, value)

            await session.commit()

            logger.debug(
                "Updated checkpoint in PostgreSQL",
                plan_id=plan_id,
                step_id=step_id,
                updates=list(updates.keys()),
            )

            return True

    async def delete_checkpoint(self, plan_id: str, step_id: str) -> bool:
        """
        Delete checkpoint from database.

        Note: Usually we don't delete checkpoints to preserve audit trail.
        Instead, update status to APPROVED/REJECTED.

        Args:
            plan_id: Plan ID
            step_id: Step ID

        Returns:
            True if deleted, False if not found
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                delete(CheckpointApproval).where(
                    and_(
                        CheckpointApproval.task_id == uuid.UUID(plan_id),
                        CheckpointApproval.step_id == step_id,
                    )
                )
            )
            await session.commit()

            deleted = result.rowcount > 0

            if deleted:
                logger.info(
                    "Deleted checkpoint from PostgreSQL",
                    plan_id=plan_id,
                    step_id=step_id,
                )

            return deleted

    async def list_pending_checkpoints(
        self, user_id: Optional[str] = None, plan_id: Optional[str] = None
    ) -> List[CheckpointState]:
        """
        List pending checkpoints for user or plan.

        Args:
            user_id: Optional user ID to filter by
            plan_id: Optional plan ID to filter by

        Returns:
            List of pending CheckpointState objects
        """
        async with self.db.get_session() as session:
            query = select(CheckpointApproval).where(
                CheckpointApproval.status == "pending"
            )

            if user_id:
                query = query.where(CheckpointApproval.user_id == user_id)

            if plan_id:
                query = query.where(
                    CheckpointApproval.task_id == uuid.UUID(plan_id)
                )

            query = query.order_by(CheckpointApproval.requested_at.desc())

            result = await session.execute(query)
            models = result.scalars().all()

            return [self._model_to_state(m) for m in models]

    async def list_plan_checkpoints(self, plan_id: str) -> List[CheckpointState]:
        """
        List all checkpoints for a plan (any status).

        Args:
            plan_id: Plan ID

        Returns:
            List of CheckpointState objects for the plan
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(CheckpointApproval)
                .where(CheckpointApproval.task_id == uuid.UUID(plan_id))
                .order_by(CheckpointApproval.requested_at.desc())
            )
            models = result.scalars().all()

            return [self._model_to_state(m) for m in models]

    async def get_expired_checkpoints(self) -> List[CheckpointState]:
        """
        Get checkpoints that have passed their timeout.

        Returns:
            List of expired CheckpointState objects
        """
        async with self.db.get_session() as session:
            now = datetime.utcnow()
            result = await session.execute(
                select(CheckpointApproval).where(
                    and_(
                        CheckpointApproval.status == "pending",
                        CheckpointApproval.timeout_at < now,
                    )
                )
            )
            models = result.scalars().all()

            return [self._model_to_state(m) for m in models]

    async def mark_expired(self, plan_id: str, step_id: str) -> bool:
        """
        Mark a checkpoint as expired/timed out.

        Args:
            plan_id: Plan ID
            step_id: Step ID

        Returns:
            True if marked, False if not found
        """
        return await self.update_checkpoint(
            plan_id,
            step_id,
            {
                "decision": CheckpointDecision.EXPIRED,
                "decided_at": datetime.utcnow(),
            },
        )

    async def get_active_checkpoint(self, plan_id: str) -> Optional[CheckpointState]:
        """
        Get the current pending checkpoint for a plan.

        Since only one checkpoint can be active per plan at a time,
        this returns the most recent pending checkpoint.

        Args:
            plan_id: Plan ID

        Returns:
            CheckpointState if pending checkpoint exists, None otherwise
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(CheckpointApproval)
                .where(
                    and_(
                        CheckpointApproval.task_id == uuid.UUID(plan_id),
                        CheckpointApproval.status == "pending",
                    )
                )
                .order_by(CheckpointApproval.requested_at.desc())
                .limit(1)
            )
            # Use scalars().first() for consistency
            model = result.scalars().first()

            if not model:
                return None

            return self._model_to_state(model)

    async def get_or_create_checkpoint(
        self, checkpoint: CheckpointState, user_id: str
    ) -> tuple[str, bool]:
        """
        Create checkpoint if not exists, return (id, created).

        Idempotent: If pending checkpoint exists for same plan+step, return it.

        Args:
            checkpoint: CheckpointState to create
            user_id: User ID who owns this checkpoint

        Returns:
            Tuple of (checkpoint_id, was_created)
        """
        # Check for existing pending checkpoint
        existing = await self.get_checkpoint(checkpoint.plan_id, checkpoint.step_id)
        if existing and existing.decision == CheckpointDecision.PENDING:
            # Return existing pending checkpoint
            async with self.db.get_session() as session:
                result = await session.execute(
                    select(CheckpointApproval.id).where(
                        and_(
                            CheckpointApproval.task_id == uuid.UUID(checkpoint.plan_id),
                            CheckpointApproval.step_id == checkpoint.step_id,
                            CheckpointApproval.status == "pending",
                        )
                    )
                )
                checkpoint_id = result.scalar_one()
                return str(checkpoint_id), False

        # Create new checkpoint
        checkpoint_id = await self.create_checkpoint(checkpoint, user_id)
        return checkpoint_id, True
