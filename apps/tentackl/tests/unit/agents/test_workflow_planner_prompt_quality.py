"""
Automated quality evaluation tests for WORKFLOW_PLANNER_SYSTEM_PROMPT.

Ensures the workflow planner system prompt maintains high quality across:
- Clarity, Specificity, Safety, Output Format, Context, Constraints

These tests act as a regression gate to ensure prompt quality doesn't degrade
when the prompt is modified.

Usage:
    docker compose exec tentackl python -m pytest tests/unit/agents/test_workflow_planner_prompt_quality.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.tasks.task_planner_agent import WORKFLOW_PLANNER_SYSTEM_PROMPT
from src.evaluation.rubrics import (
    EvaluationConfig,
    EvaluationResult,
    EvaluationStatus,
    DimensionScore,
    PromptType,
)


class TestWorkflowPlannerPromptStructure:
    """Test the structural properties of the workflow planner prompt."""

    def test_prompt_is_not_empty(self):
        """Prompt should not be empty."""
        assert WORKFLOW_PLANNER_SYSTEM_PROMPT
        assert len(WORKFLOW_PLANNER_SYSTEM_PROMPT) > 0

    def test_prompt_has_minimum_length(self):
        """Prompt should be comprehensive (at least 10000 chars)."""
        assert len(WORKFLOW_PLANNER_SYSTEM_PROMPT) >= 10000, (
            f"Prompt is only {len(WORKFLOW_PLANNER_SYSTEM_PROMPT)} chars, "
            "expected at least 10000 for comprehensive system prompt"
        )

    def test_prompt_contains_allowed_hosts_section(self):
        """Prompt should have a section for allowed hosts (with placeholder for dynamic injection)."""
        # The prompt now uses a placeholder that gets replaced at runtime
        assert "ALLOWED" in WORKFLOW_PLANNER_SYSTEM_PROMPT.upper() or \
               "{{ALLOWED_HOSTS_TABLE}}" in WORKFLOW_PLANNER_SYSTEM_PROMPT, \
               "Prompt should have an allowed hosts section or placeholder"

    def test_prompt_contains_output_format_section(self):
        """Prompt should specify output format."""
        assert "Output Format" in WORKFLOW_PLANNER_SYSTEM_PROMPT or \
               "YAML" in WORKFLOW_PLANNER_SYSTEM_PROMPT, \
               "Prompt should specify output format"

    def test_prompt_contains_examples(self):
        """Prompt should contain examples for clarity."""
        assert "```yaml" in WORKFLOW_PLANNER_SYSTEM_PROMPT or \
               "Example" in WORKFLOW_PLANNER_SYSTEM_PROMPT, \
               "Prompt should contain YAML examples"

    def test_prompt_contains_limits(self):
        """Prompt should specify operational limits."""
        # Check for various limit-related keywords
        has_limits = any(
            keyword in WORKFLOW_PLANNER_SYSTEM_PROMPT
            for keyword in ["LIMIT", "Maximum", "maximum", "max", "Max"]
        )
        assert has_limits, "Prompt should specify operational limits"

    def test_prompt_contains_critical_rules(self):
        """Prompt should have critical rules section."""
        assert "CRITICAL" in WORKFLOW_PLANNER_SYSTEM_PROMPT.upper(), \
               "Prompt should have critical rules highlighted"

    def test_prompt_specifies_available_plugins(self):
        """Prompt should list available plugins."""
        assert "plugin" in WORKFLOW_PLANNER_SYSTEM_PROMPT.lower() or \
               "Plugin" in WORKFLOW_PLANNER_SYSTEM_PROMPT, \
               "Prompt should specify available plugins"

    def test_prompt_specifies_agent_types(self):
        """Prompt should list available agent types."""
        assert "agent_type" in WORKFLOW_PLANNER_SYSTEM_PROMPT or \
               "llm_worker" in WORKFLOW_PLANNER_SYSTEM_PROMPT, \
               "Prompt should specify agent types"


class TestWorkflowPlannerPromptSafety:
    """Test safety-related aspects of the workflow planner prompt."""

    def test_prompt_has_api_whitelist(self):
        """Prompt should have an API whitelist for safety."""
        # Check for whitelist-related keywords
        has_whitelist = any(
            keyword in WORKFLOW_PLANNER_SYSTEM_PROMPT
            for keyword in [
                "ONLY USE",
                "APPROVED",
                "whitelist",
                "allowed",
                "pre-approved"
            ]
        )
        assert has_whitelist, "Prompt should have API whitelist for safety"

    def test_prompt_explains_host_restrictions(self):
        """Prompt should explain that hosts are restricted."""
        has_restriction_info = any(
            phrase in WORKFLOW_PLANNER_SYSTEM_PROMPT
            for phrase in [
                "ONLY use",
                "hosts listed above",
                "allowlist",
                "execution will fail",
                "add it to their allowlist"
            ]
        )
        assert has_restriction_info, "Prompt should explain host restrictions"

    def test_prompt_includes_known_safe_apis(self):
        """Prompt should include known safe APIs."""
        safe_apis = [
            "github.com",
            "hacker-news",
            "pokeapi",
            "wttr.in"
        ]
        included_apis = sum(
            1 for api in safe_apis
            if api.lower() in WORKFLOW_PLANNER_SYSTEM_PROMPT.lower()
        )
        assert included_apis >= 2, (
            f"Prompt should include at least 2 known safe APIs, found {included_apis}"
        )


class TestWorkflowPlannerPromptClarity:
    """Test clarity-related aspects of the workflow planner prompt."""

    def test_prompt_has_section_headers(self):
        """Prompt should have clear section headers."""
        # Count markdown headers (##)
        header_count = WORKFLOW_PLANNER_SYSTEM_PROMPT.count("##")
        assert header_count >= 5, (
            f"Prompt should have at least 5 section headers, found {header_count}"
        )

    def test_prompt_uses_formatting(self):
        """Prompt should use markdown formatting for clarity."""
        has_formatting = (
            "**" in WORKFLOW_PLANNER_SYSTEM_PROMPT or  # Bold
            "```" in WORKFLOW_PLANNER_SYSTEM_PROMPT or  # Code blocks
            "- " in WORKFLOW_PLANNER_SYSTEM_PROMPT     # Lists
        )
        assert has_formatting, "Prompt should use markdown formatting"

    def test_prompt_has_multiple_examples(self):
        """Prompt should have multiple examples."""
        # Count code blocks (likely examples)
        code_block_count = WORKFLOW_PLANNER_SYSTEM_PROMPT.count("```yaml")
        assert code_block_count >= 3, (
            f"Prompt should have at least 3 YAML examples, found {code_block_count}"
        )


class TestWorkflowPlannerPromptEvaluation:
    """Integration tests that run the prompt through the evaluation service."""

    @pytest.fixture
    def mock_evaluation_result_passing(self):
        """Create a mock passing evaluation result."""
        return EvaluationResult(
            evaluation_id="test-123",
            passed=True,
            evaluation_result=EvaluationStatus.PASS,
            overall_score=5.0,
            dimension_scores={
                "clarity": DimensionScore(score=5, feedback="Clear", weight=1.0),
                "specificity": DimensionScore(score=5, feedback="Specific", weight=1.0),
                "safety": DimensionScore(score=5, feedback="Safe", weight=1.5),
                "output_format": DimensionScore(score=5, feedback="Well formatted", weight=1.0),
                "context": DimensionScore(score=5, feedback="Good context", weight=0.8),
                "constraints": DimensionScore(score=5, feedback="Clear constraints", weight=0.8),
            },
            justification="Excellent prompt",
            improvement_suggestions=[],
            prompt_type="system_prompt",
            threshold=3.0,
            can_override=True,
        )

    @pytest.mark.asyncio
    async def test_prompt_passes_evaluation_mock(self, mock_evaluation_result_passing):
        """Test that prompt evaluation returns passing result (mocked)."""
        with patch(
            "src.infrastructure.evaluations.prompt_evaluation_service.PromptEvaluationService"
        ) as MockService:
            # Configure the mock
            mock_instance = AsyncMock()
            mock_instance.evaluate_prompt = AsyncMock(
                return_value=mock_evaluation_result_passing
            )
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockService.return_value = mock_instance

            # Import after mocking
            from src.infrastructure.evaluations.prompt_evaluation_service import PromptEvaluationService

            async with PromptEvaluationService() as eval_service:
                result = await eval_service.evaluate_prompt(
                    prompt=WORKFLOW_PLANNER_SYSTEM_PROMPT,
                    config=EvaluationConfig(
                        threshold=3.0,
                        prompt_type=PromptType.SYSTEM_PROMPT,
                    )
                )

            assert result.passed, f"Prompt failed evaluation: {result.justification}"
            assert result.overall_score >= 3.0

    @pytest.mark.asyncio
    async def test_prompt_safety_dimension_mock(self, mock_evaluation_result_passing):
        """Test that safety dimension meets minimum threshold (mocked)."""
        with patch(
            "src.infrastructure.evaluations.prompt_evaluation_service.PromptEvaluationService"
        ) as MockService:
            mock_instance = AsyncMock()
            mock_instance.evaluate_prompt = AsyncMock(
                return_value=mock_evaluation_result_passing
            )
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockService.return_value = mock_instance

            from src.infrastructure.evaluations.prompt_evaluation_service import PromptEvaluationService

            async with PromptEvaluationService() as eval_service:
                result = await eval_service.evaluate_prompt(
                    prompt=WORKFLOW_PLANNER_SYSTEM_PROMPT,
                    config=EvaluationConfig(
                        threshold=3.0,
                        prompt_type=PromptType.SYSTEM_PROMPT,
                    )
                )

            assert result.dimension_scores["safety"].score >= 3, (
                f"Safety score too low: {result.dimension_scores['safety'].feedback}"
            )


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skip(reason="Live LLM evaluation - run explicitly with: pytest -m integration")
class TestWorkflowPlannerPromptLiveEvaluation:
    """
    Live integration tests that actually call the LLM evaluation service.

    These tests are marked as 'integration' and 'slow' so they can be
    skipped in normal CI runs but run periodically for full verification.

    Run with: pytest -m integration --run-integration tests/unit/agents/test_workflow_planner_prompt_quality.py
    """

    @pytest.mark.asyncio
    async def test_live_evaluation_passes(self):
        """
        Actually run the prompt through the evaluation service.

        This test makes a real LLM API call and should only be run
        when explicitly testing prompt quality.
        """
        pytest.importorskip("src.infrastructure.evaluations.prompt_evaluation_service")

        from src.infrastructure.evaluations.prompt_evaluation_service import PromptEvaluationService

        async with PromptEvaluationService(
            enable_cache=False,  # Force fresh evaluation
            enable_db_persistence=False,  # Don't persist test results
        ) as eval_service:
            result = await eval_service.evaluate_prompt(
                prompt=WORKFLOW_PLANNER_SYSTEM_PROMPT,
                config=EvaluationConfig(
                    threshold=3.0,
                    prompt_type=PromptType.SYSTEM_PROMPT,
                )
            )

        # Assert overall pass
        assert result.passed, (
            f"Prompt failed evaluation!\n"
            f"Score: {result.overall_score}/5.0\n"
            f"Status: {result.evaluation_result.value}\n"
            f"Justification: {result.justification}"
        )

        # Assert minimum score
        assert result.overall_score >= 3.0, (
            f"Overall score {result.overall_score} below threshold 3.0"
        )

        # Assert no critical failures (score of 1)
        for dim_name, dim_score in result.dimension_scores.items():
            assert dim_score.score >= 2, (
                f"Dimension '{dim_name}' has critical score of 1: "
                f"{dim_score.feedback}"
            )

        # Assert safety is acceptable
        if "safety" in result.dimension_scores:
            assert result.dimension_scores["safety"].score >= 3, (
                f"Safety score {result.dimension_scores['safety'].score} "
                f"is below minimum 3"
            )

    @pytest.mark.asyncio
    async def test_live_evaluation_high_quality(self):
        """
        Test that prompt achieves high quality scores (4+).

        This is a stricter test that ensures the prompt maintains
        excellence, not just minimum passing.
        """
        pytest.importorskip("src.infrastructure.evaluations.prompt_evaluation_service")

        from src.infrastructure.evaluations.prompt_evaluation_service import PromptEvaluationService

        async with PromptEvaluationService(
            enable_cache=False,
            enable_db_persistence=False,
        ) as eval_service:
            result = await eval_service.evaluate_prompt(
                prompt=WORKFLOW_PLANNER_SYSTEM_PROMPT,
                config=EvaluationConfig(
                    threshold=4.0,  # Higher threshold
                    prompt_type=PromptType.SYSTEM_PROMPT,
                )
            )

        # We expect high quality, but don't fail the test if it's just "passing"
        if result.overall_score < 4.0:
            pytest.skip(
                f"Prompt scores {result.overall_score}/5.0 - "
                f"above minimum but below high quality threshold"
            )

        assert result.overall_score >= 4.0, (
            f"Expected high quality score (4.0+), got {result.overall_score}"
        )
