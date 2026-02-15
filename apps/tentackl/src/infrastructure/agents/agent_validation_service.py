# REVIEW: Duplicates capability/type lists and validation rules from
# REVIEW: capability_yaml_validation; risk of drift.
"""
Agent Validation Service for Tentackl Agent Memory System.

This service validates agent specifications before publication.
Supports schema validation, capability checking, and dry-run testing.

Validation Steps:
1. Schema validation - YAML structure and required fields
2. Capability validation - Check all capabilities are available
3. Template validation - Verify Jinja2 templates compile
4. Dry-run - Execute with mock inputs in sandbox
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import json
import yaml
import structlog
from jinja2 import Environment, BaseLoader, TemplateSyntaxError, UndefinedError

logger = structlog.get_logger(__name__)


@dataclass
class ValidationError:
    """A single validation error."""
    field: str
    message: str
    severity: str = "error"  # error, warning, info


@dataclass
class ValidationResult:
    """Result of validation operation."""
    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    info: List[ValidationError] = field(default_factory=list)

    def add_error(self, field: str, message: str):
        self.errors.append(ValidationError(field, message, "error"))
        self.is_valid = False

    def add_warning(self, field: str, message: str):
        self.warnings.append(ValidationError(field, message, "warning"))

    def add_info(self, field: str, message: str):
        self.info.append(ValidationError(field, message, "info"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [{"field": e.field, "message": e.message} for e in self.errors],
            "warnings": [{"field": w.field, "message": w.message} for w in self.warnings],
            "info": [{"field": i.field, "message": i.message} for i in self.info],
        }


@dataclass
class DryRunResult:
    """Result of dry-run execution."""
    success: bool
    prompt_rendered: Optional[str] = None
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: int = 0
    warnings: List[str] = field(default_factory=list)


class AgentValidationService:
    """
    Service for validating agent specifications.

    Provides comprehensive validation including:
    - Schema structure validation
    - Capability availability checking
    - Jinja2 template compilation
    - Dry-run execution with mock inputs

    Usage:
        service = AgentValidationService()

        # Validate spec
        result = service.validate(yaml_spec)
        if not result.is_valid:
            print(result.errors)

        # Dry-run with mock inputs
        dry_run = await service.dry_run(
            yaml_spec,
            mock_inputs={"topic": "AI", "audience": "developers"}
        )
    """

    # Required fields in agent spec
    REQUIRED_FIELDS = ["name", "type", "description"]

    # Optional but recommended fields
    RECOMMENDED_FIELDS = ["brief", "keywords", "category", "prompt_template"]

    # Valid agent types
    AGENT_TYPES = [
        "compose", "analyze", "transform", "notify",
        "http_fetch", "file_storage", "document_db",
        "agent_storage", "custom",
    ]

    # Valid capabilities
    CAPABILITIES = [
        "http_fetch", "file_storage", "document_db",
        "agent_storage", "notify", "generate_image",
        "schedule_job", "html_to_pdf",
    ]

    # Valid categories
    CATEGORIES = [
        "automation", "content", "data", "communication",
        "utility", "integration", "persistence",
    ]

    def __init__(self):
        """Initialize validation service."""
        self.jinja_env = Environment(loader=BaseLoader())

    def validate(
        self,
        spec: str | Dict[str, Any],
        strict: bool = False,
    ) -> ValidationResult:
        """
        Validate an agent specification.

        Args:
            spec: YAML string or parsed dict
            strict: If True, treat warnings as errors

        Returns:
            ValidationResult with errors and warnings
        """
        result = ValidationResult(is_valid=True)

        # Parse YAML if string
        if isinstance(spec, str):
            try:
                spec = yaml.safe_load(spec)
            except yaml.YAMLError as e:
                result.add_error("yaml", f"Invalid YAML syntax: {str(e)}")
                return result

        # Check for root agent key
        if "agent" not in spec:
            result.add_error("root", "Missing 'agent' root key")
            return result

        agent = spec["agent"]

        # Validate required fields
        self._validate_required_fields(agent, result)

        # Validate field types and values
        self._validate_field_values(agent, result)

        # Validate capabilities
        self._validate_capabilities(agent, result)

        # Validate templates
        self._validate_templates(agent, result)

        # Validate schemas
        self._validate_schemas(agent, result)

        # Check recommended fields
        self._check_recommended_fields(agent, result)

        # In strict mode, treat warnings as errors
        if strict and result.warnings:
            for warning in result.warnings:
                result.add_error(warning.field, f"[Strict] {warning.message}")

        return result

    def _validate_required_fields(
        self,
        agent: Dict[str, Any],
        result: ValidationResult,
    ) -> None:
        """Check that all required fields are present."""
        for field in self.REQUIRED_FIELDS:
            if field not in agent:
                result.add_error(field, f"Missing required field: {field}")
            elif not agent[field]:
                result.add_error(field, f"Field '{field}' cannot be empty")

    def _validate_field_values(
        self,
        agent: Dict[str, Any],
        result: ValidationResult,
    ) -> None:
        """Validate field values are correct types and within allowed values."""
        # Validate name format
        name = agent.get("name", "")
        if name:
            if not name.replace("_", "").isalnum():
                result.add_error("name", "Name must be alphanumeric with underscores only")
            if name != name.lower():
                result.add_warning("name", "Name should be lowercase (snake_case)")

        # Validate type
        agent_type = agent.get("type", "")
        if agent_type and agent_type not in self.AGENT_TYPES:
            result.add_error("type", f"Unknown agent type: {agent_type}. Valid: {self.AGENT_TYPES}")

        # Validate category
        category = agent.get("category", "")
        if category and category not in self.CATEGORIES:
            result.add_warning("category", f"Unknown category: {category}. Valid: {self.CATEGORIES}")

        # Validate version format
        version = agent.get("version", "")
        if version:
            parts = version.split(".")
            if len(parts) != 3 or not all(p.isdigit() for p in parts):
                result.add_warning("version", "Version should be semantic (e.g., 1.0.0)")

        # Validate keywords
        keywords = agent.get("keywords", [])
        if keywords and not isinstance(keywords, list):
            result.add_error("keywords", "Keywords must be a list")

        # Validate brief length
        brief = agent.get("brief", "")
        if brief and len(brief) > 150:
            result.add_warning("brief", f"Brief is too long ({len(brief)} chars). Keep under 150.")

    def _validate_capabilities(
        self,
        agent: Dict[str, Any],
        result: ValidationResult,
    ) -> None:
        """Check that all declared capabilities are available."""
        capabilities = agent.get("capabilities", [])

        if not isinstance(capabilities, list):
            result.add_error("capabilities", "Capabilities must be a list")
            return

        for cap in capabilities:
            if cap not in self.CAPABILITIES:
                result.add_error(
                    "capabilities",
                    f"Unknown capability: {cap}. Valid: {self.CAPABILITIES}"
                )

    def _validate_templates(
        self,
        agent: Dict[str, Any],
        result: ValidationResult,
    ) -> None:
        """Validate Jinja2 templates compile correctly."""
        # Validate system_prompt
        system_prompt = agent.get("system_prompt", "")
        if system_prompt:
            try:
                self.jinja_env.from_string(system_prompt)
            except TemplateSyntaxError as e:
                result.add_error("system_prompt", f"Template syntax error: {str(e)}")

        # Validate prompt_template
        prompt_template = agent.get("prompt_template", "")
        if prompt_template:
            try:
                self.jinja_env.from_string(prompt_template)
            except TemplateSyntaxError as e:
                result.add_error("prompt_template", f"Template syntax error: {str(e)}")

    def _validate_schemas(
        self,
        agent: Dict[str, Any],
        result: ValidationResult,
    ) -> None:
        """Validate input/output JSON schemas."""
        # Validate input_schema
        input_schema = agent.get("input_schema", {})
        if input_schema:
            if not isinstance(input_schema, dict):
                result.add_error("input_schema", "Input schema must be an object")
            elif "type" not in input_schema:
                result.add_warning("input_schema", "Input schema should have 'type' field")
            elif input_schema.get("type") != "object":
                result.add_warning("input_schema", "Input schema type should be 'object'")

        # Validate output_schema
        output_schema = agent.get("output_schema", {})
        if output_schema:
            if not isinstance(output_schema, dict):
                result.add_error("output_schema", "Output schema must be an object")
            elif "type" not in output_schema:
                result.add_warning("output_schema", "Output schema should have 'type' field")

    def _check_recommended_fields(
        self,
        agent: Dict[str, Any],
        result: ValidationResult,
    ) -> None:
        """Check for recommended but optional fields."""
        for field in self.RECOMMENDED_FIELDS:
            if field not in agent:
                result.add_info(field, f"Recommended field '{field}' is not defined")

        # Check for empty checkpoints
        checkpoints = agent.get("checkpoints", [])
        if not checkpoints:
            result.add_info("checkpoints", "No checkpoints defined (agent will run without user interaction)")

    async def dry_run(
        self,
        spec: str | Dict[str, Any],
        mock_inputs: Optional[Dict[str, Any]] = None,
        mock_context: Optional[Dict[str, Any]] = None,
    ) -> DryRunResult:
        """
        Execute a dry-run of the agent with mock inputs.

        Args:
            spec: YAML string or parsed dict
            mock_inputs: Mock input values for template rendering
            mock_context: Mock context values

        Returns:
            DryRunResult with rendered prompt and any errors
        """
        start_time = datetime.utcnow()
        mock_inputs = mock_inputs or {}
        mock_context = mock_context or {}
        warnings = []

        # Parse YAML if string
        if isinstance(spec, str):
            try:
                spec = yaml.safe_load(spec)
            except yaml.YAMLError as e:
                return DryRunResult(
                    success=False,
                    error=f"Invalid YAML: {str(e)}",
                )

        if "agent" not in spec:
            return DryRunResult(
                success=False,
                error="Missing 'agent' root key",
            )

        agent = spec["agent"]

        # Check for required inputs
        input_schema = agent.get("input_schema", {})
        required_inputs = input_schema.get("required", [])
        for req in required_inputs:
            if req not in mock_inputs:
                warnings.append(f"Required input '{req}' not provided in mock_inputs")

        # Build template context
        template_context = {
            "inputs": mock_inputs,
            "context": mock_context,
            "agent_name": agent.get("name", "test_agent"),
            "agent_type": agent.get("type", "custom"),
            "timestamp": datetime.utcnow().isoformat(),
            **mock_inputs,  # Also expose inputs directly
        }

        try:
            # Render system prompt
            system_prompt = agent.get("system_prompt", "")
            rendered_system = ""
            if system_prompt:
                template = self.jinja_env.from_string(system_prompt)
                rendered_system = template.render(**template_context)

            # Render prompt template
            prompt_template = agent.get("prompt_template", "")
            rendered_prompt = ""
            if prompt_template:
                template = self.jinja_env.from_string(prompt_template)
                rendered_prompt = template.render(**template_context)

            # Combine prompts
            full_prompt = ""
            if rendered_system:
                full_prompt += f"<system>\n{rendered_system}\n</system>\n\n"
            if rendered_prompt:
                full_prompt += rendered_prompt

            execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            return DryRunResult(
                success=True,
                prompt_rendered=full_prompt,
                output={
                    "system_prompt_length": len(rendered_system),
                    "prompt_length": len(rendered_prompt),
                    "total_length": len(full_prompt),
                    "template_variables_used": list(template_context.keys()),
                },
                warnings=warnings,
                execution_time_ms=execution_time,
            )

        except UndefinedError as e:
            return DryRunResult(
                success=False,
                error=f"Template variable error: {str(e)}",
                warnings=warnings,
            )
        except Exception as e:
            return DryRunResult(
                success=False,
                error=f"Dry-run failed: {str(e)}",
                warnings=warnings,
            )

    def validate_for_publish(
        self,
        spec: str | Dict[str, Any],
    ) -> Tuple[bool, ValidationResult, List[str]]:
        """
        Comprehensive validation for publication.

        Runs all validations in strict mode and returns
        whether the spec is ready for publication.

        Args:
            spec: YAML string or parsed dict

        Returns:
            Tuple of (can_publish, validation_result, blockers)
        """
        result = self.validate(spec, strict=True)

        blockers = []

        if result.errors:
            for error in result.errors:
                blockers.append(f"{error.field}: {error.message}")

        # Additional publication checks
        if isinstance(spec, str):
            spec = yaml.safe_load(spec)

        if "agent" in spec:
            agent = spec["agent"]

            # Must have description
            desc = agent.get("description", "")
            if len(desc) < 50:
                blockers.append("Description too short (min 50 chars)")

            # Must have prompt_template
            if not agent.get("prompt_template"):
                blockers.append("Missing prompt_template (required for publication)")

            # Should have at least one keyword
            if not agent.get("keywords"):
                result.add_warning("keywords", "No keywords defined (limits discoverability)")

        can_publish = len(blockers) == 0

        return can_publish, result, blockers
