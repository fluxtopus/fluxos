"""
Prompt Evaluation and Optimization System.

This module provides tools for testing prompts against targeted tasks,
verifying content and format of outputs, and iteratively optimizing
prompts until they achieve their goals.

Components:
- PromptEvalAgent: Tests prompts against test cases
- PromptOptimizerAgent: Improves prompts based on failures
- OptimizationLoopController: Self-reinforcing optimization loop
- TemplateSyntaxValidator: Validates template syntax in outputs
"""

from src.eval.models import (
    AGENT_OUTPUT_FIELDS,
    EvalTestResult,
    FormatRequirements,
    OptimizationAttempt,
    OptimizationConfig,
    OptimizationContext,
    OptimizationResult,
    OutputPattern,
    PromptEvalResult,
    PromptImprovement,
    SpecificFix,
    TemplateSyntaxRule,
    TestCase,
    ValidationResult,
    Violation,
    get_template_syntax_rules,
)

__all__ = [
    # Models
    "AGENT_OUTPUT_FIELDS",
    "EvalTestResult",
    "FormatRequirements",
    "OptimizationAttempt",
    "OptimizationConfig",
    "OptimizationContext",
    "OptimizationResult",
    "OutputPattern",
    "PromptEvalResult",
    "PromptImprovement",
    "SpecificFix",
    "TemplateSyntaxRule",
    "TestCase",
    "ValidationResult",
    "Violation",
    "get_template_syntax_rules",
]
