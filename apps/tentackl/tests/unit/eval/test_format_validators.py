"""Unit tests for format validators."""

import json

import pytest

from src.eval.format_validators import (
    FormatValidator,
    JSONSchemaValidator,
    OutputFieldValidator,
    TemplateSyntaxValidator,
    validate_template_syntax_quick,
)
from src.eval.models import FormatRequirements, get_template_syntax_rules


class TestTemplateSyntaxValidator:
    """Tests for TemplateSyntaxValidator."""

    @pytest.fixture
    def validator(self):
        """Create a validator with default rules."""
        return TemplateSyntaxValidator(get_template_syntax_rules())

    def test_valid_outputs_plural_syntax(self, validator):
        """{{step_1.outputs.content}} is valid."""
        result = validator.validate('{"inputs": {"data": "{{step_1.outputs.content}}"}}')
        assert result.valid
        assert len(result.violations) == 0
        assert result.format_score == 1.0

    def test_valid_multiple_templates(self, validator):
        """Multiple valid templates should all pass."""
        output = '''
        {
            "input1": "{{step_1.outputs.content}}",
            "input2": "{{step_2.outputs.summary}}",
            "input3": "{{step_3.outputs.findings}}"
        }
        '''
        result = validator.validate(output)
        assert result.valid
        assert len(result.violations) == 0

    def test_invalid_output_singular(self, validator):
        """{{step_1.output}} should fail."""
        result = validator.validate('{"inputs": {"data": "{{step_1.output}}"}}')
        assert not result.valid
        assert len(result.violations) > 0
        assert any(v.rule_name == "outputs_plural" for v in result.violations)

    def test_invalid_output_singular_with_field(self, validator):
        """{{step_1.output.content}} should fail (missing 's')."""
        result = validator.validate('{"inputs": {"data": "{{step_1.output.content}}"}}')
        assert not result.valid
        assert any(v.rule_name == "outputs_plural" for v in result.violations)

    def test_invalid_result_accessor(self, validator):
        """{{step_1.result}} should fail."""
        result = validator.validate('{"inputs": {"data": "{{step_1.result}}"}}')
        assert not result.valid
        assert any(v.rule_name == "outputs_plural" for v in result.violations)

    def test_invalid_data_accessor(self, validator):
        """{{step_1.data}} should fail."""
        result = validator.validate('{"inputs": {"data": "{{step_1.data}}"}}')
        assert not result.valid
        assert any(v.rule_name == "outputs_plural" for v in result.violations)

    def test_invalid_missing_field(self, validator):
        """{{step_1.outputs}} without field should fail."""
        result = validator.validate('{"inputs": {"data": "{{step_1.outputs}}"}}')
        assert not result.valid
        assert any(v.rule_name == "field_required" for v in result.violations)

    def test_mixed_valid_invalid(self, validator):
        """Multiple templates, some valid, some invalid."""
        output = '''
        "input1": "{{step_1.outputs.content}}",
        "input2": "{{step_2.output}}",
        "input3": "{{step_3.outputs.summary}}"
        '''
        result = validator.validate(output)
        assert not result.valid
        # Should have violations for step_2.output
        assert any("step_2" in v.pattern_matched for v in result.violations)

    def test_dependencies_validation_correct(self, validator):
        """Steps with proper dependencies should pass."""
        plan = {
            "steps": [
                {"id": "step_1", "outputs": ["content"]},
                {"id": "step_2", "inputs": {"data": "{{step_1.outputs.content}}"}, "dependencies": ["step_1"]}
            ]
        }
        violations = validator.validate_dependencies(json.dumps(plan))
        assert len(violations) == 0

    def test_dependencies_validation_missing(self, validator):
        """Steps referencing outputs must declare dependencies."""
        plan = {
            "steps": [
                {"id": "step_1", "outputs": ["content"]},
                {"id": "step_2", "inputs": {"data": "{{step_1.outputs.content}}"}, "dependencies": []}
            ]
        }
        violations = validator.validate_dependencies(json.dumps(plan))
        assert len(violations) == 1
        assert "step_1" in violations[0].message

    def test_dependencies_validation_multiple_missing(self, validator):
        """Multiple missing dependencies should all be reported."""
        plan = {
            "steps": [
                {"id": "step_1", "outputs": ["content"]},
                {"id": "step_2", "outputs": ["summary"]},
                {"id": "step_3", "inputs": {
                    "data1": "{{step_1.outputs.content}}",
                    "data2": "{{step_2.outputs.summary}}"
                }, "dependencies": []}
            ]
        }
        violations = validator.validate_dependencies(json.dumps(plan))
        assert len(violations) == 2

    def test_output_field_names_warning(self, validator):
        """Wrong field names should generate warnings."""
        plan = {
            "steps": [
                {"id": "step_1", "agent_type": "web_research", "outputs": ["findings"]},
                {"id": "step_2", "inputs": {"data": "{{step_1.outputs.wrong_field}}"}, "dependencies": ["step_1"]}
            ]
        }
        violations = validator.validate_output_field_names(json.dumps(plan))
        assert len(violations) == 1
        assert "web_research" in violations[0].message
        assert violations[0].severity == "warning"

    def test_context_extraction(self, validator):
        """Should extract context around violations."""
        output = 'prefix text {{step_1.output}} suffix text'
        result = validator.validate(output)
        assert len(result.violations) > 0
        assert result.violations[0].context is not None
        assert "{{step_1.output}}" in result.violations[0].context

    def test_empty_input(self, validator):
        """Empty input should be valid (no templates to validate)."""
        result = validator.validate("")
        assert result.valid
        assert result.format_score == 1.0


class TestJSONSchemaValidator:
    """Tests for JSONSchemaValidator."""

    def test_valid_json_with_required_fields(self):
        """Valid JSON with all required fields should pass."""
        schema = {
            "type": "object",
            "required": ["steps", "plan_summary"],
            "properties": {
                "steps": {"type": "array"},
                "plan_summary": {"type": "string"}
            }
        }
        validator = JSONSchemaValidator(schema)

        result = validator.validate('{"steps": [], "plan_summary": "test"}')
        assert result.valid
        assert result.format_score == 1.0

    def test_missing_required_field(self):
        """Missing required field should fail."""
        schema = {
            "type": "object",
            "required": ["steps", "plan_summary"],
        }
        validator = JSONSchemaValidator(schema)

        result = validator.validate('{"steps": []}')
        assert not result.valid
        assert any(v.rule_name == "required_field" for v in result.violations)
        assert any("plan_summary" in v.pattern_matched for v in result.violations)

    def test_wrong_field_type(self):
        """Wrong field type should fail."""
        schema = {
            "type": "object",
            "properties": {
                "steps": {"type": "array"},
            }
        }
        validator = JSONSchemaValidator(schema)

        result = validator.validate('{"steps": "not an array"}')
        assert not result.valid
        assert any(v.rule_name == "field_type" for v in result.violations)

    def test_invalid_json(self):
        """Invalid JSON should fail."""
        schema = {"type": "object"}
        validator = JSONSchemaValidator(schema)

        result = validator.validate("not valid json")
        assert not result.valid
        assert any(v.rule_name == "json_parse" for v in result.violations)

    def test_json_in_code_block(self):
        """JSON in markdown code block should be extracted."""
        schema = {
            "type": "object",
            "required": ["steps"],
        }
        validator = JSONSchemaValidator(schema)

        result = validator.validate('```json\n{"steps": []}\n```')
        assert result.valid


class TestOutputFieldValidator:
    """Tests for OutputFieldValidator."""

    def test_all_fields_present(self):
        """All required fields present should pass."""
        validator = OutputFieldValidator(["steps", "plan_summary"])

        result = validator.validate('{"steps": [], "plan_summary": "test"}')
        assert result.valid
        assert result.format_score == 1.0

    def test_missing_fields(self):
        """Missing fields should fail."""
        validator = OutputFieldValidator(["steps", "plan_summary", "metadata"])

        result = validator.validate('{"steps": []}')
        assert not result.valid
        assert result.format_score == pytest.approx(0.33, 0.1)
        assert any("plan_summary" in v.pattern_matched for v in result.violations)
        assert any("metadata" in v.pattern_matched for v in result.violations)


class TestFormatValidator:
    """Tests for combined FormatValidator."""

    def test_combined_validation(self):
        """Combined validation should check all requirements."""
        validator = FormatValidator()

        requirements = FormatRequirements(
            expected_type="json",
            required_fields=["steps"],
            template_syntax_rules=get_template_syntax_rules(),
        )

        # Valid input with proper step structure and dependencies
        valid_output = json.dumps({
            "steps": [
                {"id": "step_1", "agent_type": "web_research", "outputs": ["content"]},
                {"id": "step_2", "inputs": {"data": "{{step_1.outputs.content}}"}, "dependencies": ["step_1"]}
            ]
        })
        score, violations = validator.validate(valid_output, requirements)
        assert score >= 0.9
        assert len(violations) == 0

        # Invalid template syntax ({{step_1.output}} missing 's' and field name)
        invalid_output = json.dumps({
            "steps": [
                {"id": "step_1", "agent_type": "web_research", "outputs": ["content"]},
                {"id": "step_2", "inputs": {"data": "{{step_1.output}}"}, "dependencies": ["step_1"]}
            ]
        })
        score, violations = validator.validate(invalid_output, requirements)
        # Should have violations for invalid template syntax
        assert len(violations) > 0
        assert any("outputs" in v.lower() or "plural" in v.lower() for v in violations)


class TestQuickValidation:
    """Tests for quick validation function."""

    def test_valid_syntax(self):
        """Valid template syntax should pass."""
        valid, errors = validate_template_syntax_quick("{{step_1.outputs.content}}")
        assert valid
        assert len(errors) == 0

    def test_invalid_syntax(self):
        """Invalid template syntax should fail."""
        valid, errors = validate_template_syntax_quick("{{step_1.output}}")
        assert not valid
        assert len(errors) > 0

    def test_no_templates(self):
        """Text without templates should pass."""
        valid, errors = validate_template_syntax_quick("just regular text")
        assert valid
        assert len(errors) == 0
