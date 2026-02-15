"""Infrastructure adapter for prompt evaluation operations."""

from __future__ import annotations

from src.domain.evaluations import PromptEvaluationOperationsPort
from src.evaluation.rubrics import EvaluationConfig, EvaluationResult
from src.infrastructure.evaluations.prompt_evaluation_service import PromptEvaluationService


class PromptEvaluationServiceAdapter(PromptEvaluationOperationsPort):
    """Adapter exposing PromptEvaluationService through the domain port."""

    async def evaluate_prompt(
        self,
        prompt: str,
        config: EvaluationConfig,
    ) -> EvaluationResult:
        async with PromptEvaluationService() as eval_service:
            return await eval_service.evaluate_prompt(
                prompt=prompt,
                config=config,
            )

    async def evaluate_agent_spec_prompt(
        self,
        yaml_content: str,
        config: EvaluationConfig,
    ) -> EvaluationResult:
        async with PromptEvaluationService() as eval_service:
            return await eval_service.evaluate_agent_spec_prompt(
                yaml_content=yaml_content,
                config=config,
            )
