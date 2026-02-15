"""Rubric definitions and scoring logic for prompt evaluation.

This module defines the evaluation dimensions, rubrics, and scoring logic
used to assess prompt quality before publishing tasks or agents.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class EvaluationStatus(str, Enum):
    """Evaluation result status."""
    PASS = "pass"
    PASS_WITH_WARNINGS = "pass_with_warnings"
    FAIL = "fail"


class PromptType(str, Enum):
    """Type of prompt being evaluated."""
    SYSTEM_PROMPT = "system_prompt"
    AGENT_PROMPT = "agent_prompt"
    WORKFLOW_PROMPT = "workflow_prompt"
    GENERAL = "general"


@dataclass
class RubricDimension:
    """A single dimension in an evaluation rubric."""
    name: str
    description: str
    weight: float = 1.0
    levels: Dict[int, str] = field(default_factory=lambda: {
        5: "Excellent - Exceeds expectations",
        4: "Good - Meets expectations with minor gaps",
        3: "Adequate - Meets basic requirements",
        2: "Needs Improvement - Significant gaps",
        1: "Unacceptable - Does not meet requirements"
    })
    fail_threshold: int = 2  # Score below this triggers fail for this dimension
    critical: bool = False  # If True, score of 1 always fails entire eval


# Standard dimension definitions
CLARITY_DIMENSION = RubricDimension(
    name="clarity",
    description="Is the prompt clear and unambiguous?",
    weight=1.0,
    levels={
        5: "Crystal clear, no ambiguity whatsoever",
        4: "Very clear with minor ambiguities",
        3: "Generally clear but some parts unclear",
        2: "Confusing in several places",
        1: "Extremely unclear or contradictory"
    }
)

SPECIFICITY_DIMENSION = RubricDimension(
    name="specificity",
    description="Are instructions specific enough?",
    weight=1.0,
    levels={
        5: "Highly specific with exact requirements",
        4: "Specific with minor gaps",
        3: "Moderately specific",
        2: "Vague in key areas",
        1: "No specific guidance"
    }
)

SAFETY_DIMENSION = RubricDimension(
    name="safety",
    description="Does it avoid encouraging harmful outputs?",
    weight=1.5,  # Higher weight for safety
    fail_threshold=3,  # Must score at least 3
    critical=True,  # Score of 1 always fails
    levels={
        5: "Explicitly guards against harmful outputs with clear boundaries",
        4: "Generally safe with minor concerns",
        3: "Neutral - no explicit safety considerations",
        2: "Could potentially lead to harmful outputs",
        1: "Actively encourages or lacks guardrails for harmful outputs"
    }
)

OUTPUT_FORMAT_DIMENSION = RubricDimension(
    name="output_format",
    description="Does it specify expected output format?",
    weight=1.0,
    levels={
        5: "Exact format specified with examples",
        4: "Format clearly described",
        3: "Format mentioned but not detailed",
        2: "Format implied but unclear",
        1: "No format guidance"
    }
)

CONTEXT_DIMENSION = RubricDimension(
    name="context",
    description="Does it provide sufficient context?",
    weight=0.8,
    levels={
        5: "Complete context with background, purpose, and constraints",
        4: "Good context with minor gaps",
        3: "Basic context provided",
        2: "Insufficient context",
        1: "No context provided"
    }
)

CONSTRAINTS_DIMENSION = RubricDimension(
    name="constraints",
    description="Are constraints clearly stated?",
    weight=0.8,
    levels={
        5: "All constraints explicit with clear boundaries",
        4: "Most constraints clear",
        3: "Some constraints mentioned",
        2: "Few constraints specified",
        1: "No constraints defined"
    }
)


@dataclass
class EvaluationRubric:
    """Complete evaluation rubric configuration."""
    name: str
    description: str
    dimensions: List[RubricDimension]
    pass_threshold: float = 3.0  # Minimum weighted score to pass
    require_all_pass: bool = True  # All dimensions must pass individual thresholds


# Standard rubrics for different prompt types
STANDARD_RUBRICS: Dict[str, EvaluationRubric] = {
    "system_prompt": EvaluationRubric(
        name="System Prompt Rubric",
        description="Standard rubric for evaluating system prompts",
        dimensions=[
            CLARITY_DIMENSION,
            SPECIFICITY_DIMENSION,
            SAFETY_DIMENSION,
            OUTPUT_FORMAT_DIMENSION,
            CONTEXT_DIMENSION,
            CONSTRAINTS_DIMENSION,
        ],
        pass_threshold=3.0
    ),

    "agent_prompt": EvaluationRubric(
        name="Agent Prompt Rubric",
        description="Rubric for evaluating agent-specific prompts (higher bar)",
        dimensions=[
            RubricDimension(
                name="clarity",
                description="Is the prompt clear and unambiguous?",
                weight=1.2,  # Higher weight for agents
            ),
            RubricDimension(
                name="specificity",
                description="Are instructions specific enough?",
                weight=1.5,  # Higher weight for agents
            ),
            SAFETY_DIMENSION,
            RubricDimension(
                name="output_format",
                description="Does it specify expected output format?",
                weight=1.2,  # Higher weight for agents
            ),
            CONTEXT_DIMENSION,
            CONSTRAINTS_DIMENSION,
        ],
        pass_threshold=3.5  # Higher threshold for agent prompts
    ),

    "workflow_prompt": EvaluationRubric(
        name="Workflow Prompt Rubric",
        description="Rubric for evaluating prompts embedded in workflows",
        dimensions=[
            CLARITY_DIMENSION,
            SPECIFICITY_DIMENSION,
            SAFETY_DIMENSION,
            OUTPUT_FORMAT_DIMENSION,
            CONTEXT_DIMENSION,
            CONSTRAINTS_DIMENSION,
        ],
        pass_threshold=3.0
    ),

    "general": EvaluationRubric(
        name="General Prompt Rubric",
        description="Default rubric for general prompt evaluation",
        dimensions=[
            CLARITY_DIMENSION,
            SPECIFICITY_DIMENSION,
            SAFETY_DIMENSION,
            OUTPUT_FORMAT_DIMENSION,
            CONTEXT_DIMENSION,
            CONSTRAINTS_DIMENSION,
        ],
        pass_threshold=3.0
    ),
}


@dataclass
class EvaluationConfig:
    """Configuration for prompt evaluation."""
    threshold: float = 3.0
    rubric_name: Optional[str] = None
    custom_rubric: Optional[EvaluationRubric] = None
    prompt_type: PromptType = PromptType.GENERAL
    model: str = "google/gemini-2.5-flash"
    fail_on_safety_below: int = 3  # Always fail if safety score below this

    def get_rubric(self) -> EvaluationRubric:
        """Get the rubric to use for evaluation."""
        if self.custom_rubric:
            return self.custom_rubric
        if self.rubric_name and self.rubric_name in STANDARD_RUBRICS:
            return STANDARD_RUBRICS[self.rubric_name]
        # Default based on prompt type
        return STANDARD_RUBRICS.get(self.prompt_type.value, STANDARD_RUBRICS["general"])


@dataclass
class DimensionScore:
    """Score for a single evaluation dimension."""
    score: int
    feedback: str
    weight: float = 1.0


@dataclass
class EvaluationResult:
    """Result of prompt evaluation."""
    evaluation_id: str
    passed: bool
    evaluation_result: EvaluationStatus
    overall_score: float
    dimension_scores: Dict[str, DimensionScore]
    justification: str
    improvement_suggestions: List[Dict[str, Any]]
    prompt_type: str
    threshold: float
    can_override: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "evaluation_id": self.evaluation_id,
            "passed": self.passed,
            "evaluation_result": self.evaluation_result.value,
            "overall_score": self.overall_score,
            "dimension_scores": {
                name: {
                    "score": score.score,
                    "feedback": score.feedback,
                    "weight": score.weight
                }
                for name, score in self.dimension_scores.items()
            },
            "justification": self.justification,
            "improvement_suggestions": self.improvement_suggestions,
            "prompt_type": self.prompt_type,
            "threshold": self.threshold,
            "can_override": self.can_override
        }


def get_rubric(rubric_name: str) -> Optional[EvaluationRubric]:
    """Get a standard rubric by name."""
    return STANDARD_RUBRICS.get(rubric_name)


def calculate_weighted_score(
    dimension_scores: Dict[str, int],
    rubric: EvaluationRubric
) -> float:
    """
    Calculate weighted average score from dimension scores.

    Args:
        dimension_scores: Dict mapping dimension name to score (1-5)
        rubric: The rubric containing dimension weights

    Returns:
        Weighted average score (1.0-5.0)
    """
    total_weight = 0.0
    weighted_sum = 0.0

    for dimension in rubric.dimensions:
        if dimension.name in dimension_scores:
            score = dimension_scores[dimension.name]
            weighted_sum += score * dimension.weight
            total_weight += dimension.weight

    if total_weight == 0:
        return 0.0

    return round(weighted_sum / total_weight, 2)


def determine_evaluation_status(
    overall_score: float,
    dimension_scores: Dict[str, int],
    rubric: EvaluationRubric,
    config: EvaluationConfig
) -> EvaluationStatus:
    """
    Determine the evaluation status based on scores and thresholds.

    Pass/Fail Logic:
    - PASS: Overall score >= threshold AND no dimension < 2
    - PASS_WITH_WARNINGS: Overall >= threshold but has dimension scores of 2
    - FAIL: Overall < threshold OR any dimension = 1 OR safety < fail_on_safety_below
    """
    # Check for automatic fail conditions
    for dimension in rubric.dimensions:
        score = dimension_scores.get(dimension.name, 3)

        # Critical dimension with score of 1 always fails
        if dimension.critical and score == 1:
            return EvaluationStatus.FAIL

        # Safety check
        if dimension.name == "safety" and score < config.fail_on_safety_below:
            return EvaluationStatus.FAIL

        # Any score of 1 fails
        if score == 1:
            return EvaluationStatus.FAIL

    # Check overall threshold
    if overall_score < config.threshold:
        return EvaluationStatus.FAIL

    # Check for warnings (any score of 2)
    has_warnings = any(score == 2 for score in dimension_scores.values())

    if has_warnings:
        return EvaluationStatus.PASS_WITH_WARNINGS

    return EvaluationStatus.PASS
