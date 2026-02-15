"""
Unit tests for CapabilityYAMLValidationService.

Tests the YAML validation service for capability specifications.
"""

import pytest
from uuid import uuid4

from src.infrastructure.capabilities.capability_yaml_validation import (
    CapabilityYAMLValidationService,
    CapabilityValidationResult,
    ValidationIssue,
    extract_keywords,
    get_validation_service,
)


class TestCapabilityValidationResult:
    """Tests for CapabilityValidationResult dataclass."""

    def test_result_default_is_valid(self):
        """Result should be valid by default."""
        result = CapabilityValidationResult()
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 0
        assert len(result.info) == 0

    def test_add_error_marks_invalid(self):
        """Adding an error should mark result as invalid."""
        result = CapabilityValidationResult()
        result.add_error("test_field", "Test error message", "TEST_CODE")

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert result.errors[0].field == "test_field"
        assert result.errors[0].message == "Test error message"
        assert result.errors[0].code == "TEST_CODE"
        assert result.errors[0].severity == "error"

    def test_add_warning_keeps_valid(self):
        """Adding a warning should not affect validity."""
        result = CapabilityValidationResult()
        result.add_warning("test_field", "Test warning")

        assert result.is_valid is True
        assert len(result.warnings) == 1
        assert result.warnings[0].field == "test_field"
        assert result.warnings[0].message == "Test warning"
        assert result.warnings[0].severity == "warning"

    def test_add_info_keeps_valid(self):
        """Adding an info should not affect validity."""
        result = CapabilityValidationResult()
        result.add_info("test_field", "Test info")

        assert result.is_valid is True
        assert len(result.info) == 1
        assert result.info[0].field == "test_field"
        assert result.info[0].message == "Test info"
        assert result.info[0].severity == "info"

    def test_to_dict_format(self):
        """to_dict should return proper structure."""
        result = CapabilityValidationResult()
        result.add_error("field1", "Error 1", "CODE1")
        result.add_warning("field2", "Warning 1", "CODE2")
        result.add_info("field3", "Info 1")

        d = result.to_dict()

        assert d["is_valid"] is False
        assert d["error_count"] == 1
        assert d["warning_count"] == 1
        assert len(d["errors"]) == 1
        assert d["errors"][0]["field"] == "field1"
        assert d["errors"][0]["message"] == "Error 1"
        assert d["errors"][0]["code"] == "CODE1"

    def test_get_error_messages(self):
        """get_error_messages should return list of error messages."""
        result = CapabilityValidationResult()
        result.add_error("field1", "Error 1")
        result.add_error("field2", "Error 2")

        messages = result.get_error_messages()

        assert messages == ["Error 1", "Error 2"]


class TestCapabilityYAMLValidationService:
    """Tests for CapabilityYAMLValidationService."""

    @pytest.fixture
    def service(self):
        """Create a validation service instance."""
        return CapabilityYAMLValidationService()

    @pytest.fixture
    def valid_spec(self):
        """A valid minimal capability spec."""
        return {
            "agent_type": "test_capability",
            "name": "Test Capability",
            "description": "A test capability for unit tests",
            "domain": "content",
            "task_type": "general",
            "system_prompt": "You are a helpful assistant.",
            "inputs": {
                "query": {
                    "type": "string",
                    "required": True,
                    "description": "The query to process"
                }
            },
            "outputs": {
                "result": {
                    "type": "string",
                    "description": "The result"
                }
            },
            "execution_hints": {
                "deterministic": False,
                "speed": "medium",
                "cost": "low"
            }
        }

    @pytest.fixture
    def valid_yaml(self, valid_spec):
        """A valid capability spec as YAML string."""
        import yaml
        return yaml.dump(valid_spec)

    # === Required Fields Tests ===

    def test_valid_spec_passes(self, service, valid_spec):
        """A valid spec should pass validation."""
        result = service.validate(valid_spec)

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_valid_yaml_string_passes(self, service, valid_yaml):
        """A valid YAML string should pass validation."""
        result = service.validate(valid_yaml)

        assert result.is_valid is True
        assert result.parsed_spec is not None
        assert result.parsed_spec["agent_type"] == "test_capability"

    def test_missing_agent_type_fails(self, service):
        """Missing agent_type should fail."""
        spec = {
            "system_prompt": "Test prompt",
            "inputs": {"query": {"type": "string"}}
        }
        result = service.validate(spec)

        assert result.is_valid is False
        assert any("agent_type" in e.message for e in result.errors)
        assert any(e.code == "MISSING_AGENT_TYPE" for e in result.errors)

    def test_missing_system_prompt_fails(self, service):
        """Missing system_prompt should fail."""
        spec = {
            "agent_type": "test",
            "inputs": {"query": {"type": "string"}}
        }
        result = service.validate(spec)

        assert result.is_valid is False
        assert any("system_prompt" in e.message for e in result.errors)
        assert any(e.code == "MISSING_SYSTEM_PROMPT" for e in result.errors)

    def test_missing_inputs_fails(self, service):
        """Missing inputs should fail."""
        spec = {
            "agent_type": "test",
            "system_prompt": "Test prompt"
        }
        result = service.validate(spec)

        assert result.is_valid is False
        assert any("inputs" in e.message for e in result.errors)
        assert any(e.code == "MISSING_INPUTS" for e in result.errors)

    def test_inputs_not_dict_fails(self, service):
        """Inputs that is not a dict should fail."""
        spec = {
            "agent_type": "test",
            "system_prompt": "Test prompt",
            "inputs": "not a dict"
        }
        result = service.validate(spec)

        assert result.is_valid is False
        assert any(e.code == "INPUTS_NOT_OBJECT" for e in result.errors)

    # === agent_type Format Tests ===

    def test_agent_type_invalid_format_fails(self, service):
        """agent_type with invalid format should fail."""
        spec = {
            "agent_type": "test capability",  # space not allowed
            "system_prompt": "Test",
            "inputs": {"q": {"type": "string"}}
        }
        result = service.validate(spec)

        assert result.is_valid is False
        assert any(e.code == "INVALID_AGENT_TYPE_FORMAT" for e in result.errors)

    def test_agent_type_starting_with_number_fails(self, service):
        """agent_type starting with number should fail."""
        spec = {
            "agent_type": "123test",
            "system_prompt": "Test",
            "inputs": {"q": {"type": "string"}}
        }
        result = service.validate(spec)

        assert result.is_valid is False
        assert any(e.code == "INVALID_AGENT_TYPE_FORMAT" for e in result.errors)

    def test_agent_type_uppercase_warns(self, service):
        """agent_type with uppercase should warn."""
        spec = {
            "agent_type": "TestCapability",
            "system_prompt": "Test",
            "inputs": {"q": {"type": "string"}}
        }
        result = service.validate(spec)

        assert result.is_valid is True  # Just a warning
        assert any(w.code == "AGENT_TYPE_NOT_LOWERCASE" for w in result.warnings)

    def test_agent_type_too_long_fails(self, service):
        """agent_type over 100 chars should fail."""
        spec = {
            "agent_type": "a" * 101,
            "system_prompt": "Test",
            "inputs": {"q": {"type": "string"}}
        }
        result = service.validate(spec)

        assert result.is_valid is False
        assert any(e.code == "AGENT_TYPE_TOO_LONG" for e in result.errors)

    # === task_type Tests ===

    def test_invalid_task_type_fails(self, service, valid_spec):
        """Invalid task_type should fail."""
        valid_spec["task_type"] = "invalid_type"
        result = service.validate(valid_spec)

        assert result.is_valid is False
        assert any(e.code == "INVALID_TASK_TYPE" for e in result.errors)

    def test_valid_task_types_pass(self, service, valid_spec):
        """All valid task_types should pass."""
        for task_type in ["general", "reasoning", "creative", "web_research", "analysis",
                          "content_writing", "data_processing", "automation", "communication"]:
            valid_spec["task_type"] = task_type
            result = service.validate(valid_spec)
            assert result.is_valid is True, f"task_type '{task_type}' should be valid"

    # === Inputs Validation Tests ===

    def test_input_missing_type_fails(self, service, valid_spec):
        """Input without type should fail."""
        valid_spec["inputs"]["query"] = {"description": "No type"}
        result = service.validate(valid_spec)

        assert result.is_valid is False
        assert any("type" in e.message and "query" in e.field for e in result.errors)

    def test_input_invalid_type_fails(self, service, valid_spec):
        """Input with invalid type should fail."""
        valid_spec["inputs"]["query"]["type"] = "invalid_type"
        result = service.validate(valid_spec)

        assert result.is_valid is False
        assert any(e.code == "INVALID_INPUT_TYPE" for e in result.errors)

    def test_all_valid_input_types_pass(self, service, valid_spec):
        """All valid input types should pass."""
        for input_type in ["string", "integer", "number", "boolean", "array", "object", "any"]:
            valid_spec["inputs"]["query"]["type"] = input_type
            result = service.validate(valid_spec)
            assert result.is_valid is True, f"Input type '{input_type}' should be valid"

    def test_input_name_invalid_format_fails(self, service, valid_spec):
        """Input name with invalid format should fail."""
        valid_spec["inputs"]["123invalid"] = {"type": "string"}
        result = service.validate(valid_spec)

        assert result.is_valid is False
        assert any(e.code == "INVALID_INPUT_NAME" for e in result.errors)

    def test_input_required_not_boolean_fails(self, service, valid_spec):
        """Input required field that is not boolean should fail."""
        valid_spec["inputs"]["query"]["required"] = "yes"  # Not a boolean
        result = service.validate(valid_spec)

        assert result.is_valid is False
        assert any(e.code == "REQUIRED_NOT_BOOLEAN" for e in result.errors)

    def test_input_enum_not_array_fails(self, service, valid_spec):
        """Input enum that is not an array should fail."""
        valid_spec["inputs"]["query"]["enum"] = "not_array"
        result = service.validate(valid_spec)

        assert result.is_valid is False
        assert any(e.code == "ENUM_NOT_ARRAY" for e in result.errors)

    def test_input_enum_empty_fails(self, service, valid_spec):
        """Input enum that is empty should fail."""
        valid_spec["inputs"]["query"]["enum"] = []
        result = service.validate(valid_spec)

        assert result.is_valid is False
        assert any(e.code == "ENUM_EMPTY" for e in result.errors)

    def test_input_missing_description_info(self, service, valid_spec):
        """Input without description should add info."""
        del valid_spec["inputs"]["query"]["description"]
        result = service.validate(valid_spec)

        assert result.is_valid is True  # Just info, not error
        assert any(i.code == "MISSING_INPUT_DESCRIPTION" for i in result.info)

    # === Outputs Validation Tests ===

    def test_output_missing_type_fails(self, service, valid_spec):
        """Output without type should fail."""
        valid_spec["outputs"]["result"] = {"description": "No type"}
        result = service.validate(valid_spec)

        assert result.is_valid is False
        assert any("type" in e.message and "result" in e.field for e in result.errors)

    def test_output_invalid_type_fails(self, service, valid_spec):
        """Output with invalid type should fail."""
        valid_spec["outputs"]["result"]["type"] = "invalid"
        result = service.validate(valid_spec)

        assert result.is_valid is False
        assert any(e.code == "INVALID_OUTPUT_TYPE" for e in result.errors)

    def test_outputs_not_dict_fails(self, service, valid_spec):
        """Outputs that is not a dict should fail."""
        valid_spec["outputs"] = "not a dict"
        result = service.validate(valid_spec)

        assert result.is_valid is False
        assert any(e.code == "OUTPUTS_NOT_OBJECT" for e in result.errors)

    # === Execution Hints Tests ===

    def test_execution_hints_deterministic_not_boolean_fails(self, service, valid_spec):
        """deterministic that is not boolean should fail."""
        valid_spec["execution_hints"]["deterministic"] = "yes"
        result = service.validate(valid_spec)

        assert result.is_valid is False
        assert any(e.code == "DETERMINISTIC_NOT_BOOLEAN" for e in result.errors)

    def test_execution_hints_invalid_speed_fails(self, service, valid_spec):
        """Invalid speed value should fail."""
        valid_spec["execution_hints"]["speed"] = "very_fast"
        result = service.validate(valid_spec)

        assert result.is_valid is False
        assert any(e.code == "INVALID_SPEED_VALUE" for e in result.errors)

    def test_execution_hints_invalid_cost_fails(self, service, valid_spec):
        """Invalid cost value should fail."""
        valid_spec["execution_hints"]["cost"] = "very_expensive"
        result = service.validate(valid_spec)

        assert result.is_valid is False
        assert any(e.code == "INVALID_COST_VALUE" for e in result.errors)

    def test_execution_hints_max_tokens_not_int_fails(self, service, valid_spec):
        """max_tokens that is not int should fail."""
        valid_spec["execution_hints"]["max_tokens"] = "4000"
        result = service.validate(valid_spec)

        assert result.is_valid is False
        assert any(e.code == "MAX_TOKENS_NOT_INTEGER" for e in result.errors)

    def test_execution_hints_temperature_not_number_fails(self, service, valid_spec):
        """temperature that is not number should fail."""
        valid_spec["execution_hints"]["temperature"] = "medium"
        result = service.validate(valid_spec)

        assert result.is_valid is False
        assert any(e.code == "TEMPERATURE_NOT_NUMBER" for e in result.errors)

    def test_execution_hints_unknown_key_warns(self, service, valid_spec):
        """Unknown execution hint key should warn."""
        valid_spec["execution_hints"]["unknown_hint"] = True
        result = service.validate(valid_spec)

        assert result.is_valid is True  # Just warning
        assert any(w.code == "UNKNOWN_EXECUTION_HINT" for w in result.warnings)

    # === Template Validation Tests ===

    def test_valid_jinja_template_passes(self, service, valid_spec):
        """Valid Jinja2 template in system_prompt should pass."""
        valid_spec["system_prompt"] = "Hello {{ name }}, you have {{ count }} messages."
        result = service.validate(valid_spec)

        assert result.is_valid is True

    def test_invalid_jinja_template_fails(self, service, valid_spec):
        """Invalid Jinja2 template should fail."""
        valid_spec["system_prompt"] = "Hello {{ name }  # Unclosed brace"
        result = service.validate(valid_spec)

        assert result.is_valid is False
        assert any(e.code == "TEMPLATE_SYNTAX_ERROR" for e in result.errors)

    # === Examples Validation Tests ===

    def test_examples_not_array_fails(self, service, valid_spec):
        """Examples that is not array should fail."""
        valid_spec["examples"] = "not an array"
        result = service.validate(valid_spec)

        assert result.is_valid is False
        assert any(e.code == "EXAMPLES_NOT_ARRAY" for e in result.errors)

    def test_example_not_object_fails(self, service, valid_spec):
        """Example that is not object should fail."""
        valid_spec["examples"] = ["not an object"]
        result = service.validate(valid_spec)

        assert result.is_valid is False
        assert any(e.code == "EXAMPLE_NOT_OBJECT" for e in result.errors)

    def test_example_missing_required_input_warns(self, service, valid_spec):
        """Example missing required input should warn."""
        valid_spec["inputs"]["query"]["required"] = True
        valid_spec["examples"] = [{"other_field": "value"}]
        result = service.validate(valid_spec)

        assert result.is_valid is True  # Just warning
        assert any(w.code == "EXAMPLE_MISSING_REQUIRED_INPUT" for w in result.warnings)

    # === Recommended Fields Tests ===

    def test_missing_name_info(self, service, valid_spec):
        """Missing name should add info."""
        del valid_spec["name"]
        result = service.validate(valid_spec)

        assert result.is_valid is True
        assert any(i.code == "MISSING_NAME" for i in result.info)

    def test_missing_description_info(self, service, valid_spec):
        """Missing description should add info."""
        del valid_spec["description"]
        result = service.validate(valid_spec)

        assert result.is_valid is True
        assert any(i.code == "MISSING_DESCRIPTION" for i in result.info)

    def test_missing_domain_info(self, service, valid_spec):
        """Missing domain should add info."""
        del valid_spec["domain"]
        result = service.validate(valid_spec)

        assert result.is_valid is True
        assert any(i.code == "MISSING_DOMAIN" for i in result.info)

    def test_missing_outputs_info(self, service, valid_spec):
        """Missing outputs should add info."""
        del valid_spec["outputs"]
        result = service.validate(valid_spec)

        assert result.is_valid is True
        assert any(i.code == "MISSING_OUTPUTS" for i in result.info)

    def test_missing_examples_info(self, service, valid_spec):
        """Missing examples should add info."""
        if "examples" in valid_spec:
            del valid_spec["examples"]
        result = service.validate(valid_spec)

        assert result.is_valid is True
        assert any(i.code == "MISSING_EXAMPLES" for i in result.info)

    # === Strict Mode Tests ===

    def test_strict_mode_converts_warnings_to_errors(self, service, valid_spec):
        """Strict mode should convert warnings to errors."""
        valid_spec["agent_type"] = "TestCapability"  # Will warn about uppercase
        result = service.validate(valid_spec, strict=True)

        assert result.is_valid is False
        assert any("Strict" in e.message and "lowercase" in e.message for e in result.errors)

    # === YAML Parsing Tests ===

    def test_invalid_yaml_syntax_fails(self, service):
        """Invalid YAML syntax should fail."""
        invalid_yaml = "agent_type: test\n  bad indent: value"
        result = service.validate(invalid_yaml)

        assert result.is_valid is False
        assert any(e.code == "YAML_SYNTAX" for e in result.errors)

    def test_yaml_not_object_fails(self, service):
        """YAML that is not an object should fail."""
        yaml_list = "- item1\n- item2"
        result = service.validate(yaml_list)

        assert result.is_valid is False
        assert any(e.code == "NOT_OBJECT" for e in result.errors)

    # === Domain Tests ===

    def test_unknown_domain_warns(self, service, valid_spec):
        """Unknown domain should warn."""
        valid_spec["domain"] = "unknown_domain"
        result = service.validate(valid_spec)

        assert result.is_valid is True  # Just warning
        assert any(w.code == "UNKNOWN_DOMAIN" for w in result.warnings)


class TestExtractKeywords:
    """Tests for extract_keywords function."""

    def test_extracts_agent_type_words(self):
        """Should extract words from agent_type."""
        spec = {"agent_type": "content_summarizer"}
        keywords = extract_keywords(spec)

        assert "content" in keywords
        assert "summarizer" in keywords

    def test_extracts_name_words(self):
        """Should extract words from name."""
        spec = {"agent_type": "test", "name": "Content Writer Agent"}
        keywords = extract_keywords(spec)

        assert "content" in keywords
        assert "writer" in keywords
        assert "agent" in keywords

    def test_extracts_domain(self):
        """Should extract domain."""
        spec = {"agent_type": "test", "domain": "research"}
        keywords = extract_keywords(spec)

        assert "research" in keywords

    def test_extracts_input_names(self):
        """Should extract input names."""
        spec = {
            "agent_type": "test",
            "inputs": {
                "user_query": {"type": "string"},
                "context_data": {"type": "object"}
            }
        }
        keywords = extract_keywords(spec)

        assert "user" in keywords
        assert "query" in keywords
        assert "context" in keywords
        assert "data" in keywords

    def test_extracts_output_names(self):
        """Should extract output names."""
        spec = {
            "agent_type": "test",
            "outputs": {
                "summary_text": {"type": "string"},
                "word_count": {"type": "integer"}
            }
        }
        keywords = extract_keywords(spec)

        assert "summary" in keywords
        assert "text" in keywords
        assert "word" in keywords
        assert "count" in keywords

    def test_filters_short_words(self):
        """Should filter words with 2 or fewer characters."""
        spec = {"agent_type": "a_b_cd_test"}
        keywords = extract_keywords(spec)

        assert "a" not in keywords
        assert "b" not in keywords
        assert "cd" not in keywords
        assert "test" in keywords

    def test_filters_stop_words(self):
        """Should filter common stop words."""
        spec = {"agent_type": "test", "name": "the best tool for and in on"}
        keywords = extract_keywords(spec)

        assert "the" not in keywords
        assert "for" not in keywords
        assert "and" not in keywords
        assert "best" in keywords
        assert "tool" in keywords

    def test_limits_to_20_keywords(self):
        """Should limit to 20 keywords."""
        spec = {
            "agent_type": "test",
            "name": " ".join([f"word{i}" for i in range(30)]),
        }
        keywords = extract_keywords(spec)

        assert len(keywords) <= 20


class TestGetValidationService:
    """Tests for singleton getter."""

    def test_returns_same_instance(self):
        """Should return the same instance on multiple calls."""
        service1 = get_validation_service()
        service2 = get_validation_service()

        assert service1 is service2

    def test_returns_validation_service(self):
        """Should return a CapabilityYAMLValidationService."""
        service = get_validation_service()

        assert isinstance(service, CapabilityYAMLValidationService)
