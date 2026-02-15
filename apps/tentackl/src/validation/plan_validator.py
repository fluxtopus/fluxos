"""
Plan Validator for Delegation System

Validates LLM-generated plans before execution to catch field name errors
that would otherwise cause cryptic runtime failures.

Philosophy: No silent remapping. If the LLM generates bad field names,
validation fails and the LLM must fix it. This ensures the LLM learns
proper patterns.

Key validations:
- Step inputs match agent's inputs_schema (required fields, valid field names)
- Template references point to valid output fields from previous steps
- Step references point to existing steps
- Agent types exist in the registry
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
import structlog

from src.domain.tasks.models import TaskStep

logger = structlog.get_logger(__name__)


@dataclass
class PlanValidationError:
    """Single validation error with suggestion for fixing."""

    step_id: str
    field: str
    message: str
    suggestion: Optional[str] = None
    severity: str = "error"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "field": self.field,
            "message": self.message,
            "suggestion": self.suggestion,
            "severity": self.severity,
        }


@dataclass
class PlanValidationResult:
    """Result of plan validation."""

    valid: bool
    errors: List[PlanValidationError] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "error_count": self.error_count,
            "errors": [e.to_dict() for e in self.errors],
        }

    def to_llm_feedback(self) -> str:
        """
        Format errors as structured feedback for LLM retry.

        This provides clear, actionable corrections the LLM can use
        to fix its generated plan.
        """
        if self.valid:
            return "Plan validation passed."

        lines = [
            "PLAN VALIDATION FAILED - Please fix the following errors:",
            "",
        ]

        for i, error in enumerate(self.errors, 1):
            lines.append(f"{i}. Step '{error.step_id}', field '{error.field}':")
            lines.append(f"   Error: {error.message}")
            if error.suggestion:
                lines.append(f"   Fix: {error.suggestion}")
            lines.append("")

        lines.append("IMPORTANT: Use the EXACT field names from the agent documentation.")
        lines.append("For template references, use: {{step_X.outputs.<field_name>}}")

        return "\n".join(lines)


class PlanValidationException(Exception):
    """Raised when plan validation fails after all retries."""

    def __init__(self, message: str, errors: List[PlanValidationError]):
        self.message = message
        self.errors = errors
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        error_summary = ", ".join(
            f"{e.step_id}:{e.field}" for e in self.errors[:3]
        )
        if len(self.errors) > 3:
            error_summary += f" (+{len(self.errors) - 3} more)"
        return f"{self.message}: {error_summary}"


class PlanValidator:
    """
    Validates LLM-generated delegation plans against agent schemas.

    Uses the UnifiedCapabilityRegistry to look up agent schemas and
    validates that generated plans use correct field names.
    """

    def __init__(self):
        self._registry = None
        self._initialized = False

    async def _get_registry(self):
        """Lazy load the registry."""
        if self._registry is None:
            from src.capabilities.unified_registry import get_registry
            self._registry = await get_registry()
        return self._registry

    async def validate_plan(self, steps: List[TaskStep]) -> PlanValidationResult:
        """
        Validate a complete plan before execution.

        Performs these validations:
        1. Agent type exists in registry
        2. Required inputs are present
        3. Input field names are valid for the agent type
        4. Template references point to valid output fields
        5. Step references point to existing steps

        Args:
            steps: List of TaskStep objects from the plan

        Returns:
            PlanValidationResult with valid flag and errors
        """
        errors: List[PlanValidationError] = []

        # Build step lookup and track outputs
        step_ids = {step.id for step in steps}
        step_outputs: Dict[str, Set[str]] = {}  # step_id -> set of output field names

        for step in steps:
            # 1. Validate agent type exists
            agent_errors, outputs_schema = await self._validate_agent_type(step)
            errors.extend(agent_errors)

            # Track expected outputs for this step (for template reference validation)
            if outputs_schema:
                step_outputs[step.id] = set(outputs_schema.keys())
            else:
                # Fallback: allow common output patterns
                step_outputs[step.id] = {"output", "result", "content", "data"}

            # 2. Validate inputs against schema
            if not agent_errors:  # Only if agent type is valid
                input_errors = await self._validate_step_inputs(step)
                errors.extend(input_errors)

            # 3. Validate template references
            template_errors = self._validate_template_references(
                step, step_ids, step_outputs
            )
            errors.extend(template_errors)

        valid = len(errors) == 0

        if not valid:
            logger.warning(
                "Plan validation failed",
                error_count=len(errors),
                errors=[e.to_dict() for e in errors[:5]],
            )
        else:
            logger.info("Plan validation passed", step_count=len(steps))

        return PlanValidationResult(valid=valid, errors=errors)

    async def _validate_agent_type(
        self, step: TaskStep
    ) -> tuple[List[PlanValidationError], Optional[Dict[str, Any]]]:
        """
        Validate that the agent type exists and return its outputs schema.

        Returns:
            Tuple of (errors, outputs_schema)
        """
        errors: List[PlanValidationError] = []
        outputs_schema = None

        # Plugin types (discord_followup, http_fetch, etc.) are handled by
        # plugin_executor, not the DB agent registry. Skip validation for them.
        from src.infrastructure.execution_runtime.plugin_executor import is_plugin_type
        if is_plugin_type(step.agent_type):
            return errors, None

        registry = await self._get_registry()
        agent_config = registry.get_agent_config(step.agent_type)

        if agent_config is None:
            # Try to find similar agent types for suggestion
            available = registry.available_types()
            suggestion = None

            # Simple fuzzy match: find agents containing similar words
            step_words = set(step.agent_type.lower().replace("_", " ").split())
            for avail in available:
                avail_words = set(avail.lower().replace("_", " ").split())
                if step_words & avail_words:  # Any common words
                    suggestion = f"Did you mean '{avail}'?"
                    break

            if not suggestion and available:
                suggestion = f"Available agents: {', '.join(sorted(available)[:10])}"

            errors.append(
                PlanValidationError(
                    step_id=step.id,
                    field="agent_type",
                    message=f"Unknown agent type '{step.agent_type}'",
                    suggestion=suggestion,
                )
            )
        else:
            outputs_schema = agent_config.outputs_schema

        return errors, outputs_schema

    async def _validate_step_inputs(self, step: TaskStep) -> List[PlanValidationError]:
        """
        Validate step inputs against the agent's inputs_schema.

        Checks:
        - Required fields are present
        - Provided fields are valid (in schema)
        - Enum values are valid
        """
        errors: List[PlanValidationError] = []

        registry = await self._get_registry()
        agent_config = registry.get_agent_config(step.agent_type)

        if not agent_config or not agent_config.inputs_schema:
            return errors

        inputs_schema = agent_config.inputs_schema
        provided_inputs = step.inputs if step.inputs else {}
        provided_keys = set(provided_inputs.keys())

        # Check for required fields
        required_fields = []
        for field_name, spec in inputs_schema.items():
            if isinstance(spec, dict) and spec.get("required", False):
                required_fields.append(field_name)

        for field_name in required_fields:
            if field_name not in provided_keys:
                # Check if there's a similar field name (common mistake)
                similar = self._find_similar_field(field_name, provided_keys)
                suggestion = f"Add '{field_name}' to inputs"
                if similar:
                    suggestion = f"Use '{field_name}' instead of '{similar}'"

                errors.append(
                    PlanValidationError(
                        step_id=step.id,
                        field=field_name,
                        message=f"Missing required input '{field_name}' for {step.agent_type}",
                        suggestion=suggestion,
                    )
                )

        # Check for invalid field names
        schema_fields = set(inputs_schema.keys())
        for provided_field in provided_keys:
            if provided_field not in schema_fields:
                # Find the closest matching field for suggestion
                closest = self._find_closest_field(provided_field, schema_fields)
                suggestion = f"Valid inputs: {', '.join(sorted(schema_fields))}"
                if closest:
                    suggestion = f"Use '{closest}' instead of '{provided_field}'"

                errors.append(
                    PlanValidationError(
                        step_id=step.id,
                        field=provided_field,
                        message=f"Invalid input field '{provided_field}' for {step.agent_type}",
                        suggestion=suggestion,
                    )
                )

        # Check enum constraints and type correctness
        for field_name, spec in inputs_schema.items():
            if not isinstance(spec, dict) or field_name not in provided_inputs:
                continue

            value = provided_inputs[field_name]

            # Skip template variables - they'll be resolved at runtime
            if isinstance(value, str) and "{{" in value and "}}" in value:
                continue

            # Enum validation
            if "enum" in spec:
                allowed_values = spec["enum"]
                if value not in allowed_values:
                    errors.append(
                        PlanValidationError(
                            step_id=step.id,
                            field=field_name,
                            message=f"Invalid value '{value}' for {field_name} in {step.agent_type}",
                            suggestion=f"Allowed values: {', '.join(str(v) for v in allowed_values)}",
                        )
                    )

            # Type validation
            expected_type = spec.get("type")
            if expected_type and expected_type != "any":
                type_error = self._check_input_type(value, expected_type)
                if type_error:
                    errors.append(
                        PlanValidationError(
                            step_id=step.id,
                            field=field_name,
                            message=f"Wrong type for '{field_name}' in {step.agent_type}: {type_error}",
                            suggestion=self._type_fix_suggestion(field_name, value, expected_type),
                        )
                    )

        return errors

    @staticmethod
    def _check_input_type(value: Any, expected_type: str) -> Optional[str]:
        """Check if a value matches the expected schema type. Returns error message or None."""
        type_map = {
            "string": (str,),
            "str": (str,),
            "integer": (int,),
            "int": (int,),
            "number": (int, float),
            "float": (int, float),
            "boolean": (bool,),
            "bool": (bool,),
            "array": (list,),
            "list": (list,),
            "object": (dict,),
            "dict": (dict,),
        }
        expected_python_types = type_map.get(expected_type.lower())
        if expected_python_types is None:
            return None  # Unknown type, skip
        if not isinstance(value, expected_python_types):
            return f"expected {expected_type}, got {type(value).__name__}"
        return None

    @staticmethod
    def _type_fix_suggestion(field_name: str, value: Any, expected_type: str) -> str:
        """Generate an actionable suggestion for fixing a type mismatch."""
        if expected_type in ("array", "list") and isinstance(value, str):
            return f"Wrap the value in an array: \"{field_name}\": [\"{value}\"]"
        if expected_type in ("string", "str") and isinstance(value, (int, float)):
            return f"Provide as string: \"{field_name}\": \"{value}\""
        if expected_type in ("integer", "int") and isinstance(value, str):
            return f"Provide as integer: \"{field_name}\": {value}"
        if expected_type in ("object", "dict") and isinstance(value, str):
            return f"Provide as object: \"{field_name}\": {{...}}"
        return f"'{field_name}' must be of type {expected_type}"

    def _validate_template_references(
        self,
        step: TaskStep,
        valid_step_ids: Set[str],
        step_outputs: Dict[str, Set[str]],
    ) -> List[PlanValidationError]:
        """
        Validate template references in step inputs.

        Checks:
        - Referenced steps exist
        - Referenced output fields are valid for the source step's agent type
        """
        errors: List[PlanValidationError] = []

        if not step.inputs:
            return errors

        # Convert inputs to string to find all template references
        import json
        inputs_str = json.dumps(step.inputs)

        # Pattern: {{step_ref.outputs.field_name}} or {{step_ref.output}}
        # Also handle {{step_name.outputs.field_name}}
        template_pattern = r'\{\{([a-zA-Z][a-zA-Z0-9_]*)\.(outputs?)(\.(\w+))?\}\}'

        for match in re.finditer(template_pattern, inputs_str):
            ref_step = match.group(1)  # e.g., "step_1" or "research"
            outputs_part = match.group(2)  # "output" or "outputs"
            field_name = match.group(4)  # e.g., "results" or None

            # Check step reference exists
            if ref_step not in valid_step_ids:
                errors.append(
                    PlanValidationError(
                        step_id=step.id,
                        field="inputs",
                        message=f"Template references non-existent step '{ref_step}'",
                        suggestion=f"Valid step IDs: {', '.join(sorted(valid_step_ids))}",
                    )
                )
                continue

            # Check for common syntax error: {{step_X.output}} (missing 's' and field)
            if outputs_part == "output" and not field_name:
                errors.append(
                    PlanValidationError(
                        step_id=step.id,
                        field="inputs",
                        message=f"Invalid template syntax '{{{{{ref_step}.output}}}}'",
                        suggestion=f"Use '{{{{{ref_step}.outputs.<field_name>}}}}' with a specific field name",
                    )
                )
                continue

            # Check that outputs has a field name
            if outputs_part == "outputs" and not field_name:
                valid_outputs = step_outputs.get(ref_step, set())
                errors.append(
                    PlanValidationError(
                        step_id=step.id,
                        field="inputs",
                        message=f"Template '{{{{{ref_step}.outputs}}}}' missing field name",
                        suggestion=f"Add field name: '{{{{{ref_step}.outputs.<field>}}}}' - valid fields: {', '.join(sorted(valid_outputs))}",
                    )
                )
                continue

            # Check that referenced output field is valid for the source step
            if field_name and ref_step in step_outputs:
                valid_outputs = step_outputs[ref_step]
                if field_name not in valid_outputs:
                    # Find closest matching field
                    closest = self._find_closest_field(field_name, valid_outputs)
                    suggestion = f"Valid outputs for {ref_step}: {', '.join(sorted(valid_outputs))}"
                    if closest:
                        suggestion = f"Use '{closest}' instead of '{field_name}'"

                    errors.append(
                        PlanValidationError(
                            step_id=step.id,
                            field="inputs",
                            message=f"'{ref_step}' does not have output field '{field_name}'",
                            suggestion=suggestion,
                        )
                    )

        return errors

    def _find_similar_field(self, target: str, candidates: Set[str]) -> Optional[str]:
        """Find a field in candidates that's similar to target (common typos)."""
        target_lower = target.lower()

        # Common substitution patterns
        substitutions = {
            "data": ["events", "items", "records"],
            "results": ["search_results", "findings"],
            "content": ["text", "body"],
        }

        for candidate in candidates:
            candidate_lower = candidate.lower()

            # Check direct substitutions
            if target_lower in substitutions:
                if candidate_lower in substitutions[target_lower]:
                    return candidate

            # Check reverse substitutions
            for correct, typos in substitutions.items():
                if target_lower == correct and candidate_lower in typos:
                    return candidate

        return None

    def _find_closest_field(
        self, target: str, candidates: Set[str]
    ) -> Optional[str]:
        """Find the closest matching field name using simple heuristics."""
        if not candidates:
            return None

        target_lower = target.lower()

        # Exact match (case insensitive)
        for candidate in candidates:
            if candidate.lower() == target_lower:
                return candidate

        # Prefix match
        for candidate in candidates:
            if candidate.lower().startswith(target_lower) or target_lower.startswith(
                candidate.lower()
            ):
                return candidate

        # Contains match
        for candidate in candidates:
            if target_lower in candidate.lower() or candidate.lower() in target_lower:
                return candidate

        # Word overlap
        target_words = set(target_lower.replace("_", " ").split())
        best_match = None
        best_overlap = 0

        for candidate in candidates:
            candidate_words = set(candidate.lower().replace("_", " ").split())
            overlap = len(target_words & candidate_words)
            if overlap > best_overlap:
                best_overlap = overlap
                best_match = candidate

        return best_match

    async def validate_step_inputs_at_runtime(
        self, step: TaskStep
    ) -> PlanValidationResult:
        """
        Validate a single step's inputs at runtime (after template resolution).

        This is called by StepDispatcher as a safety net for legacy plans that
        bypass planner validation.
        It validates that resolved inputs match the agent's schema.

        Args:
            step: TaskStep with resolved inputs

        Returns:
            PlanValidationResult
        """
        errors = await self._validate_step_inputs(step)

        # Also validate agent type
        agent_errors, _ = await self._validate_agent_type(step)
        errors.extend(agent_errors)

        return PlanValidationResult(valid=len(errors) == 0, errors=errors)
