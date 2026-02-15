# REVIEW: Dispatcher handles template validation, context injection, tree updates,
# REVIEW: and Celery dispatch in one class, and relies on Redis for plan reads
# REVIEW: even though PG is the source of truth. Consider splitting template
# REVIEW: resolution/validation from dispatch and using a consistent store.
"""
StepDispatcher - Single source of truth for step preparation and dispatch.

Both orchestrator and scheduler call this module instead of having their own
preparation/dispatch logic. This ensures consistent behavior regardless of
which path triggers step execution.

Responsibilities:
- Validate template syntax
- Resolve template variables ({{step_X.outputs.field}})
- Inject plan context (org_id, workflow_id, agent_id)
- Update execution tree with resolved inputs
- Dispatch to Celery worker
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import structlog

from src.eval.format_validators import validate_template_syntax_quick
from src.domain.tasks.models import Task, TaskStep, StepStatus

logger = structlog.get_logger(__name__)


@dataclass
class DispatchResult:
    """Result of dispatching a step to Celery."""
    success: bool
    celery_task_id: Optional[str] = None
    step_id: Optional[str] = None
    error: Optional[str] = None


class StepDispatcher:
    """
    Handles all step preparation and dispatch to Celery.

    This is the single source of truth for:
    - Template resolution
    - Context injection
    - Tree updates
    - Celery dispatch
    """

    def __init__(
        self,
        plan_store=None,
        tree_adapter=None,
        model: str = None,
    ):
        """
        Initialize the dispatcher.

        Args:
            plan_store: Optional plan store (will create if not provided)
            tree_adapter: Optional tree adapter (will create if not provided)
            model: Optional model override (if None, uses agent_type-based selection)
        """
        self._plan_store = plan_store
        self._tree_adapter = tree_adapter
        self._model = model  # None = use pre-vetted model selection in Celery task

    async def _get_plan_store(self):
        """Lazy load plan store."""
        if not self._plan_store:
            from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore
            self._plan_store = RedisTaskStore()
            await self._plan_store._connect()
        return self._plan_store

    async def _get_tree_adapter(self):
        """Lazy load tree adapter."""
        if not self._tree_adapter:
            from src.infrastructure.tasks.task_tree_adapter import TaskExecutionTreeAdapter
            self._tree_adapter = TaskExecutionTreeAdapter()
        return self._tree_adapter

    async def dispatch_step(
        self,
        task_id: str,
        step: TaskStep,
        plan: Optional[Task] = None,
    ) -> DispatchResult:
        """
        Prepare and dispatch a single step to Celery.

        This is the single entry point for step execution. It:
        1. Loads plan if not provided (for context)
        2. Validates template syntax
        3. Resolves template variables from completed step outputs
        4. Injects plan context (org_id, workflow_id, agent_id)
        5. Updates execution tree with resolved inputs
        6. Dispatches to Celery worker

        Args:
            task_id: The task/plan ID
            step: The step to dispatch (with raw inputs, templates)
            plan: Optional plan document (avoids re-fetch if caller has it)

        Returns:
            DispatchResult with success status and Celery task ID
        """
        try:
            # 1. Load plan if not provided
            if not plan:
                store = await self._get_plan_store()
                plan = await store.get_task(task_id)
                if not plan:
                    return DispatchResult(
                        success=False,
                        step_id=step.id,
                        error=f"Plan not found: {task_id}",
                    )

            # 2. Validate template syntax
            try:
                validate_template_references(step)
            except ValueError as e:
                return DispatchResult(
                    success=False,
                    step_id=step.id,
                    error=str(e),
                )

            # 3. Resolve template variables
            completed_outputs = build_completed_outputs(plan)
            resolved_inputs = resolve_template_variables(step.inputs, completed_outputs)

            # DEBUG: Log plan organization_id before inject_context
            logger.debug(
                "Plan loaded for step dispatch",
                task_id=task_id,
                plan_id=plan.id,
                plan_organization_id=plan.organization_id,
                step_id=step.id,
                agent_type=step.agent_type,
            )

            # 3.5a. Auto-coerce resolved types to match agent schema
            # After template resolution, a {{step_X.outputs.field}} that resolves to
            # a list/dict may feed into a string input. Coerce to JSON string rather
            # than failing validation, since the LLM planner can't predict resolved types.
            resolved_inputs = _coerce_resolved_types(resolved_inputs, step.agent_type, raw_inputs=step.inputs)

            # 3.5b. Defensive validation of resolved inputs (safety net)
            # This catches errors from legacy plans that bypassed planner validation
            validation_error = await self._validate_resolved_inputs(step, resolved_inputs)
            if validation_error:
                return DispatchResult(
                    success=False,
                    step_id=step.id,
                    error=validation_error,
                )

            # 4. Inject context for specific agent types
            resolved_inputs = inject_context(
                inputs=resolved_inputs,
                agent_type=step.agent_type,
                step_id=step.id,
                plan=plan,
            )

            # 5. Update execution tree with resolved inputs
            if plan.tree_id:
                tree_adapter = await self._get_tree_adapter()
                await tree_adapter.update_step_inputs(
                    task_id=str(plan.id),
                    step_id=step.id,
                    resolved_inputs=resolved_inputs,
                )
                logger.debug(
                    "Updated tree with resolved inputs",
                    task_id=plan.id,
                    step_id=step.id,
                    input_keys=list(resolved_inputs.keys()),
                )

            # 6. Dispatch to Celery
            from src.core.tasks import execute_task_step
            from dataclasses import replace

            # Create step with resolved inputs
            resolved_step = replace(step, inputs=resolved_inputs)
            step_data = resolved_step.to_dict()
            # Only set model if explicitly provided; otherwise Celery task
            # uses agent_type-based selection from pre-vetted model list
            if self._model:
                step_data["model"] = self._model

            result = execute_task_step.delay(
                task_id=str(plan.id),
                step_data=step_data,
            )

            logger.info(
                "Step dispatched to Celery",
                task_id=plan.id,
                step_id=step.id,
                agent_type=step.agent_type,
                celery_task_id=result.id,
            )

            return DispatchResult(
                success=True,
                celery_task_id=result.id,
                step_id=step.id,
            )

        except Exception as e:
            logger.error(
                "Failed to dispatch step",
                task_id=task_id,
                step_id=step.id,
                error=str(e),
            )
            return DispatchResult(
                success=False,
                step_id=step.id,
                error=str(e),
            )

    async def dispatch_steps(
        self,
        task_id: str,
        steps: List[TaskStep],
        plan: Optional[Task] = None,
    ) -> List[DispatchResult]:
        """
        Dispatch multiple steps (for parallel execution).

        Args:
            task_id: The task/plan ID
            steps: List of steps to dispatch
            plan: Optional plan document (avoids re-fetch)

        Returns:
            List of DispatchResult for each step
        """
        # Load plan once for all steps
        if not plan:
            store = await self._get_plan_store()
            plan = await store.get_task(task_id)

        results = []
        for step in steps:
            result = await self.dispatch_step(task_id, step, plan)
            results.append(result)

        return results

    async def _validate_resolved_inputs(
        self,
        step: TaskStep,
        resolved_inputs: Dict[str, Any],
    ) -> Optional[str]:
        """
        Validate resolved step inputs against agent schema.

        This is a safety net for plans that bypassed TaskPlannerAgent validation
        (e.g., legacy imports, manually created plans).

        Args:
            step: The step being dispatched
            resolved_inputs: The resolved inputs after template resolution

        Returns:
            Error message if validation fails, None if valid
        """
        try:
            from src.validation.plan_validator import PlanValidator
            from dataclasses import replace

            validator = PlanValidator()

            # Create a temporary step with resolved inputs for validation
            resolved_step = replace(step, inputs=resolved_inputs)

            result = await validator.validate_step_inputs_at_runtime(resolved_step)

            if not result.valid:
                # Format errors for the dispatch result
                error_msgs = []
                for error in result.errors[:3]:  # Limit to first 3 errors
                    msg = f"{error.field}: {error.message}"
                    if error.suggestion:
                        msg += f" ({error.suggestion})"
                    error_msgs.append(msg)

                error_str = "; ".join(error_msgs)
                if len(result.errors) > 3:
                    error_str += f" (+{len(result.errors) - 3} more errors)"

                logger.warning(
                    "Step input validation failed",
                    step_id=step.id,
                    agent_type=step.agent_type,
                    error_count=len(result.errors),
                    errors=error_str,
                )

                return f"Input validation failed for {step.agent_type}: {error_str}"

            return None

        except Exception as e:
            # Don't block on validation errors - log and continue
            # This ensures backwards compatibility with existing plans
            logger.warning(
                "Step input validation error (non-blocking)",
                step_id=step.id,
                agent_type=step.agent_type,
                error=str(e),
            )
            return None


# ============================================================================
# Standalone functions (can be unit tested independently)
# ============================================================================


def _coerce_resolved_types(
    resolved_inputs: Dict[str, Any],
    agent_type: str,
    raw_inputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Auto-coerce resolved template values when they produce structured data
    in a field that was originally a string template.

    After template resolution, {{step_X.outputs.field}} may resolve to a list
    or dict. If the original (raw) input was a string containing a template,
    the planner intended it as data flow and the resolved value should be
    JSON-serialized so downstream agents (which expect string inputs) can
    consume it.

    Only coerces fields where:
    - The resolved value is a list or dict
    - AND the raw (pre-resolution) value was a string (i.e., a template)

    This preserves intentional array/object inputs while fixing the common
    case of template-resolved structured data flowing into string fields.
    """
    if not raw_inputs:
        return resolved_inputs

    coerced = dict(resolved_inputs)
    for field_name, value in resolved_inputs.items():
        raw_value = raw_inputs.get(field_name)
        # Only coerce if: resolved to list/dict AND original was a string template
        if isinstance(value, (list, dict)) and isinstance(raw_value, str):
            coerced[field_name] = json.dumps(value, indent=2, default=str)
            logger.debug(
                "auto_coerced_input_type",
                field=field_name,
                agent_type=agent_type,
                from_type=type(value).__name__,
                to_type="string",
            )
    return coerced


def validate_template_references(step: TaskStep) -> None:
    """
    Validate template references in step inputs before resolution.

    Catches invalid template syntax like {{step_X.output}} (missing field name)
    or {{step_X.outputs}} (missing field name) BEFORE attempting resolution.

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
        )
        raise ValueError(
            f"Step '{step.id}' ({step.name}) has invalid template syntax: {error_details}. "
            f"Use {{{{step_X.outputs.field_name}}}} instead of {{{{step_X.output}}}}."
        )


def build_completed_outputs(plan: Task) -> Dict[str, Dict[str, Any]]:
    """
    Build a map of completed step outputs for template resolution.

    Supports lookup by both step ID (step_1) AND step name (research_ai).

    Args:
        plan: The plan document containing all steps

    Returns:
        Dict mapping step ID/name to outputs
    """
    step_outputs = {}
    for s in plan.steps:
        if s.status in (StepStatus.DONE, StepStatus.SKIPPED):
            step_outputs[s.id] = s.outputs
            # Also map by step name for templates like {{research_ai.output}}
            if s.name and s.name != s.id:
                step_outputs[s.name] = s.outputs
    return step_outputs


def resolve_template_variables(
    inputs: Dict[str, Any],
    completed_outputs: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Resolve template variables in step inputs.

    Replaces {{step_X.output}} patterns with actual outputs from completed steps.
    This enables data flow between steps in the delegation plan.

    Supports two template syntaxes:
    1. {{step_ref.output}}, {{step_ref.outputs.field}}, {{step_ref.output[N]}}
    2. ${node.step_X.field} (alternative syntax)

    Args:
        inputs: The step inputs containing template variables
        completed_outputs: Map of step ID/name to outputs

    Returns:
        Resolved inputs with actual values
    """
    if not inputs:
        return {}

    def resolve_value(value: Any) -> Any:
        """Recursively resolve template variables in a value."""
        if isinstance(value, str):
            # Pattern 1: Curly braces syntax {{step_ref.output}} or {{step_ref.outputs.field}}
            curly_pattern = r'\{\{([a-zA-Z][a-zA-Z0-9_]*)\.(output|outputs)(?:\.(\w+))?(?:\[(\d+)\])?\}\}'

            # Pattern 2: Dollar-node syntax ${node.step_X.field}
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
            # preserve the original type (dict) for file handlers.

            # Check curly brace syntax first: {{step_X.output}}
            curly_match = re.fullmatch(curly_pattern, value)
            if curly_match:
                step_id = curly_match.group(1)
                field = curly_match.group(3)
                index = curly_match.group(4)
                if step_id in completed_outputs:
                    output = completed_outputs[step_id]
                    return extract_value(output, field, index)
                return value  # Keep original if not found

            # Check dollar-node syntax: ${node.step_X.field}
            dollar_match = re.fullmatch(dollar_pattern, value)
            if dollar_match:
                step_id = dollar_match.group(1)
                field = dollar_match.group(2)
                if step_id in completed_outputs:
                    output = completed_outputs[step_id]
                    return extract_value(output, field, None)
                return value  # Keep original if not found

            # For values with embedded templates, use regex substitution
            def curly_replacer(match):
                step_id = match.group(1)
                field = match.group(3)
                index = match.group(4)

                if step_id in completed_outputs:
                    output = completed_outputs[step_id]
                    result = extract_value(output, field, index)
                    if isinstance(result, str):
                        # Truncate large content
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

                if step_id in completed_outputs:
                    output = completed_outputs[step_id]
                    result = extract_value(output, field, None)
                    if isinstance(result, str):
                        if len(result) > 50000:
                            return result[:50000] + "\n... [content truncated]"
                        return result
                    elif isinstance(result, dict):
                        return json.dumps(result, ensure_ascii=False)
                    return str(result) if result else ""
                return match.group(0)

            # Apply both replacement patterns
            result = re.sub(curly_pattern, curly_replacer, value)
            result = re.sub(dollar_pattern, dollar_replacer, result)
            return result
        elif isinstance(value, dict):
            return {k: resolve_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [resolve_value(item) for item in value]
        return value

    resolved = resolve_value(inputs)

    # Log if any variables were resolved
    if resolved != inputs:
        resolved_json = json.dumps(resolved, default=str)
        original_json = json.dumps(inputs, default=str)
        logger.info(
            "Resolved template variables",
            original_size=len(original_json),
            resolved_size=len(resolved_json),
        )
        if len(resolved_json) > 50000:
            logger.warning(
                "Resolved inputs are very large - potential context accumulation",
                resolved_size=len(resolved_json),
            )

    return resolved


def inject_context(
    inputs: Dict[str, Any],
    agent_type: str,
    step_id: str,
    plan: Task,
) -> Dict[str, Any]:
    """
    Inject plan context into step inputs for specific agent types.

    Identity fields (org_id, user_id, plan_id, etc.) are ALWAYS overridden
    from the trusted plan document, regardless of what the agent provided
    in inputs. This prevents agents from spoofing identity fields.

    For file_storage: org_id, workflow_id, agent_id
    For generate_image: org_id, workflow_id, agent_id, folder_path
    For workspace_*: org_id, created_by_id, created_by_type
    For schedule_job: plan_id, step_id, user_id, organization_id
    For memory_*: org_id, user_id, plan_id, step_id
    For integrations: user_token

    Args:
        inputs: The step inputs
        agent_type: The agent type (e.g., "file_storage", "generate_image")
        step_id: The step ID
        plan: The plan document (for org_id, goal, etc.)

    Returns:
        Enriched inputs with context
    """
    if agent_type == "file_storage":
        return _inject_file_storage_context(inputs, step_id, plan)
    elif agent_type == "generate_image":
        return _inject_image_generation_context(inputs, step_id, plan)
    elif agent_type.startswith("workspace_"):
        return _inject_workspace_context(inputs, step_id, plan, agent_type)
    elif agent_type == "schedule_job":
        return _inject_schedule_job_context(inputs, step_id, plan)
    elif agent_type in ("list_integrations", "execute_outbound_action"):
        return _inject_integration_context(inputs, step_id, plan)
    elif agent_type in ("memory_store", "memory_query"):
        return _inject_memory_context(inputs, step_id, plan)
    elif agent_type == "task_output_retrieval":
        return _inject_task_output_retrieval_context(inputs, step_id, plan)
    return inputs


def _inject_workspace_context(
    inputs: Dict[str, Any],
    step_id: str,
    plan: Task,
    agent_type: str = "",
) -> Dict[str, Any]:
    """
    Inject plan context into workspace step inputs.

    Workspace operations need org_id which is available at the plan level.
    Also stamps created_by_id (task UUID) and created_by_type ("task") so
    workspace objects can be traced back to the task that created them.
    """
    enriched = dict(inputs) if inputs else {}

    # Always override identity fields from trusted plan
    if plan.organization_id:
        enriched["org_id"] = plan.organization_id

    # Always stamp task identity for traceability
    if plan.id:
        enriched["created_by_id"] = str(plan.id)
    enriched["created_by_type"] = "task"

    # Tag with agent_type for filtering
    if agent_type:
        tags = enriched.get("tags") or []
        agent_tag = f"agent:{agent_type}"
        if agent_tag not in tags:
            tags.append(agent_tag)
        enriched["tags"] = tags

    logger.debug(
        "Injected workspace context",
        step_id=step_id,
        org_id=enriched.get("org_id"),
        created_by_id=enriched.get("created_by_id"),
        agent_type=agent_type,
    )

    return enriched


def _inject_schedule_job_context(
    inputs: Dict[str, Any],
    step_id: str,
    plan: Task,
) -> Dict[str, Any]:
    """
    Inject plan context into schedule_job step inputs.

    Schedule jobs need plan_id, step_id, and user_id which are available
    at the plan level but not in individual step definitions.
    """
    enriched = dict(inputs) if inputs else {}

    # Always override identity fields from trusted plan
    if plan.id:
        enriched["plan_id"] = str(plan.id)

    enriched["step_id"] = step_id

    if plan.user_id:
        enriched["user_id"] = str(plan.user_id)

    if plan.organization_id:
        enriched["organization_id"] = plan.organization_id

    # Inject task metadata so the plugin can detect cloned executions
    if plan.metadata:
        enriched["_task_metadata"] = plan.metadata

    logger.debug(
        "Injected schedule_job context",
        step_id=step_id,
        plan_id=enriched.get("plan_id"),
        user_id=enriched.get("user_id"),
    )

    return enriched


def _inject_file_storage_context(
    inputs: Dict[str, Any],
    step_id: str,
    plan: Task,
) -> Dict[str, Any]:
    """
    Inject plan context into file_storage step inputs.

    File storage operations need org_id, workflow_id, agent_id which are
    available at the plan level but not in individual step definitions.
    """
    enriched = dict(inputs) if inputs else {}

    # Always override identity fields from trusted plan
    if plan.organization_id:
        enriched["org_id"] = plan.organization_id

    # Always override workflow context (use plan ID as workflow ID)
    if plan.id:
        enriched["workflow_id"] = str(plan.id)

    # Always override agent context (use step ID as agent ID)
    enriched["agent_id"] = step_id

    # Map 'file_data' to 'content' for the upload handler
    if "file_data" in enriched and "content" not in enriched:
        enriched["content"] = enriched["file_data"]

    # Infer content_type from filename if not provided
    operation = enriched.get("operation", "")
    if operation == "upload" and "content_type" not in enriched:
        filename = enriched.get("filename", "")
        if filename.endswith(".png"):
            enriched["content_type"] = "image/png"
        elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
            enriched["content_type"] = "image/jpeg"
        elif filename.endswith(".webp"):
            enriched["content_type"] = "image/webp"
        elif filename.endswith(".gif"):
            enriched["content_type"] = "image/gif"
        elif filename.endswith(".json"):
            enriched["content_type"] = "application/json"
        elif filename.endswith(".pdf"):
            enriched["content_type"] = "application/pdf"

    logger.debug(
        "Injected file_storage context",
        step_id=step_id,
        org_id=enriched.get("org_id"),
        workflow_id=enriched.get("workflow_id"),
    )

    return enriched


def _inject_image_generation_context(
    inputs: Dict[str, Any],
    step_id: str,
    plan: Task,
) -> Dict[str, Any]:
    """
    Inject plan context into generate_image step inputs.

    This enables auto-upload to Den: generated images are stored in Den
    and the step output contains file URLs instead of base64 data.
    """
    enriched = dict(inputs) if inputs else {}

    # Always override identity fields from trusted plan
    if plan.organization_id:
        enriched["org_id"] = plan.organization_id

    # Always override workflow context
    if plan.id:
        enriched["workflow_id"] = str(plan.id)

    # Always override agent context
    enriched["agent_id"] = step_id

    # Default folder path based on plan goal
    if "folder_path" not in enriched:
        goal_slug = re.sub(r'[^a-zA-Z0-9\s-]', '', plan.goal or 'images')[:30].strip()
        goal_slug = re.sub(r'\s+', '-', goal_slug).lower()
        enriched["folder_path"] = f"/generated-images/{goal_slug}"

    # Default to public images
    if "is_public" not in enriched:
        enriched["is_public"] = True

    logger.debug(
        "Injected generate_image context",
        step_id=step_id,
        org_id=enriched.get("org_id"),
        folder_path=enriched.get("folder_path"),
    )

    return enriched


def _inject_integration_context(
    inputs: Dict[str, Any],
    step_id: str,
    plan: Task,
) -> Dict[str, Any]:
    """
    Inject plan context into integration step inputs.

    Integration plugins (list_integrations, execute_outbound_action) need
    the user_token which is stored in plan constraints at the API layer.
    Without this injection, the handlers will fail with "user_token is required".
    """
    enriched = dict(inputs) if inputs else {}

    # Always override user_token from trusted plan constraints
    if plan.constraints:
        user_token = plan.constraints.get("user_token")
        if user_token:
            enriched["user_token"] = user_token

    logger.debug(
        "Injected integration context",
        step_id=step_id,
        has_user_token="user_token" in enriched,
    )

    return enriched


def _inject_memory_context(
    inputs: Dict[str, Any],
    step_id: str,
    plan: Task,
) -> Dict[str, Any]:
    """
    Inject plan context into memory step inputs.

    Memory operations need org_id, user_id, and plan_id from the plan.
    These are always overridden from the plan to prevent spoofing.
    """
    enriched = dict(inputs) if inputs else {}

    # Always override identity fields from the trusted plan
    if plan.organization_id:
        enriched["org_id"] = plan.organization_id

    if plan.user_id:
        enriched["user_id"] = str(plan.user_id)

    if plan.id:
        enriched["plan_id"] = str(plan.id)

    enriched["step_id"] = step_id

    logger.debug(
        "Injected memory context",
        step_id=step_id,
        org_id=enriched.get("org_id"),
        user_id=enriched.get("user_id"),
    )

    return enriched


def _inject_task_output_retrieval_context(
    inputs: Dict[str, Any],
    step_id: str,
    plan: Task,
) -> Dict[str, Any]:
    """
    Inject plan context into task_output_retrieval step inputs.

    Task output retrieval needs org_id from the plan for access control.
    These are always overridden from the plan to prevent spoofing.
    """
    enriched = dict(inputs) if inputs else {}

    # Always override identity fields from the trusted plan
    if plan.organization_id:
        enriched["org_id"] = plan.organization_id

    if plan.user_id:
        enriched["user_id"] = str(plan.user_id)

    if plan.id:
        enriched["plan_id"] = str(plan.id)

    enriched["step_id"] = step_id

    logger.debug(
        "Injected task_output_retrieval context",
        step_id=step_id,
        org_id=enriched.get("org_id"),
        user_id=enriched.get("user_id"),
    )

    return enriched
