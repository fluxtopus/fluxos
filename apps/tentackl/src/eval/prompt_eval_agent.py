"""
PromptEvalAgent - Tests prompts against targeted test cases.

This agent evaluates prompt effectiveness by:
1. Running LLM with prompt + test case input
2. Validating output format (template syntax, JSON schema)
3. Checking content patterns (contains, regex, not_contains)
4. Returning detailed pass/fail results
"""

import re
import time
from typing import Any, Dict, List, Optional, Tuple

import structlog

from src.eval.format_validators import FormatValidator, TemplateSyntaxValidator
from src.eval.models import (
    EvalTestResult,
    FormatRequirements,
    OutputPattern,
    PromptEvalResult,
    TestCase,
    get_template_syntax_rules,
)
from src.interfaces.llm import LLMMessage
from src.llm.openrouter_client import OpenRouterClient

logger = structlog.get_logger(__name__)


class PromptEvalAgent:
    """
    Tests a prompt against targeted test cases.

    Unlike the existing PromptEvaluationService which evaluates prompt quality
    (clarity, specificity, etc.), this agent tests the prompt's EFFECTIVENESS
    at producing correct outputs for specific tasks.
    """

    def __init__(
        self,
        llm_client: Optional[OpenRouterClient] = None,
        default_model: str = "x-ai/grok-2-1212",
        default_temperature: float = 0.3,
    ):
        """
        Initialize the eval agent.

        Args:
            llm_client: Optional LLM client. Created if not provided.
            default_model: Default model for generating test outputs.
            default_temperature: Default temperature for LLM calls.
        """
        self.llm_client = llm_client or OpenRouterClient()
        self.default_model = default_model
        self.default_temperature = default_temperature
        self.format_validator = FormatValidator()

    async def evaluate(
        self,
        prompt_text: str,
        test_cases: List[TestCase],
        llm_model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> PromptEvalResult:
        """
        Run the prompt against all test cases and return aggregated results.

        Args:
            prompt_text: The prompt to evaluate
            test_cases: Test cases to run
            llm_model: Model to use (defaults to default_model)
            temperature: Temperature to use (defaults to default_temperature)

        Returns:
            PromptEvalResult with pass/fail per test case and analysis
        """
        model = llm_model or self.default_model
        temp = temperature if temperature is not None else self.default_temperature

        start_time = time.time()
        test_results: List[EvalTestResult] = []

        # Sort by priority (higher first)
        sorted_cases = sorted(test_cases, key=lambda tc: tc.priority, reverse=True)

        for test_case in sorted_cases:
            try:
                result = await self.evaluate_single(prompt_text, test_case, model, temp)
                test_results.append(result)
            except Exception as e:
                logger.error(
                    "test_case_evaluation_failed",
                    test_case_id=test_case.id,
                    error=str(e),
                )
                test_results.append(
                    EvalTestResult(
                        test_case_id=test_case.id,
                        test_case_name=test_case.name,
                        passed=False,
                        content_score=0.0,
                        format_score=0.0,
                        pattern_matches={},
                        format_violations=[f"Evaluation error: {str(e)}"],
                        raw_output="",
                        error=str(e),
                    )
                )

        # Aggregate results
        tests_passed = sum(1 for r in test_results if r.passed)
        tests_failed = len(test_results) - tests_passed
        total_tests = len(test_results)

        content_scores = [r.content_score for r in test_results]
        format_scores = [r.format_score for r in test_results]

        avg_content_score = sum(content_scores) / len(content_scores) if content_scores else 0.0
        avg_format_score = sum(format_scores) / len(format_scores) if format_scores else 0.0
        overall_score = (avg_content_score * 0.6) + (avg_format_score * 0.4)

        # Pass threshold: 90% of tests must pass
        passed = (tests_passed / total_tests) >= 0.9 if total_tests > 0 else True

        execution_time_ms = int((time.time() - start_time) * 1000)

        return PromptEvalResult(
            passed=passed,
            overall_score=overall_score,
            content_score=avg_content_score,
            format_score=avg_format_score,
            test_results=test_results,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            total_tests=total_tests,
            execution_time_ms=execution_time_ms,
        )

    async def evaluate_single(
        self,
        prompt_text: str,
        test_case: TestCase,
        llm_model: str,
        temperature: float = 0.3,
    ) -> EvalTestResult:
        """
        Run a single test case.

        Args:
            prompt_text: The prompt to evaluate
            test_case: Test case to run
            llm_model: Model to use
            temperature: Temperature for LLM

        Returns:
            EvalTestResult with detailed results
        """
        start_time = time.time()

        # Build user message from test case input context
        user_message = self._build_user_message(test_case)

        # Call LLM with the prompt
        raw_output = await self._call_llm(
            prompt_text=prompt_text,
            user_message=user_message,
            model=llm_model,
            temperature=temperature,
        )

        # Validate format
        format_score, format_violations = self.validate_format(
            raw_output, test_case.format_requirements
        )

        # Match patterns
        content_score, pattern_matches = self.match_patterns(
            raw_output, test_case.expected_output_patterns
        )

        # Determine pass/fail
        # Pass requires: content_score >= 0.8 AND format_score >= 0.9 AND no critical violations
        critical_violations = [v for v in format_violations if "error" in v.lower() or "invalid" in v.lower()]
        passed = content_score >= 0.8 and format_score >= 0.9 and len(critical_violations) == 0

        execution_time_ms = int((time.time() - start_time) * 1000)

        return EvalTestResult(
            test_case_id=test_case.id,
            test_case_name=test_case.name,
            passed=passed,
            content_score=content_score,
            format_score=format_score,
            pattern_matches=pattern_matches,
            format_violations=format_violations,
            raw_output=raw_output,
            execution_time_ms=execution_time_ms,
        )

    def validate_format(
        self,
        output: str,
        requirements: FormatRequirements,
    ) -> Tuple[float, List[str]]:
        """
        Validate output format against requirements.

        Args:
            output: The LLM output to validate
            requirements: Format requirements to check

        Returns:
            Tuple of (format_score, list of violations)
        """
        return self.format_validator.validate(output, requirements)

    def match_patterns(
        self,
        output: str,
        patterns: List[OutputPattern],
    ) -> Tuple[float, Dict[str, bool]]:
        """
        Check which patterns are present in the output.

        Args:
            output: The LLM output to check
            patterns: List of OutputPattern to match

        Returns:
            Tuple of (content_score, pattern_matches dict)
        """
        if not patterns:
            return 1.0, {}

        pattern_matches: Dict[str, bool] = {}
        total_weight = 0.0
        matched_weight = 0.0

        for pattern in patterns:
            matched = self._check_pattern(output, pattern)
            pattern_matches[pattern.pattern] = matched
            total_weight += pattern.weight

            if pattern.pattern_type == "not_contains":
                # For not_contains, matched=True means pattern WAS found (violation)
                if not matched:
                    matched_weight += pattern.weight
            else:
                # For other types, matched=True means success
                if matched:
                    matched_weight += pattern.weight

        content_score = matched_weight / total_weight if total_weight > 0 else 1.0
        return content_score, pattern_matches

    def _check_pattern(self, output: str, pattern: OutputPattern) -> bool:
        """
        Check if a single pattern matches the output.

        Args:
            output: The LLM output to check
            pattern: Pattern to match

        Returns:
            True if pattern matches, False otherwise
        """
        if pattern.pattern_type == "contains":
            return pattern.pattern in output

        elif pattern.pattern_type == "not_contains":
            return pattern.pattern in output  # True = violation found

        elif pattern.pattern_type == "regex":
            try:
                return bool(re.search(pattern.pattern, output))
            except re.error as e:
                logger.warning("invalid_regex_pattern", pattern=pattern.pattern, error=str(e))
                return False

        elif pattern.pattern_type == "json_path":
            # JSON path matching (simplified)
            return self._check_json_path(output, pattern.pattern)

        elif pattern.pattern_type == "custom_validator":
            return self._run_custom_validator(output, pattern.validator)

        return False

    def _check_json_path(self, output: str, json_path: str) -> bool:
        """
        Check if a JSON path exists in the output.

        Simplified JSON path checking (e.g., $.steps, $.analysis).
        """
        import json

        try:
            # Try to parse JSON from output
            data = None
            try:
                data = json.loads(output)
            except json.JSONDecodeError:
                # Try extracting from code block
                json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", output, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group(1))

            if data is None:
                return False

            # Parse simple JSON path (e.g., $.steps or $.analysis.findings)
            if json_path.startswith("$."):
                path_parts = json_path[2:].split(".")
                current = data
                for part in path_parts:
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                    else:
                        return False
                return True

            return False

        except Exception:
            return False

    def _run_custom_validator(self, output: str, validator_name: Optional[str]) -> bool:
        """
        Run a custom validator by name.

        Args:
            output: The LLM output to validate
            validator_name: Name of the validator to run

        Returns:
            True if validation passes
        """
        if validator_name == "dependencies_match_references":
            validator = TemplateSyntaxValidator()
            violations = validator.validate_dependencies(output)
            return len(violations) == 0

        logger.warning("unknown_custom_validator", validator=validator_name)
        return True  # Unknown validators pass by default

    def _build_user_message(self, test_case: TestCase) -> str:
        """
        Build the user message from test case input context.

        Args:
            test_case: Test case with input context

        Returns:
            User message string
        """
        context = test_case.input_context

        # Check for common input patterns
        if "goal" in context:
            return f"Generate a plan for: {context['goal']}"
        elif "task" in context:
            return f"Task: {context['task']}"
        elif "prompt" in context:
            return context["prompt"]
        elif "input" in context:
            return str(context["input"])
        else:
            # Default: JSON dump of context
            import json
            return json.dumps(context)

    async def _call_llm(
        self,
        prompt_text: str,
        user_message: str,
        model: str,
        temperature: float,
    ) -> str:
        """
        Call the LLM with the prompt and user message.

        Args:
            prompt_text: System prompt to use
            user_message: User message to send
            model: Model to use
            temperature: Temperature for generation

        Returns:
            LLM response content
        """
        messages = [
            LLMMessage(role="system", content=prompt_text),
            LLMMessage(role="user", content=user_message),
        ]

        try:
            client = self.llm_client

            # If the client supports async context manager (needs HTTP init),
            # initialize it. Mocks and pre-initialized clients skip this.
            if hasattr(client, "__aenter__") and isinstance(client, OpenRouterClient):
                async with client:
                    response = await client.create_completion(
                        messages=messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=4000,
                    )
                    return response.content
            else:
                response = await client.create_completion(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=4000,
                )
                return response.content
        except Exception as e:
            logger.error("llm_call_failed", model=model, error=str(e))
            raise


async def evaluate_prompt(
    prompt_text: str,
    test_cases: List[TestCase],
    model: str = "x-ai/grok-2-1212",
) -> PromptEvalResult:
    """
    Convenience function to evaluate a prompt.

    Args:
        prompt_text: The prompt to evaluate
        test_cases: Test cases to run
        model: Model to use

    Returns:
        PromptEvalResult with results
    """
    agent = PromptEvalAgent()
    return await agent.evaluate(prompt_text, test_cases, llm_model=model)
