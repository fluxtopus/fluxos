# REVIEW:
# - skip_evaluation permission checks use AuthUser.scopes; bearer tokens via InkPass may have empty scopes, blocking admin bypass.
# - Default evaluation model is hard-coded (not in config), making environment overrides harder.
"""Shared utilities for prompt evaluation gates.

This module extracts common evaluation gate logic used across:
- agent_registry.py (register_agent, update_agent)

Provides:
- Shared Pydantic response models
- Permission checking for skip_evaluation
- Unified evaluation gate runner with backwards-compatible wrappers
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from fastapi import HTTPException
import structlog

from src.application.evaluations import PromptEvaluationUseCases
from src.evaluation.rubrics import EvaluationConfig, EvaluationResult, PromptType
from src.infrastructure.evaluations import PromptEvaluationServiceAdapter
from src.api.auth_middleware import AuthUser

logger = structlog.get_logger(__name__)

# Maximum YAML size to prevent YAML bomb attacks (100KB)
MAX_YAML_SIZE = 100 * 1024


def _validate_yaml_size(content: str, context: str) -> None:
    """
    Validate YAML content size to prevent YAML bomb attacks.

    Args:
        content: The YAML content to validate
        context: Description for error message

    Raises:
        HTTPException: 413 if content exceeds MAX_YAML_SIZE
    """
    if len(content) > MAX_YAML_SIZE:
        logger.warning(
            "YAML content size exceeds limit",
            context=context,
            size=len(content),
            max_size=MAX_YAML_SIZE
        )
        raise HTTPException(
            status_code=413,
            detail=f"YAML content exceeds maximum size of {MAX_YAML_SIZE // 1024}KB"
        )


# =============================================================================
# Shared Response Models
# =============================================================================


class DimensionScoreResponse(BaseModel):
    """Score for a single evaluation dimension."""
    score: int
    feedback: str
    weight: float


class AgentEvaluationFailureResponse(BaseModel):
    """Details of a failed agent prompt evaluation (single prompt)."""
    overall_score: float
    evaluation_result: str
    justification: str
    dimension_scores: Dict[str, DimensionScoreResponse]
    suggestions: List[Dict[str, Any]]


# =============================================================================
# Permission Checking
# =============================================================================


def check_skip_evaluation_permission(
    skip_evaluation: bool,
    current_user: Optional[AuthUser],
    context: str
) -> None:
    """
    Check if user has permission to skip evaluation.

    Args:
        skip_evaluation: Whether skip was requested
        current_user: The authenticated user (may be None for agent registry)
        context: Description for logging (e.g., "task prompt registration")

    Raises:
        HTTPException: 403 if skip_evaluation requested without admin permission
    """
    if not skip_evaluation:
        return

    if not current_user or "admin" not in (current_user.scopes or []):
        raise HTTPException(
            status_code=403,
            detail="skip_evaluation requires admin permission"
        )

    logger.info(
        f"Prompt evaluation skipped for {context}",
        skipped_by=current_user.id
    )


# =============================================================================
# Evaluation Gate Runners
# =============================================================================


def _convert_dimension_scores(
    result_dimension_scores: Dict
) -> Dict[str, DimensionScoreResponse]:
    """Convert evaluation result dimension scores to response format."""
    return {
        dim_name: DimensionScoreResponse(
            score=dim_score.score,
            feedback=dim_score.feedback,
            weight=dim_score.weight
        )
        for dim_name, dim_score in result_dimension_scores.items()
    }


def _format_agent_failure(result: EvaluationResult) -> AgentEvaluationFailureResponse:
    """Format an agent evaluation failure for response."""
    return AgentEvaluationFailureResponse(
        overall_score=result.overall_score,
        evaluation_result=result.evaluation_result.value,
        justification=result.justification,
        dimension_scores=_convert_dimension_scores(result.dimension_scores),
        suggestions=result.improvement_suggestions
    )


async def run_evaluation_gate(
    yaml_content: str,
    threshold: float,
    model: Optional[str],
    context: str,
    identifier: str,
    service: Optional[Any] = None,
) -> EvaluationResult:
    """
    Unified evaluation gate for agent specs.

    Args:
        yaml_content: The YAML content to evaluate
        threshold: Minimum score to pass (1.0-5.0)
        model: LLM model to use for evaluation (None for default)
        context: Description for error messages (e.g., "registration", "update")
        identifier: Spec name or ID for logging
        service: Optional PromptEvaluationService instance for dependency injection

    Returns:
        Evaluation result if passed

    Raises:
        HTTPException: 413 if YAML content too large
        HTTPException: 422 if evaluation fails
    """
    _validate_yaml_size(yaml_content, f"agent {context}")

    # Use provided service for backwards compatibility in tests;
    # otherwise resolve application use cases over infrastructure adapter.
    if service is not None:
        eval_config = EvaluationConfig(
            threshold=threshold,
            prompt_type=PromptType.AGENT_PROMPT,
            model=model,
        )
        result = await service.evaluate_agent_spec_prompt(
            yaml_content=yaml_content,
            config=eval_config,
        )
    else:
        use_cases = PromptEvaluationUseCases(
            evaluation_ops=PromptEvaluationServiceAdapter(),
        )
        result = await use_cases.evaluate_agent_spec_prompt(
            yaml_content=yaml_content,
            threshold=threshold,
            model=model,
        )

    if not result.passed:
        failure = _format_agent_failure(result)
        logger.warning(
            f"Agent {context} blocked by prompt evaluation",
            identifier=identifier,
            overall_score=result.overall_score,
            threshold=threshold
        )
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"Agent prompt evaluation failed - {context} blocked",
                "failure": failure.model_dump(),
                "hint": "Improve the system prompt based on suggestions or use skip_evaluation=true with ADMIN scope"
            }
        )

    logger.info(
        f"Agent prompt passed evaluation for {context}",
        identifier=identifier,
        overall_score=result.overall_score,
        threshold=threshold
    )
    return result


# =============================================================================
# Backwards-Compatible Wrappers
# =============================================================================


async def run_agent_evaluation_gate(
    yaml_content: str,
    threshold: float,
    model: Optional[str],
    context: str,
    identifier: str,
    service: Optional[Any] = None,
) -> None:
    """
    Run evaluation gate for agent spec system prompt.

    Evaluates the agent's system prompt and raises HTTP 422 if it fails.
    This is a backwards-compatible wrapper around run_evaluation_gate().

    Args:
        yaml_content: The agent YAML content
        threshold: Minimum score to pass (1.0-5.0)
        model: LLM model to use for evaluation (None for default)
        context: Description for error messages (e.g., "registration", "update")
        identifier: Agent name or spec ID for logging
        service: Optional PromptEvaluationService for dependency injection

    Raises:
        HTTPException: 413 if YAML content too large
        HTTPException: 422 if prompt fails evaluation
    """
    await run_evaluation_gate(
        yaml_content=yaml_content,
        threshold=threshold,
        model=model,
        context=context,
        identifier=identifier,
        service=service,
    )
