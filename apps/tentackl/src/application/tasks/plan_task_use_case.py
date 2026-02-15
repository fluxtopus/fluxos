"""Application use case for task planning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import asyncio
import uuid
import structlog

from src.domain.tasks.ports import (
    PlanningIntentPort,
    FastPathPlannerPort,
    AutomationSchedulerPort,
    PlanCancellationPort,
    PlanningEventBusPort,
    TaskPlanningStorePort,
    TaskStatusTransitionPort,
    TaskExecutionTreePort,
    TaskPlannerPort,
)
from src.domain.tasks.planning_helpers import assign_parallel_groups
from src.domain.tasks.planning_models import PlanningIntent, ScheduleSpec
from src.domain.tasks.models import TaskStatus, TaskStep
from src.domain.tasks.risk_detector import RiskDetectorService


logger = structlog.get_logger(__name__)


@dataclass
class PlanTaskUseCase:
    """Orchestrates the planning pipeline for a task."""

    intent_port: PlanningIntentPort
    fast_path_planner: FastPathPlannerPort
    automation_scheduler: AutomationSchedulerPort
    cancellation_port: PlanCancellationPort
    event_bus: PlanningEventBusPort
    task_store: TaskPlanningStorePort
    status_transition: TaskStatusTransitionPort
    tree_port: TaskExecutionTreePort
    planner: TaskPlannerPort
    risk_detector: Optional[RiskDetectorService] = None

    async def plan_task(
        self,
        task_id: str,
        user_id: str,
        organization_id: str,
        goal: str,
        constraints: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        skip_spec_matching: bool = False,
    ) -> TaskStatus:
        from src.database.models import TriggerType, ConversationStatus

        try:
            await self.event_bus.planning_started(task_id, goal)

            if await self.cancellation_port.is_cancelled(task_id):
                return TaskStatus.PLANNING

            intent = await self.intent_port.extract_intent(goal)
            schedule = self._normalize_schedule(intent)

            if schedule:
                schedule_label = schedule.cron or (
                    schedule.execute_at.isoformat() if schedule.execute_at else "unknown"
                )
                await self.event_bus.planning_intent_detected(
                    task_id,
                    "schedule",
                    schedule_label,
                )

                if intent and intent.one_shot_goal and len(intent.one_shot_goal) >= 10:
                    goal = intent.one_shot_goal

            if await self.cancellation_port.is_cancelled(task_id):
                return TaskStatus.PLANNING

            fast_path_task = await self.fast_path_planner.try_fast_path(
                user_id=user_id,
                organization_id=organization_id,
                goal=goal,
                intent_info=intent,
                metadata=metadata,
            )
            if fast_path_task:
                await self.event_bus.planning_fast_path(task_id, "Direct data retrieval")
                update_data = {
                    "steps": [
                        s.to_dict() if hasattr(s, "to_dict") else s
                        for s in (fast_path_task.steps or [])
                    ],
                    "metadata": fast_path_task.metadata,
                    "completed_at": fast_path_task.completed_at,
                }
                await self.task_store.update_task(task_id, update_data)
                await self.status_transition.transition(task_id, TaskStatus.COMPLETED)
                await self.event_bus.planning_completed(
                    task_id,
                    len(fast_path_task.steps or []),
                    "fast_path",
                )
                return TaskStatus.COMPLETED

            if await self.cancellation_port.is_cancelled(task_id):
                return TaskStatus.PLANNING

            await self.event_bus.planning_llm_started(task_id)

            await self.planner.start_conversation(
                workflow_id=str(uuid.uuid4()),
                trigger_type=TriggerType.API_CALL,
                trigger_source="delegation_service",
                trigger_details={"goal": goal[:500], "user_id": user_id},
            )

            try:
                steps: List[TaskStep] = []
                max_retries = 3
                retry_delay = 2.0

                for attempt in range(max_retries):
                    if await self.cancellation_port.is_cancelled(task_id):
                        return TaskStatus.PLANNING

                    try:
                        steps = await self.planner.generate_delegation_steps(
                            goal,
                            constraints=constraints,
                            skip_validation=skip_spec_matching,
                        )
                        if steps:
                            break
                        logger.warning(
                            "Empty steps returned, retrying",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                        )
                        if attempt < max_retries - 1:
                            await self.event_bus.planning_llm_retry(
                                task_id,
                                attempt + 1,
                                max_retries,
                                "Empty steps returned",
                            )
                    except Exception as exc:
                        logger.warning(
                            "Step generation failed, retrying",
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            error=str(exc),
                        )
                        if attempt < max_retries - 1:
                            await self.event_bus.planning_llm_retry(
                                task_id,
                                attempt + 1,
                                max_retries,
                                str(exc),
                            )

                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (attempt + 1))

                if not steps:
                    logger.error("Failed to generate steps after all retries", max_retries=max_retries)
                    raise Exception("Failed to generate plan steps after all retries")
            finally:
                await self.planner.end_conversation(ConversationStatus.COMPLETED)

            step_names = [s.name for s in steps]
            await self.event_bus.planning_steps_generated(task_id, len(steps), step_names)

            if await self.cancellation_port.is_cancelled(task_id):
                return TaskStatus.PLANNING

            checkpoints_added = 0
            if steps and self.risk_detector:
                assessments = self.risk_detector.assess_plan(steps)
                for step in steps:
                    if not step.checkpoint_required and step.id in assessments:
                        assessment = assessments[step.id]
                        if assessment.requires_checkpoint:
                            step.checkpoint_required = True
                            step.checkpoint_config = assessment.checkpoint_config
                            checkpoints_added += 1

            await self.event_bus.planning_risk_detection(task_id, checkpoints_added)

            if steps:
                assign_parallel_groups(steps)

            task_metadata = metadata.copy() if metadata else {}
            update_data = {
                "steps": [s.to_dict() if hasattr(s, "to_dict") else s for s in steps],
                "metadata": task_metadata,
            }
            await self.task_store.update_task(task_id, update_data)

            plan = await self.task_store.get_task(task_id)
            if not plan:
                raise RuntimeError(f"Task missing during execution tree creation: {task_id}")
            tree_id = await self.tree_port.create_task_tree(plan)
            await self.task_store.update_task(task_id, {"tree_id": tree_id})
            logger.info("Created execution tree for task", task_id=task_id, tree_id=tree_id)

            await self.status_transition.transition(task_id, TaskStatus.READY)
            await self.event_bus.planning_completed(task_id, len(steps), "llm")

            logger.info("Plan created", plan_id=task_id, user_id=user_id, step_count=len(steps))

            if schedule:
                try:
                    await self.automation_scheduler.create_automation_for_task(
                        task_id=task_id,
                        user_id=user_id,
                        organization_id=organization_id,
                        goal=goal,
                        schedule=schedule,
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to create automation from scheduling intent",
                        task_id=task_id,
                        error=str(exc),
                    )

            return TaskStatus.READY

        except asyncio.CancelledError:
            logger.info("Planning cancelled via asyncio", task_id=task_id)
            try:
                await self.status_transition.transition(task_id, TaskStatus.CANCELLED)
            except Exception:
                pass
            return TaskStatus.CANCELLED
        except Exception as exc:
            logger.error("Planning failed", task_id=task_id, error=str(exc))
            try:
                await self.task_store.update_task(
                    task_id,
                    {"metadata": {**(metadata or {}), "planning_error": str(exc)}},
                )
                await self.status_transition.transition(task_id, TaskStatus.FAILED)
                await self.event_bus.planning_failed(task_id, str(exc))
            except Exception as inner_exc:
                logger.error(
                    "Failed to update task after planning error",
                    task_id=task_id,
                    error=str(inner_exc),
                )
            return TaskStatus.FAILED

    def _normalize_schedule(self, intent: Optional[PlanningIntent]) -> Optional[ScheduleSpec]:
        if not intent or not intent.has_schedule or not intent.schedule:
            return None

        schedule = intent.schedule
        if schedule.execute_at is None and schedule.execute_at_raw:
            raw = schedule.execute_at_raw
            if isinstance(raw, str) and raw.startswith("+"):
                offset_str = raw[1:]
                try:
                    if offset_str.endswith("m"):
                        delta = timedelta(minutes=int(offset_str[:-1]))
                    elif offset_str.endswith("h"):
                        delta = timedelta(hours=int(offset_str[:-1]))
                    elif offset_str.endswith("s"):
                        delta = timedelta(seconds=int(offset_str[:-1]))
                    else:
                        delta = timedelta(minutes=int(offset_str))
                    schedule.execute_at = datetime.utcnow() + delta
                except (ValueError, TypeError):
                    logger.warning("Could not parse execute_at offset", raw=raw)

        return schedule
