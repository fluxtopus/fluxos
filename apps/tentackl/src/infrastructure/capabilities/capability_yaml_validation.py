# REVIEW: Validation rules are hard-coded lists; adding domains/task types
# REVIEW: requires code changes.
# REVIEW: No schema versioning; legacy specs may break silently.
"""
Capability YAML Validation Service.

This service validates capability YAML specifications for the unified
capabilities system. It ensures specs conform to the expected format
and can be used for task execution.

The validation service is used by:
- POST /api/capabilities/agents (create)
- PUT /api/capabilities/agents/{id} (update)
- Future: UI live validation
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from uuid import UUID
import re
import yaml
import structlog
from jinja2 import Environment, BaseLoader, TemplateSyntaxError

logger = structlog.get_logger(__name__)


@dataclass
class ValidationIssue:
    """A single validation issue (error or warning)."""
    field: str
    message: str
    severity: str = "error"  # error, warning, info
    code: Optional[str] = None  # Machine-readable error code


@dataclass
class CapabilityValidationResult:
    """Result of capability validation."""
    is_valid: bool = True
    errors: List[ValidationIssue] = field(default_factory=list)
    warnings: List[ValidationIssue] = field(default_factory=list)
    info: List[ValidationIssue] = field(default_factory=list)
    parsed_spec: Optional[Dict[str, Any]] = None

    def add_error(self, field: str, message: str, code: Optional[str] = None) -> None:
        """Add an error to the result."""
        self.errors.append(ValidationIssue(field, message, "error", code))
        self.is_valid = False

    def add_warning(self, field: str, message: str, code: Optional[str] = None) -> None:
        """Add a warning to the result."""
        self.warnings.append(ValidationIssue(field, message, "warning", code))

    def add_info(self, field: str, message: str, code: Optional[str] = None) -> None:
        """Add an info message to the result."""
        self.info.append(ValidationIssue(field, message, "info", code))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "is_valid": self.is_valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [
                {"field": e.field, "message": e.message, "code": e.code}
                for e in self.errors
            ],
            "warnings": [
                {"field": w.field, "message": w.message, "code": w.code}
                for w in self.warnings
            ],
            "info": [
                {"field": i.field, "message": i.message, "code": i.code}
                for i in self.info
            ],
        }

    def get_error_messages(self) -> List[str]:
        """Get list of error messages for API responses."""
        return [e.message for e in self.errors]


class CapabilityYAMLValidationService:
    """
    Service for validating capability YAML specifications.

    Validates:
    - Required fields (agent_type, system_prompt, inputs)
    - Field formats and types
    - Input/output schema structures
    - Template syntax (Jinja2)
    - Execution hints
    - Examples

    Usage:
        service = CapabilityYAMLValidationService()

        # Validate a YAML string
        result = service.validate(yaml_string)
        if not result.is_valid:
            print(result.errors)

        # Validate with uniqueness check (async)
        result = await service.validate_with_uniqueness(
            yaml_string,
            organization_id=org_id,
            db=db,
            exclude_id=capability_id  # For updates
        )
    """

    # Valid task types
    VALID_TASK_TYPES = [
        "general",
        "reasoning",
        "creative",
        "web_research",
        "analysis",
        "content_writing",
        "data_processing",
        "automation",
        "communication",
    ]

    # Valid input types
    VALID_INPUT_TYPES = [
        "string",
        "integer",
        "number",
        "boolean",
        "array",
        "object",
        "any",
    ]

    # Valid output types
    VALID_OUTPUT_TYPES = [
        "string",
        "integer",
        "number",
        "boolean",
        "array",
        "object",
        "any",
    ]

    # Valid domains
    VALID_DOMAINS = [
        "content",
        "research",
        "analytics",
        "automation",
        "communication",
        "integration",
        "utility",
        "data",
        "finance",
        "marketing",
    ]

    # Valid execution hint keys
    VALID_EXECUTION_HINTS = [
        "deterministic",
        "speed",
        "cost",
        "max_tokens",
        "temperature",
        "uses_web_plugin",
        "requires_tool",
        "parallel_safe",
    ]

    # Speed/cost values
    VALID_SPEED_VALUES = ["fast", "medium", "slow"]
    VALID_COST_VALUES = ["low", "medium", "high"]

    def __init__(self):
        """Initialize the validation service."""
        self.jinja_env = Environment(loader=BaseLoader())

    def validate(
        self,
        spec: str | Dict[str, Any],
        strict: bool = False,
    ) -> CapabilityValidationResult:
        """
        Validate a capability specification.

        Args:
            spec: YAML string or already-parsed dict
            strict: If True, treat warnings as errors

        Returns:
            CapabilityValidationResult with errors, warnings, and parsed spec
        """
        result = CapabilityValidationResult()

        # Parse YAML if string
        if isinstance(spec, str):
            try:
                parsed = yaml.safe_load(spec)
                result.parsed_spec = parsed
            except yaml.YAMLError as e:
                result.add_error("yaml", f"Invalid YAML syntax: {str(e)}", "YAML_SYNTAX")
                return result
        else:
            parsed = spec
            result.parsed_spec = parsed

        # Must be a dict
        if not isinstance(parsed, dict):
            result.add_error("root", "YAML specification must be an object", "NOT_OBJECT")
            return result

        # Validate required fields
        self._validate_required_fields(parsed, result)

        # Validate field formats
        self._validate_field_formats(parsed, result)

        # Validate inputs schema
        self._validate_inputs(parsed, result)

        # Validate outputs schema
        self._validate_outputs(parsed, result)

        # Validate system_prompt template
        self._validate_template(parsed, result)

        # Validate execution hints
        self._validate_execution_hints(parsed, result)

        # Validate examples
        self._validate_examples(parsed, result)

        # Check recommended fields
        self._check_recommended_fields(parsed, result)

        # In strict mode, convert warnings to errors
        if strict and result.warnings:
            for warning in result.warnings:
                result.add_error(
                    warning.field,
                    f"[Strict] {warning.message}",
                    f"STRICT_{warning.code}" if warning.code else "STRICT_WARNING"
                )

        return result

    def _validate_required_fields(
        self,
        spec: Dict[str, Any],
        result: CapabilityValidationResult,
    ) -> None:
        """Validate required fields are present and non-empty."""
        # agent_type is required
        if not spec.get("agent_type"):
            result.add_error("agent_type", "Missing required field: agent_type", "MISSING_AGENT_TYPE")

        # system_prompt is required
        if not spec.get("system_prompt"):
            result.add_error("system_prompt", "Missing required field: system_prompt", "MISSING_SYSTEM_PROMPT")

        # inputs is required (must be a dict)
        inputs = spec.get("inputs")
        if inputs is None:
            result.add_error("inputs", "Missing required field: inputs", "MISSING_INPUTS")
        elif not isinstance(inputs, dict):
            result.add_error("inputs", "inputs must be an object with input field definitions", "INPUTS_NOT_OBJECT")

    def _validate_field_formats(
        self,
        spec: Dict[str, Any],
        result: CapabilityValidationResult,
    ) -> None:
        """Validate field formats and allowed values."""
        # Validate agent_type format (alphanumeric and underscores only)
        agent_type = spec.get("agent_type", "")
        if agent_type:
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', agent_type):
                result.add_error(
                    "agent_type",
                    "agent_type must start with a letter and contain only alphanumeric characters and underscores",
                    "INVALID_AGENT_TYPE_FORMAT"
                )
            if len(agent_type) > 100:
                result.add_error(
                    "agent_type",
                    "agent_type must be 100 characters or less",
                    "AGENT_TYPE_TOO_LONG"
                )
            # Recommend snake_case
            if agent_type != agent_type.lower():
                result.add_warning(
                    "agent_type",
                    "agent_type should be lowercase (snake_case recommended)",
                    "AGENT_TYPE_NOT_LOWERCASE"
                )

        # Validate name (optional but if present should be string)
        name = spec.get("name")
        if name is not None:
            if not isinstance(name, str):
                result.add_error("name", "name must be a string", "NAME_NOT_STRING")
            elif len(name) > 200:
                result.add_error("name", "name must be 200 characters or less", "NAME_TOO_LONG")

        # Validate description (optional but recommended)
        description = spec.get("description")
        if description is not None and not isinstance(description, str):
            result.add_error("description", "description must be a string", "DESCRIPTION_NOT_STRING")

        # Validate domain
        domain = spec.get("domain")
        if domain:
            if not isinstance(domain, str):
                result.add_error("domain", "domain must be a string", "DOMAIN_NOT_STRING")
            elif domain not in self.VALID_DOMAINS:
                result.add_warning(
                    "domain",
                    f"Unknown domain '{domain}'. Known domains: {', '.join(self.VALID_DOMAINS)}",
                    "UNKNOWN_DOMAIN"
                )

        # Validate task_type
        task_type = spec.get("task_type")
        if task_type:
            if not isinstance(task_type, str):
                result.add_error("task_type", "task_type must be a string", "TASK_TYPE_NOT_STRING")
            elif task_type not in self.VALID_TASK_TYPES:
                result.add_error(
                    "task_type",
                    f"Invalid task_type '{task_type}'. Valid values: {', '.join(self.VALID_TASK_TYPES)}",
                    "INVALID_TASK_TYPE"
                )

        # Validate system_prompt type
        system_prompt = spec.get("system_prompt")
        if system_prompt is not None and not isinstance(system_prompt, str):
            result.add_error("system_prompt", "system_prompt must be a string", "SYSTEM_PROMPT_NOT_STRING")

    def _validate_inputs(
        self,
        spec: Dict[str, Any],
        result: CapabilityValidationResult,
    ) -> None:
        """Validate input schema structure."""
        inputs = spec.get("inputs", {})
        if not isinstance(inputs, dict):
            return  # Already reported in required fields

        for input_name, input_def in inputs.items():
            # Validate input name format
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', input_name):
                result.add_error(
                    f"inputs.{input_name}",
                    f"Input name '{input_name}' must start with a letter and contain only alphanumeric characters and underscores",
                    "INVALID_INPUT_NAME"
                )

            # Input definition must be a dict
            if not isinstance(input_def, dict):
                result.add_error(
                    f"inputs.{input_name}",
                    f"Input '{input_name}' definition must be an object",
                    "INPUT_NOT_OBJECT"
                )
                continue

            # Required: type field
            input_type = input_def.get("type")
            if not input_type:
                result.add_error(
                    f"inputs.{input_name}.type",
                    f"Input '{input_name}' missing required 'type' field",
                    "MISSING_INPUT_TYPE"
                )
            elif input_type not in self.VALID_INPUT_TYPES:
                result.add_error(
                    f"inputs.{input_name}.type",
                    f"Input '{input_name}' has invalid type '{input_type}'. Valid types: {', '.join(self.VALID_INPUT_TYPES)}",
                    "INVALID_INPUT_TYPE"
                )

            # Validate required field (must be boolean if present)
            required = input_def.get("required")
            if required is not None and not isinstance(required, bool):
                result.add_error(
                    f"inputs.{input_name}.required",
                    f"Input '{input_name}' required field must be a boolean",
                    "REQUIRED_NOT_BOOLEAN"
                )

            # Validate description (recommended)
            if "description" not in input_def:
                result.add_info(
                    f"inputs.{input_name}.description",
                    f"Input '{input_name}' should have a description for documentation",
                    "MISSING_INPUT_DESCRIPTION"
                )

            # Validate enum if present
            enum = input_def.get("enum")
            if enum is not None:
                if not isinstance(enum, list):
                    result.add_error(
                        f"inputs.{input_name}.enum",
                        f"Input '{input_name}' enum must be an array",
                        "ENUM_NOT_ARRAY"
                    )
                elif len(enum) == 0:
                    result.add_error(
                        f"inputs.{input_name}.enum",
                        f"Input '{input_name}' enum cannot be empty",
                        "ENUM_EMPTY"
                    )

            # Validate default value type matches declared type
            default = input_def.get("default")
            if default is not None and input_type:
                self._validate_value_matches_type(
                    default,
                    input_type,
                    f"inputs.{input_name}.default",
                    result
                )

    def _validate_outputs(
        self,
        spec: Dict[str, Any],
        result: CapabilityValidationResult,
    ) -> None:
        """Validate output schema structure."""
        outputs = spec.get("outputs", {})
        if not outputs:
            # Outputs are optional
            return

        if not isinstance(outputs, dict):
            result.add_error("outputs", "outputs must be an object with output field definitions", "OUTPUTS_NOT_OBJECT")
            return

        for output_name, output_def in outputs.items():
            # Validate output name format
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', output_name):
                result.add_error(
                    f"outputs.{output_name}",
                    f"Output name '{output_name}' must start with a letter and contain only alphanumeric characters and underscores",
                    "INVALID_OUTPUT_NAME"
                )

            # Output definition must be a dict
            if not isinstance(output_def, dict):
                result.add_error(
                    f"outputs.{output_name}",
                    f"Output '{output_name}' definition must be an object",
                    "OUTPUT_NOT_OBJECT"
                )
                continue

            # Required: type field
            output_type = output_def.get("type")
            if not output_type:
                result.add_error(
                    f"outputs.{output_name}.type",
                    f"Output '{output_name}' missing required 'type' field",
                    "MISSING_OUTPUT_TYPE"
                )
            elif output_type not in self.VALID_OUTPUT_TYPES:
                result.add_error(
                    f"outputs.{output_name}.type",
                    f"Output '{output_name}' has invalid type '{output_type}'. Valid types: {', '.join(self.VALID_OUTPUT_TYPES)}",
                    "INVALID_OUTPUT_TYPE"
                )

            # Validate description (recommended)
            if "description" not in output_def:
                result.add_info(
                    f"outputs.{output_name}.description",
                    f"Output '{output_name}' should have a description for documentation",
                    "MISSING_OUTPUT_DESCRIPTION"
                )

    def _validate_template(
        self,
        spec: Dict[str, Any],
        result: CapabilityValidationResult,
    ) -> None:
        """Validate Jinja2 template syntax in system_prompt."""
        system_prompt = spec.get("system_prompt", "")
        if not system_prompt or not isinstance(system_prompt, str):
            return

        # Check for Jinja2 syntax if template markers are present
        if "{{" in system_prompt or "{%" in system_prompt:
            try:
                self.jinja_env.from_string(system_prompt)
            except TemplateSyntaxError as e:
                result.add_error(
                    "system_prompt",
                    f"Jinja2 template syntax error: {str(e)}",
                    "TEMPLATE_SYNTAX_ERROR"
                )

    def _validate_execution_hints(
        self,
        spec: Dict[str, Any],
        result: CapabilityValidationResult,
    ) -> None:
        """Validate execution hints structure."""
        hints = spec.get("execution_hints", {})
        if not hints:
            return

        if not isinstance(hints, dict):
            result.add_error("execution_hints", "execution_hints must be an object", "HINTS_NOT_OBJECT")
            return

        # Validate known hint keys
        for key, value in hints.items():
            if key not in self.VALID_EXECUTION_HINTS:
                result.add_warning(
                    f"execution_hints.{key}",
                    f"Unknown execution hint '{key}'. Known hints: {', '.join(self.VALID_EXECUTION_HINTS)}",
                    "UNKNOWN_EXECUTION_HINT"
                )

            # Validate specific hint values
            if key == "deterministic" and not isinstance(value, bool):
                result.add_error(
                    "execution_hints.deterministic",
                    "deterministic must be a boolean",
                    "DETERMINISTIC_NOT_BOOLEAN"
                )

            if key == "speed" and value not in self.VALID_SPEED_VALUES:
                result.add_error(
                    "execution_hints.speed",
                    f"Invalid speed value '{value}'. Valid values: {', '.join(self.VALID_SPEED_VALUES)}",
                    "INVALID_SPEED_VALUE"
                )

            if key == "cost" and value not in self.VALID_COST_VALUES:
                result.add_error(
                    "execution_hints.cost",
                    f"Invalid cost value '{value}'. Valid values: {', '.join(self.VALID_COST_VALUES)}",
                    "INVALID_COST_VALUE"
                )

            if key == "max_tokens":
                if not isinstance(value, int):
                    result.add_error(
                        "execution_hints.max_tokens",
                        "max_tokens must be an integer",
                        "MAX_TOKENS_NOT_INTEGER"
                    )
                elif value < 1 or value > 128000:
                    result.add_warning(
                        "execution_hints.max_tokens",
                        f"max_tokens value {value} seems unusual (expected 1-128000)",
                        "MAX_TOKENS_UNUSUAL"
                    )

            if key == "temperature":
                if not isinstance(value, (int, float)):
                    result.add_error(
                        "execution_hints.temperature",
                        "temperature must be a number",
                        "TEMPERATURE_NOT_NUMBER"
                    )
                elif value < 0 or value > 2:
                    result.add_warning(
                        "execution_hints.temperature",
                        f"temperature value {value} is outside typical range (0-2)",
                        "TEMPERATURE_UNUSUAL"
                    )

    def _validate_examples(
        self,
        spec: Dict[str, Any],
        result: CapabilityValidationResult,
    ) -> None:
        """Validate examples structure."""
        examples = spec.get("examples", [])
        if not examples:
            return

        if not isinstance(examples, list):
            result.add_error("examples", "examples must be an array", "EXAMPLES_NOT_ARRAY")
            return

        inputs = spec.get("inputs", {})
        required_inputs = [
            name for name, defn in inputs.items()
            if isinstance(defn, dict) and defn.get("required", False)
        ]

        for i, example in enumerate(examples):
            if not isinstance(example, dict):
                result.add_error(
                    f"examples[{i}]",
                    f"Example {i} must be an object",
                    "EXAMPLE_NOT_OBJECT"
                )
                continue

            # Check that required inputs are present in example
            for req in required_inputs:
                if req not in example:
                    result.add_warning(
                        f"examples[{i}]",
                        f"Example {i} is missing required input '{req}'",
                        "EXAMPLE_MISSING_REQUIRED_INPUT"
                    )

    def _check_recommended_fields(
        self,
        spec: Dict[str, Any],
        result: CapabilityValidationResult,
    ) -> None:
        """Check for recommended but optional fields."""
        if not spec.get("name"):
            result.add_info("name", "Recommended field 'name' is not defined", "MISSING_NAME")

        if not spec.get("description"):
            result.add_info("description", "Recommended field 'description' is not defined", "MISSING_DESCRIPTION")

        if not spec.get("domain"):
            result.add_info("domain", "Recommended field 'domain' is not defined", "MISSING_DOMAIN")

        if not spec.get("outputs"):
            result.add_info("outputs", "No outputs defined (capability won't have typed outputs)", "MISSING_OUTPUTS")

        if not spec.get("examples"):
            result.add_info("examples", "No examples defined (examples help document usage)", "MISSING_EXAMPLES")

    def _validate_value_matches_type(
        self,
        value: Any,
        expected_type: str,
        field_path: str,
        result: CapabilityValidationResult,
    ) -> None:
        """Validate that a value matches the expected type."""
        type_checks = {
            "string": lambda v: isinstance(v, str),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
            "array": lambda v: isinstance(v, list),
            "object": lambda v: isinstance(v, dict),
            "any": lambda v: True,
        }

        checker = type_checks.get(expected_type)
        if checker and not checker(value):
            result.add_warning(
                field_path,
                f"Default value type mismatch: expected {expected_type}, got {type(value).__name__}",
                "TYPE_MISMATCH"
            )

    async def validate_with_uniqueness(
        self,
        spec: str | Dict[str, Any],
        organization_id: UUID,
        db: Any,  # Database interface
        exclude_id: Optional[UUID] = None,
        strict: bool = False,
    ) -> CapabilityValidationResult:
        """
        Validate spec with uniqueness check against database.

        Args:
            spec: YAML string or parsed dict
            organization_id: Organization to check uniqueness within
            db: Database interface
            exclude_id: Capability ID to exclude (for updates)
            strict: If True, treat warnings as errors

        Returns:
            CapabilityValidationResult with uniqueness check included
        """
        # First run standard validation
        result = self.validate(spec, strict=strict)

        # If basic validation failed, don't check uniqueness
        if not result.is_valid:
            return result

        # Get agent_type from parsed spec
        agent_type = result.parsed_spec.get("agent_type") if result.parsed_spec else None
        if not agent_type:
            return result  # Already handled in required fields

        # Check uniqueness in database
        try:
            from src.database.capability_models import AgentCapability
            from sqlalchemy import select, and_

            async with db.get_session() as session:
                conditions = [
                    AgentCapability.organization_id == organization_id,
                    AgentCapability.agent_type == agent_type,
                    AgentCapability.is_latest == True,  # noqa: E712
                ]

                if exclude_id:
                    conditions.append(AgentCapability.id != exclude_id)

                query = select(AgentCapability).where(and_(*conditions))
                existing = await session.execute(query)
                if existing.scalar_one_or_none():
                    result.add_error(
                        "agent_type",
                        f"Capability with agent_type '{agent_type}' already exists in your organization",
                        "AGENT_TYPE_NOT_UNIQUE"
                    )

        except Exception as e:
            logger.error("Failed to check uniqueness", error=str(e))
            result.add_warning(
                "uniqueness",
                f"Could not verify uniqueness: {str(e)}",
                "UNIQUENESS_CHECK_FAILED"
            )

        return result


def extract_keywords(spec: Dict[str, Any]) -> List[str]:
    """
    Extract keywords from capability spec for text search fallback.

    Extracts from: agent_type, name, description, domain, input names, output names.
    """
    keywords = set()

    # Add agent_type words
    agent_type = spec.get("agent_type", "")
    keywords.update(agent_type.replace("_", " ").split())

    # Add name words
    name = spec.get("name", "")
    keywords.update(name.lower().split())

    # Add domain
    domain = spec.get("domain", "")
    if domain:
        keywords.add(domain.lower())

    # Add input names
    inputs = spec.get("inputs", {})
    if isinstance(inputs, dict):
        for input_name in inputs.keys():
            keywords.update(input_name.replace("_", " ").lower().split())

    # Add output names
    outputs = spec.get("outputs", {})
    if isinstance(outputs, dict):
        for output_name in outputs.keys():
            keywords.update(output_name.replace("_", " ").lower().split())

    # Clean up: remove very short words and common words
    stop_words = {"the", "a", "an", "is", "of", "to", "for", "and", "or", "in", "on"}
    keywords = [k for k in keywords if len(k) > 2 and k not in stop_words]

    # Limit to reasonable number
    return list(keywords)[:20]


# Singleton instance for convenience
_validation_service: Optional[CapabilityYAMLValidationService] = None


def get_validation_service() -> CapabilityYAMLValidationService:
    """Get the singleton validation service instance."""
    global _validation_service
    if _validation_service is None:
        _validation_service = CapabilityYAMLValidationService()
    return _validation_service
