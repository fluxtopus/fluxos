"""Application use cases for task setup and trigger cloning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional
import uuid
import re
import structlog

from src.domain.tasks.ports import TaskExecutionTreePort, TaskPersistencePort
from src.domain.tasks.planning_helpers import assign_parallel_groups
from src.domain.tasks.risk_detector import RiskDetectorService
from src.domain.tasks.models import Task, TaskStep, TaskStatus, StepStatus


logger = structlog.get_logger(__name__)


@dataclass
class CreateTaskWithStepsUseCase:
    """Creates a task with pre-defined steps and durable tree setup."""

    task_store: TaskPersistencePort
    tree_port: TaskExecutionTreePort
    risk_detector: Optional[RiskDetectorService] = None
    register_trigger: Optional[Callable[[Task], Awaitable[None]]] = None

    async def execute(
        self,
        user_id: str,
        organization_id: Optional[str],
        goal: str,
        steps: List[Dict[str, Any]],
        constraints: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Task:
        logger.info(
            "Creating plan with steps",
            user_id=user_id,
            goal=goal[:100],
            step_count=len(steps),
        )

        plan_steps = self._build_plan_steps(steps)
        self._resolve_name_dependencies(plan_steps)

        plan = Task(
            goal=goal,
            user_id=user_id,
            organization_id=organization_id,
            steps=plan_steps,
            constraints=constraints or {},
            metadata=metadata or {},
            status=TaskStatus.READY,
        )

        if self.risk_detector:
            assessments = self.risk_detector.assess_plan(plan_steps)
            for step in plan_steps:
                if not step.checkpoint_required and step.id in assessments:
                    assessment = assessments[step.id]
                    if assessment.requires_checkpoint:
                        step.checkpoint_required = True
                        step.checkpoint_config = assessment.checkpoint_config
                        logger.debug(
                            "Added checkpoint via risk detection",
                            step_id=step.id,
                            risk_type=assessment.risks[0]["type"] if assessment.risks else "unknown",
                        )

        assign_parallel_groups(plan_steps)
        await self.task_store.create_task(plan)

        tree_id = await self.tree_port.create_task_tree(plan)
        plan.tree_id = tree_id
        await self.task_store.update_task(plan.id, {"tree_id": tree_id})
        logger.info("Created execution tree for task", task_id=plan.id, tree_id=tree_id)

        plan.status = TaskStatus.READY
        await self.task_store.update_task(plan.id, {"status": TaskStatus.READY.value})

        if self.register_trigger:
            await self.register_trigger(plan)

        logger.info(
            "Plan with steps created",
            plan_id=plan.id,
            checkpoints_added=sum(1 for s in plan_steps if s.checkpoint_required),
            status=plan.status.value,
        )
        return plan

    def _build_plan_steps(self, steps: List[Dict[str, Any]]) -> List[TaskStep]:
        plan_steps: List[TaskStep] = []
        for i, step_data in enumerate(steps):
            if isinstance(step_data, TaskStep):
                step = step_data
            else:
                step_payload = dict(step_data)
                step_payload.setdefault("id", f"step_{i+1}")
                if not step_payload.get("name"):
                    step_payload["name"] = step_payload["id"]
                if not step_payload.get("agent_type"):
                    step_payload["agent_type"] = step_payload.get("type", "agent")
                step_payload.setdefault("description", "")
                step_payload.setdefault("domain", None)
                step_payload.setdefault("inputs", {})
                step_payload.setdefault("outputs", {})
                step_payload.setdefault("dependencies", [])
                step_payload.setdefault("status", StepStatus.PENDING.value)

                checkpoint_config = step_payload.get("checkpoint_config")
                if checkpoint_config is not None and hasattr(checkpoint_config, "to_dict"):
                    step_payload["checkpoint_config"] = checkpoint_config.to_dict()

                fallback_config = step_payload.get("fallback_config")
                if fallback_config is not None and hasattr(fallback_config, "to_dict"):
                    step_payload["fallback_config"] = fallback_config.to_dict()

                failure_policy = step_payload.get("failure_policy")
                if failure_policy is not None and hasattr(failure_policy, "value"):
                    step_payload["failure_policy"] = failure_policy.value

                step = TaskStep.from_dict(step_payload)
            plan_steps.append(step)
        return plan_steps

    def _resolve_name_dependencies(self, plan_steps: List[TaskStep]) -> None:
        name_to_id = {step.name: step.id for step in plan_steps}
        for step in plan_steps:
            step.dependencies = [name_to_id.get(dep, dep) for dep in step.dependencies]


@dataclass
class CloneTaskForTriggerUseCase:
    """Clones task templates for event trigger execution."""

    task_store: TaskPersistencePort
    tree_port: TaskExecutionTreePort

    async def execute(self, template_task_id: str, trigger_event: Dict[str, Any]) -> Task:
        template = await self.task_store.get_task(template_task_id)
        if not template:
            raise ValueError(f"Template task not found: {template_task_id}")

        logger.info(
            "Cloning task for trigger",
            template_task_id=template_task_id,
            event_id=trigger_event.get("id"),
            event_type=trigger_event.get("type"),
        )

        cloned_steps: List[TaskStep] = []
        for step in template.steps:
            cloned_steps.append(
                TaskStep(
                    id=step.id,
                    name=step.name,
                    description=step.description,
                    agent_type=step.agent_type,
                    domain=step.domain,
                    inputs=self._substitute_trigger_data(step.inputs, trigger_event),
                    outputs={},
                    dependencies=step.dependencies.copy(),
                    status=StepStatus.PENDING,
                    parallel_group=step.parallel_group,
                    failure_policy=step.failure_policy,
                    checkpoint_required=step.checkpoint_required,
                    checkpoint_config=step.checkpoint_config,
                    fallback_config=step.fallback_config,
                    is_critical=step.is_critical,
                    retry_count=0,
                    max_retries=step.max_retries,
                )
            )

        cloned_metadata = {
            k: v for k, v in template.metadata.items()
            if k != "trigger"
        }
        cloned_metadata.update({
            "template_task_id": template_task_id,
            "trigger_event": trigger_event,
            "triggered_at": datetime.utcnow().isoformat(),
            "source": "trigger",
        })

        cloned = Task(
            id=str(uuid.uuid4()),
            user_id=template.user_id,
            organization_id=template.organization_id,
            goal=template.goal,
            steps=cloned_steps,
            status=TaskStatus.READY,
            constraints=template.constraints.copy(),
            success_criteria=template.success_criteria.copy(),
            max_parallel_steps=template.max_parallel_steps,
            metadata=cloned_metadata,
        )

        await self.task_store.create_task(cloned)

        tree_id = await self.tree_port.create_task_tree(cloned)
        cloned.tree_id = tree_id
        await self.task_store.update_task(cloned.id, {"tree_id": tree_id})
        logger.debug(
            "Created execution tree for cloned task",
            task_id=cloned.id,
            tree_id=tree_id,
        )

        logger.info(
            "Task cloned for trigger execution",
            template_task_id=template_task_id,
            cloned_task_id=cloned.id,
            event_id=trigger_event.get("id"),
            step_count=len(cloned_steps),
        )
        return cloned

    def _substitute_trigger_data(self, data: Any, trigger_event: Dict[str, Any]) -> Any:
        if isinstance(data, str):
            if "${trigger_event." not in data:
                return data

            pattern = r"\$\{trigger_event\.([^}]+)\}"

            def replace_match(match):
                path = match.group(1)
                value = self._get_nested_trigger_value(trigger_event, path)
                if value is None:
                    return match.group(0)
                return str(value)

            return re.sub(pattern, replace_match, data)

        if isinstance(data, dict):
            return {k: self._substitute_trigger_data(v, trigger_event) for k, v in data.items()}

        if isinstance(data, list):
            return [self._substitute_trigger_data(item, trigger_event) for item in data]

        return data

    def _get_nested_trigger_value(self, trigger_event: Dict[str, Any], path: str) -> Any:
        current: Any = trigger_event
        for key in path.split("."):
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current
