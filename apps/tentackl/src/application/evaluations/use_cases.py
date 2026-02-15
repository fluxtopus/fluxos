"""Application use cases for prompt evaluation flows."""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.evaluations import PromptEvaluationOperationsPort
from src.evaluation.rubrics import EvaluationConfig, EvaluationResult, PromptType


DEFAULT_EVALUATION_MODEL = "google/gemini-2.5-flash-preview"


@dataclass
class PromptEvaluationUseCases:
    """Application-layer orchestration for prompt evaluation."""

    evaluation_ops: PromptEvaluationOperationsPort

    async def evaluate_prompt(
        self,
        prompt: str,
        prompt_type: PromptType,
        threshold: float,
        model: str | None = None,
    ) -> EvaluationResult:
        config = EvaluationConfig(
            threshold=threshold,
            prompt_type=prompt_type,
            model=model or DEFAULT_EVALUATION_MODEL,
        )
        return await self.evaluation_ops.evaluate_prompt(prompt=prompt, config=config)

    async def evaluate_agent_spec_prompt(
        self,
        yaml_content: str,
        threshold: float,
        model: str | None = None,
    ) -> EvaluationResult:
        config = EvaluationConfig(
            threshold=threshold,
            prompt_type=PromptType.AGENT_PROMPT,
            model=model or DEFAULT_EVALUATION_MODEL,
        )
        return await self.evaluation_ops.evaluate_agent_spec_prompt(
            yaml_content=yaml_content,
            config=config,
        )

