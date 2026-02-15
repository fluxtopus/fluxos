# REVIEW: Prompt text and evaluation metadata are stored verbatim without size
# REVIEW: limits or redaction; consider constraints or masking for sensitive data.
"""SQLAlchemy models for prompt evaluation."""

import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Text, JSON, Integer, Index,
    Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import UUID

from src.interfaces.database import Base


class PromptEvaluationType(str, enum.Enum):
    """Types of prompts that can be evaluated."""
    SYSTEM_PROMPT = "system_prompt"
    AGENT_PROMPT = "agent_prompt"
    WORKFLOW_PROMPT = "workflow_prompt"
    GENERAL = "general"


class PromptEvaluationResult(str, enum.Enum):
    """Evaluation result status."""
    PASS = "pass"
    PASS_WITH_WARNINGS = "pass_with_warnings"
    FAIL = "fail"


class PromptEvaluation(Base):
    """
    Stores LLM-as-judge evaluation results for prompts.

    This is used as a CI/CD quality gate before publishing agent versions.
    Evaluations assess prompts across multiple dimensions:
    clarity, specificity, safety, output_format, context, and constraints.
    """
    __tablename__ = "prompt_evaluations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_text = Column(Text, nullable=False)
    prompt_type = Column(
        SQLEnum(PromptEvaluationType, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    prompt_path = Column(String(255), nullable=True)

    # References (nullable - evaluation can be standalone or linked)
    task_id = Column(UUID(as_uuid=True), nullable=True)
    agent_spec_id = Column(UUID(as_uuid=True), nullable=True)

    # Evaluation results
    evaluation_result = Column(
        SQLEnum(PromptEvaluationResult, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    overall_score = Column(Integer, nullable=False)  # Stored as integer (score * 100)
    dimension_scores = Column(JSON, nullable=False)
    justification = Column(Text, nullable=True)
    improvement_suggestions = Column(JSON, nullable=True)

    # Configuration used
    threshold = Column(Integer, nullable=False)  # Stored as integer (threshold * 100)
    model_used = Column(String(100), nullable=True)

    # Override tracking
    override_by = Column(String(255), nullable=True)
    override_reason = Column(Text, nullable=True)
    overridden_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("idx_prompt_eval_task", "task_id"),
        Index("idx_prompt_eval_agent_spec", "agent_spec_id"),
        Index("idx_prompt_eval_result", "evaluation_result"),
        Index("idx_prompt_eval_type", "prompt_type"),
        Index("idx_prompt_eval_created", "created_at"),
        Index("idx_prompt_eval_score", "overall_score"),
    )

    @property
    def score_float(self) -> float:
        """Get overall_score as a float (1.0-5.0)."""
        return self.overall_score / 100.0

    @property
    def threshold_float(self) -> float:
        """Get threshold as a float."""
        return self.threshold / 100.0

    @property
    def passed(self) -> bool:
        """Check if the evaluation passed."""
        return self.evaluation_result in (
            PromptEvaluationResult.PASS,
            PromptEvaluationResult.PASS_WITH_WARNINGS
        )
