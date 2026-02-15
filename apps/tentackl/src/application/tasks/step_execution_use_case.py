"""Application use case for executing a single task step.

Orchestrates the full step lifecycle — initialisation, checkpoint handling,
plugin execution, store sync, event publishing, inbox messaging,
dependency scheduling, and task finalization — via domain ports so that the
Celery worker is reduced to a thin composition root.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
import structlog

from src.domain.tasks.models import TaskStep, StepStatus
from src.domain.tasks.ports import (
    TaskExecutionTreePort,
    TaskPlanStorePort,
    TaskPlanningStorePort,
    TaskExecutionEventBusPort,
    TaskSchedulerPort,
    StepInboxMessagingPort,
    StepPluginExecutorPort,
    StepCheckpointPort,
    StepModelSelectorPort,
)


logger = structlog.get_logger(__name__)


def _is_transient_error(error_msg: str) -> bool:
    """Check if an error message indicates a transient/retryable failure."""
    indicators = [
        "timeout", "timed out", "rate limit", "temporary",
        "try again", "503", "429", "connection", "ECONNREFUSED",
    ]
    error_lower = (error_msg or "").lower()
    return any(ind.lower() in error_lower for ind in indicators)


@dataclass
class StepExecutionResult:
    """Value object returned by ``StepExecutionUseCase.execute``."""

    status: str  # "success" | "error" | "retrying" | "checkpoint"
    task_id: str
    step_id: str
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_step_data: Optional[Dict[str, Any]] = None


@dataclass
class StepExecutionUseCase:
    """Orchestrates a single step execution through domain ports."""

    tree: TaskExecutionTreePort
    plan_store: TaskPlanStorePort
    task_store: TaskPlanningStorePort
    event_bus: TaskExecutionEventBusPort
    scheduler: TaskSchedulerPort
    inbox: StepInboxMessagingPort
    plugin: StepPluginExecutorPort
    model_selector: StepModelSelectorPort
    checkpoint: StepCheckpointPort

    async def execute(self, task_id: str, step_data: dict) -> StepExecutionResult:
        """Execute a single task step and return the result."""
        step_id = step_data.get("id")

        logger.info(
            "Executing task step via use case",
            task_id=task_id,
            step_id=step_id,
            agent_type=step_data.get("agent_type"),
        )

        # 1. Initialise the step
        step = await self._initialize_step(task_id, step_id, step_data)

        # 2. Mark RUNNING in execution tree
        await self.tree.start_step(task_id, step_id)

        # 3. Handle checkpoint if required (may return early)
        if step.checkpoint_required:
            checkpoint_result = await self._handle_checkpoint(task_id, step_id, step, step_data)
            if checkpoint_result is not None:
                return checkpoint_result

        # 4. Select model
        model = self.model_selector.select_model(
            agent_type=step_data.get("agent_type", ""),
            explicit_model=step_data.get("model"),
        )

        # 5. Build execution context from PG task (trusted source)
        org_id = None
        file_references = None
        try:
            plan = await self.task_store.get_task(task_id)
            if plan:
                if plan.organization_id:
                    org_id = plan.organization_id
                if plan.constraints and plan.constraints.get("file_references"):
                    file_references = plan.constraints["file_references"]
        except Exception:
            pass

        # 6. Execute plugin
        result = await self.plugin.execute(
            step=step,
            model=model,
            task_id=task_id,
            org_id=org_id,
            step_id=step_id,
            file_references=file_references,
        )

        # 7. Handle result
        if result.success:
            return await self._handle_success(task_id, step_id, step, result)
        else:
            return await self._handle_failure(task_id, step_id, step, result, step_data)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _initialize_step(
        self, task_id: str, step_id: str, step_data: dict,
    ) -> TaskStep:
        """Get step from tree or reconstruct from step_data as fallback."""
        step = await self.tree.get_step_from_tree(task_id, step_id)
        if not step:
            logger.warning(
                "Step not found in tree, reconstructing from step_data",
                task_id=task_id,
                step_id=step_id,
            )
            step = TaskStep.from_dict(step_data)
        else:
            # Use resolved inputs from step_data (StepDispatcher resolves templates)
            resolved_inputs = step_data.get("inputs", {})
            if resolved_inputs:
                from dataclasses import replace
                step = replace(step, inputs=resolved_inputs)
                logger.debug(
                    "Using resolved inputs from step_data",
                    task_id=task_id,
                    step_id=step_id,
                    input_keys=list(resolved_inputs.keys()),
                )
        return step

    async def _handle_checkpoint(
        self,
        task_id: str,
        step_id: str,
        step: TaskStep,
        step_data: dict,
    ) -> Optional[StepExecutionResult]:
        """Handle checkpoint logic. Returns a result if execution should stop."""
        if await self.checkpoint.is_already_approved(task_id, step_id):
            logger.info(
                "Checkpoint already approved, proceeding with execution",
                task_id=task_id,
                step_id=step_id,
            )
            step.checkpoint_required = False
            return None

        logger.info(
            "Step requires checkpoint, pausing for approval",
            task_id=task_id,
            step_id=step_id,
        )

        # Pause in execution tree
        await self.tree.pause_step(task_id, step_id)

        # Sync to both stores
        checkpoint_updates = {"status": StepStatus.CHECKPOINT.value}
        await self.plan_store.update_step(task_id, step_id, checkpoint_updates)
        await self.task_store.update_step(task_id, step_id, checkpoint_updates)

        task_checkpoint_updates = {"status": "checkpoint"}
        await self.plan_store.update_task(task_id, task_checkpoint_updates)
        await self.task_store.update_task(task_id, task_checkpoint_updates)

        # Create checkpoint for user approval
        await self.checkpoint.create_checkpoint(
            task_id=task_id,
            step=step,
            user_id=step_data.get("user_id", "system"),
        )

        # Publish event
        await self.event_bus.checkpoint_created(
            task_id=task_id,
            step_id=step_id,
            checkpoint_name=step.name or step_id,
            preview={"description": step.description},
        )

        # Inbox message
        await self.inbox.add_checkpoint_message(
            task_id=task_id,
            step_id=step_id,
            step_name=step.name or step_id,
            description=step.description or "",
        )

        return StepExecutionResult(
            status="checkpoint",
            task_id=task_id,
            step_id=step_id,
        )

    async def _handle_success(
        self,
        task_id: str,
        step_id: str,
        step: TaskStep,
        result: Any,
    ) -> StepExecutionResult:
        """Process a successful step execution."""
        outputs = result.output or {}

        # Complete in execution tree
        await self.tree.complete_step(task_id, step_id, outputs)

        # Sync to both stores
        updates = {
            "status": StepStatus.DONE.value,
            "outputs": outputs,
            "completed_at": datetime.utcnow().isoformat(),
            "execution_time_ms": result.execution_time_ms,
        }
        await self.plan_store.update_step(task_id, step_id, updates)
        await self.task_store.update_step(task_id, step_id, updates)

        # Publish event
        await self.event_bus.step_completed(
            task_id=task_id,
            step_id=step_id,
            step_name=step.name or step_id,
            output=outputs,
        )

        # Inbox message
        await self.inbox.add_step_message(
            task_id=task_id,
            step_name=step.name or step_id,
            event_type="completed",
            text=f"{step.name or step_id} — done.",
            data={"step_id": step_id, "outputs": outputs},
        )

        logger.info(
            "Task step completed successfully",
            task_id=task_id,
            step_id=step_id,
            execution_time_ms=result.execution_time_ms,
        )

        # Schedule dependent steps
        try:
            scheduled_count = await self.scheduler.schedule_ready_nodes(task_id)
            logger.info(
                "Scheduled dependent steps",
                task_id=task_id,
                completed_step=step_id,
                scheduled_count=scheduled_count,
            )
        except Exception as sched_error:
            logger.warning(
                "Failed to schedule dependent steps",
                task_id=task_id,
                step_id=step_id,
                error=str(sched_error),
            )

        # Check task finalization
        await self._check_task_finalization(task_id)

        return StepExecutionResult(
            status="success",
            task_id=task_id,
            step_id=step_id,
            output=outputs,
        )

    async def _handle_failure(
        self,
        task_id: str,
        step_id: str,
        step: TaskStep,
        result: Any,
        step_data: dict,
    ) -> StepExecutionResult:
        """Process a failed step execution. May trigger retry."""
        error_msg = result.error or "Step execution failed"

        retry_count = step_data.get("retry_count", 0)
        max_retries = step_data.get("max_retries", 3)

        if retry_count < max_retries and _is_transient_error(error_msg):
            return await self._handle_retry(
                task_id, step_id, step, error_msg, retry_count, max_retries, step_data,
            )

        # Permanent failure
        await self.tree.fail_step(task_id, step_id, error_msg)

        updates = {
            "status": StepStatus.FAILED.value,
            "error_message": error_msg,
            "completed_at": datetime.utcnow().isoformat(),
            "execution_time_ms": result.execution_time_ms,
        }
        await self.plan_store.update_step(task_id, step_id, updates)
        await self.task_store.update_step(task_id, step_id, updates)

        await self.event_bus.step_failed(
            task_id=task_id,
            step_id=step_id,
            step_name=step.name or step_id,
            error=error_msg,
        )

        await self.inbox.add_step_message(
            task_id=task_id,
            step_name=step.name or step_id,
            event_type="failed",
            text=f"{step.name or step_id} — failed: {error_msg}",
            data={"step_id": step_id, "error": error_msg},
        )

        logger.error(
            "Task step failed",
            task_id=task_id,
            step_id=step_id,
            error=error_msg,
        )

        # Check if task should be marked as failed
        is_complete, final_status = await self.tree.is_task_complete(task_id)
        if is_complete and final_status == "failed":
            await self._finalize_task(task_id, "failed", error=error_msg)

        return StepExecutionResult(
            status="error",
            task_id=task_id,
            step_id=step_id,
            error=error_msg,
        )

    async def _handle_retry(
        self,
        task_id: str,
        step_id: str,
        step: TaskStep,
        error_msg: str,
        retry_count: int,
        max_retries: int,
        step_data: dict,
    ) -> StepExecutionResult:
        """Handle a transient error by preparing retry data."""
        new_retry_count = retry_count + 1

        # Reset step in execution tree
        await self.tree.reset_step(task_id, step_id)

        retry_updates = {
            "status": StepStatus.PENDING.value,
            "retry_count": new_retry_count,
            "error_message": f"Retry {new_retry_count}/{max_retries}: {error_msg}",
        }
        await self.plan_store.update_step(task_id, step_id, retry_updates)
        await self.task_store.update_step(task_id, step_id, retry_updates)

        await self.event_bus.step_started(
            task_id=task_id,
            step_id=step_id,
            step_name=step.name or step_id,
        )

        logger.info(
            "Step retrying after transient error",
            task_id=task_id,
            step_id=step_id,
            retry=f"{new_retry_count}/{max_retries}",
            error=error_msg,
        )

        # Return retry data so the Celery wrapper can re-dispatch
        retry_step_data = dict(step_data)
        retry_step_data["retry_count"] = new_retry_count

        return StepExecutionResult(
            status="retrying",
            task_id=task_id,
            step_id=step_id,
            retry_step_data=retry_step_data,
        )

    async def _check_task_finalization(self, task_id: str) -> None:
        """Check if the task is complete and finalize if so."""
        is_complete, final_status = await self.tree.is_task_complete(task_id)
        if is_complete:
            status_value = "completed" if final_status == "completed" else "failed"
            await self._finalize_task(task_id, status_value)

    async def _finalize_task(
        self,
        task_id: str,
        status_value: str,
        error: Optional[str] = None,
    ) -> None:
        """Finalize a task by updating stores, publishing events, and sending inbox message."""
        now = datetime.utcnow()

        await self.plan_store.update_task(task_id, {
            "status": status_value,
            "completed_at": now,
        })
        await self.task_store.update_task(task_id, {
            "status": status_value,
            "completed_at": now,
        })

        # Get metrics for event and inbox message
        metrics = await self.tree.get_tree_metrics(task_id)
        # Subtract 1 for root node which is always completed
        steps_completed = max(0, metrics.get("status_counts", {}).get("completed", 1) - 1)
        total_steps = max(0, metrics.get("total_nodes", 1) - 1)

        await self.event_bus.task_completed(
            task_id=task_id,
            steps_completed=steps_completed,
        )

        await self.inbox.add_completion_message(
            task_id=task_id,
            status=status_value,
            steps_completed=steps_completed,
            total_steps=total_steps,
            error=error,
        )

        logger.info(
            "Task finalized",
            task_id=task_id,
            final_status=status_value,
        )
