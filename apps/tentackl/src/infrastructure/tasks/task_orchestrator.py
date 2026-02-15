"""
# REVIEW:
# - Orchestrator is very large; mixes planning, execution, memory injection, and observer logic in one class.
# - RedisTaskStore connections are opened lazily without explicit close.

Delegation Orchestrator Agent

A stateless orchestrator that executes ONE step group per cycle from the plan document.
Each invocation starts fresh - no context accumulation.

The orchestrator:
1. Loads the plan document fresh
2. Finds the next ready step group (may contain parallel steps)
3. Checks for checkpoint requirements
4. Dispatches to appropriate subagent(s) - parallel if grouped
5. Updates the plan with results
6. Exits (context cleared)

Parallel Execution:
- Steps with the same parallel_group run concurrently
- Steps without parallel_group run individually
- Respects max_parallel_steps limit from the plan
- Handles failure_policy per group (ALL_OR_NOTHING, BEST_EFFORT, FAIL_FAST)
"""

import asyncio
import re
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import structlog

from src.agents.llm_agent import LLMAgent
from src.agents.base import AgentConfig
from src.domain.tasks.models import (
    Task,
    TaskStep,
    Finding,
    TaskStatus,
    StepStatus,
    ProposalType,
    ParallelFailurePolicy,
    CheckpointRequiredError,
    CheckpointConfig,
)
from src.domain.memory import MemoryOperationsPort
from src.domain.memory.models import MemoryQuery
from src.domain.tasks.ports import (
    TaskPlanStorePort,
    TaskObserverPort,
    TaskPlannerPort,
    TaskStepDispatchPort,
)
from src.llm.openrouter_client import OpenRouterClient
from src.infrastructure.execution_runtime.plugin_executor import execute_step
from src.eval.format_validators import validate_template_syntax_quick


logger = structlog.get_logger(__name__)


def _load_orchestrator_prompt() -> str:
    """Load the orchestrator system prompt from external file."""
    prompt_path = Path(__file__).parent / "prompts" / "task_orchestrator_prompt.md"
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Strip markdown title
        if content.startswith("# Delegation Orchestrator"):
            lines = content.split("\n", 2)
            content = lines[2] if len(lines) > 2 else content
        return content.strip()
    except FileNotFoundError:
        logger.warning("Orchestrator prompt not found, using fallback", path=str(prompt_path))
        return """<system>
You are the Delegation Orchestrator. Execute ONE step per cycle, then exit.
You are STATELESS - read the plan fresh each invocation.
</system>"""


ORCHESTRATOR_PROMPT_TEMPLATE = _load_orchestrator_prompt()


class TaskOrchestratorAgent(LLMAgent):
    """
    Stateless orchestrator for autonomous task delegation.

    Each execute() call:
    1. Loads plan fresh (no accumulated context)
    2. Executes exactly ONE step
    3. Updates plan with result
    4. Returns (context cleared next cycle)

    This design prevents context window degradation over long-running tasks.

    Execution Modes:
    - "in_process": Execute steps directly in the API process (default, simpler)
    - "queue": Enqueue steps to Redis queue for worker processing (scalable)

    Use "queue" mode when you need horizontal scaling for thousands of concurrent plans.
    """

    def __init__(
        self,
        name: str = "delegation-orchestrator",
        model: str = "x-ai/grok-4.1-fast",
        llm_client: Optional[OpenRouterClient] = None,
        plan_store: Optional[TaskPlanStorePort] = None,
        observer: Optional[TaskObserverPort] = None,
        planner: Optional[TaskPlannerPort] = None,
        step_dispatcher: Optional[TaskStepDispatchPort] = None,
        enable_conversation_tracking: bool = True,  # Track LLM calls for usage monitoring
        execution_mode: str = "queue",  # "queue" for horizontal scaling
        memory_service: Optional[MemoryOperationsPort] = None,  # Memory service for prompt injection
    ):
        # Create config for the LLM agent
        config = AgentConfig(
            name=name,
            agent_type="task_orchestrator",
            metadata={
                "model": model,
                "temperature": 0.2,  # Low temperature for consistent execution
                "system_prompt": "",  # Will be set dynamically per cycle
            }
        )

        super().__init__(
            config=config,
            llm_client=llm_client,
            enable_conversation_tracking=enable_conversation_tracking,
        )

        self.model = model
        self._plan_store = plan_store
        self._subagent_factory = None  # Lazy loaded
        self._observer: Optional[TaskObserverPort] = observer
        self._planner: Optional[TaskPlannerPort] = planner
        self._step_dispatcher: Optional[TaskStepDispatchPort] = step_dispatcher
        self._execution_mode = execution_mode
        self._memory_service = memory_service  # Memory service for prompt injection

    async def _get_plan_store(self) -> TaskPlanStorePort:
        """Get or create plan store."""
        if not self._plan_store:
            raise RuntimeError("TaskOrchestratorAgent requires a TaskPlanStorePort")
        await self._plan_store.connect()
        return self._plan_store

    def _get_observer(self) -> TaskObserverPort:
        """Get or create observer agent for failure analysis."""
        if not self._observer:
            raise RuntimeError("TaskOrchestratorAgent requires a TaskObserverPort")
        return self._observer

    def _get_planner(self) -> TaskPlannerPort:
        """Get or create planner for strategic replanning."""
        if not self._planner:
            raise RuntimeError("TaskOrchestratorAgent requires a TaskPlannerPort")
        return self._planner

    async def _build_prompt(self, plan: Task, current_step: TaskStep) -> str:
        """Build the orchestrator prompt with plan context and injected memories."""
        prompt = ORCHESTRATOR_PROMPT_TEMPLATE

        # Replace placeholders
        prompt = prompt.replace("{{plan_document}}", plan.to_xml())
        prompt = prompt.replace("{{current_step}}", json.dumps(current_step.to_dict(), indent=2))
        prompt = prompt.replace(
            "{{accumulated_findings}}",
            json.dumps([f.to_dict() for f in plan.accumulated_findings], indent=2)
        )
        prompt = prompt.replace("{{max_tokens}}", "2000")

        # Inject memories if memory service is available
        memories_fragment = await self._inject_memories(plan, current_step)
        prompt = prompt.replace("{{memories}}", memories_fragment)

        return prompt

    async def _inject_memories(self, plan: Task, current_step: TaskStep) -> str:
        """
        Inject relevant memories into the prompt.

        Queries the memory service for memories relevant to the current task
        and step, then formats them for prompt injection.

        Args:
            plan: The plan document containing organization_id and goal
            current_step: The current step being executed

        Returns:
            str: Formatted memories for injection, or empty string if no memories
        """
        if not self._memory_service:
            return ""

        try:
            # Build query based on plan and step context
            query = MemoryQuery(
                organization_id=plan.organization_id or "",
                text=plan.goal,
                topic=current_step.agent_type,
                requesting_user_id=plan.user_id,
            )

            # Format memories for injection with token budget
            memories_fragment = await self._memory_service.format_for_injection(
                query, max_tokens=2000
            )

            logger.debug(
                "Injected memories into orchestrator prompt",
                plan_id=plan.id,
                step_id=current_step.id,
                memories_length=len(memories_fragment),
            )

            return memories_fragment

        except Exception as e:
            logger.warning(
                "Failed to inject memories, continuing without",
                plan_id=plan.id,
                error=str(e),
            )
            return ""

    async def execute_cycle(self, plan_id: str) -> Dict[str, Any]:
        """
        Execute one cycle of the orchestrator.

        This is the main entry point. Each call:
        1. Loads plan fresh
        2. Finds next step
        3. Executes or pauses at checkpoint
        4. Updates plan
        5. Returns result

        Args:
            plan_id: The plan to execute

        Returns:
            Dict with cycle result (completed, checkpoint, error, etc.)
        """
        logger.info("Starting orchestrator cycle", plan_id=plan_id, agent_id=self.agent_id)

        store = await self._get_plan_store()

        # Step 1: Load plan fresh (no accumulated context)
        plan = await store.get_task(plan_id)
        if not plan:
            logger.error("Plan not found", plan_id=plan_id)
            return {
                "status": "error",
                "error": f"Plan not found: {plan_id}",
                "plan_id": plan_id,
            }

        # Check if plan is already complete or failed
        if plan.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            logger.info("Plan already terminal", plan_id=plan_id, status=plan.status.value)
            return {
                "status": plan.status.value,
                "plan_id": plan_id,
                "message": f"Plan is already {plan.status.value}",
            }

        # Step 2: Find next ready step group (may contain parallel steps)
        step_groups = plan.get_ready_steps_grouped()
        if not step_groups:
            # Check if all steps are done (DONE or SKIPPED count as complete)
            all_done = all(
                s.status in (StepStatus.DONE, StepStatus.SKIPPED)
                for s in plan.steps
            )
            if all_done:
                await store.update_task(plan_id, {
                    "status": TaskStatus.COMPLETED,
                    "completed_at": datetime.utcnow(),
                })
                return {
                    "status": "completed",
                    "plan_id": plan_id,
                    "message": "All steps completed successfully",
                    "accumulated_findings": [f.to_dict() for f in plan.accumulated_findings],
                }

            # Check if any steps are at checkpoint status needing approval
            checkpoint_steps = [
                s for s in plan.steps
                if s.status == StepStatus.CHECKPOINT
            ]
            if checkpoint_steps:
                # Return checkpoint info for the first step needing approval
                step = checkpoint_steps[0]
                logger.info(
                    "Step at checkpoint needs approval",
                    plan_id=plan_id,
                    step_id=step.id,
                )
                # Ensure plan status reflects checkpoint state
                if plan.status != TaskStatus.CHECKPOINT:
                    await store.update_task(plan_id, {"status": TaskStatus.CHECKPOINT})

                return {
                    "status": "checkpoint",
                    "plan_id": plan_id,
                    "step_id": step.id,
                    "checkpoint": {
                        "step_id": step.id,
                        "name": step.checkpoint_config.name if step.checkpoint_config else "Approval Required",
                        "description": step.checkpoint_config.description if step.checkpoint_config else f"Approve step: {step.name}",
                        "preference_key": step.checkpoint_config.preference_key if step.checkpoint_config else None,
                        "preview": self._build_checkpoint_preview(step),
                    },
                }

            # Some steps failed or blocked - check if Observer can help
            failed_steps = [s for s in plan.steps if s.status == StepStatus.FAILED]
            pending_steps = [s for s in plan.steps if s.status == StepStatus.PENDING]

            # Find pending steps that are ACTUALLY blocked by failed dependencies
            # A step is blocked only if one of its direct dependencies failed
            blocked_steps = []
            failed_step_ids = {s.id for s in failed_steps}
            for step in pending_steps:
                if step.dependencies:
                    failed_deps = [d for d in step.dependencies if d in failed_step_ids]
                    if failed_deps:
                        blocked_steps.append(step)

            # IMPORTANT: Only consult Observer if steps are ACTUALLY blocked by failed dependencies
            # If there are pending steps but none are blocked, don't trigger replan
            if failed_steps and blocked_steps:
                # We have failed steps actually blocking progress - consult Observer
                logger.info(
                    "Consulting Observer for blocked dependencies",
                    plan_id=plan_id,
                    failed_count=len(failed_steps),
                    blocked_count=len(blocked_steps),
                )

                observer = self._get_observer()
                proposal = await observer.analyze_blocked_dependencies(
                    plan, blocked_steps, failed_steps
                )

                if proposal and proposal.proposal_type == ProposalType.REPLAN:
                    logger.info(
                        "Observer proposes REPLAN for blocked state",
                        plan_id=plan_id,
                        reason=proposal.reason,
                    )
                    # Add finding about the blocked state and recovery
                    finding = Finding(
                        step_id=blocked_steps[0].id if blocked_steps else pending_steps[0].id,
                        type="observer_blocked_proposal",
                        content={
                            "proposal_type": proposal.proposal_type.value,
                            "reason": proposal.reason,
                            "confidence": proposal.confidence,
                            "failed_steps": [s.id for s in failed_steps],
                            "blocked_steps": [s.id for s in blocked_steps],
                        },
                    )
                    await store.add_finding(plan.id, finding)

                    # Apply the replan
                    return await self._apply_replan(
                        plan,
                        failed_steps[0],  # Use first failed step as trigger
                        proposal,
                        store,
                    )
                else:
                    # Observer analyzed but no recovery path found
                    # Mark the plan as failed since we can't proceed
                    logger.error(
                        "No recovery path found - marking plan as failed",
                        plan_id=plan_id,
                        failed_steps=[s.id for s in failed_steps],
                        blocked_steps=[s.id for s in blocked_steps],
                    )

                    # Add finding about unrecoverable failure
                    finding = Finding(
                        step_id=failed_steps[0].id,
                        type="unrecoverable_failure",
                        content={
                            "reason": "Observer determined no recovery path exists",
                            "failed_steps": [s.id for s in failed_steps],
                            "blocked_steps": [s.id for s in blocked_steps],
                            "failed_errors": [s.error_message for s in failed_steps],
                        },
                    )
                    await store.add_finding(plan.id, finding)

                    # Mark plan as failed
                    await store.update_task(plan_id, {"status": TaskStatus.FAILED})

                    return {
                        "status": "failed",
                        "plan_id": plan_id,
                        "message": f"Unrecoverable failure: {len(failed_steps)} step(s) failed with no recovery path",
                        "failed_steps": [s.id for s in failed_steps],
                        "errors": [s.error_message for s in failed_steps],
                    }

            logger.warning("No ready steps but plan not complete", plan_id=plan_id)
            return {
                "status": "blocked",
                "plan_id": plan_id,
                "message": "No steps ready to execute",
            }

        # Take the first group (ONE group per cycle)
        current_group = step_groups[0]
        is_parallel = len(current_group) > 1

        logger.info(
            "Found next step group",
            plan_id=plan_id,
            group_size=len(current_group),
            step_ids=[s.id for s in current_group],
            parallel=is_parallel,
            parallel_group=current_group[0].parallel_group if is_parallel else None,
        )

        # Step 3: Check for checkpoints in any step of the group
        for step in current_group:
            if step.checkpoint_required:
                # Auto-create checkpoint_config if not provided
                if not step.checkpoint_config:
                    step.checkpoint_config = CheckpointConfig(
                        name=f"Approve {step.name}",
                        description=step.description or f"Step {step.id} requires approval before execution",
                        preference_key=f"checkpoint:{step.agent_type}:{step.name}",
                    )
                    logger.debug(
                        "Auto-created checkpoint config",
                        plan_id=plan_id,
                        step_id=step.id,
                    )
                logger.info(
                    "Checkpoint required",
                    plan_id=plan_id,
                    step_id=step.id,
                    checkpoint=step.checkpoint_config.name,
                )

                # Update plan status to checkpoint
                await store.update_task(plan_id, {"status": TaskStatus.CHECKPOINT})
                await store.update_step(plan_id, step.id, {"status": "checkpoint"})

                return {
                    "status": "checkpoint",
                    "plan_id": plan_id,
                    "step_id": step.id,
                    "checkpoint": {
                        "step_id": step.id,
                        "name": step.checkpoint_config.name,
                        "description": step.checkpoint_config.description,
                        "preference_key": step.checkpoint_config.preference_key,
                        "preview": self._build_checkpoint_preview(step),
                    },
                }

        # Step 4: Execute step(s) - parallel if grouped, sequential otherwise
        for step in current_group:
            await store.update_step(plan_id, step.id, {
                "status": "running",
                "started_at": datetime.utcnow().isoformat(),
            })
        await store.update_task(plan_id, {"status": TaskStatus.EXECUTING})

        try:
            if is_parallel:
                # Execute group in parallel
                result = await self._execute_step_group(
                    plan, current_group, store, plan.max_parallel_steps
                )
            else:
                # Single step - execute directly
                result = await self._execute_step(plan, current_group[0])
                result["step_id"] = current_group[0].id

            # Step 5: Update plan with result
            # Handle enqueued status (queue mode) - return immediately
            if result.get("status") == "enqueued":
                return {
                    "status": "step_enqueued" if not is_parallel else "group_enqueued",
                    "plan_id": plan_id,
                    "step_id": result.get("step_id") if not is_parallel else None,
                    "step_ids": [s.id for s in current_group] if is_parallel else None,
                    "task_id": result.get("task_id"),
                    "next_action": "wait_for_event",  # Caller should wait for completion event
                    "parallel": is_parallel,
                    "execution_mode": "queue",
                    "message": "Step(s) enqueued for worker processing",
                }

            if result.get("status") == "success":
                # For parallel execution, results are already saved in _execute_step_group
                if not is_parallel:
                    current_step = current_group[0]
                    await store.update_step(plan_id, current_step.id, {
                        "status": "done",
                        "outputs": result.get("output", {}),
                        "completed_at": datetime.utcnow().isoformat(),
                        "execution_time_ms": result.get("execution_time_ms"),
                    })

                    # Add findings
                    for finding_data in result.get("findings", []):
                        finding = Finding(
                            step_id=current_step.id,
                            type=finding_data.get("type", current_step.agent_type),
                            content=finding_data,
                        )
                        await store.add_finding(plan_id, finding)

                return {
                    "status": "step_completed" if not is_parallel else "group_completed",
                    "plan_id": plan_id,
                    "step_id": result.get("step_id") if not is_parallel else None,
                    "step_ids": result.get("step_ids") if is_parallel else None,
                    "output": result.get("output"),
                    "outputs": result.get("outputs") if is_parallel else None,
                    "next_action": "continue",
                    "parallel": is_parallel,
                }

            else:
                # Step/group failed
                if is_parallel:
                    # Parallel group failure - result contains failure details
                    return {
                        "status": "group_failed",
                        "plan_id": plan_id,
                        "step_ids": result.get("step_ids"),
                        "failed_step_ids": result.get("failed_step_ids"),
                        "error": result.get("error"),
                        "failure_policy": result.get("failure_policy"),
                    }
                else:
                    # Single step failed - consult Observer for intelligent course correction
                    current_step = current_group[0]
                    current_step.error_message = result.get("error")
                    current_step.retry_count += 1

                    # Consult the Observer to determine recovery action
                    recovery_result = await self._handle_step_failure(
                        plan, current_step, store
                    )
                    return recovery_result

        except Exception as e:
            logger.error(
                "Step execution error",
                plan_id=plan_id,
                step_ids=[s.id for s in current_group],
                error=str(e),
            )
            for step in current_group:
                await store.update_step(plan_id, step.id, {
                    "status": "failed",
                    "error_message": str(e),
                })
            await store.update_task(plan_id, {"status": TaskStatus.FAILED})

            return {
                "status": "error",
                "plan_id": plan_id,
                "step_ids": [s.id for s in current_group],
                "error": str(e),
            }

    def _validate_template_references(self, step: TaskStep) -> None:
        """
        Validate template references in step inputs before resolution.

        Catches invalid template syntax like {{step_X.output}} (missing field name)
        or {{step_X.outputs}} (missing field name) BEFORE attempting resolution.
        This provides clear error messages instead of silent failures with empty data.

        Args:
            step: The step to validate

        Raises:
            ValueError: If invalid template syntax is found
        """
        if not step.inputs:
            return

        # Convert inputs to string for pattern matching
        inputs_str = json.dumps(step.inputs)

        # Use the eval system's template syntax validator
        is_valid, errors = validate_template_syntax_quick(inputs_str)

        if not is_valid:
            error_details = "; ".join(errors)
            logger.error(
                "Invalid template syntax in step inputs",
                step_id=step.id,
                step_name=step.name,
                errors=errors,
                inputs=step.inputs,
            )
            raise ValueError(
                f"Step '{step.id}' ({step.name}) has invalid template syntax: {error_details}. "
                f"Use {{{{step_X.outputs.field_name}}}} instead of {{{{step_X.output}}}}."
            )

    def _resolve_template_variables(self, plan: Task, step: TaskStep) -> TaskStep:
        """
        Resolve template variables in step inputs.

        Replaces {{step_X.output}} patterns with actual outputs from completed steps.
        This enables data flow between steps in the delegation plan.

        Args:
            plan: The plan document containing all steps
            step: The step whose inputs need resolution

        Returns:
            A copy of the step with resolved inputs
        """
        # Build a map of step outputs for quick lookup
        # Support lookup by BOTH step ID (step_1) AND step name (research_ai)
        step_outputs = {}
        for s in plan.steps:
            if s.status in (StepStatus.DONE, StepStatus.SKIPPED):
                step_outputs[s.id] = s.outputs
                # Also map by step name for templates like {{research_ai.output}}
                if s.name and s.name != s.id:
                    step_outputs[s.name] = s.outputs

        def resolve_value(value: Any) -> Any:
            """Recursively resolve template variables in a value."""
            if isinstance(value, str):
                # Two template syntaxes are supported:
                # 1. {{step_ref.output}}, {{step_ref.outputs.field}}, {{step_ref.output[N]}}
                #    where step_ref can be step ID (step_1) or step name (research_ai)
                # 2. ${node.step_X.field} (alternative syntax used by workflow planner)
                #
                # Pattern 1: Curly braces syntax
                # Step refs can be: step_1, step_2a, research_ai, fetch_data, etc.
                curly_pattern = r'\{\{([a-zA-Z][a-zA-Z0-9_]*)\.(output|outputs)(?:\.(\w+))?(?:\[(\d+)\])?\}\}'

                # Pattern 2: Dollar-node syntax ${node.step_X.field}
                # This is the preferred syntax from workflow planner
                dollar_pattern = r'\$\{node\.([a-zA-Z][a-zA-Z0-9_]*)\.(\w+)\}'

                def extract_value(output: Any, field: str | None, index: str | None) -> Any:
                    """Extract value from output with optional field and array index access."""
                    result = output
                    # First apply field accessor if present
                    if field and isinstance(result, dict):
                        result = result.get(field, "")
                    # Then apply array index if present
                    if index is not None and isinstance(result, list):
                        idx = int(index)
                        if 0 <= idx < len(result):
                            result = result[idx]
                        else:
                            result = ""  # Out of bounds
                    return result

                # IMPORTANT: If the entire value is JUST the template variable (no surrounding text),
                # preserve the original type (dict) for file handlers. This allows compose output
                # like {"content": "...", "character_count": 123} to be passed as-is to save_json_handler.

                # Check curly brace syntax first: {{step_X.output}}
                curly_match = re.fullmatch(curly_pattern, value)
                if curly_match:
                    step_id = curly_match.group(1)
                    field = curly_match.group(3)
                    index = curly_match.group(4)
                    if step_id in step_outputs:
                        output = step_outputs[step_id]
                        return extract_value(output, field, index)
                    return value  # Keep original if not found

                # Check dollar-node syntax: ${node.step_X.field}
                dollar_match = re.fullmatch(dollar_pattern, value)
                if dollar_match:
                    step_id = dollar_match.group(1)
                    field = dollar_match.group(2)  # Field name directly
                    if step_id in step_outputs:
                        output = step_outputs[step_id]
                        return extract_value(output, field, None)
                    return value  # Keep original if not found

                # For values with embedded templates (like "prefix {{step_1.output}} suffix"),
                # use regex substitution which serializes dicts to JSON strings
                def curly_replacer(match):
                    step_id = match.group(1)
                    field = match.group(3)
                    index = match.group(4)

                    if step_id in step_outputs:
                        output = step_outputs[step_id]
                        result = extract_value(output, field, index)
                        if isinstance(result, str):
                            # For large HTML content, truncate to avoid overwhelming LLM
                            if len(result) > 50000:
                                return result[:50000] + "\n... [content truncated]"
                            return result
                        elif isinstance(result, dict):
                            return json.dumps(result, ensure_ascii=False)
                        return str(result) if result else ""
                    return match.group(0)  # Keep original if not found

                def dollar_replacer(match):
                    step_id = match.group(1)
                    field = match.group(2)

                    if step_id in step_outputs:
                        output = step_outputs[step_id]
                        result = extract_value(output, field, None)
                        if isinstance(result, str):
                            # For large HTML content, truncate to avoid overwhelming LLM
                            if len(result) > 50000:
                                return result[:50000] + "\n... [content truncated]"
                            return result
                        elif isinstance(result, dict):
                            return json.dumps(result, ensure_ascii=False)
                        return str(result) if result else ""
                    return match.group(0)  # Keep original if not found

                # Apply both replacement patterns
                result = re.sub(curly_pattern, curly_replacer, value)
                result = re.sub(dollar_pattern, dollar_replacer, result)
                return result
            elif isinstance(value, dict):
                return {k: resolve_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [resolve_value(item) for item in value]
            return value

        # Create a copy of the step with resolved inputs
        resolved_inputs = resolve_value(step.inputs)

        # Log if any variables were resolved
        if resolved_inputs != step.inputs:
            # DEBUG: Log resolved input sizes to trace data accumulation
            resolved_json = json.dumps(resolved_inputs, default=str)
            original_json = json.dumps(step.inputs, default=str)
            logger.info(
                "Resolved template variables in step inputs",
                step_id=step.id,
                original_keys=list(step.inputs.keys()) if isinstance(step.inputs, dict) else None,
                original_size=len(original_json),
                resolved_size=len(resolved_json),
            )
            # Log warning if resolved data is very large
            if len(resolved_json) > 50000:
                logger.warning(
                    "Resolved inputs are very large - potential context accumulation",
                    step_id=step.id,
                    resolved_size=len(resolved_json),
                )

        # Return a new step with resolved inputs
        from dataclasses import replace
        return replace(step, inputs=resolved_inputs)

    def _inject_file_storage_context(self, plan: Task, step: TaskStep) -> TaskStep:
        """
        Inject plan context into file_storage step inputs.

        File storage operations need org_id, workflow_id, agent_id which are
        available at the plan level but not in individual step definitions.
        This method also maps 'file_data' to 'content' for the upload handler.
        """
        from dataclasses import replace

        enriched_inputs = dict(step.inputs) if step.inputs else {}

        # Inject organization context from plan
        if "org_id" not in enriched_inputs and plan.organization_id:
            enriched_inputs["org_id"] = plan.organization_id

        # Inject workflow context (use plan ID as workflow ID)
        if "workflow_id" not in enriched_inputs and plan.id:
            enriched_inputs["workflow_id"] = str(plan.id)

        # Inject agent context (use step ID as agent ID)
        if "agent_id" not in enriched_inputs:
            enriched_inputs["agent_id"] = step.id

        # Map 'file_data' to 'content' for the upload handler
        if "file_data" in enriched_inputs and "content" not in enriched_inputs:
            enriched_inputs["content"] = enriched_inputs["file_data"]

        # For image uploads, try to infer content_type from filename if not provided
        operation = enriched_inputs.get("operation", "")
        if operation == "upload" and "content_type" not in enriched_inputs:
            filename = enriched_inputs.get("filename", "")
            if filename.endswith(".png"):
                enriched_inputs["content_type"] = "image/png"
            elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
                enriched_inputs["content_type"] = "image/jpeg"
            elif filename.endswith(".webp"):
                enriched_inputs["content_type"] = "image/webp"
            elif filename.endswith(".gif"):
                enriched_inputs["content_type"] = "image/gif"
            elif filename.endswith(".json"):
                enriched_inputs["content_type"] = "application/json"

        logger.debug(
            "Injected file storage context",
            step_id=step.id,
            org_id=enriched_inputs.get("org_id"),
            workflow_id=enriched_inputs.get("workflow_id"),
            content_type=enriched_inputs.get("content_type"),
        )

        return replace(step, inputs=enriched_inputs)

    def _inject_image_generation_context(self, plan: Task, step: TaskStep) -> TaskStep:
        """
        Inject plan context into generate_image step inputs.

        This enables auto-upload to Den: generated images are stored in Den
        and the step output contains file URLs instead of base64 data.
        This prevents plan bloat from accumulating large image data.
        """
        from dataclasses import replace

        enriched_inputs = dict(step.inputs) if step.inputs else {}

        # Inject organization context from plan
        if "org_id" not in enriched_inputs and plan.organization_id:
            enriched_inputs["org_id"] = plan.organization_id

        # Inject workflow context (use plan ID as workflow ID)
        if "workflow_id" not in enriched_inputs and plan.id:
            enriched_inputs["workflow_id"] = str(plan.id)

        # Inject agent context (use step ID as agent ID)
        if "agent_id" not in enriched_inputs:
            enriched_inputs["agent_id"] = step.id

        # Default folder path based on plan goal (sanitized)
        if "folder_path" not in enriched_inputs:
            import re
            # Create folder from plan goal (first 30 chars, sanitized)
            goal_slug = re.sub(r'[^a-zA-Z0-9\s-]', '', plan.goal or 'images')[:30].strip()
            goal_slug = re.sub(r'\s+', '-', goal_slug).lower()
            enriched_inputs["folder_path"] = f"/generated-images/{goal_slug}"

        # Default to public images for easy sharing
        if "is_public" not in enriched_inputs:
            enriched_inputs["is_public"] = True

        logger.debug(
            "Injected image generation context",
            step_id=step.id,
            org_id=enriched_inputs.get("org_id"),
            folder_path=enriched_inputs.get("folder_path"),
        )

        return replace(step, inputs=enriched_inputs)

    async def _execute_step_group(
        self,
        plan: Task,
        steps: List[TaskStep],
        store: TaskPlanStorePort,
        max_concurrent: int = 5,
    ) -> Dict[str, Any]:
        """
        Execute a group of steps in parallel with failure policy handling.

        Args:
            plan: The plan document (for context)
            steps: The steps to execute in parallel
            store: Plan store for updates
            max_concurrent: Maximum concurrent executions

        Returns:
            Dict with group execution result
        """
        if not steps:
            return {"status": "success", "outputs": {}, "step_ids": []}

        # Determine failure policy - use the first step's policy (all should match)
        failure_policy = steps[0].failure_policy

        logger.info(
            "Executing parallel step group",
            plan_id=plan.id,
            step_ids=[s.id for s in steps],
            failure_policy=failure_policy.value,
            max_concurrent=max_concurrent,
        )

        # Create semaphore for limiting concurrency
        semaphore = asyncio.Semaphore(max_concurrent)

        async def execute_with_limit(step: TaskStep) -> Tuple[str, Dict[str, Any]]:
            """Execute a single step with semaphore limiting."""
            async with semaphore:
                result = await self._execute_step(plan, step)
                return step.id, result

        # Execute all steps concurrently
        tasks = [execute_with_limit(step) for step in steps]

        if failure_policy == ParallelFailurePolicy.FAIL_FAST:
            # Cancel remaining on first failure
            results_dict = {}
            pending = set(asyncio.create_task(t, name=f"step_{i}") for i, t in enumerate(tasks))
            first_exception = None

            while pending:
                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    try:
                        step_id, result = task.result()
                        results_dict[step_id] = result
                        # enqueued is not a failure - queue mode
                        if result.get("status") not in ("success", "enqueued") and not first_exception:
                            first_exception = result.get("error", "Step failed")
                            # Cancel remaining
                            for p in pending:
                                p.cancel()
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        if not first_exception:
                            first_exception = str(e)
                            for p in pending:
                                p.cancel()

            if first_exception:
                # Update failed steps
                await self._update_group_results(plan.id, steps, results_dict, store)
                failed_ids = [
                    sid for sid, r in results_dict.items()
                    if r.get("status") not in ("success", "enqueued")
                ]
                return {
                    "status": "error",
                    "error": first_exception,
                    "step_ids": [s.id for s in steps],
                    "failed_step_ids": failed_ids,
                    "outputs": {
                        sid: r.get("output") for sid, r in results_dict.items()
                    },
                    "failure_policy": failure_policy.value,
                }
        else:
            # BEST_EFFORT or ALL_OR_NOTHING: gather all results
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)

            results_dict = {}
            for item in raw_results:
                if isinstance(item, Exception):
                    # This shouldn't happen often since _execute_step catches exceptions
                    logger.error("Unexpected exception in parallel execution", error=str(item))
                    continue
                step_id, result = item
                results_dict[step_id] = result

        # Update all step statuses
        await self._update_group_results(plan.id, steps, results_dict, store)

        # Check for failures (enqueued is not a failure - queue mode)
        failed_results = {
            sid: r for sid, r in results_dict.items()
            if r.get("status") not in ("success", "enqueued")
        }

        # Check if all steps were enqueued (queue mode)
        all_enqueued = all(
            r.get("status") == "enqueued" for r in results_dict.values()
        )
        if all_enqueued and results_dict:
            return {
                "status": "enqueued",
                "step_ids": [s.id for s in steps],
                "task_ids": {
                    sid: r.get("task_id") for sid, r in results_dict.items()
                },
                "message": "All steps enqueued for worker processing",
            }

        if failed_results:
            if failure_policy == ParallelFailurePolicy.ALL_OR_NOTHING:
                # All fail if any fail
                first_error = list(failed_results.values())[0].get("error", "Step failed")
                return {
                    "status": "error",
                    "error": first_error,
                    "step_ids": [s.id for s in steps],
                    "failed_step_ids": list(failed_results.keys()),
                    "outputs": {
                        sid: r.get("output") for sid, r in results_dict.items()
                    },
                    "failure_policy": failure_policy.value,
                }
            else:
                # BEST_EFFORT: return partial success
                logger.warning(
                    "Parallel group partial failure (best effort)",
                    plan_id=plan.id,
                    failed_steps=list(failed_results.keys()),
                    success_count=len(results_dict) - len(failed_results),
                )
                return {
                    "status": "success",  # Best effort = partial success is success
                    "step_ids": [s.id for s in steps],
                    "failed_step_ids": list(failed_results.keys()),
                    "outputs": {
                        sid: r.get("output") for sid, r in results_dict.items()
                    },
                    "partial_failure": True,
                    "failure_policy": failure_policy.value,
                }

        # All succeeded
        return {
            "status": "success",
            "step_ids": [s.id for s in steps],
            "outputs": {
                sid: r.get("output") for sid, r in results_dict.items()
            },
            "failure_policy": failure_policy.value,
        }

    async def _update_group_results(
        self,
        plan_id: str,
        steps: List[TaskStep],
        results: Dict[str, Dict[str, Any]],
        store: TaskPlanStorePort,
    ) -> None:
        """Update step statuses based on execution results."""
        for step in steps:
            result = results.get(step.id)
            if not result:
                # Step was cancelled or didn't complete
                await store.update_step(plan_id, step.id, {
                    "status": "failed",
                    "error_message": "Execution cancelled",
                })
                continue

            if result.get("status") == "success":
                await store.update_step(plan_id, step.id, {
                    "status": "done",
                    "outputs": result.get("output", {}),
                    "completed_at": datetime.utcnow().isoformat(),
                    "execution_time_ms": result.get("execution_time_ms"),
                })

                # Add findings
                for finding_data in result.get("findings", []):
                    finding = Finding(
                        step_id=step.id,
                        type=finding_data.get("type", step.agent_type),
                        content=finding_data,
                    )
                    await store.add_finding(plan_id, finding)
            else:
                await store.update_step(plan_id, step.id, {
                    "status": "failed",
                    "error_message": result.get("error", "Unknown error"),
                })

    async def _execute_step(self, plan: Task, step: TaskStep) -> Dict[str, Any]:
        """
        Execute a single step by dispatching to appropriate plugin or agent.

        The orchestrator does NOT execute steps itself - it dispatches to
        plugins (infrastructure) or DB-configured agents (LLM). This keeps
        the orchestrator stateless and prevents context accumulation.

        In queue mode, the step is dispatched via StepDispatcher (single source
        of truth for template resolution, context injection, and Celery dispatch).
        In in_process mode (default), the step is executed directly.

        Args:
            plan: The plan document (for context)
            step: The step to execute

        Returns:
            Dict with execution result
        """
        # Queue mode dispatches through the injected port.
        # The infrastructure layer owns adapter construction.
        if self._execution_mode == "queue":
            if self._step_dispatcher is None:
                raise RuntimeError(
                    "TaskOrchestratorAgent(queue) requires TaskStepDispatchPort"
                )

            result = await self._step_dispatcher.dispatch_step(
                task_id=str(plan.id),
                step=step,
                plan=plan,
                model=self.model,
            )

            if result.get("success"):
                return {
                    "status": "enqueued",
                    "step_id": result.get("step_id", step.id),
                    "celery_task_id": result.get("celery_task_id"),
                    "message": "Step dispatched via StepDispatcher for Celery worker processing",
                }
            else:
                return {
                    "status": "error",
                    "step_id": result.get("step_id", step.id),
                    "error": result.get("error"),
                }

        # In-process mode: validate, resolve, inject, then execute directly
        # Validate template syntax BEFORE resolution to catch errors early
        self._validate_template_references(step)

        # Resolve template variables before dispatching
        resolved_step = self._resolve_template_variables(plan, step)

        # Inject plan context for file_storage and generate_image operations
        if resolved_step.agent_type == "file_storage":
            resolved_step = self._inject_file_storage_context(plan, resolved_step)
        elif resolved_step.agent_type == "generate_image":
            resolved_step = self._inject_image_generation_context(plan, resolved_step)

        logger.info(
            "Dispatching step to subagent",
            step_id=resolved_step.id,
            agent_type=resolved_step.agent_type,
            execution_mode=self._execution_mode,
        )

        return await self._execute_step_in_process(plan, resolved_step)

    async def _enqueue_step(self, plan: Task, step: TaskStep) -> Dict[str, Any]:
        """
        Enqueue a step for worker processing (queue mode).

        Kept for backward compatibility with tests and callers that explicitly
        enqueue a single step. Queue dispatch still flows through the port.
        """
        if self._step_dispatcher is None:
            raise RuntimeError(
                "TaskOrchestratorAgent(queue) requires TaskStepDispatchPort"
            )

        result = await self._step_dispatcher.dispatch_step(
            task_id=str(plan.id),
            step=step,
            plan=plan,
            model=self.model,
        )

        if result.get("success"):
            return {
                "status": "enqueued",
                "task_id": result.get("celery_task_id"),
                "step_id": result.get("step_id", step.id),
                "message": "Step enqueued for worker processing",
            }

        return {
            "status": "error",
            "step_id": result.get("step_id", step.id),
            "error": result.get("error"),
        }

    async def _execute_step_in_process(self, plan: Task, step: TaskStep) -> Dict[str, Any]:
        """
        Execute a step directly in-process (default mode).

        This is the original execution path - suitable for development
        and single-instance deployments.
        """
        try:
            # Inject organization context for brand-aware subagents
            # This allows compose/notify agents to use org-specific brand settings
            step.inputs["organization_id"] = plan.organization_id or "aios-platform"

            # Build ExecutionContext from the plan (trusted DB source)
            # This provides org_id, user_id, etc. to plugin handlers
            from src.infrastructure.execution_runtime.execution_context import ExecutionContext
            execution_context = ExecutionContext.from_plan(plan, step.id) if plan.organization_id else None

            # Dispatch to appropriate plugin or DB-configured agent
            # The step gets ONLY the inputs - minimal context
            result = await execute_step(
                step=step,
                llm_client=self.llm_client,  # Share LLM client if available
                model=self.model,
                organization_id=plan.organization_id,
                context=execution_context,
            )

            # Convert SubagentResult to dict format
            if result.success:
                return {
                    "status": "success",
                    "output": result.output,
                    "findings": [{"type": step.agent_type, **result.metadata}] if result.metadata else [],
                    "execution_time_ms": result.execution_time_ms,
                }
            else:
                return {
                    "status": "error",
                    "error": result.error or "Subagent execution failed",
                    "output": result.output,
                    "execution_time_ms": result.execution_time_ms,
                }

        except ValueError as e:
            # Unknown agent type
            logger.error("Unknown subagent type", step_id=step.id, agent_type=step.agent_type, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "execution_time_ms": 0,
            }
        except Exception as e:
            logger.error("Subagent execution error", step_id=step.id, error=str(e))
            return {
                "status": "error",
                "error": f"Subagent error: {str(e)}",
                "execution_time_ms": 0,
            }

    async def _handle_step_failure(
        self,
        plan: Task,
        failed_step: TaskStep,
        store: TaskPlanStorePort,
    ) -> Dict[str, Any]:
        """
        Handle a step failure using Observer-based intelligent course correction.

        The Observer analyzes the failure and proposes one of:
        - RETRY: Try the same step again (transient failure)
        - FALLBACK: Switch to a fallback model/API (permanent failure)
        - SKIP: Skip the step if non-critical
        - ABORT: Abort the plan if critical and no recovery

        Args:
            plan: The plan document
            failed_step: The step that failed
            store: Plan store for updates

        Returns:
            Dict with recovery result
        """
        logger.info(
            "Consulting Observer for failure recovery",
            plan_id=plan.id,
            step_id=failed_step.id,
            error=failed_step.error_message,
            retry_count=failed_step.retry_count,
        )

        # Get Observer proposal
        observer = self._get_observer()
        proposal = await observer.analyze_failure(plan, failed_step)

        logger.info(
            "Observer proposal received",
            step_id=failed_step.id,
            proposal_type=proposal.proposal_type.value,
            fallback_target=proposal.fallback_target,
            confidence=proposal.confidence,
            reason=proposal.reason,
        )

        # Add finding about the failure and recovery
        finding = Finding(
            step_id=failed_step.id,
            type="observer_proposal",
            content={
                "proposal_type": proposal.proposal_type.value,
                "reason": proposal.reason,
                "confidence": proposal.confidence,
                "fallback_target": proposal.fallback_target,
                "error": failed_step.error_message,
            },
        )
        await store.add_finding(plan.id, finding)

        # Apply the proposal
        if proposal.proposal_type == ProposalType.RETRY:
            return await self._apply_retry(plan.id, failed_step, store)

        elif proposal.proposal_type == ProposalType.FALLBACK:
            return await self._apply_fallback(
                plan.id, failed_step, proposal.fallback_target, store
            )

        elif proposal.proposal_type == ProposalType.SKIP:
            return await self._apply_skip(plan.id, failed_step, store)

        elif proposal.proposal_type == ProposalType.REPLAN:
            return await self._apply_replan(plan, failed_step, proposal, store)

        elif proposal.proposal_type == ProposalType.MODIFY:
            return await self._apply_modify(
                plan.id, failed_step, proposal.modified_inputs, store
            )

        else:  # ABORT
            return await self._apply_abort(plan.id, failed_step, proposal.reason, store)

    async def _apply_retry(
        self,
        plan_id: str,
        step: TaskStep,
        store: TaskPlanStorePort,
    ) -> Dict[str, Any]:
        """Apply RETRY proposal - mark step for retry."""
        logger.info(
            "Applying RETRY proposal",
            plan_id=plan_id,
            step_id=step.id,
            retry_count=step.retry_count,
        )

        await store.update_step(plan_id, step.id, {
            "status": "pending",
            "retry_count": step.retry_count,
            "error_message": step.error_message,
        })

        return {
            "status": "step_retry",
            "plan_id": plan_id,
            "step_id": step.id,
            "retry_count": step.retry_count,
            "error": step.error_message,
            "observer_action": "retry",
        }

    async def _apply_modify(
        self,
        plan_id: str,
        step: TaskStep,
        modified_inputs: Optional[Dict[str, Any]],
        store: TaskPlanStorePort,
    ) -> Dict[str, Any]:
        """
        Apply MODIFY proposal - update step inputs and retry.

        This is used when a step failed due to content filters or validation
        errors that can be fixed by modifying the inputs (e.g., rewriting
        a prompt to avoid copyrighted terms).

        Args:
            plan_id: Plan ID
            step: The step to modify
            modified_inputs: New inputs to use
            store: Plan store for updates

        Returns:
            Dict indicating step should be retried with new inputs
        """
        logger.info(
            "Applying MODIFY proposal",
            plan_id=plan_id,
            step_id=step.id,
            has_modified_inputs=modified_inputs is not None,
        )

        if not modified_inputs:
            logger.warning(
                "MODIFY proposal without modified_inputs, falling back to abort",
                step_id=step.id,
            )
            return {
                "status": "error",
                "plan_id": plan_id,
                "step_id": step.id,
                "error": "MODIFY proposal without modified inputs",
            }

        # Log the modification for transparency
        original_prompt = step.inputs.get("prompt", "")[:100] if step.inputs else ""
        new_prompt = modified_inputs.get("prompt", "")[:100]
        logger.info(
            "Modifying step inputs",
            step_id=step.id,
            original_prompt=original_prompt,
            new_prompt=new_prompt,
        )

        # Update step with modified inputs and reset for retry
        await store.update_step(plan_id, step.id, {
            "status": "pending",
            "inputs": modified_inputs,
            "retry_count": step.retry_count,
            "error_message": f"[MODIFIED] Previous error: {step.error_message}",
        })

        return {
            "status": "step_modified",
            "plan_id": plan_id,
            "step_id": step.id,
            "retry_count": step.retry_count,
            "observer_action": "modify",
            "modification_summary": f"Rewrote inputs to avoid content filter",
        }

    async def _apply_fallback(
        self,
        plan_id: str,
        step: TaskStep,
        fallback_target: Optional[str],
        store: TaskPlanStorePort,
    ) -> Dict[str, Any]:
        """Apply FALLBACK proposal - switch to fallback model/API."""
        logger.info(
            "Applying FALLBACK proposal",
            plan_id=plan_id,
            step_id=step.id,
            fallback_target=fallback_target,
        )

        # Update step with fallback target in inputs
        updated_inputs = dict(step.inputs)

        if fallback_target:
            # Determine if it's a model or API fallback
            if fallback_target.startswith("http"):
                updated_inputs["fallback_api"] = fallback_target
            else:
                updated_inputs["fallback_model"] = fallback_target

            # Remove used fallback from config
            if step.fallback_config:
                if fallback_target in step.fallback_config.models:
                    step.fallback_config.models.remove(fallback_target)
                if fallback_target in step.fallback_config.apis:
                    step.fallback_config.apis.remove(fallback_target)

        await store.update_step(plan_id, step.id, {
            "status": "pending",
            "inputs": updated_inputs,
            "error_message": step.error_message,
            "fallback_config": step.fallback_config.to_dict() if step.fallback_config else None,
        })

        return {
            "status": "step_fallback",
            "plan_id": plan_id,
            "step_id": step.id,
            "fallback_target": fallback_target,
            "error": step.error_message,
            "observer_action": "fallback",
        }

    async def _apply_skip(
        self,
        plan_id: str,
        step: TaskStep,
        store: TaskPlanStorePort,
    ) -> Dict[str, Any]:
        """Apply SKIP proposal - skip non-critical step."""
        logger.info(
            "Applying SKIP proposal",
            plan_id=plan_id,
            step_id=step.id,
        )

        await store.update_step(plan_id, step.id, {
            "status": "skipped",
            "error_message": step.error_message,
        })

        return {
            "status": "step_skipped",
            "plan_id": plan_id,
            "step_id": step.id,
            "error": step.error_message,
            "observer_action": "skip",
            "next_action": "continue",
        }

    async def _apply_abort(
        self,
        plan_id: str,
        step: TaskStep,
        reason: str,
        store: TaskPlanStorePort,
    ) -> Dict[str, Any]:
        """Apply ABORT proposal - abort the plan."""
        logger.info(
            "Applying ABORT proposal",
            plan_id=plan_id,
            step_id=step.id,
            reason=reason,
        )

        await store.update_step(plan_id, step.id, {
            "status": "failed",
            "error_message": step.error_message,
        })
        await store.update_task(plan_id, {"status": TaskStatus.FAILED})

        return {
            "status": "plan_aborted",
            "plan_id": plan_id,
            "step_id": step.id,
            "error": step.error_message,
            "abort_reason": reason,
            "observer_action": "abort",
        }

    async def _apply_replan(
        self,
        plan: Task,
        failed_step: TaskStep,
        proposal: "ObserverProposal",
        store: TaskPlanStorePort,
    ) -> Dict[str, Any]:
        """
        Apply REPLAN proposal - escalate to TaskPlannerAgent for strategic replanning.

        This is called when tactical recovery (RETRY/FALLBACK/SKIP) isn't possible
        and the Observer has diagnosed a structural problem that requires replanning.

        The flow is:
        1. Create a REPLAN checkpoint for user approval
        2. After approval, call TaskPlannerAgent.replan()
        3. Store the new plan version
        4. Continue execution with the new plan

        For now, we require a checkpoint for all REPLAN proposals.
        """
        from src.domain.tasks.models import ObserverProposal, CheckpointConfig, ApprovalType

        logger.info(
            "Applying REPLAN proposal",
            plan_id=plan.id,
            step_id=failed_step.id,
            diagnosis=proposal.replan_context.diagnosis[:100] if proposal.replan_context else "No context",
        )

        # Check if we have replan context
        if not proposal.replan_context:
            logger.error("REPLAN proposal without context, falling back to ABORT")
            return await self._apply_abort(
                plan.id, failed_step, "REPLAN failed: no context provided", store
            )

        # REPLAN requires user approval - create checkpoint
        # This gives the user a chance to review the diagnosis and proposed changes
        replan_checkpoint = CheckpointConfig(
            name="replan_approval",
            description=f"Strategic replan required: {proposal.replan_context.diagnosis[:100]}",
            approval_type=ApprovalType.EXPLICIT,
            preference_key="delegation.replan",
            preview_fields=["diagnosis", "affected_steps", "suggested_approach"],
        )

        # Store the replan context in step inputs for retrieval after approval
        replan_preview = {
            "diagnosis": proposal.replan_context.diagnosis,
            "affected_steps": proposal.replan_context.affected_steps,
            "suggested_approach": proposal.replan_context.suggested_approach,
            "constraints": proposal.replan_context.constraints,
            "original_error": failed_step.error_message,
        }

        # Update step with checkpoint for replan
        # Note: checkpoint_config must be the CheckpointConfig object, not dict
        # The serialization will call to_dict() when saving to Redis
        await store.update_step(plan.id, failed_step.id, {
            "status": "checkpoint",
            "checkpoint_required": True,
            "checkpoint_config": replan_checkpoint,
            "inputs": {**failed_step.inputs, "_replan_context": proposal.replan_context.to_dict()},
        })
        await store.update_task(plan.id, {"status": TaskStatus.CHECKPOINT})

        return {
            "status": "replan_checkpoint",
            "plan_id": plan.id,
            "step_id": failed_step.id,
            "observer_action": "replan",
            "checkpoint": {
                "step_id": failed_step.id,
                "name": "replan_approval",
                "description": replan_checkpoint.description,
                "preview": replan_preview,
            },
            "message": "Strategic replanning required - awaiting user approval",
        }

    async def execute_replan(self, plan_id: str, step_id: str) -> Dict[str, Any]:
        """
        Execute the strategic replan after user approval.

        Called after user approves the replan checkpoint.
        """
        store = await self._get_plan_store()
        plan = await store.get_task(plan_id)

        if not plan:
            return {"status": "error", "error": f"Plan not found: {plan_id}"}

        step = plan.get_step_by_id(step_id)
        if not step:
            return {"status": "error", "error": f"Step not found: {step_id}"}

        # Get replan context from step inputs
        replan_context_data = step.inputs.get("_replan_context")
        if not replan_context_data:
            return {"status": "error", "error": "Replan context not found"}

        from src.domain.tasks.models import ReplanContext

        replan_context = ReplanContext.from_dict(replan_context_data)

        logger.info(
            "Executing strategic replan",
            plan_id=plan_id,
            step_id=step_id,
            diagnosis=replan_context.diagnosis[:100],
        )

        planner = self._get_planner()

        try:
            # Generate the new plan
            new_plan = await planner.replan(plan, step, replan_context)

            # Store the new plan version
            await store.create_task(new_plan)

            # Mark the original plan as superseded
            await store.update_task(plan_id, {
                "status": TaskStatus.SUPERSEDED,
                "superseded_by": new_plan.id,
            })

            logger.info(
                "Strategic replan complete",
                original_plan_id=plan_id,
                new_plan_id=new_plan.id,
                new_plan_version=new_plan.version,
            )

            return {
                "status": "replan_complete",
                "original_plan_id": plan_id,
                "new_plan_id": new_plan.id,
                "new_plan_version": new_plan.version,
                "observer_action": "replan",
                "next_action": "execute_new_plan",
                "message": f"Plan v{new_plan.version} created, ready for execution",
            }

        except Exception as e:
            logger.error(
                "Replan failed",
                plan_id=plan_id,
                error=str(e),
            )
            return {
                "status": "error",
                "plan_id": plan_id,
                "error": f"Replan failed: {str(e)}",
            }

        finally:
            cleanup = getattr(planner, "cleanup", None)
            if cleanup:
                await cleanup()

    def _parse_result_xml(self, content: str) -> Dict[str, Any]:
        """Parse XML result from LLM response."""
        # Extract status
        status_match = re.search(r'<status>(\w+)</status>', content)
        status = status_match.group(1) if status_match else "success"

        # Extract output
        output_match = re.search(r'<output>(.*?)</output>', content, re.DOTALL)
        output = output_match.group(1).strip() if output_match else content

        # Try to parse output as JSON if possible
        try:
            output = json.loads(output)
        except (json.JSONDecodeError, TypeError):
            pass

        # Extract findings
        findings = []
        findings_match = re.search(r'<findings>(.*?)</findings>', content, re.DOTALL)
        if findings_match:
            finding_matches = re.findall(
                r'<finding[^>]*>(.*?)</finding>',
                findings_match.group(1),
                re.DOTALL
            )
            for finding_text in finding_matches:
                findings.append({"description": finding_text.strip()})

        # Extract error if present
        error = None
        error_match = re.search(r'<error>(.*?)</error>', content, re.DOTALL)
        if error_match:
            error = error_match.group(1).strip()

        return {
            "status": "success" if status in ("completed", "success") else "error",
            "output": output,
            "findings": findings,
            "error": error,
        }

    def _build_checkpoint_preview(self, step: TaskStep) -> Dict[str, Any]:
        """Build preview data for checkpoint approval."""
        preview = {}

        config = step.checkpoint_config
        if config and config.preview_fields:
            for field in config.preview_fields:
                if field in step.inputs:
                    preview[field] = step.inputs[field]

        # Default preview fields based on step type
        if not preview:
            if step.agent_type == "notify":
                preview = {
                    "to": step.inputs.get("to"),
                    "subject": step.inputs.get("subject"),
                    "body_preview": str(step.inputs.get("body", ""))[:200],
                }
            elif step.agent_type == "http_fetch":
                preview = {
                    "url": step.inputs.get("url"),
                    "method": step.inputs.get("method", "GET"),
                }
            else:
                preview = {"inputs": step.inputs}

        return preview

    async def resume_after_approval(self, plan_id: str, step_id: str) -> Dict[str, Any]:
        """
        Resume execution after checkpoint approval.

        Called after user approves a checkpoint.
        """
        store = await self._get_plan_store()
        plan = await store.get_task(plan_id)

        if not plan:
            return {"status": "error", "error": f"Plan not found: {plan_id}"}

        step = plan.get_step_by_id(step_id)
        if not step:
            return {"status": "error", "error": f"Step not found: {step_id}"}

        # Check if this is a replan checkpoint
        if step.inputs and step.inputs.get("_replan_context"):
            logger.info(
                "Replan checkpoint approved, executing replan",
                plan_id=plan_id,
                step_id=step_id,
            )
            return await self.execute_replan(plan_id, step_id)

        # Clear checkpoint requirement (user approved)
        await store.update_step(plan_id, step_id, {
            "checkpoint_required": False,
            "status": "pending",
        })

        # Check if there are other steps still waiting for checkpoint approval
        # Refresh plan to get updated step statuses
        plan = await store.get_task(plan_id)
        other_checkpoint_steps = [
            s for s in plan.steps
            if s.id != step_id and s.status == StepStatus.CHECKPOINT
        ]

        if other_checkpoint_steps:
            # Keep status as CHECKPOINT since other steps need approval
            logger.info(
                "Other steps still need checkpoint approval",
                plan_id=plan_id,
                remaining_checkpoints=len(other_checkpoint_steps),
            )
        else:
            # No more checkpoints, set to READY
            await store.update_task(plan_id, {"status": TaskStatus.READY})

        # Continue execution
        return await self.execute_cycle(plan_id)

    async def cleanup(self) -> None:
        """Cleanup orchestrator resources."""
        if self._observer:
            await self._observer.cleanup()
        if self._plan_store:
            await self._plan_store.disconnect()
        await super().cleanup()
