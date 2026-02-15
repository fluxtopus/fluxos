"""
OptimizationLoopController - Orchestrates the eval-optimize-repeat loop.

The self-reinforcing pattern:
1. Run eval with test cases
2. If all pass, done
3. If failures, run optimizer
4. Re-eval the improved prompt
5. If better, continue; if worse, rollback
6. Repeat until pass or max iterations
"""

import time
from datetime import datetime
from typing import List, Optional

import structlog

from src.eval.models import (
    OptimizationAttempt,
    OptimizationConfig,
    OptimizationContext,
    OptimizationResult,
    PromptEvalResult,
    TestCase,
)
from src.eval.prompt_eval_agent import PromptEvalAgent
from src.eval.prompt_optimizer_agent import PromptOptimizerAgent

logger = structlog.get_logger(__name__)


class OptimizationLoopController:
    """
    Orchestrates the eval -> optimize -> repeat loop.

    The self-reinforcing pattern:
    1. Run eval with test cases
    2. If all pass, done
    3. If failures, run optimizer
    4. Re-eval the improved prompt
    5. If better, continue; if worse, rollback
    6. Repeat until pass or max iterations
    """

    def __init__(
        self,
        config: Optional[OptimizationConfig] = None,
        eval_agent: Optional[PromptEvalAgent] = None,
        optimizer_agent: Optional[PromptOptimizerAgent] = None,
    ):
        """
        Initialize the optimization loop controller.

        Args:
            config: Configuration for the optimization loop
            eval_agent: PromptEvalAgent instance (created if not provided)
            optimizer_agent: PromptOptimizerAgent instance (created if not provided)
        """
        self.config = config or OptimizationConfig()
        self.eval_agent = eval_agent or PromptEvalAgent(
            default_model=self.config.eval_model,
            default_temperature=self.config.eval_temperature,
        )
        self.optimizer_agent = optimizer_agent or PromptOptimizerAgent(
            llm_model=self.config.optimizer_model,
            temperature=self.config.optimizer_temperature,
        )

    async def run(
        self,
        prompt_text: str,
        test_cases: List[TestCase],
        prompt_type: str = "general",
    ) -> OptimizationResult:
        """
        Run the full optimization loop.

        Args:
            prompt_text: The prompt to optimize
            test_cases: Test cases to evaluate against
            prompt_type: Type of prompt (for logging)

        Returns:
            OptimizationResult with final prompt and history
        """
        start_time = time.time()

        current_prompt = prompt_text
        history: List[OptimizationAttempt] = []
        best_prompt = prompt_text
        best_score = 0.0
        best_eval: Optional[PromptEvalResult] = None

        logger.info(
            "optimization_loop_started",
            prompt_type=prompt_type,
            max_iterations=self.config.max_iterations,
            num_test_cases=len(test_cases),
        )

        for iteration in range(self.config.max_iterations):
            logger.info("optimization_iteration_started", iteration=iteration + 1)

            # EVAL PHASE
            eval_result = await self.eval_agent.evaluate(
                current_prompt,
                test_cases,
                llm_model=self.config.eval_model,
            )

            score = self._calculate_score(eval_result)

            # Track history
            attempt = OptimizationAttempt(
                iteration=iteration,
                prompt_version=current_prompt,
                changes_made=[] if iteration == 0 else ["Optimization applied"],
                eval_result=eval_result,
                timestamp=datetime.utcnow(),
                notes="",
            )
            history.append(attempt)

            logger.info(
                "eval_completed",
                iteration=iteration + 1,
                passed=eval_result.passed,
                score=score,
                tests_passed=eval_result.tests_passed,
                tests_failed=eval_result.tests_failed,
            )

            # Track best
            if score > best_score:
                best_score = score
                best_prompt = current_prompt
                best_eval = eval_result

            # EARLY EXIT: Perfect score or passes threshold
            if self._meets_thresholds(eval_result):
                logger.info(
                    "optimization_succeeded",
                    iterations=iteration + 1,
                    final_score=score,
                )
                return OptimizationResult(
                    success=True,
                    original_prompt=prompt_text,
                    final_prompt=current_prompt,
                    best_prompt=best_prompt,
                    iterations=iteration + 1,
                    history=history,
                    final_eval=eval_result,
                    original_score=history[0].eval_result.overall_score if history else 0.0,
                    final_score=score,
                    improvement_summary=self._generate_summary(history),
                    execution_time_ms=int((time.time() - start_time) * 1000),
                )

            # Last iteration - don't optimize, just return best
            if iteration == self.config.max_iterations - 1:
                break

            # ANALYZE FAILURES
            failed_tests = [tc for tc in test_cases if not eval_result.get_test_passed(tc.id)]
            failure_analysis = self._analyze_failures(eval_result, failed_tests)

            # OPTIMIZE PHASE
            context = OptimizationContext(
                original_prompt=prompt_text,
                current_prompt=current_prompt,
                eval_results=eval_result,
                failed_test_cases=failed_tests,
                failure_analysis=failure_analysis,
                iteration=iteration,
                previous_attempts=history,
            )

            improvement = await self.optimizer_agent.optimize(context)

            logger.info(
                "optimization_applied",
                iteration=iteration + 1,
                confidence=improvement.confidence_score,
                num_fixes=len(improvement.specific_fixes),
            )

            # ROLLBACK CHECK
            if self.config.enable_rollback and iteration > 0:
                # Quick eval of improved prompt
                new_eval = await self.eval_agent.evaluate(
                    improvement.improved_prompt,
                    test_cases,
                    llm_model=self.config.eval_model,
                )
                new_score = self._calculate_score(new_eval)

                if new_score < score * 0.9:  # More than 10% worse
                    logger.warning(
                        "rollback_triggered",
                        old_score=score,
                        new_score=new_score,
                    )
                    history[-1].notes = f"Rollback: score dropped from {score:.2f} to {new_score:.2f}"

                    # Try a different approach by adding constraints
                    context.constraints = {"previous_approach_failed": True}
                    improvement = await self.optimizer_agent.optimize(context)

            current_prompt = improvement.improved_prompt
            history[-1].changes_made = improvement.changes_explanation

        # Max iterations reached
        logger.info(
            "optimization_max_iterations",
            iterations=self.config.max_iterations,
            best_score=best_score,
        )

        return OptimizationResult(
            success=False,
            original_prompt=prompt_text,
            final_prompt=best_prompt,
            best_prompt=best_prompt,
            iterations=self.config.max_iterations,
            history=history,
            final_eval=best_eval or history[-1].eval_result,
            original_score=history[0].eval_result.overall_score if history else 0.0,
            final_score=best_score,
            improvement_summary=self._generate_summary(history),
            execution_time_ms=int((time.time() - start_time) * 1000),
        )

    def _calculate_score(self, eval_result: PromptEvalResult) -> float:
        """
        Calculate composite score from eval result.

        Args:
            eval_result: Evaluation result

        Returns:
            Composite score (0-1)
        """
        content_weight = 0.6
        format_weight = 0.4
        return (eval_result.content_score * content_weight) + (eval_result.format_score * format_weight)

    def _meets_thresholds(self, eval_result: PromptEvalResult) -> bool:
        """
        Check if eval result meets pass thresholds.

        Args:
            eval_result: Evaluation result

        Returns:
            True if thresholds are met
        """
        # Check pass rate
        pass_rate = eval_result.tests_passed / eval_result.total_tests if eval_result.total_tests > 0 else 0
        if pass_rate < self.config.pass_threshold:
            return False

        # Check format score
        if eval_result.format_score < self.config.format_threshold:
            return False

        return True

    def _analyze_failures(
        self,
        eval_result: PromptEvalResult,
        failed_tests: List[TestCase],
    ) -> str:
        """
        Analyze failures and generate a summary.

        Args:
            eval_result: Evaluation result
            failed_tests: List of failed test cases

        Returns:
            Analysis summary string
        """
        analysis_parts = []

        # Group violations by type
        violation_counts: dict = {}
        for result in eval_result.test_results:
            if not result.passed:
                for violation in result.format_violations:
                    # Extract key part of violation message
                    key = violation[:50] if len(violation) > 50 else violation
                    violation_counts[key] = violation_counts.get(key, 0) + 1

        if violation_counts:
            analysis_parts.append("**Common violations:**")
            for violation, count in sorted(violation_counts.items(), key=lambda x: -x[1]):
                analysis_parts.append(f"  - ({count}x) {violation}")

        # Check for specific patterns
        template_issues = 0
        dependency_issues = 0
        field_name_issues = 0

        for result in eval_result.test_results:
            for violation in result.format_violations:
                if "{{step_" in violation and ".output" in violation:
                    template_issues += 1
                if "dependencies" in violation.lower():
                    dependency_issues += 1
                if "typically uses outputs" in violation:
                    field_name_issues += 1

        if template_issues > 0:
            analysis_parts.append(f"\n**Template syntax errors: {template_issues}**")
            analysis_parts.append("The LLM is using incorrect template syntax like `{{step_X.output}}` instead of `{{step_X.outputs.field}}`.")

        if dependency_issues > 0:
            analysis_parts.append(f"\n**Dependency declaration errors: {dependency_issues}**")
            analysis_parts.append("Steps referencing other steps' outputs are not listing them in dependencies.")

        if field_name_issues > 0:
            analysis_parts.append(f"\n**Output field name errors: {field_name_issues}**")
            analysis_parts.append("The LLM is using incorrect output field names for specific agent types.")

        # Summary stats
        analysis_parts.append(f"\n**Summary:**")
        analysis_parts.append(f"  - Tests passed: {eval_result.tests_passed}/{eval_result.total_tests}")
        analysis_parts.append(f"  - Content score: {eval_result.content_score:.2f}")
        analysis_parts.append(f"  - Format score: {eval_result.format_score:.2f}")

        return "\n".join(analysis_parts)

    def _generate_summary(self, history: List[OptimizationAttempt]) -> str:
        """
        Generate a summary of the optimization process.

        Args:
            history: List of optimization attempts

        Returns:
            Summary string
        """
        if not history:
            return "No optimization history"

        initial_score = history[0].eval_result.overall_score
        final_score = history[-1].eval_result.overall_score
        improvement = final_score - initial_score

        summary_parts = [
            f"Optimization completed in {len(history)} iteration(s).",
            f"Initial score: {initial_score:.2f}",
            f"Final score: {final_score:.2f}",
            f"Improvement: {improvement:+.2f}",
        ]

        if history[-1].eval_result.passed:
            summary_parts.append("Result: PASSED")
        else:
            summary_parts.append("Result: DID NOT PASS (returned best result)")

        return " ".join(summary_parts)


async def optimize_prompt_with_tests(
    prompt_text: str,
    test_cases: List[TestCase],
    config: Optional[OptimizationConfig] = None,
) -> OptimizationResult:
    """
    Convenience function to run the optimization loop.

    Args:
        prompt_text: The prompt to optimize
        test_cases: Test cases to evaluate against
        config: Optional configuration

    Returns:
        OptimizationResult with results
    """
    controller = OptimizationLoopController(config=config)
    return await controller.run(prompt_text, test_cases)
