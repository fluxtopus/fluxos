"""
Contract Validator

Validates inputs and outputs against schemas to enforce contracts
between pipeline steps. Prevents bad data from propagating.
"""

import structlog
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum

logger = structlog.get_logger(__name__)


class ValidationSeverity(Enum):
    """Severity of validation errors."""
    ERROR = "error"      # Blocks execution
    WARNING = "warning"  # Logs but continues


@dataclass
class ValidationError:
    """A single validation error."""
    field: str
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR
    expected: Optional[Any] = None
    actual: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "message": self.message,
            "severity": self.severity.value,
            "expected": self.expected,
            "actual": self.actual,
        }


@dataclass
class ValidationResult:
    """Result of a validation check."""
    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)

    def add_error(self, field: str, message: str, expected: Any = None, actual: Any = None):
        """Add an error (blocks execution)."""
        self.errors.append(ValidationError(
            field=field,
            message=message,
            severity=ValidationSeverity.ERROR,
            expected=expected,
            actual=actual,
        ))
        self.valid = False

    def add_warning(self, field: str, message: str, expected: Any = None, actual: Any = None):
        """Add a warning (logs but continues)."""
        self.warnings.append(ValidationError(
            field=field,
            message=message,
            severity=ValidationSeverity.WARNING,
            expected=expected,
            actual=actual,
        ))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
        }

    def error_summary(self) -> str:
        """Get a human-readable summary of errors."""
        if not self.errors:
            return ""
        return "; ".join(f"{e.field}: {e.message}" for e in self.errors)


class ContractValidator:
    """
    Validates data against schemas to enforce contracts.

    Supports the schema format used in agent YAML configs:
    ```yaml
    inputs:
      content:
        type: string
        required: true
        description: "Content to process"
      count:
        type: integer
        required: false
        default: 10
        min: 1
        max: 100
    ```

    Validation modes:
    - STRICT: All errors block execution
    - LENIENT: Only required field errors block; type mismatches become warnings
    """

    # Type mapping for validation
    TYPE_MAP = {
        "string": str,
        "str": str,
        "integer": int,
        "int": int,
        "number": (int, float),
        "float": float,
        "boolean": bool,
        "bool": bool,
        "array": list,
        "list": list,
        "object": dict,
        "dict": dict,
        "any": object,
    }

    @classmethod
    def validate_inputs(
        cls,
        inputs: Dict[str, Any],
        schema: Dict[str, Any],
        strict: bool = True,
    ) -> ValidationResult:
        """
        Validate inputs against an input schema.

        Args:
            inputs: The input data to validate
            schema: The input schema (field definitions)
            strict: If True, type errors block; if False, they become warnings

        Returns:
            ValidationResult with errors and warnings
        """
        result = ValidationResult(valid=True)

        if not schema:
            return result

        # Check each field in the schema
        for field_name, field_spec in schema.items():
            if not isinstance(field_spec, dict):
                continue

            value = inputs.get(field_name)
            is_required = field_spec.get("required", False)
            default = field_spec.get("default")
            expected_type = field_spec.get("type", "any")

            # Check required fields
            if value is None:
                if is_required and default is None:
                    result.add_error(
                        field=field_name,
                        message=f"Required field '{field_name}' is missing",
                        expected="value",
                        actual=None,
                    )
                continue

            # Type validation
            cls._validate_type(result, field_name, value, expected_type, field_spec, strict)

            # Enum validation
            if "enum" in field_spec and value is not None:
                allowed = field_spec["enum"]
                if value not in allowed:
                    result.add_error(
                        field=field_name,
                        message=f"Value '{value}' not in allowed values",
                        expected=allowed,
                        actual=value,
                    )

            # Range validation for numbers
            if expected_type in ("integer", "int", "number", "float") and isinstance(value, (int, float)):
                if "min" in field_spec and value < field_spec["min"]:
                    result.add_error(
                        field=field_name,
                        message=f"Value {value} is below minimum {field_spec['min']}",
                        expected=f">= {field_spec['min']}",
                        actual=value,
                    )
                if "max" in field_spec and value > field_spec["max"]:
                    result.add_error(
                        field=field_name,
                        message=f"Value {value} is above maximum {field_spec['max']}",
                        expected=f"<= {field_spec['max']}",
                        actual=value,
                    )

            # Length validation for strings
            if expected_type in ("string", "str") and isinstance(value, str):
                if "min_length" in field_spec and len(value) < field_spec["min_length"]:
                    result.add_error(
                        field=field_name,
                        message=f"String length {len(value)} is below minimum {field_spec['min_length']}",
                        expected=f">= {field_spec['min_length']} chars",
                        actual=len(value),
                    )
                if "max_length" in field_spec and len(value) > field_spec["max_length"]:
                    result.add_error(
                        field=field_name,
                        message=f"String length {len(value)} is above maximum {field_spec['max_length']}",
                        expected=f"<= {field_spec['max_length']} chars",
                        actual=len(value),
                    )

            # Pattern validation for strings
            if "pattern" in field_spec and isinstance(value, str):
                import re
                pattern = field_spec["pattern"]
                if not re.match(pattern, value):
                    result.add_error(
                        field=field_name,
                        message=f"Value does not match required pattern",
                        expected=pattern,
                        actual=value,
                    )

        return result

    @classmethod
    def validate_outputs(
        cls,
        outputs: Any,
        schema: Dict[str, Any],
        strict: bool = True,
    ) -> ValidationResult:
        """
        Validate outputs against an output schema.

        Output validation is more lenient by default since LLMs may
        produce slightly different structures.

        Args:
            outputs: The output data to validate
            schema: The output schema (field definitions)
            strict: If True, missing required fields block; if False, they warn

        Returns:
            ValidationResult with errors and warnings
        """
        result = ValidationResult(valid=True)

        if not schema:
            return result

        # Handle non-dict outputs
        if not isinstance(outputs, dict):
            # If schema expects specific fields but output is not a dict, that's an error
            if schema:
                result.add_error(
                    field="_root",
                    message=f"Expected dict output, got {type(outputs).__name__}",
                    expected="dict",
                    actual=type(outputs).__name__,
                )
            return result

        # Check each field in the schema
        for field_name, field_spec in schema.items():
            if not isinstance(field_spec, dict):
                continue

            value = outputs.get(field_name)
            expected_type = field_spec.get("type", "any")
            is_required = field_spec.get("required", False)

            # Check for required output fields (lenient by default)
            if value is None:
                if is_required:
                    if strict:
                        result.add_error(
                            field=field_name,
                            message=f"Required output field '{field_name}' is missing",
                            expected="value",
                            actual=None,
                        )
                    else:
                        result.add_warning(
                            field=field_name,
                            message=f"Expected output field '{field_name}' is missing",
                            expected="value",
                            actual=None,
                        )
                continue

            # Type validation (warnings for outputs, not errors, unless strict)
            cls._validate_type(result, field_name, value, expected_type, field_spec, strict)

        return result

    @classmethod
    def _validate_type(
        cls,
        result: ValidationResult,
        field_name: str,
        value: Any,
        expected_type: str,
        field_spec: Dict[str, Any],
        strict: bool,
    ) -> None:
        """Validate a value's type against expected type."""
        if expected_type == "any":
            return

        expected_python_type = cls.TYPE_MAP.get(expected_type.lower())
        if expected_python_type is None:
            return  # Unknown type, skip validation

        if not isinstance(value, expected_python_type):
            # Special case: allow int for number type
            if expected_type in ("number", "float") and isinstance(value, int):
                return

            # Special case: allow string representations of numbers
            if expected_type in ("integer", "int", "number", "float") and isinstance(value, str):
                try:
                    if expected_type in ("integer", "int"):
                        int(value)
                    else:
                        float(value)
                    # It's a valid numeric string, just warn
                    result.add_warning(
                        field=field_name,
                        message=f"Numeric string provided instead of {expected_type}",
                        expected=expected_type,
                        actual=type(value).__name__,
                    )
                    return
                except ValueError:
                    pass

            if strict:
                result.add_error(
                    field=field_name,
                    message=f"Expected type '{expected_type}', got '{type(value).__name__}'",
                    expected=expected_type,
                    actual=type(value).__name__,
                )
            else:
                result.add_warning(
                    field=field_name,
                    message=f"Expected type '{expected_type}', got '{type(value).__name__}'",
                    expected=expected_type,
                    actual=type(value).__name__,
                )

    @classmethod
    def apply_defaults(
        cls,
        inputs: Dict[str, Any],
        schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Apply default values from schema to inputs.

        Args:
            inputs: The input data
            schema: The input schema with defaults

        Returns:
            New dict with defaults applied
        """
        result = inputs.copy()

        for field_name, field_spec in schema.items():
            if not isinstance(field_spec, dict):
                continue

            if field_name not in result or result[field_name] is None:
                if "default" in field_spec:
                    result[field_name] = field_spec["default"]

        return result

    @classmethod
    def coerce_types(
        cls,
        data: Dict[str, Any],
        schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Attempt to coerce values to their expected types.

        Args:
            data: The data to coerce
            schema: The schema with type definitions

        Returns:
            New dict with coerced values where possible
        """
        result = data.copy()

        for field_name, field_spec in schema.items():
            if not isinstance(field_spec, dict):
                continue

            if field_name not in result:
                continue

            value = result[field_name]
            expected_type = field_spec.get("type", "any")

            try:
                if expected_type in ("integer", "int") and not isinstance(value, int):
                    result[field_name] = int(value)
                elif expected_type in ("number", "float") and not isinstance(value, (int, float)):
                    result[field_name] = float(value)
                elif expected_type in ("string", "str") and not isinstance(value, str):
                    result[field_name] = str(value)
                elif expected_type in ("boolean", "bool") and not isinstance(value, bool):
                    if isinstance(value, str):
                        result[field_name] = value.lower() in ("true", "yes", "1")
                    else:
                        result[field_name] = bool(value)
            except (ValueError, TypeError):
                pass  # Keep original value if coercion fails

        return result


# Convenience functions
def validate_inputs(inputs: Dict[str, Any], schema: Dict[str, Any], strict: bool = True) -> ValidationResult:
    """Validate inputs against schema."""
    return ContractValidator.validate_inputs(inputs, schema, strict)


def validate_outputs(outputs: Any, schema: Dict[str, Any], strict: bool = True) -> ValidationResult:
    """Validate outputs against schema."""
    return ContractValidator.validate_outputs(outputs, schema, strict)
