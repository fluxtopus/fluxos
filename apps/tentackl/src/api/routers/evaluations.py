# REVIEW:
# - Default model is hard-coded here (and in evaluation_helpers); config drift likely.
# - Endpoint does not surface evaluation cost/latency controls; potential abuse outside rate limiting.
"""API routes for standalone prompt evaluation."""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import structlog

from src.application.evaluations import PromptEvaluationUseCases
from src.infrastructure.evaluations import PromptEvaluationServiceAdapter
from src.evaluation.rubrics import (
    EvaluationResult,
    PromptType,
    STANDARD_RUBRICS,
)
from src.api.auth_middleware import auth_middleware, AuthUser
from src.api.evaluation_helpers import DimensionScoreResponse

logger = structlog.get_logger()

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


def get_evaluation_use_cases() -> PromptEvaluationUseCases:
    """Provide application-layer prompt evaluation use cases."""
    return PromptEvaluationUseCases(
        evaluation_ops=PromptEvaluationServiceAdapter(),
    )


# Request/Response models


class EvaluatePromptRequest(BaseModel):
    """Request to evaluate a single prompt."""
    prompt: str = Field(..., description="The prompt text to evaluate")
    prompt_type: str = Field(
        "general",
        description="Type of prompt: system_prompt, agent_prompt, workflow_prompt, general"
    )
    threshold: float = Field(3.0, description="Minimum score to pass (1.0-5.0)")
    model: Optional[str] = Field(None, description="Model to use for evaluation")


class EvaluateAgentSpecRequest(BaseModel):
    """Request to evaluate an agent spec's system prompt."""
    yaml_content: str = Field(..., description="YAML agent specification")
    threshold: float = Field(3.5, description="Minimum score to pass (1.0-5.0)")
    model: Optional[str] = Field(None, description="Model to use for evaluation")


class EvaluationResultResponse(BaseModel):
    """Response for a single prompt evaluation."""
    evaluation_id: str
    passed: bool
    evaluation_result: str  # pass, pass_with_warnings, fail
    overall_score: float
    dimension_scores: Dict[str, DimensionScoreResponse]
    justification: str
    improvement_suggestions: List[Dict[str, Any]]
    prompt_type: str
    threshold: float
    can_override: bool


class RubricDimensionInfo(BaseModel):
    """Information about a rubric dimension."""
    name: str
    description: str
    weight: float
    fail_threshold: int
    critical: bool


class RubricInfo(BaseModel):
    """Information about an evaluation rubric."""
    name: str
    description: str
    pass_threshold: float
    dimensions: List[RubricDimensionInfo]


# Helper functions


def _format_evaluation_result(result: EvaluationResult) -> EvaluationResultResponse:
    """Convert EvaluationResult to response model."""
    dim_scores = {}
    for dim_name, dim_score in result.dimension_scores.items():
        dim_scores[dim_name] = DimensionScoreResponse(
            score=dim_score.score,
            feedback=dim_score.feedback,
            weight=dim_score.weight
        )

    return EvaluationResultResponse(
        evaluation_id=result.evaluation_id,
        passed=result.passed,
        evaluation_result=result.evaluation_result.value,
        overall_score=result.overall_score,
        dimension_scores=dim_scores,
        justification=result.justification,
        improvement_suggestions=result.improvement_suggestions,
        prompt_type=result.prompt_type,
        threshold=result.threshold,
        can_override=result.can_override
    )


# Endpoints


@router.post("/prompt", response_model=EvaluationResultResponse)
async def evaluate_prompt(
    request: EvaluatePromptRequest,
    use_cases: PromptEvaluationUseCases = Depends(get_evaluation_use_cases),
    current_user: AuthUser = Depends(auth_middleware.require_permission("workflows", "view"))
):
    """
    Evaluate a single prompt using LLM-as-judge methodology.

    Returns detailed scores across 6 dimensions:
    - clarity: Is the prompt clear and unambiguous?
    - specificity: Are instructions specific enough?
    - safety: Does it avoid encouraging harmful outputs?
    - output_format: Does it specify expected output format?
    - context: Does it provide sufficient context?
    - constraints: Are constraints clearly stated?

    **Pass/Fail Criteria:**
    - PASS: Overall score >= threshold AND no dimension < 2
    - PASS_WITH_WARNINGS: Overall >= threshold but has dimension scores of 2
    - FAIL: Overall < threshold OR any dimension = 1 OR safety < 3
    """
    try:
        # Map string to enum
        prompt_type_map = {
            "system_prompt": PromptType.SYSTEM_PROMPT,
            "agent_prompt": PromptType.AGENT_PROMPT,
            "workflow_prompt": PromptType.WORKFLOW_PROMPT,
            "general": PromptType.GENERAL,
        }
        prompt_type = prompt_type_map.get(request.prompt_type, PromptType.GENERAL)

        result = await use_cases.evaluate_prompt(
            prompt=request.prompt,
            prompt_type=prompt_type,
            threshold=request.threshold,
            model=request.model,
        )

        logger.info(
            "Prompt evaluated via API",
            evaluation_id=result.evaluation_id,
            passed=result.passed,
            overall_score=result.overall_score
        )

        return _format_evaluation_result(result)

    except Exception as e:
        logger.error("Prompt evaluation failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Evaluation failed: An unexpected error occurred")


@router.post("/agent-spec", response_model=EvaluationResultResponse)
async def evaluate_agent_spec(
    request: EvaluateAgentSpecRequest,
    use_cases: PromptEvaluationUseCases = Depends(get_evaluation_use_cases),
    current_user: AuthUser = Depends(auth_middleware.require_permission("workflows", "view"))
):
    """
    Evaluate an agent specification's system prompt.

    Agent prompts have a higher default threshold (3.5) as they typically
    require more precision in instructions.
    """
    try:
        result = await use_cases.evaluate_agent_spec_prompt(
            yaml_content=request.yaml_content,
            threshold=request.threshold,
            model=request.model,
        )

        logger.info(
            "Agent spec evaluated via API",
            evaluation_id=result.evaluation_id,
            passed=result.passed,
            overall_score=result.overall_score
        )

        return _format_evaluation_result(result)

    except Exception as e:
        logger.error("Agent spec evaluation failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="Evaluation failed: An unexpected error occurred")


@router.get("/rubrics", response_model=Dict[str, RubricInfo])
async def list_rubrics():
    """
    List available evaluation rubrics.

    Returns information about the standard rubrics used for different prompt types.
    """
    rubrics_info = {}

    for rubric_name, rubric in STANDARD_RUBRICS.items():
        dimensions = []
        for dim in rubric.dimensions:
            dimensions.append(RubricDimensionInfo(
                name=dim.name,
                description=dim.description,
                weight=dim.weight,
                fail_threshold=dim.fail_threshold,
                critical=dim.critical
            ))

        rubrics_info[rubric_name] = RubricInfo(
            name=rubric.name,
            description=rubric.description,
            pass_threshold=rubric.pass_threshold,
            dimensions=dimensions
        )

    return rubrics_info


@router.get("/rubrics/{rubric_name}", response_model=RubricInfo)
async def get_rubric(rubric_name: str):
    """
    Get details of a specific evaluation rubric.

    Available rubrics: system_prompt, agent_prompt, workflow_prompt, general
    """
    if rubric_name not in STANDARD_RUBRICS:
        raise HTTPException(
            status_code=404,
            detail=f"Rubric '{rubric_name}' not found. Available: {list(STANDARD_RUBRICS.keys())}"
        )

    rubric = STANDARD_RUBRICS[rubric_name]
    dimensions = []
    for dim in rubric.dimensions:
        dimensions.append(RubricDimensionInfo(
            name=dim.name,
            description=dim.description,
            weight=dim.weight,
            fail_threshold=dim.fail_threshold,
            critical=dim.critical
        ))

    return RubricInfo(
        name=rubric.name,
        description=rubric.description,
        pass_threshold=rubric.pass_threshold,
        dimensions=dimensions
    )
