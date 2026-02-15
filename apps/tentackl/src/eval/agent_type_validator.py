"""
Agent Type Validator for the Prompt Evaluation System.

Validates that all agent_type values in generated plans are from the
allowed list of agent types, preventing invented types like
'marketing_strategist' or 'content_creator'.
"""

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog

from src.eval.models import AGENT_OUTPUT_FIELDS, ValidationResult, Violation

logger = structlog.get_logger(__name__)


# Canonical list of valid agent types
VALID_AGENT_TYPES: Set[str] = {
    "web_research",
    "http_fetch",
    "summarize",
    "compose",
    "analyze",
    "transform",
    "aggregate",
    "file_storage",
    "generate_image",
    "html_to_pdf",
    "pdf_composer",
    "notify",
    "send_email",
    "schedule_job",
    "document_db",
    "agent_storage",
}


class AgentTypeValidator:
    """
    Validates that agent_type values in plans are from the allowed list.

    This prevents the LLM from inventing agent types that don't exist,
    such as 'marketing_strategist', 'brand_analyst', etc.
    """

    def __init__(self, valid_types: Optional[Set[str]] = None):
        """
        Initialize the validator.

        Args:
            valid_types: Set of valid agent types. If None, uses VALID_AGENT_TYPES.
        """
        self.valid_types = valid_types or VALID_AGENT_TYPES

    def validate(self, output: str) -> ValidationResult:
        """
        Validate all agent_type values in the output.

        Args:
            output: The LLM output (should be JSON with steps array)

        Returns:
            ValidationResult with valid flag, violations, and score
        """
        violations: List[Violation] = []

        try:
            plan = self._extract_json(output)
            if plan is None:
                violations.append(
                    Violation(
                        rule_name="agent_type_json_parse",
                        pattern_matched="",
                        message="Output is not valid JSON, cannot validate agent types",
                        severity="error",
                    )
                )
                return ValidationResult(valid=False, violations=violations, format_score=0.0)

            steps = plan.get("steps", [])
            if not steps:
                # No steps to validate
                return ValidationResult(valid=True, violations=[], format_score=1.0)

            total_steps = len(steps)
            valid_steps = 0

            for step in steps:
                step_id = step.get("id", step.get("step_id", "unknown"))
                agent_type = step.get("agent_type", "")

                if not agent_type:
                    violations.append(
                        Violation(
                            rule_name="agent_type_missing",
                            pattern_matched=step_id,
                            message=f"Step '{step_id}' is missing agent_type field",
                            severity="error",
                        )
                    )
                elif agent_type not in self.valid_types:
                    violations.append(
                        Violation(
                            rule_name="agent_type_invalid",
                            pattern_matched=agent_type,
                            message=f"Step '{step_id}' uses invalid agent_type '{agent_type}'. Valid types: {sorted(self.valid_types)}",
                            severity="error",
                        )
                    )
                else:
                    valid_steps += 1

            format_score = valid_steps / total_steps if total_steps > 0 else 1.0
            valid = len([v for v in violations if v.severity == "error"]) == 0

            return ValidationResult(
                valid=valid,
                violations=violations,
                format_score=format_score,
            )

        except Exception as e:
            logger.warning("agent_type_validation_failed", error=str(e))
            violations.append(
                Violation(
                    rule_name="agent_type_validation_error",
                    pattern_matched="",
                    message=f"Agent type validation error: {str(e)}",
                    severity="error",
                )
            )
            return ValidationResult(valid=False, violations=violations, format_score=0.0)

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


class OutputFieldsValidator:
    """
    Validates that declared output fields match the agent type's valid outputs.

    This checks the 'outputs' array in each step against the agent's
    allowed output fields from AGENT_OUTPUT_FIELDS.
    """

    def __init__(self, agent_output_fields: Optional[Dict[str, List[str]]] = None):
        """
        Initialize the validator.

        Args:
            agent_output_fields: Mapping of agent types to valid output fields.
                                 If None, uses AGENT_OUTPUT_FIELDS.
        """
        self.agent_output_fields = agent_output_fields or AGENT_OUTPUT_FIELDS

    def validate(self, output: str) -> ValidationResult:
        """
        Validate declared output fields match agent type expectations.

        Args:
            output: The LLM output (should be JSON with steps array)

        Returns:
            ValidationResult with valid flag, violations, and score
        """
        violations: List[Violation] = []

        try:
            plan = self._extract_json(output)
            if plan is None:
                return ValidationResult(valid=True, violations=[], format_score=1.0)

            steps = plan.get("steps", [])
            if not steps:
                return ValidationResult(valid=True, violations=[], format_score=1.0)

            total_fields = 0
            valid_fields = 0

            for step in steps:
                step_id = step.get("id", step.get("step_id", "unknown"))
                agent_type = step.get("agent_type", "")
                declared_outputs = step.get("outputs", [])

                if not declared_outputs or agent_type not in self.agent_output_fields:
                    continue

                allowed_outputs = self.agent_output_fields[agent_type]

                for output_field in declared_outputs:
                    total_fields += 1
                    if output_field in allowed_outputs:
                        valid_fields += 1
                    else:
                        violations.append(
                            Violation(
                                rule_name="output_field_invalid",
                                pattern_matched=output_field,
                                message=f"Step '{step_id}' ({agent_type}) declares invalid output '{output_field}'. Valid outputs: {allowed_outputs}",
                                severity="warning",
                            )
                        )

            format_score = valid_fields / total_fields if total_fields > 0 else 1.0

            # Warnings don't affect validity, only errors do
            error_count = len([v for v in violations if v.severity == "error"])
            valid = error_count == 0

            return ValidationResult(
                valid=valid,
                violations=violations,
                format_score=format_score,
            )

        except Exception as e:
            logger.warning("output_fields_validation_failed", error=str(e))
            return ValidationResult(valid=True, violations=[], format_score=1.0)

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


def validate_agent_types(output: str) -> Tuple[bool, List[str]]:
    """
    Quick function to validate agent types in output.

    Args:
        output: The LLM output to validate

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    validator = AgentTypeValidator()
    result = validator.validate(output)
    errors = [v.message for v in result.violations if v.severity == "error"]
    return result.valid, errors


def validate_output_fields_match_agent(output: str) -> Tuple[bool, List[str]]:
    """
    Quick function to validate output fields match agent types.

    Args:
        output: The LLM output to validate

    Returns:
        Tuple of (is_valid, list of violation messages)
    """
    validator = OutputFieldsValidator()
    result = validator.validate(output)
    messages = [v.message for v in result.violations]
    return result.valid, messages
