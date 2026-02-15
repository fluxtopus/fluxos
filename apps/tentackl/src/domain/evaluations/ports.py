"""Domain ports for prompt evaluation operations."""

from __future__ import annotations

from typing import Protocol

from src.evaluation.rubrics import EvaluationConfig, EvaluationResult


class PromptEvaluationOperationsPort(Protocol):
    """Port for evaluating prompts and agent specs."""

    async def evaluate_prompt(
        self,
        prompt: str,
        config: EvaluationConfig,
    ) -> EvaluationResult:
        ...

    async def evaluate_agent_spec_prompt(
        self,
        yaml_content: str,
        config: EvaluationConfig,
    ) -> EvaluationResult:
        ...

