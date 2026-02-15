"""Unit tests for PromptEvalAgent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.eval.models import (
    FormatRequirements,
    OutputPattern,
    TestCase,
    get_template_syntax_rules,
)
from src.eval.prompt_eval_agent import PromptEvalAgent


class TestPromptEvalAgent:
    """Tests for PromptEvalAgent."""

    @pytest.fixture
    def eval_agent(self):
        """Create an eval agent with mocked LLM client."""
        agent = PromptEvalAgent()
        agent.llm_client = MagicMock()
        return agent

    def test_pattern_matching_contains(self, eval_agent):
        """Contains pattern matches correctly."""
        output = "The summary includes key findings about AI."
        patterns = [OutputPattern("contains", "key findings", "Has key findings")]
        score, matches = eval_agent.match_patterns(output, patterns)
        assert score == 1.0
        assert matches["key findings"] is True

    def test_pattern_matching_contains_not_found(self, eval_agent):
        """Contains pattern returns False when not found."""
        output = "The summary is about technology."
        patterns = [OutputPattern("contains", "key findings", "Has key findings")]
        score, matches = eval_agent.match_patterns(output, patterns)
        assert score == 0.0
        assert matches["key findings"] is False

    def test_pattern_matching_not_contains_pass(self, eval_agent):
        """Not_contains pattern passes when pattern is absent."""
        output = '{"inputs": {"data": "{{step_1.outputs.content}}"}}'
        patterns = [OutputPattern("not_contains", "{{step_1.output}}", "No singular output")]
        score, matches = eval_agent.match_patterns(output, patterns)
        assert score == 1.0  # Pattern NOT found = pass

    def test_pattern_matching_not_contains_fail(self, eval_agent):
        """Not_contains pattern fails when pattern is present."""
        output = '{"inputs": {"data": "{{step_1.output}}"}}'
        patterns = [OutputPattern("not_contains", "{{step_1.output}}", "No singular output")]
        score, matches = eval_agent.match_patterns(output, patterns)
        assert score == 0.0  # Pattern WAS found = fail
        assert matches["{{step_1.output}}"] is True  # Pattern was found

    def test_pattern_matching_regex_match(self, eval_agent):
        """Regex pattern validates template syntax."""
        output = '{"inputs": {"data": "{{step_1.outputs.content}}"}}'
        patterns = [OutputPattern("regex", r"\{\{step_\d+\.outputs\.\w+\}\}", "Valid template")]
        score, matches = eval_agent.match_patterns(output, patterns)
        assert score == 1.0

    def test_pattern_matching_regex_no_match(self, eval_agent):
        """Regex pattern returns False when no match."""
        output = '{"inputs": {"data": "{{step_1.output}}"}}'
        patterns = [OutputPattern("regex", r"\{\{step_\d+\.outputs\.\w+\}\}", "Valid template")]
        score, matches = eval_agent.match_patterns(output, patterns)
        assert score == 0.0

    def test_weighted_scoring(self, eval_agent):
        """Weights affect final score correctly."""
        output = "Contains first but not second"
        patterns = [
            OutputPattern("contains", "first", "Has first", weight=1.0),
            OutputPattern("contains", "missing", "Has missing", weight=3.0),
        ]
        score, _ = eval_agent.match_patterns(output, patterns)
        # 1 / (1 + 3) = 0.25
        assert score == pytest.approx(0.25, 0.01)

    def test_weighted_scoring_all_pass(self, eval_agent):
        """All patterns matching should give score 1.0."""
        output = "Contains first and second"
        patterns = [
            OutputPattern("contains", "first", "Has first", weight=1.0),
            OutputPattern("contains", "second", "Has second", weight=3.0),
        ]
        score, _ = eval_agent.match_patterns(output, patterns)
        assert score == 1.0

    def test_empty_patterns(self, eval_agent):
        """Empty patterns list should return score 1.0."""
        output = "Any content"
        patterns = []
        score, matches = eval_agent.match_patterns(output, patterns)
        assert score == 1.0
        assert matches == {}

    def test_json_path_valid(self, eval_agent):
        """JSON path pattern validates structure."""
        output = '{"steps": [{"id": "step_1"}]}'
        patterns = [OutputPattern("json_path", "$.steps", "Has steps")]
        score, matches = eval_agent.match_patterns(output, patterns)
        assert score == 1.0

    def test_json_path_missing(self, eval_agent):
        """JSON path pattern fails when path missing."""
        output = '{"data": []}'
        patterns = [OutputPattern("json_path", "$.steps", "Has steps")]
        score, matches = eval_agent.match_patterns(output, patterns)
        assert score == 0.0

    def test_custom_validator_dependencies(self, eval_agent):
        """Custom validator for dependencies works."""
        output = json.dumps({
            "steps": [
                {"id": "step_1", "outputs": ["content"]},
                {"id": "step_2", "inputs": {"data": "{{step_1.outputs.content}}"}, "dependencies": ["step_1"]}
            ]
        })
        patterns = [OutputPattern("custom_validator", "", "Dependencies match", validator="dependencies_match_references")]
        score, _ = eval_agent.match_patterns(output, patterns)
        assert score == 1.0

    def test_custom_validator_missing_dependency(self, eval_agent):
        """Custom validator catches missing dependency."""
        output = json.dumps({
            "steps": [
                {"id": "step_1", "outputs": ["content"]},
                {"id": "step_2", "inputs": {"data": "{{step_1.outputs.content}}"}, "dependencies": []}
            ]
        })
        patterns = [OutputPattern("custom_validator", "", "Dependencies match", validator="dependencies_match_references")]
        score, _ = eval_agent.match_patterns(output, patterns)
        assert score == 0.0

    def test_build_user_message_with_goal(self, eval_agent):
        """User message built correctly from goal."""
        test_case = TestCase(
            id="test_1",
            name="Test",
            input_context={"goal": "Research AI trends"},
            expected_output_patterns=[],
            format_requirements=FormatRequirements(),
        )
        message = eval_agent._build_user_message(test_case)
        assert "Research AI trends" in message

    def test_build_user_message_with_task(self, eval_agent):
        """User message built correctly from task."""
        test_case = TestCase(
            id="test_1",
            name="Test",
            input_context={"task": "Summarize content"},
            expected_output_patterns=[],
            format_requirements=FormatRequirements(),
        )
        message = eval_agent._build_user_message(test_case)
        assert "Summarize content" in message

    def test_build_user_message_fallback(self, eval_agent):
        """User message falls back to JSON dump."""
        test_case = TestCase(
            id="test_1",
            name="Test",
            input_context={"custom_field": "value"},
            expected_output_patterns=[],
            format_requirements=FormatRequirements(),
        )
        message = eval_agent._build_user_message(test_case)
        assert "custom_field" in message

    @pytest.mark.asyncio
    async def test_evaluate_single_test_case(self, eval_agent):
        """Full test case evaluation with mocked LLM."""
        # Mock the LLM call
        mock_response = MagicMock()
        mock_response.content = '{"steps": [{"inputs": {"data": "{{step_1.outputs.content}}"}}]}'
        eval_agent.llm_client.create_completion = AsyncMock(return_value=mock_response)

        test_case = TestCase(
            id="test_1",
            name="Template syntax",
            input_context={"goal": "Test goal"},
            expected_output_patterns=[
                OutputPattern("regex", r"\{\{step_\d+\.outputs\.\w+\}\}", "Valid template")
            ],
            format_requirements=FormatRequirements(expected_type="json"),
        )

        result = await eval_agent.evaluate_single("prompt text", test_case, "test-model")
        assert result.passed
        assert result.content_score == 1.0

    @pytest.mark.asyncio
    async def test_evaluate_single_test_case_fail(self, eval_agent):
        """Test case fails with invalid output."""
        mock_response = MagicMock()
        mock_response.content = '{"steps": [{"inputs": {"data": "{{step_1.output}}"}}]}'
        eval_agent.llm_client.create_completion = AsyncMock(return_value=mock_response)

        test_case = TestCase(
            id="test_1",
            name="Template syntax",
            input_context={"goal": "Test goal"},
            expected_output_patterns=[
                OutputPattern("not_contains", "{{step_1.output}}", "No singular output", weight=2.0)
            ],
            format_requirements=FormatRequirements(
                expected_type="json",
                template_syntax_rules=get_template_syntax_rules(),
            ),
        )

        result = await eval_agent.evaluate_single("prompt text", test_case, "test-model")
        assert not result.passed
        assert result.content_score < 1.0

    @pytest.mark.asyncio
    async def test_evaluate_multiple_test_cases(self, eval_agent):
        """Evaluation aggregates results correctly."""
        mock_response = MagicMock()
        mock_response.content = '{"steps": [{"inputs": {"data": "{{step_1.outputs.content}}"}}]}'
        eval_agent.llm_client.create_completion = AsyncMock(return_value=mock_response)

        test_cases = [
            TestCase(
                id="test_1",
                name="Test 1",
                input_context={"goal": "Goal 1"},
                expected_output_patterns=[
                    OutputPattern("regex", r"\{\{step_\d+\.outputs\.\w+\}\}", "Valid template")
                ],
                format_requirements=FormatRequirements(expected_type="json"),
            ),
            TestCase(
                id="test_2",
                name="Test 2",
                input_context={"goal": "Goal 2"},
                expected_output_patterns=[
                    OutputPattern("contains", "steps", "Has steps")
                ],
                format_requirements=FormatRequirements(expected_type="json"),
            ),
        ]

        result = await eval_agent.evaluate("prompt text", test_cases)
        assert result.total_tests == 2
        assert result.tests_passed == 2
        assert result.passed


import json
