"""Unit tests for PromptEvaluationService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from src.infrastructure.evaluations.prompt_evaluation_service import PromptEvaluationService
from src.evaluation.rubrics import (
    EvaluationConfig,
    EvaluationResult,
    EvaluationStatus,
    PromptType,
    DimensionScore,
    calculate_weighted_score,
    determine_evaluation_status,
    STANDARD_RUBRICS,
)


class TestRubrics:
    """Tests for rubric definitions and scoring logic."""

    def test_standard_rubrics_exist(self):
        """Test that all standard rubrics are defined."""
        assert "system_prompt" in STANDARD_RUBRICS
        assert "agent_prompt" in STANDARD_RUBRICS
        assert "workflow_prompt" in STANDARD_RUBRICS
        assert "general" in STANDARD_RUBRICS

    def test_rubric_dimensions(self):
        """Test that rubrics have required dimensions."""
        for rubric_name, rubric in STANDARD_RUBRICS.items():
            dimension_names = {d.name for d in rubric.dimensions}
            assert "clarity" in dimension_names
            assert "specificity" in dimension_names
            assert "safety" in dimension_names
            assert "output_format" in dimension_names
            assert "context" in dimension_names
            assert "constraints" in dimension_names

    def test_safety_dimension_is_critical(self):
        """Test that safety dimension is marked as critical."""
        rubric = STANDARD_RUBRICS["system_prompt"]
        safety_dim = next(d for d in rubric.dimensions if d.name == "safety")
        assert safety_dim.critical is True
        assert safety_dim.weight > 1.0  # Higher weight

    def test_agent_prompt_higher_threshold(self):
        """Test that agent prompts have a higher pass threshold."""
        agent_rubric = STANDARD_RUBRICS["agent_prompt"]
        general_rubric = STANDARD_RUBRICS["general"]
        assert agent_rubric.pass_threshold > general_rubric.pass_threshold


class TestCalculateWeightedScore:
    """Tests for weighted score calculation."""

    def test_calculate_equal_weights(self):
        """Test score calculation with equal weights."""
        # Use a rubric where all dimensions have weight 1.0
        rubric = STANDARD_RUBRICS["general"]

        # Create dimension scores with all 1.0 weights
        scores = {
            "clarity": 4,
            "specificity": 4,
            "safety": 4,
            "output_format": 4,
            "context": 4,
            "constraints": 4,
        }

        # Calculate weighted score
        result = calculate_weighted_score(scores, rubric)

        # With mixed weights, result should be close to 4
        assert 3.5 <= result <= 4.5

    def test_calculate_with_missing_dimensions(self):
        """Test score calculation handles missing dimensions."""
        rubric = STANDARD_RUBRICS["general"]
        scores = {"clarity": 5}  # Only one dimension

        result = calculate_weighted_score(scores, rubric)
        assert result == 5.0  # Only clarity counts

    def test_calculate_empty_scores(self):
        """Test score calculation with empty scores."""
        rubric = STANDARD_RUBRICS["general"]
        scores = {}

        result = calculate_weighted_score(scores, rubric)
        assert result == 0.0


class TestDetermineEvaluationStatus:
    """Tests for evaluation status determination."""

    def test_pass_all_good_scores(self):
        """Test PASS when all scores are good."""
        rubric = STANDARD_RUBRICS["general"]
        config = EvaluationConfig(threshold=3.0)

        scores = {
            "clarity": 4,
            "specificity": 4,
            "safety": 4,
            "output_format": 4,
            "context": 4,
            "constraints": 4,
        }

        status = determine_evaluation_status(4.0, scores, rubric, config)
        assert status == EvaluationStatus.PASS

    def test_fail_on_low_safety(self):
        """Test FAIL when safety score is below threshold."""
        rubric = STANDARD_RUBRICS["general"]
        config = EvaluationConfig(threshold=3.0, fail_on_safety_below=3)

        scores = {
            "clarity": 5,
            "specificity": 5,
            "safety": 2,  # Below safety threshold
            "output_format": 5,
            "context": 5,
            "constraints": 5,
        }

        status = determine_evaluation_status(4.5, scores, rubric, config)
        assert status == EvaluationStatus.FAIL

    def test_fail_on_score_of_one(self):
        """Test FAIL when any score is 1."""
        rubric = STANDARD_RUBRICS["general"]
        config = EvaluationConfig(threshold=3.0)

        scores = {
            "clarity": 1,  # Score of 1
            "specificity": 5,
            "safety": 5,
            "output_format": 5,
            "context": 5,
            "constraints": 5,
        }

        status = determine_evaluation_status(4.0, scores, rubric, config)
        assert status == EvaluationStatus.FAIL

    def test_pass_with_warnings(self):
        """Test PASS_WITH_WARNINGS when scores include 2."""
        rubric = STANDARD_RUBRICS["general"]
        config = EvaluationConfig(threshold=3.0)

        scores = {
            "clarity": 4,
            "specificity": 2,  # Warning-level score
            "safety": 4,
            "output_format": 4,
            "context": 4,
            "constraints": 4,
        }

        status = determine_evaluation_status(3.5, scores, rubric, config)
        assert status == EvaluationStatus.PASS_WITH_WARNINGS

    def test_fail_below_threshold(self):
        """Test FAIL when overall score is below threshold."""
        rubric = STANDARD_RUBRICS["general"]
        config = EvaluationConfig(threshold=3.0)

        scores = {
            "clarity": 2,
            "specificity": 2,
            "safety": 3,
            "output_format": 2,
            "context": 2,
            "constraints": 2,
        }

        status = determine_evaluation_status(2.1, scores, rubric, config)
        assert status == EvaluationStatus.FAIL


class TestEvaluationConfig:
    """Tests for EvaluationConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = EvaluationConfig()
        assert config.threshold == 3.0
        assert config.prompt_type == PromptType.GENERAL
        assert config.fail_on_safety_below == 3

    def test_get_rubric_by_prompt_type(self):
        """Test rubric selection by prompt type."""
        config = EvaluationConfig(prompt_type=PromptType.AGENT_PROMPT)
        rubric = config.get_rubric()
        assert rubric.name == "Agent Prompt Rubric"

    def test_custom_rubric_override(self):
        """Test that custom rubric overrides default."""
        custom_rubric = STANDARD_RUBRICS["system_prompt"]
        config = EvaluationConfig(
            prompt_type=PromptType.GENERAL,
            custom_rubric=custom_rubric
        )
        rubric = config.get_rubric()
        assert rubric.name == "System Prompt Rubric"


class TestPromptEvaluationService:
    """Tests for PromptEvaluationService."""

    @pytest.fixture
    def mock_llm_response(self):
        """Create a mock LLM response."""
        return MagicMock(
            content=json.dumps({
                "evaluation_result": "pass",
                "dimension_scores": {
                    "clarity": {"score": 4, "feedback": "Clear and concise"},
                    "specificity": {"score": 4, "feedback": "Well specified"},
                    "safety": {"score": 5, "feedback": "Includes safety guardrails"},
                    "output_format": {"score": 4, "feedback": "Format specified"},
                    "context": {"score": 4, "feedback": "Good context"},
                    "constraints": {"score": 4, "feedback": "Constraints defined"},
                },
                "overall_score": 4.17,
                "passed": True,
                "justification": "Well-structured prompt with clear instructions",
                "improvement_suggestions": [
                    {"dimension": "clarity", "suggestion": "Add examples", "priority": "low"}
                ]
            })
        )

    @pytest.mark.asyncio
    async def test_evaluate_prompt_success(self, mock_llm_response):
        """Test successful prompt evaluation."""
        with patch("src.infrastructure.evaluations.prompt_evaluation_service.OpenRouterClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.create_completion = AsyncMock(return_value=mock_llm_response)
            MockClient.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()

            service = PromptEvaluationService(llm_client=mock_client)
            service._owns_client = False

            result = await service.evaluate_prompt(
                prompt="You are a helpful assistant. Please help the user with their questions.",
                config=EvaluationConfig(threshold=3.0)
            )

            assert result.passed is True
            assert result.evaluation_result == EvaluationStatus.PASS
            assert result.overall_score >= 4.0
            assert "clarity" in result.dimension_scores

    @pytest.mark.asyncio
    async def test_evaluate_prompt_failure(self):
        """Test prompt evaluation with failing score."""
        mock_response = MagicMock(
            content=json.dumps({
                "evaluation_result": "fail",
                "dimension_scores": {
                    "clarity": {"score": 1, "feedback": "Very unclear"},
                    "specificity": {"score": 2, "feedback": "Too vague"},
                    "safety": {"score": 2, "feedback": "Safety concerns"},
                    "output_format": {"score": 1, "feedback": "No format"},
                    "context": {"score": 2, "feedback": "No context"},
                    "constraints": {"score": 1, "feedback": "No constraints"},
                },
                "overall_score": 1.5,
                "passed": False,
                "justification": "Prompt is too vague and lacks structure",
                "improvement_suggestions": []
            })
        )

        with patch("src.infrastructure.evaluations.prompt_evaluation_service.OpenRouterClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.create_completion = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()

            service = PromptEvaluationService(llm_client=mock_client)
            service._owns_client = False

            result = await service.evaluate_prompt(
                prompt="Do stuff",
                config=EvaluationConfig(threshold=3.0)
            )

            assert result.passed is False
            assert result.evaluation_result == EvaluationStatus.FAIL

    @pytest.mark.asyncio
    async def test_evaluate_workflow_spec_prompts(self, mock_llm_response):
        """Test evaluating prompts from workflow spec YAML."""
        workflow_yaml = """
workflow:
  name: test_workflow
  nodes:
    - id: analyzer
      executor: agent
      agent:
        system_prompt: |
          You are a data analyzer. Analyze the input data and provide insights.
          Always format your response as JSON.
        config:
          model: gpt-4
    - id: processor
      executor: function
      inputs:
        prompt: "Process this data: ${node.analyzer.output}"
"""

        with patch("src.infrastructure.evaluations.prompt_evaluation_service.OpenRouterClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.create_completion = AsyncMock(return_value=mock_llm_response)
            MockClient.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()

            service = PromptEvaluationService(llm_client=mock_client)
            service._owns_client = False

            results = await service.evaluate_workflow_spec_prompts(
                yaml_content=workflow_yaml,
                config=EvaluationConfig(threshold=3.0)
            )

            # Should find the system_prompt in the analyzer node
            assert len(results) >= 1
            assert any("system_prompt" in path for path in results.keys())

    @pytest.mark.asyncio
    async def test_evaluate_agent_spec_prompt(self, mock_llm_response):
        """Test evaluating agent spec system prompt."""
        agent_yaml = """
agent:
  metadata:
    name: test_agent
    version: "1.0.0"
  state_schema:
    type: llm_worker
    config:
      system_prompt: |
        You are a test agent. Help users with their queries.
        Always be polite and helpful.
"""

        with patch("src.infrastructure.evaluations.prompt_evaluation_service.OpenRouterClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.create_completion = AsyncMock(return_value=mock_llm_response)
            MockClient.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()

            service = PromptEvaluationService(llm_client=mock_client)
            service._owns_client = False

            result = await service.evaluate_agent_spec_prompt(
                yaml_content=agent_yaml,
                config=EvaluationConfig(threshold=3.5)
            )

            assert result.passed is True

    @pytest.mark.asyncio
    async def test_evaluate_agent_spec_no_prompt(self):
        """Test evaluating agent spec with no system prompt."""
        agent_yaml = """
agent:
  metadata:
    name: test_agent
  state_schema:
    type: function_worker
"""

        with patch("src.infrastructure.evaluations.prompt_evaluation_service.OpenRouterClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()

            service = PromptEvaluationService(llm_client=mock_client)
            service._owns_client = False

            result = await service.evaluate_agent_spec_prompt(
                yaml_content=agent_yaml,
                config=EvaluationConfig(threshold=3.5)
            )

            # Should pass by default when no prompt is found
            assert result.passed is True
            assert "No system prompt found" in result.justification

    def test_parse_json_response_direct(self):
        """Test JSON parsing from direct JSON."""
        service = PromptEvaluationService()

        json_str = '{"evaluation_result": "pass", "overall_score": 4.0}'
        result = service._parse_json_response(json_str)

        assert result["evaluation_result"] == "pass"
        assert result["overall_score"] == 4.0

    def test_parse_json_response_markdown(self):
        """Test JSON parsing from markdown code block."""
        service = PromptEvaluationService()

        json_str = """Here is my evaluation:

```json
{"evaluation_result": "pass", "overall_score": 4.0}
```

I hope this helps!"""

        result = service._parse_json_response(json_str)
        assert result["evaluation_result"] == "pass"

    def test_parse_json_response_embedded(self):
        """Test JSON parsing from embedded JSON."""
        service = PromptEvaluationService()

        json_str = """I analyzed the prompt and here is my evaluation:
{"evaluation_result": "pass", "overall_score": 4.0}
The prompt looks good overall."""

        result = service._parse_json_response(json_str)
        assert result["evaluation_result"] == "pass"

    def test_is_template_reference(self):
        """Test template reference detection."""
        service = PromptEvaluationService()

        assert service._is_template_reference("${node.analyzer.output}") is True
        assert service._is_template_reference("${{parameters.input}}") is True
        assert service._is_template_reference("Hello world") is False
        assert service._is_template_reference("Use ${node.x} for output") is True


class TestEvaluationResult:
    """Tests for EvaluationResult dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = EvaluationResult(
            evaluation_id="test-123",
            passed=True,
            evaluation_result=EvaluationStatus.PASS,
            overall_score=4.0,
            dimension_scores={
                "clarity": DimensionScore(score=4, feedback="Good", weight=1.0)
            },
            justification="Well done",
            improvement_suggestions=[],
            prompt_type="general",
            threshold=3.0,
            can_override=True
        )

        d = result.to_dict()
        assert d["evaluation_id"] == "test-123"
        assert d["passed"] is True
        assert d["evaluation_result"] == "pass"
        assert d["overall_score"] == 4.0
        assert "clarity" in d["dimension_scores"]
