"""
Schema Validator for Delegation System

Provides strict validation for subagent inputs and outputs based on
declarative schema definitions. Integrates with the Orchestrator for
pre/post-execution validation.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Callable
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class SchemaType(Enum):
    """Supported schema types."""

    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    LIST = "list"
    DICT = "dict"
    ANY = "any"


@dataclass
class ValidationError:
    """Single validation error."""

    field: str
    message: str
    expected: Optional[str] = None
    actual: Optional[str] = None
    severity: str = "error"  # error, warning

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
            "severity": self.severity,
        }


@dataclass
class ValidationResult:
    """Result of schema validation."""

    valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    coerced_data: Optional[Dict[str, Any]] = None

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
        }


def _is_numeric(s: str) -> bool:
    """Check if string represents a number."""
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def _str_to_bool(s: str) -> Optional[bool]:
    """Convert string to boolean."""
    if not isinstance(s, str):
        return None
    s_lower = s.lower().strip()
    if s_lower in ("true", "yes", "1", "on"):
        return True
    if s_lower in ("false", "no", "0", "off"):
        return False
    return None


def _str_to_int(s: str) -> Optional[int]:
    """Convert string to int if valid."""
    if not isinstance(s, str):
        return None
    s = s.strip()
    if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
        return int(s)
    return None


def _str_to_float(s: str) -> Optional[float]:
    """Convert string to float if valid."""
    if not isinstance(s, str):
        return None
    if _is_numeric(s):
        return float(s)
    return None


def _dict_to_list(d: dict) -> Optional[list]:
    """Extract list from dict with known keys."""
    if not isinstance(d, dict):
        return None
    if "rows" in d and isinstance(d["rows"], list):
        return d["rows"]
    if "data" in d and isinstance(d["data"], list):
        return d["data"]
    return None


class SchemaValidator:
    """
    Validates data against schema definitions.

    Supports:
    - Type validation (string, int, float, bool, list, dict, any)
    - Required field validation
    - Enum validation
    - Numeric constraints (min, max)
    - Length constraints (min_length, max_length)
    - Optional type coercion for safe conversions
    """

    # Type coercion rules: (source_type, target_type) -> coercion_function
    SAFE_COERCIONS: Dict[Tuple[str, str], Callable[[Any], Optional[Any]]] = {
        ("int", "float"): lambda x: float(x),
        ("float", "int"): lambda x: int(x) if float(x).is_integer() else None,
        ("string", "int"): _str_to_int,
        ("string", "float"): _str_to_float,
        ("string", "bool"): _str_to_bool,
        ("bool", "string"): lambda x: str(x).lower(),
        ("dict", "list"): _dict_to_list,
    }

    def __init__(self, enable_coercion: bool = True):
        """
        Initialize validator.

        Args:
            enable_coercion: If True, attempt safe type coercions
        """
        self.enable_coercion = enable_coercion

    def validate_inputs(
        self,
        data: Dict[str, Any],
        schema: Dict[str, Dict[str, Any]],
        agent_type: str = "unknown",
    ) -> ValidationResult:
        """
        Validate input data against schema.

        Args:
            data: Input data to validate
            schema: inputs_schema from subagent
            agent_type: Name of agent (for logging)

        Returns:
            ValidationResult with errors, warnings, and optionally coerced data
        """
        if not schema:
            return ValidationResult(valid=True, coerced_data=data)

        errors: List[ValidationError] = []
        warnings: List[ValidationError] = []
        coerced = dict(data) if self.enable_coercion else None

        # Check for required fields
        for field_name, spec in schema.items():
            if spec.get("required", False) and field_name not in data:
                if "default" in spec:
                    if coerced is not None:
                        coerced[field_name] = spec["default"]
                else:
                    errors.append(
                        ValidationError(
                            field=field_name,
                            message=f"Required field '{field_name}' is missing",
                            expected="value",
                            actual="missing",
                        )
                    )

        # Validate each provided field
        for field_name, value in data.items():
            if field_name not in schema:
                # Unknown field - warn but don't error (extensibility)
                warnings.append(
                    ValidationError(
                        field=field_name,
                        message=f"Unknown field '{field_name}' not in schema",
                        severity="warning",
                    )
                )
                continue

            spec = schema[field_name]
            field_errors, field_warnings, coerced_value = self._validate_field(
                field_name, value, spec
            )
            errors.extend(field_errors)
            warnings.extend(field_warnings)

            if coerced is not None and coerced_value is not None:
                coerced[field_name] = coerced_value

        valid = len(errors) == 0

        if not valid:
            logger.warning(
                "Input validation failed",
                agent_type=agent_type,
                error_count=len(errors),
                errors=[e.to_dict() for e in errors],
            )

        return ValidationResult(
            valid=valid,
            errors=errors,
            warnings=warnings,
            coerced_data=coerced if valid else None,
        )

    def validate_outputs(
        self,
        data: Dict[str, Any],
        schema: Dict[str, Dict[str, Any]],
        agent_type: str = "unknown",
    ) -> ValidationResult:
        """
        Validate output data against schema.

        Output validation is less strict - we don't fail on missing fields
        but do type-check provided fields.
        """
        if not schema:
            return ValidationResult(valid=True)

        errors: List[ValidationError] = []
        warnings: List[ValidationError] = []

        for field_name, spec in schema.items():
            if field_name not in data:
                if not spec.get("nullable", False):
                    warnings.append(
                        ValidationError(
                            field=field_name,
                            message=f"Expected output field '{field_name}' is missing",
                            severity="warning",
                        )
                    )
                continue

            value = data[field_name]
            expected_type = spec.get("type", "any")

            if expected_type != "any" and value is not None:
                actual_type = self._get_type_name(value)
                if not self._types_match(actual_type, expected_type):
                    errors.append(
                        ValidationError(
                            field=field_name,
                            message="Output type mismatch",
                            expected=expected_type,
                            actual=actual_type,
                        )
                    )

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def _validate_field(
        self,
        field_name: str,
        value: Any,
        spec: Dict[str, Any],
    ) -> Tuple[List[ValidationError], List[ValidationError], Any]:
        """Validate a single field against its spec."""
        errors: List[ValidationError] = []
        warnings: List[ValidationError] = []
        coerced_value = value

        # Handle null values
        if value is None:
            if spec.get("nullable", False):
                return errors, warnings, None
            if spec.get("required", False):
                errors.append(
                    ValidationError(
                        field=field_name,
                        message=f"Field '{field_name}' cannot be null",
                    )
                )
            return errors, warnings, None

        # Type validation
        expected_type = spec.get("type", "any")
        if expected_type != "any":
            actual_type = self._get_type_name(value)

            if not self._types_match(actual_type, expected_type):
                # Attempt coercion
                if self.enable_coercion:
                    coerced = self._attempt_coercion(
                        value, actual_type, expected_type, field_name
                    )
                    if coerced is not None:
                        coerced_value = coerced
                        warnings.append(
                            ValidationError(
                                field=field_name,
                                message=f"Coerced from {actual_type} to {expected_type}",
                                severity="warning",
                            )
                        )
                    else:
                        errors.append(
                            ValidationError(
                                field=field_name,
                                message=f"Type mismatch for '{field_name}'",
                                expected=expected_type,
                                actual=actual_type,
                            )
                        )
                else:
                    errors.append(
                        ValidationError(
                            field=field_name,
                            message=f"Type mismatch for '{field_name}'",
                            expected=expected_type,
                            actual=actual_type,
                        )
                    )

        # Enum validation
        if "enum" in spec and value not in spec["enum"]:
            errors.append(
                ValidationError(
                    field=field_name,
                    message=f"Value must be one of {spec['enum']}",
                    expected=str(spec["enum"]),
                    actual=str(value),
                )
            )

        # Numeric constraints
        if expected_type in ("int", "float") and isinstance(value, (int, float)):
            if "min" in spec and value < spec["min"]:
                errors.append(
                    ValidationError(
                        field=field_name,
                        message=f"Value {value} is below minimum {spec['min']}",
                    )
                )
            if "max" in spec and value > spec["max"]:
                errors.append(
                    ValidationError(
                        field=field_name,
                        message=f"Value {value} exceeds maximum {spec['max']}",
                    )
                )

        # Length constraints
        if expected_type in ("string", "list") and hasattr(value, "__len__"):
            if "min_length" in spec and len(value) < spec["min_length"]:
                errors.append(
                    ValidationError(
                        field=field_name,
                        message=f"Length {len(value)} is below minimum {spec['min_length']}",
                    )
                )
            if "max_length" in spec and len(value) > spec["max_length"]:
                errors.append(
                    ValidationError(
                        field=field_name,
                        message=f"Length {len(value)} exceeds maximum {spec['max_length']}",
                    )
                )

        return errors, warnings, coerced_value

    def _get_type_name(self, value: Any) -> str:
        """Get the schema type name for a Python value."""
        if isinstance(value, bool):  # Must check before int
            return "bool"
        elif isinstance(value, int):
            return "int"
        elif isinstance(value, float):
            return "float"
        elif isinstance(value, str):
            return "string"
        elif isinstance(value, list):
            return "list"
        elif isinstance(value, dict):
            return "dict"
        return "any"

    def _types_match(self, actual: str, expected: str) -> bool:
        """Check if types match, with some flexibility."""
        if actual == expected:
            return True
        # int is acceptable where float is expected
        if expected == "float" and actual == "int":
            return True
        return False

    def _attempt_coercion(
        self,
        value: Any,
        actual_type: str,
        expected_type: str,
        field_name: str,
    ) -> Optional[Any]:
        """Attempt to coerce value to expected type."""
        key = (actual_type, expected_type)

        if key in self.SAFE_COERCIONS:
            try:
                result = self.SAFE_COERCIONS[key](value)
                if result is not None:
                    logger.debug(
                        "Coerced field value",
                        field=field_name,
                        from_type=actual_type,
                        to_type=expected_type,
                    )
                    return result
            except (ValueError, TypeError):
                pass

        return None
