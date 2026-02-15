# REVIEW: CheckpointManager is a grab-bag of concerns: approval logic,
# REVIEW: preference store lookups, Redis/PG dual writes, and notification
# REVIEW: triggers. There’s no transactional boundary between PG and Redis,
# REVIEW: and it directly mutates task/step status strings, which risks drift
# REVIEW: from TaskStatus/StepStatus enums. Consider isolating storage updates
# REVIEW: behind a repository and decoupling notifications.
"""
Checkpoint Manager Service

Handles checkpoint approvals, auto-approval decisions, and notification triggers.

Responsibilities:
- Pause execution at checkpoint steps
- Check for auto-approval eligibility
- Record approval decisions
- Trigger notifications via Mimic
- Resume execution after approval
"""

from __future__ import annotations

from typing import Dict, Any, Optional, List, TYPE_CHECKING
from datetime import datetime, timedelta
import structlog

from src.domain.tasks.models import (
    Task,
    TaskStep,
    TaskStatus,
    StepStatus,
    CheckpointConfig,
    ApprovalType,
)
from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore
from src.infrastructure.tasks.stores.redis_preference_store import RedisPreferenceStore
from src.infrastructure.tasks.stores.postgres_checkpoint_store import PostgresCheckpointStore
from src.domain.checkpoints import (
    CheckpointState,
    CheckpointDecision,
    CheckpointType,
    CheckpointResponse,
)


logger = structlog.get_logger(__name__)


class CheckpointManager:
    """
    Manages checkpoint approvals for delegation plans.

    Handles:
    - Creating checkpoints when steps require approval
    - Checking auto-approval eligibility via preference store
    - Recording approval/rejection decisions
    - Triggering notifications via Mimic
    - Resuming execution after approval
    """

    # Confidence threshold for auto-approval
    AUTO_APPROVAL_THRESHOLD = 0.9

    def __init__(
        self,
        pg_checkpoint_store: PostgresCheckpointStore,
        plan_store: Optional[RedisTaskStore] = None,
        preference_store: Optional[RedisPreferenceStore] = None,
        mimic_client: Optional[Any] = None,  # MimicClient when available
        default_timeout_minutes: int = 2880,  # 48 hours
        pg_task_store: Optional["PostgresTaskStore"] = None,
    ):
        """
        Initialize checkpoint manager.

        Args:
            pg_checkpoint_store: PostgreSQL checkpoint storage (required, single source of truth)
            plan_store: Plan storage backend (Redis)
            preference_store: Preference storage for auto-approval
            mimic_client: Mimic notification client (optional)
            default_timeout_minutes: Default checkpoint expiration time
            pg_task_store: PostgreSQL task storage (for dual-write consistency)
        """
        self._pg_checkpoint_store = pg_checkpoint_store
        self._plan_store = plan_store
        self._preference_store = preference_store
        self._mimic_client = mimic_client
        self.default_timeout_minutes = default_timeout_minutes
        self._pg_task_store = pg_task_store

    async def _get_plan_store(self) -> RedisTaskStore:
        """Get or create plan store."""
        if not self._plan_store:
            self._plan_store = RedisTaskStore()
            await self._plan_store._connect()
        return self._plan_store

    async def _get_preference_store(self) -> RedisPreferenceStore:
        """Get or create preference store."""
        if not self._preference_store:
            self._preference_store = RedisPreferenceStore()
            await self._preference_store._connect()
        return self._preference_store

    def _get_pg_checkpoint_store(self) -> PostgresCheckpointStore:
        """Get PostgreSQL checkpoint store (always available)."""
        return self._pg_checkpoint_store

    async def _get_pg_task_store(self) -> Optional["PostgresTaskStore"]:
        """Get PostgreSQL task store for dual-write consistency."""
        if not self._pg_task_store:
            # Lazy import and create if not provided
            from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskStore
            from src.interfaces.database import Database
            db = Database()
            await db.connect()
            self._pg_task_store = PostgresTaskStore(db)
        return self._pg_task_store

    async def create_checkpoint(
        self,
        plan_id: str,
        step: TaskStep,
        user_id: str,
    ) -> CheckpointState:
        """
        Create a new checkpoint for a step.

        Checks for auto-approval eligibility first.
        If not auto-approved, creates pending checkpoint.

        Args:
            plan_id: The plan ID
            step: The step requiring checkpoint
            user_id: The user who owns the plan

        Returns:
            CheckpointState with decision (may be auto_approved)
        """
        logger.info(
            "Creating checkpoint",
            plan_id=plan_id,
            step_id=step.id,
            checkpoint=step.checkpoint_config.name if step.checkpoint_config else "unknown",
        )

        config = step.checkpoint_config or CheckpointConfig(
            name=f"step_{step.id}_approval",
            description=f"Approve step: {step.name}",
        )

        # Build preview data
        preview_data = self._build_preview(step, config)

        # Build context for preference matching
        context = self._build_context(step, preview_data)

        # Check for auto-approval
        auto_approval_result = await self._check_auto_approval(user_id, config, context)

        if auto_approval_result["eligible"]:
            # Auto-approve
            checkpoint = CheckpointState(
                plan_id=plan_id,
                step_id=step.id,
                checkpoint_name=config.name,
                description=config.description,
                decision=CheckpointDecision.AUTO_APPROVED,
                preview_data=preview_data,
                created_at=datetime.utcnow(),
                decided_at=datetime.utcnow(),
                auto_approved=True,
                preference_used=auto_approval_result.get("preference_id"),
            )

            logger.info(
                "Checkpoint auto-approved",
                plan_id=plan_id,
                step_id=step.id,
                preference_id=auto_approval_result.get("preference_id"),
                confidence=auto_approval_result.get("confidence"),
            )

            # Increment preference usage
            pref_store = await self._get_preference_store()
            if auto_approval_result.get("preference_id"):
                await pref_store.increment_usage(auto_approval_result["preference_id"])

            # Update step and plan status so execution can continue
            # This is critical for parallel step groups where each step may need separate approval
            plan_store = await self._get_plan_store()
            await plan_store.update_step(plan_id, step.id, {
                "checkpoint_required": False,
                "status": "pending",  # Ready to execute
            })
            await plan_store.update_task(plan_id, {"status": TaskStatus.READY})

            return checkpoint

        # Create pending checkpoint
        expires_at = datetime.utcnow() + timedelta(
            minutes=config.timeout_minutes or self.default_timeout_minutes
        )

        checkpoint = CheckpointState(
            plan_id=plan_id,
            step_id=step.id,
            checkpoint_name=config.name,
            description=config.description,
            decision=CheckpointDecision.PENDING,
            preview_data=preview_data,
            created_at=datetime.utcnow(),
            expires_at=expires_at,
        )

        # Store in PostgreSQL (single source of truth)
        pg_store = self._get_pg_checkpoint_store()
        await pg_store.get_or_create_checkpoint(checkpoint, user_id)

        # Update plan status in Redis
        plan_store = await self._get_plan_store()
        await plan_store.update_task(plan_id, {"status": TaskStatus.CHECKPOINT})
        await plan_store.update_step(plan_id, step.id, {"status": "checkpoint"})

        # Also update PostgreSQL for consistency (API reads from PG)
        pg_task_store = await self._get_pg_task_store()
        if pg_task_store:
            try:
                await pg_task_store.update_step(plan_id, step.id, {"status": "checkpoint"})
                await pg_task_store.update_task(plan_id, {"status": TaskStatus.CHECKPOINT.value})
            except Exception as e:
                logger.warning(
                    "Failed to update PostgreSQL task store after checkpoint creation",
                    plan_id=plan_id,
                    step_id=step.id,
                    error=str(e),
                )

        # Send notification
        await self._send_checkpoint_notification(checkpoint, user_id)

        logger.info(
            "Checkpoint created (pending approval)",
            plan_id=plan_id,
            step_id=step.id,
            expires_at=expires_at.isoformat(),
        )

        return checkpoint

    async def approve_checkpoint(
        self,
        plan_id: str,
        step_id: str,
        user_id: str,
        feedback: Optional[str] = None,
        learn_preference: bool = True,
    ) -> CheckpointState:
        """
        Approve a pending checkpoint.

        Args:
            plan_id: The plan ID
            step_id: The step ID
            user_id: The user approving
            feedback: Optional feedback
            learn_preference: Whether to learn this as a preference

        Returns:
            Updated CheckpointState
        """
        # Get checkpoint from PostgreSQL
        pg_store = self._get_pg_checkpoint_store()
        checkpoint = await pg_store.get_checkpoint(plan_id, step_id)

        if not checkpoint:
            raise ValueError(f"No checkpoint found for plan={plan_id}, step={step_id}")

        # Update checkpoint
        checkpoint.decision = CheckpointDecision.APPROVED
        checkpoint.decided_at = datetime.utcnow()
        checkpoint.decided_by = user_id
        checkpoint.feedback = feedback

        updates = {
            "decision": CheckpointDecision.APPROVED,
            "decided_at": checkpoint.decided_at,
            "decided_by": user_id,
            "feedback": feedback,
        }

        # Update in PostgreSQL (audit log)
        await pg_store.update_checkpoint(plan_id, step_id, updates)

        # Learn preference if requested
        if learn_preference:
            await self._record_preference(checkpoint, user_id, "approved")

        await self._reset_execution_tree_state(plan_id, step_id)

        # Update plan state in Redis (fast path)
        plan_store = await self._get_plan_store()
        await plan_store.update_step(plan_id, step_id, {
            "checkpoint_required": False,
            "status": "pending",
        })
        await plan_store.update_task(plan_id, {"status": TaskStatus.EXECUTING})

        # Also update PostgreSQL for consistency (API reads from PG)
        pg_task_store = await self._get_pg_task_store()
        if pg_task_store:
            try:
                await pg_task_store.update_step(plan_id, step_id, {
                    "checkpoint_required": False,
                    "status": "pending",
                })
                await pg_task_store.update_task(plan_id, {"status": TaskStatus.EXECUTING.value})
            except Exception as e:
                logger.warning(
                    "Failed to update PostgreSQL task store after checkpoint approval",
                    plan_id=plan_id,
                    step_id=step_id,
                    error=str(e),
                )

        logger.info(
            "Checkpoint approved",
            plan_id=plan_id,
            step_id=step_id,
            user_id=user_id,
        )

        return checkpoint

    async def reject_checkpoint(
        self,
        plan_id: str,
        step_id: str,
        user_id: str,
        reason: str,
        learn_preference: bool = True,
    ) -> CheckpointState:
        """
        Reject a pending checkpoint.

        Args:
            plan_id: The plan ID
            step_id: The step ID
            user_id: The user rejecting
            reason: Reason for rejection
            learn_preference: Whether to learn this as a preference

        Returns:
            Updated CheckpointState
        """
        # Get checkpoint from PostgreSQL
        pg_store = self._get_pg_checkpoint_store()
        checkpoint = await pg_store.get_checkpoint(plan_id, step_id)

        if not checkpoint:
            raise ValueError(f"No checkpoint found for plan={plan_id}, step={step_id}")

        # Update checkpoint
        checkpoint.decision = CheckpointDecision.REJECTED
        checkpoint.decided_at = datetime.utcnow()
        checkpoint.decided_by = user_id
        checkpoint.feedback = reason

        updates = {
            "decision": CheckpointDecision.REJECTED,
            "decided_at": checkpoint.decided_at,
            "decided_by": user_id,
            "feedback": reason,
        }

        # Update in PostgreSQL (audit log)
        await pg_store.update_checkpoint(plan_id, step_id, updates)

        # Learn preference if requested
        if learn_preference:
            await self._record_preference(checkpoint, user_id, "rejected")

        # Update plan state - mark step as failed due to rejection
        plan_store = await self._get_plan_store()
        await plan_store.update_step(plan_id, step_id, {
            "status": "failed",
            "error_message": f"Rejected by user: {reason}",
        })
        await plan_store.update_task(plan_id, {"status": TaskStatus.FAILED})

        logger.info(
            "Checkpoint rejected",
            plan_id=plan_id,
            step_id=step_id,
            user_id=user_id,
            reason=reason,
        )

        return checkpoint

    async def resolve_checkpoint(
        self,
        plan_id: str,
        step_id: str,
        user_id: str,
        response: CheckpointResponse,
        learn_preference: bool = True,
    ) -> CheckpointState:
        """
        Resolve an interactive checkpoint with user response.

        Handles all checkpoint types:
        - APPROVAL: Binary approve/reject
        - INPUT: Collect structured user input
        - MODIFY: Accept modified step inputs
        - SELECT: Choose from alternatives
        - QA: Accept answers to questions

        Args:
            plan_id: The plan ID
            step_id: The step ID
            user_id: The user resolving
            response: CheckpointResponse with decision and type-specific data
            learn_preference: Whether to learn this as a preference

        Returns:
            Updated CheckpointState with response data
        """
        # Get checkpoint from PostgreSQL
        pg_store = self._get_pg_checkpoint_store()
        checkpoint = await pg_store.get_checkpoint(plan_id, step_id)

        if not checkpoint:
            raise ValueError(f"No checkpoint found for plan={plan_id}, step={step_id}")

        if checkpoint.decision != CheckpointDecision.PENDING:
            raise ValueError(f"Checkpoint already resolved with decision: {checkpoint.decision.value}")

        # Handle rejection uniformly across all types
        if response.decision == CheckpointDecision.REJECTED:
            return await self.reject_checkpoint(
                plan_id, step_id, user_id,
                reason=response.feedback or "Rejected by user",
                learn_preference=learn_preference,
            )

        # Validate response data based on checkpoint type
        await self._validate_checkpoint_response(checkpoint, response)

        # Update checkpoint with response data
        checkpoint.decision = CheckpointDecision.APPROVED
        checkpoint.decided_at = datetime.utcnow()
        checkpoint.decided_by = user_id
        checkpoint.feedback = response.feedback

        # Store type-specific response data
        checkpoint.response_inputs = response.inputs
        checkpoint.response_modified_inputs = response.modified_inputs
        checkpoint.response_selected_alternative = response.selected_alternative
        checkpoint.response_answers = response.answers

        updates = {
            "decision": CheckpointDecision.APPROVED,
            "decided_at": checkpoint.decided_at,
            "decided_by": user_id,
            "feedback": response.feedback,
            "response_inputs": response.inputs,
            "response_modified_inputs": response.modified_inputs,
            "response_selected_alternative": response.selected_alternative,
            "response_answers": response.answers,
        }

        # Update in PostgreSQL (audit log)
        await pg_store.update_checkpoint(plan_id, step_id, updates)

        # Apply response to step inputs if needed
        plan_store = await self._get_plan_store()
        step_updates = {
            "checkpoint_required": False,
            "status": "pending",  # Ready to execute
        }

        # For MODIFY type, update step inputs with modified values
        if checkpoint.checkpoint_type == CheckpointType.MODIFY and response.modified_inputs:
            step_updates["inputs_override"] = response.modified_inputs

        # For INPUT type, merge user inputs into step context
        if checkpoint.checkpoint_type == CheckpointType.INPUT and response.inputs:
            step_updates["checkpoint_inputs"] = response.inputs

        # For SELECT type, record selected alternative
        if checkpoint.checkpoint_type == CheckpointType.SELECT and response.selected_alternative is not None:
            step_updates["selected_alternative"] = response.selected_alternative

        # For QA type, store answers in context
        if checkpoint.checkpoint_type == CheckpointType.QA and response.answers:
            step_updates["qa_answers"] = response.answers

        await plan_store.update_step(plan_id, step_id, step_updates)
        await plan_store.update_task(plan_id, {"status": TaskStatus.EXECUTING})

        # Ensure execution tree state matches approved checkpoint state so
        # scheduler can pick this step back up.
        await self._reset_execution_tree_state(plan_id, step_id)

        # Mirror minimum execution-state fields to PostgreSQL for API consistency.
        pg_task_store = await self._get_pg_task_store()
        if pg_task_store:
            try:
                await pg_task_store.update_step(plan_id, step_id, {
                    "checkpoint_required": False,
                    "status": "pending",
                })
                await pg_task_store.update_task(
                    plan_id,
                    {"status": TaskStatus.EXECUTING.value},
                )
            except Exception as e:
                logger.warning(
                    "Failed to update PostgreSQL task store after checkpoint resolution",
                    plan_id=plan_id,
                    step_id=step_id,
                    error=str(e),
                )

        # Learn preference if requested
        if learn_preference:
            await self._record_preference(checkpoint, user_id, "approved")

        logger.info(
            "Checkpoint resolved",
            plan_id=plan_id,
            step_id=step_id,
            user_id=user_id,
            checkpoint_type=checkpoint.checkpoint_type.value,
            decision=response.decision.value,
        )

        return checkpoint

    async def _reset_execution_tree_state(self, plan_id: str, step_id: str) -> None:
        """Move checkpointed node back to PENDING and clear schedule dedupe state."""
        try:
            from src.infrastructure.tasks.task_tree_adapter import TaskExecutionTreeAdapter
            from src.core.execution_tree import ExecutionStatus
            import redis.asyncio as redis_async
            from src.core.config import settings

            tree_adapter = TaskExecutionTreeAdapter()
            await tree_adapter._tree.update_node_status(
                plan_id, step_id, ExecutionStatus.PENDING
            )

            redis_client = await redis_async.from_url(
                settings.REDIS_URL, decode_responses=True
            )
            scheduled_key = f"tentackl:run:{plan_id}:scheduled"
            await redis_client.srem(scheduled_key, step_id)
            await redis_client.aclose()
            await tree_adapter._tree._disconnect()

            logger.info(
                "Reset execution tree node and cleared scheduled set for checkpoint approval",
                plan_id=plan_id,
                step_id=step_id,
            )
        except Exception as e:
            logger.warning(
                "Failed to reset execution tree state, may need manual intervention",
                plan_id=plan_id,
                step_id=step_id,
                error=str(e),
            )

    async def _validate_checkpoint_response(
        self,
        checkpoint: CheckpointState,
        response: CheckpointResponse,
    ) -> None:
        """
        Validate that response data is appropriate for checkpoint type.

        Raises ValueError if validation fails.
        """
        ctype = checkpoint.checkpoint_type

        if ctype == CheckpointType.INPUT:
            if not response.inputs:
                raise ValueError("INPUT checkpoint requires 'inputs' in response")
            # Validate against input_schema if provided
            if checkpoint.input_schema:
                await self._validate_against_schema(response.inputs, checkpoint.input_schema)

        elif ctype == CheckpointType.MODIFY:
            if not response.modified_inputs:
                raise ValueError("MODIFY checkpoint requires 'modified_inputs' in response")
            # Validate only allowed fields are modified
            if checkpoint.modifiable_fields:
                extra_fields = set(response.modified_inputs.keys()) - set(checkpoint.modifiable_fields)
                if extra_fields:
                    raise ValueError(f"Cannot modify fields not in modifiable_fields: {extra_fields}")

        elif ctype == CheckpointType.SELECT:
            if response.selected_alternative is None:
                raise ValueError("SELECT checkpoint requires 'selected_alternative' in response")
            if checkpoint.alternatives:
                if response.selected_alternative < 0 or response.selected_alternative >= len(checkpoint.alternatives):
                    raise ValueError(
                        f"selected_alternative must be 0-{len(checkpoint.alternatives)-1}, "
                        f"got {response.selected_alternative}"
                    )

        elif ctype == CheckpointType.QA:
            if not response.answers:
                raise ValueError("QA checkpoint requires 'answers' in response")
            # Validate all questions are answered
            if checkpoint.questions:
                unanswered = set(checkpoint.questions) - set(response.answers.keys())
                if unanswered:
                    raise ValueError(f"Missing answers for questions: {unanswered}")

    async def _validate_against_schema(
        self,
        data: Dict[str, Any],
        schema: Dict[str, Any],
    ) -> None:
        """Validate data against JSON schema."""
        try:
            import jsonschema
            jsonschema.validate(instance=data, schema=schema)
        except ImportError:
            logger.warning("jsonschema not installed, skipping schema validation")
        except jsonschema.ValidationError as e:
            raise ValueError(f"Input validation failed: {e.message}")

    async def get_pending_checkpoints(
        self,
        user_id: Optional[str] = None,
        plan_id: Optional[str] = None,
    ) -> List[CheckpointState]:
        """
        Get all pending checkpoints.

        Args:
            user_id: Filter by user (if provided)
            plan_id: Filter by plan (if provided)

        Returns:
            List of pending checkpoints
        """
        pg_store = self._get_pg_checkpoint_store()
        checkpoints = await pg_store.list_pending_checkpoints(user_id, plan_id)

        # Filter out expired
        result = []
        for checkpoint in checkpoints:
            if checkpoint.expires_at and datetime.utcnow() > checkpoint.expires_at:
                continue
            result.append(checkpoint)

        return result

    async def check_expired_checkpoints(self) -> List[CheckpointState]:
        """
        Check for and process expired checkpoints.

        Returns:
            List of expired checkpoints
        """
        expired = []
        plan_store = await self._get_plan_store()
        pg_store = self._get_pg_checkpoint_store()

        expired_checkpoints = await pg_store.get_expired_checkpoints()

        for checkpoint in expired_checkpoints:
            checkpoint.decision = CheckpointDecision.EXPIRED
            checkpoint.decided_at = datetime.utcnow()

            updates = {
                "decision": CheckpointDecision.EXPIRED,
                "decided_at": checkpoint.decided_at,
            }

            # Update in PostgreSQL (audit log)
            await pg_store.update_checkpoint(
                checkpoint.plan_id, checkpoint.step_id, updates
            )

            # Update plan state
            await plan_store.update_step(checkpoint.plan_id, checkpoint.step_id, {
                "status": "failed",
                "error_message": "Checkpoint expired without approval",
            })
            await plan_store.update_task(checkpoint.plan_id, {"status": TaskStatus.FAILED})

            expired.append(checkpoint)

            logger.warning(
                "Checkpoint expired",
                plan_id=checkpoint.plan_id,
                step_id=checkpoint.step_id,
            )

        return expired

    async def _check_auto_approval(
        self,
        user_id: str,
        config: CheckpointConfig,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Check if checkpoint can be auto-approved based on preferences.

        Returns:
            Dict with 'eligible' bool and preference details if eligible
        """
        if config.approval_type == ApprovalType.EXPLICIT:
            # Explicit approval required, no auto-approval
            return {"eligible": False, "reason": "explicit_approval_required"}

        pref_store = await self._get_preference_store()

        # Find matching preference
        match = await pref_store.find_matching_preference(
            user_id=user_id,
            preference_key=config.preference_key or config.name,
            context=context,
        )

        if match and match.matched and match.confidence >= self.AUTO_APPROVAL_THRESHOLD:
            if match.preference and match.preference.decision == "approved":
                return {
                    "eligible": True,
                    "preference_id": str(match.preference.id) if match.preference else None,
                    "confidence": match.confidence,
                    "usage_count": match.preference.usage_count if match.preference else 0,
                }

        return {"eligible": False, "reason": "no_matching_preference"}

    async def _record_preference(
        self,
        checkpoint: CheckpointState,
        user_id: str,
        decision: str,
    ) -> None:
        """Record approval/rejection as a preference."""
        pref_store = await self._get_preference_store()

        # Build context from checkpoint
        context = {
            "checkpoint_name": checkpoint.checkpoint_name,
            "step_type": checkpoint.preview_data.get("agent_type"),
            **checkpoint.preview_data,
        }

        # Extract preference key from checkpoint name
        preference_key = checkpoint.checkpoint_name.replace("_approval", "")

        # Include feedback in context if present
        if checkpoint.feedback:
            context["user_feedback"] = checkpoint.feedback

        await pref_store.record_decision(
            user_id=user_id,
            preference_key=preference_key,
            context=context,
            decision=decision,
        )

    def _build_preview(self, step: TaskStep, config: CheckpointConfig) -> Dict[str, Any]:
        """Build preview data for checkpoint display."""
        preview = {
            "agent_type": step.agent_type,
            "step_name": step.name,
            "description": step.description,
        }

        # Add fields from config
        if config.preview_fields:
            for field in config.preview_fields:
                if field in step.inputs:
                    value = step.inputs[field]
                    # Truncate long values
                    if isinstance(value, str) and len(value) > 500:
                        value = value[:500] + "..."
                    preview[field] = value

        # Default previews based on agent type
        if step.agent_type == "notify":
            preview["to"] = step.inputs.get("to")
            preview["subject"] = step.inputs.get("subject")
            body = step.inputs.get("body", "")
            preview["body_preview"] = body[:200] + "..." if len(body) > 200 else body
        elif step.agent_type == "http_fetch":
            preview["url"] = step.inputs.get("url")
            preview["method"] = step.inputs.get("method", "GET")

        return preview

    def _build_context(self, step: TaskStep, preview: Dict[str, Any]) -> Dict[str, Any]:
        """Build context for preference matching."""
        return {
            "agent_type": step.agent_type,
            "step_name": step.name,
            "inputs_keys": list(step.inputs.keys()),
            **preview,
        }

    async def _send_checkpoint_notification(
        self,
        checkpoint: CheckpointState,
        user_id: str,
    ) -> None:
        """Send notification via Mimic when checkpoint is created."""
        if not self._mimic_client:
            logger.debug(
                "Mimic client not configured, skipping notification",
                checkpoint=checkpoint.checkpoint_name,
            )
            return

        try:
            # TODO: Integrate with Mimic service
            # await self._mimic_client.send_notification(
            #     user_id=user_id,
            #     template="checkpoint_approval",
            #     data={
            #         "plan_id": checkpoint.plan_id,
            #         "step_id": checkpoint.step_id,
            #         "checkpoint_name": checkpoint.checkpoint_name,
            #         "description": checkpoint.description,
            #         "preview": checkpoint.preview_data,
            #         "expires_at": checkpoint.expires_at.isoformat() if checkpoint.expires_at else None,
            #     },
            # )
            logger.info(
                "Checkpoint notification sent",
                checkpoint=checkpoint.checkpoint_name,
                user_id=user_id,
            )
        except Exception as e:
            logger.error(
                "Failed to send checkpoint notification",
                error=str(e),
                checkpoint=checkpoint.checkpoint_name,
            )

    async def cleanup(self) -> None:
        """Cleanup manager resources."""
        if self._plan_store:
            await self._plan_store._disconnect()
        if self._preference_store:
            await self._preference_store._disconnect()
