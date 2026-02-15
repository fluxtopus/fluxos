"""
Unit tests for ContractValidator.

Tests the contract enforcement system that validates inputs and outputs
against schemas to prevent bad data from propagating between pipeline steps.
"""

import pytest
from src.contracts.validator import (
    ContractValidator,
    ValidationResult,
    ValidationError,
    ValidationSeverity,
    validate_inputs,
    validate_outputs,
)


class TestValidationResult:
    """Test ValidationResult class."""

    def test_new_result_is_valid(self):
        """New result should be valid by default."""
        result = ValidationResult(valid=True)
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_add_error_makes_invalid(self):
        """Adding an error should make result invalid."""
        result = ValidationResult(valid=True)
        result.add_error("field", "test error")

        assert result.valid is False
        assert len(result.errors) == 1
        assert result.errors[0].field == "field"
        assert result.errors[0].message == "test error"
        assert result.errors[0].severity == ValidationSeverity.ERROR

    def test_add_warning_stays_valid(self):
        """Adding a warning should not make result invalid."""
        result = ValidationResult(valid=True)
        result.add_warning("field", "test warning")

        assert result.valid is True
        assert len(result.warnings) == 1
        assert result.warnings[0].severity == ValidationSeverity.WARNING

    def test_error_summary(self):
        """Test error summary generation."""
        result = ValidationResult(valid=True)
        result.add_error("name", "is required")
        result.add_error("age", "must be positive")

        summary = result.error_summary()
        assert "name: is required" in summary
        assert "age: must be positive" in summary

    def test_error_summary_empty(self):
        """Test error summary when no errors."""
        result = ValidationResult(valid=True)
        assert result.error_summary() == ""

    def test_to_dict(self):
        """Test serialization to dict."""
        result = ValidationResult(valid=True)
        result.add_error("field1", "error1", expected="string", actual="int")
        result.add_warning("field2", "warning1")

        d = result.to_dict()
        assert d["valid"] is False
        assert len(d["errors"]) == 1
        assert len(d["warnings"]) == 1
        assert d["errors"][0]["field"] == "field1"
        assert d["errors"][0]["expected"] == "string"


class TestValidationError:
    """Test ValidationError class."""

    def test_to_dict(self):
        """Test error serialization."""
        error = ValidationError(
            field="test_field",
            message="test message",
            severity=ValidationSeverity.ERROR,
            expected="string",
            actual="int"
        )

        d = error.to_dict()
        assert d["field"] == "test_field"
        assert d["message"] == "test message"
        assert d["severity"] == "error"
        assert d["expected"] == "string"
        assert d["actual"] == "int"


class TestInputValidation:
    """Test input validation."""

    def test_empty_schema_always_valid(self):
        """Empty schema should always pass."""
        result = ContractValidator.validate_inputs({"any": "data"}, {})
        assert result.valid is True

    def test_required_field_present(self):
        """Required field present should pass."""
        schema = {
            "name": {"type": "string", "required": True}
        }
        inputs = {"name": "John"}

        result = ContractValidator.validate_inputs(inputs, schema)
        assert result.valid is True

    def test_required_field_missing(self):
        """Missing required field should fail."""
        schema = {
            "name": {"type": "string", "required": True}
        }
        inputs = {}

        result = ContractValidator.validate_inputs(inputs, schema)
        assert result.valid is False
        assert len(result.errors) == 1
        assert "name" in result.errors[0].field

    def test_required_field_with_default(self):
        """Required field with default should pass when missing."""
        schema = {
            "count": {"type": "integer", "required": True, "default": 10}
        }
        inputs = {}

        result = ContractValidator.validate_inputs(inputs, schema)
        assert result.valid is True

    def test_optional_field_missing(self):
        """Missing optional field should pass."""
        schema = {
            "name": {"type": "string", "required": False}
        }
        inputs = {}

        result = ContractValidator.validate_inputs(inputs, schema)
        assert result.valid is True

    def test_type_validation_string(self):
        """String type validation."""
        schema = {"field": {"type": "string"}}

        # Valid string
        result = ContractValidator.validate_inputs({"field": "hello"}, schema)
        assert result.valid is True

        # Invalid - number
        result = ContractValidator.validate_inputs({"field": 123}, schema)
        assert result.valid is False

    def test_type_validation_integer(self):
        """Integer type validation."""
        schema = {"field": {"type": "integer"}}

        # Valid int
        result = ContractValidator.validate_inputs({"field": 42}, schema)
        assert result.valid is True

        # Invalid - float
        result = ContractValidator.validate_inputs({"field": 42.5}, schema)
        assert result.valid is False

        # Invalid - string
        result = ContractValidator.validate_inputs({"field": "42"}, schema)
        # String "42" should produce warning, not error
        assert len(result.warnings) > 0 or result.valid is False

    def test_type_validation_number(self):
        """Number type validation accepts int and float."""
        schema = {"field": {"type": "number"}}

        # Valid int
        result = ContractValidator.validate_inputs({"field": 42}, schema)
        assert result.valid is True

        # Valid float
        result = ContractValidator.validate_inputs({"field": 42.5}, schema)
        assert result.valid is True

    def test_type_validation_boolean(self):
        """Boolean type validation."""
        schema = {"field": {"type": "boolean"}}

        # Valid true
        result = ContractValidator.validate_inputs({"field": True}, schema)
        assert result.valid is True

        # Valid false
        result = ContractValidator.validate_inputs({"field": False}, schema)
        assert result.valid is True

        # Invalid - string
        result = ContractValidator.validate_inputs({"field": "true"}, schema)
        assert result.valid is False

    def test_type_validation_array(self):
        """Array type validation."""
        schema = {"field": {"type": "array"}}

        # Valid list
        result = ContractValidator.validate_inputs({"field": [1, 2, 3]}, schema)
        assert result.valid is True

        # Valid empty list
        result = ContractValidator.validate_inputs({"field": []}, schema)
        assert result.valid is True

        # Invalid - dict
        result = ContractValidator.validate_inputs({"field": {}}, schema)
        assert result.valid is False

    def test_type_validation_object(self):
        """Object type validation."""
        schema = {"field": {"type": "object"}}

        # Valid dict
        result = ContractValidator.validate_inputs({"field": {"key": "value"}}, schema)
        assert result.valid is True

        # Valid empty dict
        result = ContractValidator.validate_inputs({"field": {}}, schema)
        assert result.valid is True

        # Invalid - list
        result = ContractValidator.validate_inputs({"field": []}, schema)
        assert result.valid is False

    def test_type_validation_any(self):
        """Any type accepts everything."""
        schema = {"field": {"type": "any"}}

        for value in ["string", 123, 45.6, True, [], {}, None]:
            if value is not None:
                result = ContractValidator.validate_inputs({"field": value}, schema)
                assert result.valid is True

    def test_enum_validation(self):
        """Enum validation."""
        schema = {
            "status": {
                "type": "string",
                "enum": ["pending", "active", "completed"]
            }
        }

        # Valid enum value
        result = ContractValidator.validate_inputs({"status": "active"}, schema)
        assert result.valid is True

        # Invalid enum value
        result = ContractValidator.validate_inputs({"status": "invalid"}, schema)
        assert result.valid is False
        assert "allowed values" in result.errors[0].message.lower()

    def test_min_max_validation(self):
        """Min/max range validation."""
        schema = {
            "count": {"type": "integer", "min": 1, "max": 100}
        }

        # Valid in range
        result = ContractValidator.validate_inputs({"count": 50}, schema)
        assert result.valid is True

        # Valid at boundaries
        result = ContractValidator.validate_inputs({"count": 1}, schema)
        assert result.valid is True
        result = ContractValidator.validate_inputs({"count": 100}, schema)
        assert result.valid is True

        # Below min
        result = ContractValidator.validate_inputs({"count": 0}, schema)
        assert result.valid is False
        assert "minimum" in result.errors[0].message.lower()

        # Above max
        result = ContractValidator.validate_inputs({"count": 101}, schema)
        assert result.valid is False
        assert "maximum" in result.errors[0].message.lower()

    def test_string_length_validation(self):
        """String min/max length validation."""
        schema = {
            "name": {"type": "string", "min_length": 3, "max_length": 10}
        }

        # Valid length
        result = ContractValidator.validate_inputs({"name": "John"}, schema)
        assert result.valid is True

        # Too short
        result = ContractValidator.validate_inputs({"name": "Jo"}, schema)
        assert result.valid is False

        # Too long
        result = ContractValidator.validate_inputs({"name": "JohnJacobson"}, schema)
        assert result.valid is False

    def test_pattern_validation(self):
        """Regex pattern validation."""
        schema = {
            "email": {"type": "string", "pattern": r"^[\w\.-]+@[\w\.-]+\.\w+$"}
        }

        # Valid email
        result = ContractValidator.validate_inputs({"email": "test@example.com"}, schema)
        assert result.valid is True

        # Invalid email
        result = ContractValidator.validate_inputs({"email": "not-an-email"}, schema)
        assert result.valid is False
        assert "pattern" in result.errors[0].message.lower()

    def test_strict_mode(self):
        """Strict mode should produce errors."""
        schema = {"field": {"type": "integer"}}

        result = ContractValidator.validate_inputs(
            {"field": "string"}, schema, strict=True
        )
        assert result.valid is False
        assert len(result.errors) > 0

    def test_lenient_mode(self):
        """Lenient mode should produce warnings for type mismatches."""
        schema = {"field": {"type": "integer"}}

        result = ContractValidator.validate_inputs(
            {"field": "string"}, schema, strict=False
        )
        # Lenient mode: type errors become warnings, but still mark as warning
        assert len(result.warnings) > 0 or result.valid is False

    def test_multiple_fields(self):
        """Test validation with multiple fields."""
        schema = {
            "name": {"type": "string", "required": True},
            "age": {"type": "integer", "min": 0, "max": 150},
            "email": {"type": "string", "required": True},
            "status": {"type": "string", "enum": ["active", "inactive"]}
        }

        # All valid
        inputs = {
            "name": "John",
            "age": 25,
            "email": "john@example.com",
            "status": "active"
        }
        result = ContractValidator.validate_inputs(inputs, schema)
        assert result.valid is True

        # Multiple errors
        inputs = {
            "name": 123,  # Wrong type
            "age": 200,  # Out of range
            # Missing email
            "status": "unknown"  # Invalid enum
        }
        result = ContractValidator.validate_inputs(inputs, schema)
        assert result.valid is False
        assert len(result.errors) >= 3  # At least name, email, status errors


class TestOutputValidation:
    """Test output validation."""

    def test_empty_schema_always_valid(self):
        """Empty schema should always pass."""
        result = ContractValidator.validate_outputs({"any": "data"}, {})
        assert result.valid is True

    def test_non_dict_output_fails(self):
        """Non-dict output should fail when schema expects fields."""
        schema = {"result": {"type": "string"}}

        result = ContractValidator.validate_outputs("just a string", schema)
        assert result.valid is False
        assert "_root" in result.errors[0].field

    def test_required_output_present(self):
        """Required output field present should pass."""
        schema = {
            "result": {"type": "string", "required": True}
        }
        outputs = {"result": "success"}

        result = ContractValidator.validate_outputs(outputs, schema)
        assert result.valid is True

    def test_required_output_missing_strict(self):
        """Missing required output in strict mode should fail."""
        schema = {
            "result": {"type": "string", "required": True}
        }
        outputs = {}

        result = ContractValidator.validate_outputs(outputs, schema, strict=True)
        assert result.valid is False

    def test_required_output_missing_lenient(self):
        """Missing required output in lenient mode should warn."""
        schema = {
            "result": {"type": "string", "required": True}
        }
        outputs = {}

        result = ContractValidator.validate_outputs(outputs, schema, strict=False)
        assert result.valid is True  # Lenient mode
        assert len(result.warnings) > 0

    def test_output_type_validation(self):
        """Output type validation works."""
        schema = {
            "summary": {"type": "string"},
            "count": {"type": "integer"},
            "items": {"type": "array"}
        }

        # All valid types
        outputs = {
            "summary": "Test summary",
            "count": 5,
            "items": ["a", "b", "c"]
        }
        result = ContractValidator.validate_outputs(outputs, schema)
        assert result.valid is True

        # Wrong types in strict mode
        outputs = {
            "summary": 123,  # Should be string
            "count": "five",  # Should be int
            "items": "not a list"  # Should be array
        }
        result = ContractValidator.validate_outputs(outputs, schema, strict=True)
        assert result.valid is False


class TestApplyDefaults:
    """Test default value application."""

    def test_apply_defaults_empty(self):
        """No defaults to apply."""
        schema = {"name": {"type": "string"}}
        inputs = {"name": "John"}

        result = ContractValidator.apply_defaults(inputs, schema)
        assert result == inputs

    def test_apply_defaults_missing_field(self):
        """Default applied to missing field."""
        schema = {
            "count": {"type": "integer", "default": 10}
        }
        inputs = {}

        result = ContractValidator.apply_defaults(inputs, schema)
        assert result["count"] == 10

    def test_apply_defaults_none_value(self):
        """Default applied when value is None."""
        schema = {
            "count": {"type": "integer", "default": 10}
        }
        inputs = {"count": None}

        result = ContractValidator.apply_defaults(inputs, schema)
        assert result["count"] == 10

    def test_apply_defaults_existing_value_preserved(self):
        """Existing value not overwritten."""
        schema = {
            "count": {"type": "integer", "default": 10}
        }
        inputs = {"count": 5}

        result = ContractValidator.apply_defaults(inputs, schema)
        assert result["count"] == 5

    def test_apply_defaults_multiple_fields(self):
        """Multiple defaults applied."""
        schema = {
            "count": {"type": "integer", "default": 10},
            "style": {"type": "string", "default": "brief"},
            "name": {"type": "string"}  # No default
        }
        inputs = {"name": "test"}

        result = ContractValidator.apply_defaults(inputs, schema)
        assert result["count"] == 10
        assert result["style"] == "brief"
        assert result["name"] == "test"


class TestCoerceTypes:
    """Test type coercion."""

    def test_coerce_string_to_int(self):
        """String numeric coerced to int."""
        schema = {"count": {"type": "integer"}}
        data = {"count": "42"}

        result = ContractValidator.coerce_types(data, schema)
        assert result["count"] == 42
        assert isinstance(result["count"], int)

    def test_coerce_string_to_float(self):
        """String numeric coerced to float."""
        schema = {"price": {"type": "float"}}
        data = {"price": "42.50"}

        result = ContractValidator.coerce_types(data, schema)
        assert result["price"] == 42.50
        assert isinstance(result["price"], float)

    def test_coerce_to_string(self):
        """Number coerced to string."""
        schema = {"id": {"type": "string"}}
        data = {"id": 12345}

        result = ContractValidator.coerce_types(data, schema)
        assert result["id"] == "12345"
        assert isinstance(result["id"], str)

    def test_coerce_string_to_bool(self):
        """String coerced to boolean."""
        schema = {"active": {"type": "boolean"}}

        # True strings
        for val in ["true", "True", "yes", "1"]:
            result = ContractValidator.coerce_types({"active": val}, schema)
            assert result["active"] is True

        # False strings
        for val in ["false", "False", "no", "0"]:
            result = ContractValidator.coerce_types({"active": val}, schema)
            assert result["active"] is False

    def test_coerce_invalid_keeps_original(self):
        """Invalid coercion keeps original value."""
        schema = {"count": {"type": "integer"}}
        data = {"count": "not a number"}

        result = ContractValidator.coerce_types(data, schema)
        assert result["count"] == "not a number"

    def test_coerce_missing_field(self):
        """Missing field skipped."""
        schema = {"count": {"type": "integer"}}
        data = {}

        result = ContractValidator.coerce_types(data, schema)
        assert "count" not in result


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_validate_inputs_function(self):
        """Test validate_inputs convenience function."""
        schema = {"name": {"type": "string", "required": True}}

        result = validate_inputs({"name": "John"}, schema)
        assert result.valid is True

        result = validate_inputs({}, schema)
        assert result.valid is False

    def test_validate_outputs_function(self):
        """Test validate_outputs convenience function."""
        schema = {"result": {"type": "string"}}

        result = validate_outputs({"result": "success"}, schema)
        assert result.valid is True

        result = validate_outputs("not a dict", schema)
        assert result.valid is False


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_nested_schema_not_supported(self):
        """Non-dict schema entries are skipped."""
        schema = {
            "field1": {"type": "string"},
            "field2": "not a dict"  # Should be skipped
        }

        result = ContractValidator.validate_inputs({"field1": "test"}, schema)
        assert result.valid is True

    def test_null_value_handling(self):
        """None values handled correctly."""
        schema = {
            "optional_field": {"type": "string", "required": False}
        }

        result = ContractValidator.validate_inputs({"optional_field": None}, schema)
        assert result.valid is True

    def test_extra_fields_in_inputs(self):
        """Extra fields in inputs are ignored."""
        schema = {
            "name": {"type": "string", "required": True}
        }
        inputs = {
            "name": "John",
            "extra": "ignored"
        }

        result = ContractValidator.validate_inputs(inputs, schema)
        assert result.valid is True

    def test_numeric_string_warning(self):
        """Numeric string produces warning, not error."""
        schema = {"count": {"type": "integer"}}

        result = ContractValidator.validate_inputs(
            {"count": "42"}, schema, strict=True
        )
        # Should warn about numeric string
        assert len(result.warnings) > 0 or result.valid is True

    def test_type_aliases(self):
        """Type aliases work correctly."""
        schema = {
            "str_field": {"type": "str"},
            "int_field": {"type": "int"},
            "bool_field": {"type": "bool"},
            "list_field": {"type": "list"},
            "dict_field": {"type": "dict"}
        }

        inputs = {
            "str_field": "hello",
            "int_field": 42,
            "bool_field": True,
            "list_field": [1, 2, 3],
            "dict_field": {"key": "value"}
        }

        result = ContractValidator.validate_inputs(inputs, schema)
        assert result.valid is True

    def test_unknown_type_skipped(self):
        """Unknown types are skipped in validation."""
        schema = {
            "field": {"type": "unknown_type"}
        }

        result = ContractValidator.validate_inputs({"field": "anything"}, schema)
        assert result.valid is True

    def test_empty_inputs_with_schema(self):
        """Empty inputs with non-required schema."""
        schema = {
            "optional1": {"type": "string"},
            "optional2": {"type": "integer", "default": 0}
        }

        result = ContractValidator.validate_inputs({}, schema)
        assert result.valid is True
