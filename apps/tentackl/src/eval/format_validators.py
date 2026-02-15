"""
Format validators for the Prompt Evaluation System.

Key validator: TemplateSyntaxValidator - catches template syntax errors
like {{step_X.output}} vs {{step_X.outputs.field}}.
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

import structlog

from src.eval.models import (
    AGENT_OUTPUT_FIELDS,
    FormatRequirements,
    TemplateSyntaxRule,
    ValidationResult,
    Violation,
    get_template_syntax_rules,
)
from src.eval.agent_type_validator import (
    AgentTypeValidator,
    OutputFieldsValidator,
    VALID_AGENT_TYPES,
)

logger = structlog.get_logger(__name__)


class TemplateSyntaxValidator:
    """
    Validates template syntax in generated outputs.

    This is the key validator for the task planner template syntax issue.
    It checks for correct {{step_X.outputs.field}} syntax and catches
    common errors like {{step_X.output}} or missing field names.
    """

    def __init__(self, rules: Optional[List[TemplateSyntaxRule]] = None):
        """
        Initialize the validator with syntax rules.

        Args:
            rules: List of TemplateSyntaxRule objects. If None, uses default rules.
        """
        self.rules = rules or get_template_syntax_rules()
        self._compiled_rules: Dict[str, Dict[str, List[re.Pattern]]] = {}
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns for efficiency."""
        for rule in self.rules:
            self._compiled_rules[rule.name] = {
                "valid": [re.compile(p) for p in rule.valid_patterns],
                "invalid": [re.compile(p) for p in rule.invalid_patterns],
            }

    def validate(self, output: str) -> ValidationResult:
        """
        Validate output against all template syntax rules.

        Args:
            output: The LLM output to validate

        Returns:
            ValidationResult with valid flag, violations, and score
        """
        violations: List[Violation] = []
        total_checks = 0
        passed_checks = 0

        for rule in self.rules:
            compiled = self._compiled_rules[rule.name]

            # Check for invalid patterns (these should NOT appear)
            for pattern in compiled["invalid"]:
                matches = list(pattern.finditer(output))
                total_checks += 1

                if matches:
                    for match in matches:
                        violations.append(
                            Violation(
                                rule_name=rule.name,
                                pattern_matched=match.group(0),
                                message=rule.error_message,
                                severity=rule.severity,
                                position=match.start(),
                                context=self._get_context(output, match.start()),
                            )
                        )
                else:
                    passed_checks += 1

        # Calculate format score
        format_score = passed_checks / total_checks if total_checks > 0 else 1.0

        # Determine validity (no errors = valid)
        error_violations = [v for v in violations if v.severity == "error"]
        valid = len(error_violations) == 0

        return ValidationResult(
            valid=valid,
            violations=violations,
            format_score=format_score,
        )

    def validate_dependencies(self, output: str) -> List[Violation]:
        """
        Semantic validation: check that dependencies are properly declared.

        This parses the JSON output and verifies that steps referencing
        other steps' outputs have those steps in their dependencies.

        Args:
            output: The LLM output (should be JSON with steps array)

        Returns:
            List of violations for missing dependencies
        """
        violations: List[Violation] = []

        try:
            # Try to extract JSON from the output
            plan = self._extract_json(output)
            if plan is None:
                return violations

            steps = plan.get("steps", [])
            if not steps:
                return violations

            for step in steps:
                step_id = step.get("id", step.get("step_id", ""))
                inputs = step.get("inputs", {})
                dependencies = set(step.get("dependencies", step.get("depends_on", [])))

                # Convert inputs to string for pattern matching
                inputs_str = json.dumps(inputs)

                # Find all step references in inputs
                referenced_steps = set(re.findall(r"\{\{(step_\d+)\.outputs", inputs_str))

                # Check each reference has corresponding dependency
                for ref in referenced_steps:
                    if ref not in dependencies:
                        violations.append(
                            Violation(
                                rule_name="dependencies_declared",
                                pattern_matched=f"{{{{{ref}.outputs...}}}}",
                                message=f"Step {step_id} references {ref} but doesn't list it in dependencies",
                                severity="error",
                            )
                        )

            return violations

        except Exception as e:
            logger.warning("dependency_validation_failed", error=str(e))
            return violations

    def validate_output_field_names(self, output: str) -> List[Violation]:
        """
        Validate that output field names match agent-specific expectations.

        For example, web_research should use outputs.findings, not outputs.content.

        Args:
            output: The LLM output (should be JSON with steps array)

        Returns:
            List of violations for incorrect output field names
        """
        violations: List[Violation] = []

        try:
            plan = self._extract_json(output)
            if plan is None:
                return violations

            steps = plan.get("steps", [])
            if not steps:
                return violations

            # Build a map of step_id -> agent_type
            step_agents: Dict[str, str] = {}
            for step in steps:
                step_id = step.get("id", step.get("step_id", ""))
                agent_type = step.get("agent_type", "")
                if step_id and agent_type:
                    step_agents[step_id] = agent_type

            # Find all template references
            output_str = json.dumps(plan)
            template_refs = re.findall(r"\{\{(step_\d+)\.outputs\.(\w+)\}\}", output_str)

            for step_ref, field_name in template_refs:
                agent_type = step_agents.get(step_ref)
                if agent_type and agent_type in AGENT_OUTPUT_FIELDS:
                    valid_fields = AGENT_OUTPUT_FIELDS[agent_type]
                    if field_name not in valid_fields:
                        violations.append(
                            Violation(
                                rule_name="output_field_names",
                                pattern_matched=f"{{{{{step_ref}.outputs.{field_name}}}}}",
                                message=f"Agent '{agent_type}' typically uses outputs: {valid_fields}, not '{field_name}'",
                                severity="warning",
                            )
                        )

            return violations

        except Exception as e:
            logger.warning("field_name_validation_failed", error=str(e))
            return violations

    def _extract_json(self, output: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from output, handling markdown code blocks."""
        # Try direct parse
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            pass

        # Try extracting from code block
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", output, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding JSON object in text
        json_start = output.find("{")
        json_end = output.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            try:
                return json.loads(output[json_start:json_end])
            except json.JSONDecodeError:
                pass

        return None

    def _get_context(self, output: str, position: int, context_chars: int = 50) -> str:
        """Get surrounding context for a violation."""
        start = max(0, position - context_chars)
        end = min(len(output), position + context_chars)
        context = output[start:end]
        if start > 0:
            context = "..." + context
        if end < len(output):
            context = context + "..."
        return context


class JSONSchemaValidator:
    """Validates JSON output against a JSON schema."""

    def __init__(self, schema: Dict[str, Any]):
        self.schema = schema

    def validate(self, output: str) -> ValidationResult:
        """
        Validate output against JSON schema.

        Args:
            output: The LLM output to validate

        Returns:
            ValidationResult with valid flag and violations
        """
        violations: List[Violation] = []

        try:
            # Try to parse JSON
            data = self._extract_json(output)
            if data is None:
                violations.append(
                    Violation(
                        rule_name="json_parse",
                        pattern_matched="",
                        message="Output is not valid JSON",
                        severity="error",
                    )
                )
                return ValidationResult(valid=False, violations=violations, format_score=0.0)

            # Check required fields
            required = self.schema.get("required", [])
            for field in required:
                if field not in data:
                    violations.append(
                        Violation(
                            rule_name="required_field",
                            pattern_matched=field,
                            message=f"Required field '{field}' is missing",
                            severity="error",
                        )
                    )

            # Check field types
            properties = self.schema.get("properties", {})
            for field, field_schema in properties.items():
                if field in data:
                    expected_type = field_schema.get("type")
                    if expected_type and not self._check_type(data[field], expected_type):
                        violations.append(
                            Violation(
                                rule_name="field_type",
                                pattern_matched=field,
                                message=f"Field '{field}' expected type '{expected_type}', got '{type(data[field]).__name__}'",
                                severity="error",
                            )
                        )

            # Calculate score
            total_checks = len(required) + len(properties)
            error_count = len([v for v in violations if v.severity == "error"])
            format_score = 1.0 - (error_count / total_checks) if total_checks > 0 else 1.0

            return ValidationResult(
                valid=len([v for v in violations if v.severity == "error"]) == 0,
                violations=violations,
                format_score=max(0.0, format_score),
            )

        except Exception as e:
            violations.append(
                Violation(
                    rule_name="validation_error",
                    pattern_matched="",
                    message=f"Validation error: {str(e)}",
                    severity="error",
                )
            )
            return ValidationResult(valid=False, violations=violations, format_score=0.0)

    def _extract_json(self, output: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from output."""
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", output, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        json_start = output.find("{")
        json_end = output.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            try:
                return json.loads(output[json_start:json_end])
            except json.JSONDecodeError:
                pass

        return None

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected JSON schema type."""
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None),
        }
        expected = type_map.get(expected_type)
        if expected is None:
            return True
        return isinstance(value, expected)


class OutputFieldValidator:
    """Validates that expected output fields are present."""

    def __init__(self, required_fields: List[str]):
        self.required_fields = required_fields

    def validate(self, output: str) -> ValidationResult:
        """
        Validate that required fields are present in output.

        Args:
            output: The LLM output to validate

        Returns:
            ValidationResult with valid flag and violations
        """
        violations: List[Violation] = []

        try:
            data = self._extract_json(output)
            if data is None:
                violations.append(
                    Violation(
                        rule_name="json_parse",
                        pattern_matched="",
                        message="Output is not valid JSON",
                        severity="error",
                    )
                )
                return ValidationResult(valid=False, violations=violations, format_score=0.0)

            missing = []
            for field in self.required_fields:
                if field not in data:
                    missing.append(field)
                    violations.append(
                        Violation(
                            rule_name="required_field",
                            pattern_matched=field,
                            message=f"Required field '{field}' is missing",
                            severity="error",
                        )
                    )

            format_score = 1.0 - (len(missing) / len(self.required_fields)) if self.required_fields else 1.0

            return ValidationResult(
                valid=len(missing) == 0,
                violations=violations,
                format_score=format_score,
            )

        except Exception as e:
            violations.append(
                Violation(
                    rule_name="validation_error",
                    pattern_matched="",
                    message=f"Validation error: {str(e)}",
                    severity="error",
                )
            )
            return ValidationResult(valid=False, violations=violations, format_score=0.0)

    def _extract_json(self, output: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from output."""
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", output, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        return None


class FormatValidator:
    """
    Combined format validator that checks all format requirements.

    Uses TemplateSyntaxValidator, JSONSchemaValidator, and OutputFieldValidator
    as needed based on the FormatRequirements.
    """

    def validate(self, output: str, requirements: FormatRequirements) -> Tuple[float, List[str]]:
        """
        Validate output against all format requirements.

        Args:
            output: The LLM output to validate
            requirements: FormatRequirements specifying what to check

        Returns:
            Tuple of (format_score, list of violation messages)
        """
        all_violations: List[str] = []
        total_score = 0.0
        num_validators = 0

        # Template syntax validation
        if requirements.template_syntax_rules:
            validator = TemplateSyntaxValidator(requirements.template_syntax_rules)
            result = validator.validate(output)
            total_score += result.format_score
            num_validators += 1
            all_violations.extend([v.message for v in result.violations])

            # Also check dependencies
            dep_violations = validator.validate_dependencies(output)
            all_violations.extend([v.message for v in dep_violations])

            # And field names
            field_violations = validator.validate_output_field_names(output)
            all_violations.extend([v.message for v in field_violations if v.severity == "error"])

        # JSON schema validation
        if requirements.json_schema:
            validator = JSONSchemaValidator(requirements.json_schema)
            result = validator.validate(output)
            total_score += result.format_score
            num_validators += 1
            all_violations.extend([v.message for v in result.violations])

        # Required fields validation
        if requirements.required_fields:
            validator = OutputFieldValidator(requirements.required_fields)
            result = validator.validate(output)
            total_score += result.format_score
            num_validators += 1
            all_violations.extend([v.message for v in result.violations])

        # JSON type check
        if requirements.expected_type == "json":
            try:
                json.loads(output)
            except json.JSONDecodeError:
                # Try extracting from code block
                json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", output, re.DOTALL)
                if json_match:
                    try:
                        json.loads(json_match.group(1))
                    except json.JSONDecodeError:
                        all_violations.append("Output is not valid JSON")
                        total_score -= 0.5
                else:
                    all_violations.append("Output is not valid JSON")
                    total_score -= 0.5

        # Agent type validation (for task planner outputs)
        if requirements.validate_agent_types:
            agent_validator = AgentTypeValidator()
            result = agent_validator.validate(output)
            total_score += result.format_score
            num_validators += 1
            all_violations.extend([v.message for v in result.violations if v.severity == "error"])

        # Output fields validation (check declared outputs match agent type)
        if requirements.validate_output_fields:
            fields_validator = OutputFieldsValidator()
            result = fields_validator.validate(output)
            total_score += result.format_score
            num_validators += 1
            # Include warnings as well for output fields
            all_violations.extend([v.message for v in result.violations])

        # Calculate final score
        format_score = total_score / num_validators if num_validators > 0 else 1.0
        format_score = max(0.0, min(1.0, format_score))

        return format_score, all_violations


def validate_template_syntax_quick(text: str) -> Tuple[bool, List[str]]:
    """
    Quick template syntax validation without full configuration.

    Args:
        text: Text to validate for template syntax

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    validator = TemplateSyntaxValidator()
    result = validator.validate(text)
    errors = [v.message for v in result.violations if v.severity == "error"]
    return result.valid, errors
