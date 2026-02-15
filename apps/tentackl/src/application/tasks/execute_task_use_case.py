"""Application use case for task execution lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional
import asyncio
import structlog

from src.domain.tasks.ports import (
    TaskOrchestratorPort,
    TaskPlanStorePort,
    TaskPlanningStorePort,
    TaskStatusTransitionPort,
    TaskSchedulerPort,
    TaskExecutionEventBusPort,
    TaskConversationPort,
    PreferenceLearningPort,
)
from src.domain.tasks import InvalidTransitionError
from src.domain.checkpoints import CheckpointDecision, CheckpointResponse, CheckpointState
from src.domain.tasks.models import TaskStatus, StepStatus, Finding


logger = structlog.get_logger(__name__)


@dataclass
class TaskExecutionUseCase:
    """Orchestrates execution and checkpoint flows for tasks."""

    orchestrator: TaskOrchestratorPort
    plan_store: TaskPlanStorePort
    task_store: TaskPlanningStorePort
    status_transition: TaskStatusTransitionPort
    scheduler: TaskSchedulerPort
    event_bus: TaskExecutionEventBusPort
    conversation_port: TaskConversationPort
    checkpoint_manager: Any
    preference_service: Optional[PreferenceLearningPort] = None

    async def execute_plan(
        self,
        plan_id: str,
        user_id: str,
        run_to_completion: bool = False,
    ) -> Dict[str, Any]:
        """Execute a delegation plan and return execution payload."""
        logger.info(
            "Starting plan execution",
            plan_id=plan_id,
            user_id=user_id,
            run_to_completion=run_to_completion,
        )

        plan = await self._get_task_for_execution(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        if plan.user_id != user_id:
            raise PermissionError(f"User {user_id} does not own plan {plan_id}")

        try:
            await self.status_transition.transition(plan_id, TaskStatus.EXECUTING)
        except InvalidTransitionError as exc:
            if plan.status != TaskStatus.EXECUTING:
                raise ValueError(f"Cannot start execution: {exc.message}")

        from src.database.models import TriggerType, ConversationStatus
        await self.orchestrator.start_conversation(
            workflow_id=plan_id,
            trigger_type=TriggerType.API_CALL,
            trigger_source="delegation_service",
            trigger_details={"plan_id": plan_id, "user_id": user_id, "goal": plan.goal[:500]},
        )

        max_cycles = len(plan.steps) * 3
        cycles = 0

        try:
            while cycles < max_cycles:
                cycles += 1

                result = await self.orchestrator.execute_cycle(plan_id)
                status = result.get("status")

                logger.debug(
                    "Cycle completed",
                    plan_id=plan_id,
                    cycle=cycles,
                    status=status,
                )

                if status == "completed":
                    return await self._build_execution_result(plan_id, "completed", result)

                if status in ("failed", "error"):
                    return await self._build_execution_result(plan_id, "failed", result)

                if status == "checkpoint":
                    plan = await self._get_task_for_execution(plan_id)
                    step_id = result.get("step_id")
                    step = plan.get_step_by_id(step_id) if plan else None
                    checkpoint_state = None
                    if step:
                        checkpoint_state = await self.checkpoint_manager.create_checkpoint(
                            plan_id=plan_id,
                            step=step,
                            user_id=user_id,
                        )

                    if checkpoint_state and checkpoint_state.decision == CheckpointDecision.AUTO_APPROVED:
                        logger.info(
                            "Checkpoint auto-approved by preferences, continuing",
                            plan_id=plan_id,
                            step_id=step_id,
                        )
                        continue

                    if run_to_completion:
                        await self.checkpoint_manager.approve_checkpoint(
                            plan_id, step_id, user_id,
                            feedback="Auto-approved (run_to_completion)",
                            learn_preference=False,
                        )
                        continue

                    return await self._build_execution_result(plan_id, "checkpoint", result)

                if status == "blocked":
                    return await self._build_execution_result(plan_id, "blocked", result)

                if status in ("step_completed", "step_retry", "step_fallback", "step_skipped", "step_modified"):
                    continue

                if status == "plan_aborted":
                    return await self._build_execution_result(plan_id, "aborted", result)

                if status == "replan_checkpoint":
                    plan = await self._get_task_for_execution(plan_id)
                    step_id = result.get("step_id")
                    step = plan.get_step_by_id(step_id) if plan else None
                    if step:
                        await self.checkpoint_manager.create_checkpoint(
                            plan_id=plan_id,
                            step=step,
                            user_id=user_id,
                        )

                    if run_to_completion:
                        replan_result = await self.approve_replan(
                            plan_id, step_id, user_id,
                            feedback="Auto-approved replan (run_to_completion)",
                        )
                        if replan_result.get("status") == "replan_complete":
                            plan_id = replan_result["new_plan_id"]
                            continue
                        return await self._build_execution_result(plan_id, "replan_failed", replan_result)

                    return await self._build_execution_result(plan_id, "replan_checkpoint", result)

                if status == "replan_complete":
                    new_plan_id = result.get("new_plan_id")
                    if new_plan_id:
                        plan_id = new_plan_id
                        continue
                    return await self._build_execution_result(plan_id, "replan_error", result)

                logger.warning(
                    "Unknown execution status",
                    plan_id=plan_id,
                    status=status,
                )

            return await self._build_execution_result(
                plan_id, "max_cycles_reached",
                {"error": f"Exceeded {max_cycles} cycles"},
            )
        finally:
            from src.database.models import ConversationStatus
            await self.orchestrator.end_conversation(ConversationStatus.COMPLETED)

    async def start_plan_async(self, plan_id: str, user_id: str) -> Dict[str, Any]:
        """Start plan execution asynchronously."""
        plan = await self._get_task_for_execution(plan_id)
        if not plan:
            return {"error": "Plan not found", "status": "error"}

        if plan.user_id != user_id:
            return {"error": "Access denied", "status": "error"}

        try:
            plan = await self.status_transition.transition(plan_id, TaskStatus.EXECUTING)
        except InvalidTransitionError as exc:
            current_task = await self.task_store.get_task(plan_id)
            if current_task and current_task.status == TaskStatus.EXECUTING:
                logger.info(
                    "Task already executing, scheduling any pending steps",
                    task_id=plan_id,
                    status=current_task.status.value,
                )
                if not current_task.tree_id:
                    return {
                        "status": "error",
                        "task_id": plan_id,
                        "error": "Task is missing execution tree metadata.",
                    }
                try:
                    scheduled_count = await self.scheduler.schedule_ready_nodes(plan_id)
                    logger.info(
                        "Scheduled ready steps for already-executing task",
                        plan_id=plan_id,
                        scheduled_count=scheduled_count,
                    )
                except Exception as sched_exc:
                    logger.error(
                        "Failed to schedule ready steps for already-executing task",
                        plan_id=plan_id,
                        error=str(sched_exc),
                    )
                    return {
                        "status": "error",
                        "task_id": plan_id,
                        "error": f"Failed to schedule ready steps: {sched_exc}",
                    }
                return {
                    "status": "already_executing",
                    "task_id": plan_id,
                    "task": current_task.to_dict() if current_task else None,
                    "message": "Task is already executing. Connect to observe endpoint for updates.",
                }
            return {
                "error": f"Cannot start task: {exc.message}",
                "status": "error",
                "current_status": exc.current_status.value,
            }

        await self.conversation_port.ensure_conversation(plan_id, plan.goal, user_id)

        await self.event_bus.task_started(
            task_id=plan_id,
            goal=plan.goal,
            step_count=len(plan.steps) if plan.steps else 0,
            user_id=user_id,
        )

        if not plan.tree_id:
            logger.error(
                "Task start aborted: missing execution tree metadata",
                plan_id=plan_id,
            )
            try:
                await self.status_transition.transition(plan_id, TaskStatus.FAILED)
            except InvalidTransitionError:
                logger.warning("Could not transition to FAILED state", plan_id=plan_id)
            return {
                "status": "error",
                "plan_id": plan_id,
                "error": "Task is missing execution tree metadata.",
            }

        try:
            scheduled_count = await self.scheduler.schedule_ready_nodes(plan_id)
            logger.info(
                "Scheduled ready steps via execution tree",
                plan_id=plan_id,
                scheduled_count=scheduled_count,
            )
            return {
                "status": "started",
                "plan_id": plan_id,
                "scheduled_steps": scheduled_count,
                "message": "Execution started via durable tree. Connect to observe endpoint for updates.",
            }
        except Exception as exc:
            logger.error(
                "Failed to schedule via execution tree",
                plan_id=plan_id,
                error=str(exc),
            )
            try:
                await self.status_transition.transition(plan_id, TaskStatus.FAILED)
            except InvalidTransitionError:
                logger.warning("Could not transition to FAILED state", plan_id=plan_id)
            return {"error": str(exc), "status": "error"}

    async def approve_checkpoint(
        self,
        plan_id: str,
        step_id: str,
        user_id: str,
        feedback: Optional[str] = None,
        learn_preference: bool = True,
    ) -> CheckpointState:
        plan = await self.task_store.get_task(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")
        if plan.user_id != user_id:
            raise PermissionError(f"User {user_id} does not own plan {plan_id}")

        step = plan.get_step_by_id(step_id) if plan else None
        is_replan = step and step.inputs and step.inputs.get("_replan_context")

        checkpoint = await self.checkpoint_manager.approve_checkpoint(
            plan_id=plan_id,
            step_id=step_id,
            user_id=user_id,
            feedback=feedback,
            learn_preference=learn_preference,
        )

        logger.info(
            "Checkpoint approved",
            plan_id=plan_id,
            step_id=step_id,
            user_id=user_id,
            is_replan=is_replan,
        )
        await self._continue_execution_after_checkpoint_approval(plan_id, step_id)

        return checkpoint

    async def reject_checkpoint(
        self,
        plan_id: str,
        step_id: str,
        user_id: str,
        reason: str,
        learn_preference: bool = True,
    ) -> CheckpointState:
        plan = await self.task_store.get_task(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")
        if plan.user_id != user_id:
            raise PermissionError(f"User {user_id} does not own plan {plan_id}")

        checkpoint = await self.checkpoint_manager.reject_checkpoint(
            plan_id=plan_id,
            step_id=step_id,
            user_id=user_id,
            reason=reason,
            learn_preference=learn_preference,
        )

        logger.info(
            "Checkpoint rejected",
            plan_id=plan_id,
            step_id=step_id,
            user_id=user_id,
            reason=reason,
        )

        await self.conversation_port.add_checkpoint_resolution_message(
            task_id=plan_id,
            approved=False,
            reason=reason,
        )

        return checkpoint

    async def approve_replan(
        self,
        plan_id: str,
        step_id: str,
        user_id: str,
        feedback: Optional[str] = None,
    ) -> Dict[str, Any]:
        logger.info(
            "Approving replan",
            plan_id=plan_id,
            step_id=step_id,
            user_id=user_id,
        )

        plan = await self.task_store.get_task(plan_id)
        if not plan:
            return {"status": "error", "error": f"Plan not found: {plan_id}"}

        if plan.user_id != user_id:
            return {"status": "error", "error": "Permission denied"}

        result = await self.orchestrator.execute_replan(plan_id, step_id)

        if result.get("status") == "replan_complete":
            finding = Finding(
                step_id=step_id,
                type="replan_approved",
                content={
                    "user_id": user_id,
                    "feedback": feedback,
                    "new_plan_id": result.get("new_plan_id"),
                    "new_plan_version": result.get("new_plan_version"),
                },
            )
            await self.plan_store.add_finding(plan_id, finding)

            if self.preference_service:
                step = plan.get_step_by_id(step_id)
                if step:
                    replan_context = step.inputs.get("_replan_context", {})
                    await self.preference_service.learn_from_replan(
                        user_id=user_id,
                        plan_id=plan_id,
                        diagnosis=replan_context.get("diagnosis", ""),
                        approved=True,
                    )

            logger.info(
                "Replan approved and executed",
                plan_id=plan_id,
                new_plan_id=result.get("new_plan_id"),
            )

        return result

    async def reject_replan(
        self,
        plan_id: str,
        step_id: str,
        user_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        logger.info(
            "Rejecting replan",
            plan_id=plan_id,
            step_id=step_id,
            user_id=user_id,
            reason=reason,
        )

        plan = await self.task_store.get_task(plan_id)
        if not plan:
            return {"status": "error", "error": f"Plan not found: {plan_id}"}

        if plan.user_id != user_id:
            return {"status": "error", "error": "Permission denied"}

        await self.plan_store.update_step(plan_id, step_id, {
            "status": "failed",
            "error_message": f"Replan rejected: {reason}",
        })
        try:
            await self.status_transition.transition(plan_id, TaskStatus.FAILED)
        except InvalidTransitionError:
            logger.warning("Could not transition to FAILED", plan_id=plan_id)

        finding = Finding(
            step_id=step_id,
            type="replan_rejected",
            content={"user_id": user_id, "reason": reason},
        )
        await self.plan_store.add_finding(plan_id, finding)

        return {
            "status": "replan_rejected",
            "plan_id": plan_id,
            "reason": reason,
        }

    async def resolve_checkpoint(
        self,
        plan_id: str,
        step_id: str,
        user_id: str,
        response: CheckpointResponse,
        learn_preference: bool = True,
    ) -> CheckpointState:
        plan = await self.task_store.get_task(plan_id)
        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        if plan.user_id != user_id:
            raise PermissionError(f"User {user_id} does not own plan {plan_id}")

        checkpoint = await self.checkpoint_manager.resolve_checkpoint(
            plan_id=plan_id,
            step_id=step_id,
            user_id=user_id,
            response=response,
            learn_preference=learn_preference,
        )

        logger.info(
            "Checkpoint resolved via service",
            plan_id=plan_id,
            step_id=step_id,
            user_id=user_id,
            decision=response.decision.value,
        )

        if response.decision == CheckpointDecision.APPROVED:
            await self._continue_execution_after_checkpoint_approval(plan_id, step_id)
        elif response.decision == CheckpointDecision.REJECTED:
            await self.conversation_port.add_checkpoint_resolution_message(
                task_id=plan_id,
                approved=False,
                reason=response.feedback or "Rejected by user",
            )

        return checkpoint

    async def _continue_execution_after_checkpoint_approval(
        self,
        plan_id: str,
        step_id: str,
    ) -> None:
        plan = await self.task_store.get_task(plan_id)
        step = plan.get_step_by_id(step_id) if plan else None
        is_replan = bool(step and step.inputs and step.inputs.get("_replan_context"))

        await self.conversation_port.add_checkpoint_resolution_message(
            task_id=plan_id,
            approved=True,
        )

        if is_replan:
            logger.info(
                "Executing replan after checkpoint approval",
                plan_id=plan_id,
                step_id=step_id,
            )
            await self.orchestrator.execute_replan(plan_id, step_id)
            return

        logger.info(
            "Continuing execution after checkpoint approval",
            plan_id=plan_id,
            step_id=step_id,
        )
        if plan and plan.tree_id:
            try:
                scheduled_count = await self.scheduler.schedule_ready_nodes(plan_id)
                logger.info(
                    "Scheduled ready steps after checkpoint approval",
                    plan_id=plan_id,
                    step_id=step_id,
                    scheduled_count=scheduled_count,
                )
                return
            except Exception as exc:
                logger.warning(
                    "Failed to schedule via execution tree, falling back to orchestrator",
                    plan_id=plan_id,
                    step_id=step_id,
                    error=str(exc),
                )
        await self.orchestrator.execute_cycle(plan_id)

    async def _get_task_for_execution(self, plan_id: str):
        plan = await self.plan_store.get_task(plan_id)
        if plan:
            return plan
        return await self.task_store.get_task(plan_id)

    async def _build_execution_result(
        self,
        plan_id: str,
        status: str,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        steps_completed = result.get("steps_completed", 0)
        steps_total = result.get("steps_total", 0)

        if steps_total == 0:
            try:
                plan = await self._get_task_for_execution(plan_id)
                if plan:
                    steps_total = len(plan.steps) if plan.steps else 0
                    steps_completed = sum(
                        1 for step in plan.steps if step.status == StepStatus.DONE
                    )
            except Exception:
                pass

        return {
            "plan_id": plan_id,
            "status": status,
            "steps_completed": steps_completed,
            "steps_total": steps_total,
            "findings": result.get("accumulated_findings", []),
            "checkpoint": result.get("checkpoint"),
            "error": result.get("error"),
        }
