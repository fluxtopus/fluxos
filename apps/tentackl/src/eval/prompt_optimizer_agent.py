"""
PromptOptimizerAgent - Improves prompts based on evaluation failures.

Uses LLM-as-optimizer pattern: given the original prompt and failure
analysis, generates an improved version that addresses specific issues.
"""

import json
import re
from typing import List, Optional

import structlog

from src.eval.models import (
    OptimizationContext,
    PromptImprovement,
    SpecificFix,
    TestCase,
)
from src.interfaces.llm import LLMMessage
from src.llm.openrouter_client import OpenRouterClient

logger = structlog.get_logger(__name__)


OPTIMIZER_SYSTEM_PROMPT = """You are an expert prompt engineer. Your task is to improve a prompt based on test failures.

## Context
You will receive:
1. The original prompt that needs improvement
2. Test cases that failed with specific violations
3. Previous optimization attempts (if any)

## Your Task
Analyze the failures and generate an improved prompt that:
1. Addresses EVERY specific failure pattern
2. Preserves all working parts of the original prompt
3. Makes the rules clearer and more explicit
4. Adds examples that demonstrate the correct behavior

## Output Format
You MUST respond with valid JSON in this exact format:
```json
{
  "improved_prompt": "The full improved prompt text...",
  "changes_explanation": [
    "Added explicit rule about X",
    "Clarified the Y section",
    "Added example showing correct Z usage"
  ],
  "confidence_score": 0.85,
  "specific_fixes": [
    {
      "issue": "Description of the issue",
      "before_snippet": "The problematic text",
      "after_snippet": "The fixed text",
      "test_cases_addressed": ["test_case_id_1"]
    }
  ]
}
```

## Critical Rules
1. The improved_prompt must be the COMPLETE prompt, not just the changes
2. Do NOT remove working sections - only add/modify what's broken
3. Be very explicit about format requirements
4. Add concrete examples for every rule that failed
5. Use bold/caps for critical rules that were ignored
6. confidence_score should be 0-1 based on how confident you are the fixes will work
"""


class PromptOptimizerAgent:
    """
    Improves prompts based on evaluation failures.

    Uses LLM-as-optimizer pattern: given the original prompt and failure
    analysis, generates an improved version that addresses specific issues.
    """

    def __init__(
        self,
        llm_client: Optional[OpenRouterClient] = None,
        llm_model: str = "anthropic/claude-sonnet-4",
        temperature: float = 0.5,
    ):
        """
        Initialize the optimizer agent.

        Args:
            llm_client: Optional LLM client. Created if not provided.
            llm_model: Model to use for optimization (stronger model recommended).
            temperature: Temperature for generation.
        """
        self.llm_client = llm_client or OpenRouterClient()
        self.llm_model = llm_model
        self.temperature = temperature

    async def optimize(
        self,
        context: OptimizationContext,
    ) -> PromptImprovement:
        """
        Generate an improved prompt based on failure analysis.

        The optimizer:
        1. Analyzes why each test case failed
        2. Identifies patterns in the failures
        3. Generates specific fixes
        4. Creates an improved prompt version

        Args:
            context: OptimizationContext with all relevant information

        Returns:
            PromptImprovement with the improved prompt and explanation
        """
        # Build the optimization prompt
        optimization_prompt = self._build_optimization_prompt(context)

        # Call LLM to get improvement suggestions
        messages = [
            LLMMessage(role="system", content=OPTIMIZER_SYSTEM_PROMPT),
            LLMMessage(role="user", content=optimization_prompt),
        ]

        try:
            # Use async context manager to initialize the HTTP client
            async with OpenRouterClient() as client:
                response = await client.create_completion(
                    messages=messages,
                    model=self.llm_model,
                    temperature=self.temperature,
                    max_tokens=8000,  # Need more tokens for full prompt
                )

                # Parse the response
                return self._parse_response(response.content, context.current_prompt)

        except Exception as e:
            logger.error("optimization_failed", error=str(e))
            # Return minimal improvement on error
            return PromptImprovement(
                improved_prompt=context.current_prompt,
                changes_explanation=[f"Optimization failed: {str(e)}"],
                confidence_score=0.0,
                specific_fixes=[],
            )

    def _build_optimization_prompt(self, context: OptimizationContext) -> str:
        """
        Build the prompt for the optimizer LLM.

        Args:
            context: OptimizationContext with all information

        Returns:
            The prompt string for the optimizer
        """
        parts = []

        # Current iteration
        parts.append(f"## Optimization Iteration: {context.iteration + 1}")
        parts.append("")

        # Original prompt
        parts.append("## Original Prompt")
        parts.append("```")
        parts.append(context.current_prompt)
        parts.append("```")
        parts.append("")

        # Failure analysis
        parts.append("## Failure Analysis")
        parts.append(context.failure_analysis)
        parts.append("")

        # Failed test cases
        parts.append("## Failed Test Cases")
        for tc in context.failed_test_cases:
            parts.append(f"### Test: {tc.name} (ID: {tc.id})")
            parts.append(f"**Input:** {json.dumps(tc.input_context)}")
            parts.append("**Expected patterns:**")
            for pattern in tc.expected_output_patterns:
                parts.append(f"  - {pattern.pattern_type}: `{pattern.pattern}` ({pattern.description})")

            # Find the corresponding test result
            for result in context.eval_results.test_results:
                if result.test_case_id == tc.id:
                    parts.append(f"**Actual output (excerpt):**")
                    parts.append("```")
                    parts.append(result.raw_output[:1000] + "..." if len(result.raw_output) > 1000 else result.raw_output)
                    parts.append("```")
                    parts.append(f"**Format violations:** {result.format_violations}")
                    parts.append(f"**Pattern matches:** {result.pattern_matches}")
                    break
            parts.append("")

        # Previous attempts
        if context.previous_attempts:
            parts.append("## Previous Optimization Attempts")
            for attempt in context.previous_attempts[-3:]:  # Last 3 attempts
                parts.append(f"### Iteration {attempt.iteration}")
                parts.append(f"**Changes made:** {attempt.changes_made}")
                parts.append(f"**Result:** Score {attempt.eval_result.overall_score:.2f}")
                if attempt.notes:
                    parts.append(f"**Notes:** {attempt.notes}")
                parts.append("")

        # Constraints
        if context.constraints:
            parts.append("## Constraints")
            for key, value in context.constraints.items():
                parts.append(f"- {key}: {value}")
            parts.append("")

        # Specific guidance for common issues
        parts.append("## Specific Issues to Address")
        parts.append(self._identify_specific_issues(context))
        parts.append("")

        parts.append("## Your Task")
        parts.append("Generate an improved version of the prompt that addresses ALL the failures above.")
        parts.append("Remember: The improved_prompt in your response must be the COMPLETE prompt, not just patches.")

        return "\n".join(parts)

    def _identify_specific_issues(self, context: OptimizationContext) -> str:
        """
        Identify specific issues from the failures.

        Args:
            context: OptimizationContext

        Returns:
            String describing specific issues to fix
        """
        issues = []

        for result in context.eval_results.test_results:
            if not result.passed:
                # Check for template syntax issues
                for violation in result.format_violations:
                    if "{{step_" in violation and ".output" in violation:
                        issues.append(
                            "- **TEMPLATE SYNTAX ERROR**: The LLM is generating `{{step_X.output}}` "
                            "instead of `{{step_X.outputs.field}}`. Add VERY explicit rules with "
                            "examples showing the CORRECT syntax and WRONG syntax side by side."
                        )
                        break

                # Check for missing dependencies
                for violation in result.format_violations:
                    if "dependencies" in violation.lower():
                        issues.append(
                            "- **MISSING DEPENDENCIES**: Steps that reference other steps' outputs "
                            "are not declaring them in dependencies. Add explicit rule requiring "
                            "all step references to be listed in dependencies."
                        )
                        break

                # Check for wrong field names
                for violation in result.format_violations:
                    if "typically uses outputs" in violation:
                        issues.append(
                            "- **WRONG FIELD NAMES**: The LLM is using incorrect output field names "
                            "for specific agents. Add a reference table showing correct field names "
                            "for each agent type."
                        )
                        break

        if not issues:
            issues.append(
                "- General format/content issues. Review the pattern matches and violations "
                "to understand what's failing."
            )

        return "\n".join(issues)

    def _parse_response(self, response: str, fallback_prompt: str) -> PromptImprovement:
        """
        Parse the optimizer's response.

        Args:
            response: Raw LLM response
            fallback_prompt: Prompt to use if parsing fails

        Returns:
            PromptImprovement object
        """
        try:
            # Try to extract JSON from response
            json_data = self._extract_json(response)

            if json_data is None:
                raise ValueError("Could not extract JSON from response")

            # Parse specific fixes
            specific_fixes = []
            for fix_data in json_data.get("specific_fixes", []):
                specific_fixes.append(
                    SpecificFix(
                        issue=fix_data.get("issue", ""),
                        before_snippet=fix_data.get("before_snippet", ""),
                        after_snippet=fix_data.get("after_snippet", ""),
                        test_cases_addressed=fix_data.get("test_cases_addressed", []),
                    )
                )

            return PromptImprovement(
                improved_prompt=json_data.get("improved_prompt", fallback_prompt),
                changes_explanation=json_data.get("changes_explanation", []),
                confidence_score=float(json_data.get("confidence_score", 0.5)),
                specific_fixes=specific_fixes,
            )

        except Exception as e:
            logger.warning("response_parse_failed", error=str(e))
            # Try to extract just the prompt from the response
            improved = self._extract_prompt_from_text(response, fallback_prompt)
            return PromptImprovement(
                improved_prompt=improved,
                changes_explanation=["Parsed from unstructured response"],
                confidence_score=0.3,
                specific_fixes=[],
            )

    def _extract_json(self, text: str) -> Optional[dict]:
        """Extract JSON from text, handling markdown code blocks."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from code block
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding JSON object in text
        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            try:
                return json.loads(text[json_start:json_end])
            except json.JSONDecodeError:
                pass

        return None

    def _extract_prompt_from_text(self, text: str, fallback: str) -> str:
        """
        Try to extract an improved prompt from unstructured text.

        Args:
            text: Response text
            fallback: Fallback prompt if extraction fails

        Returns:
            Extracted prompt or fallback
        """
        # Look for "improved_prompt" mentions
        if '"improved_prompt"' in text:
            # Try to find the content after improved_prompt
            match = re.search(r'"improved_prompt"\s*:\s*"(.+?)"', text, re.DOTALL)
            if match:
                return match.group(1).replace("\\n", "\n").replace('\\"', '"')

        # Look for markdown code blocks that might contain the prompt
        code_blocks = re.findall(r"```(?:markdown)?\s*(.+?)```", text, re.DOTALL)
        for block in code_blocks:
            # If it looks like a system prompt (long, instructional)
            if len(block) > 500 and ("you are" in block.lower() or "your task" in block.lower()):
                return block.strip()

        return fallback


async def optimize_prompt(
    original_prompt: str,
    failed_test_cases: List[TestCase],
    failure_analysis: str,
) -> PromptImprovement:
    """
    Convenience function to optimize a prompt.

    Args:
        original_prompt: The prompt to optimize
        failed_test_cases: Test cases that failed
        failure_analysis: Analysis of why they failed

    Returns:
        PromptImprovement with the improved prompt
    """
    from src.eval.models import OptimizationContext, PromptEvalResult

    # Create minimal context
    context = OptimizationContext(
        original_prompt=original_prompt,
        current_prompt=original_prompt,
        eval_results=PromptEvalResult(
            passed=False,
            overall_score=0.0,
            content_score=0.0,
            format_score=0.0,
            test_results=[],
            tests_passed=0,
            tests_failed=len(failed_test_cases),
            total_tests=len(failed_test_cases),
        ),
        failed_test_cases=failed_test_cases,
        failure_analysis=failure_analysis,
        iteration=0,
        previous_attempts=[],
    )

    agent = PromptOptimizerAgent()
    return await agent.optimize(context)
