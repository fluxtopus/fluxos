"""
CLI for prompt evaluation and optimization.

Usage:
    # Evaluate a prompt file
    python -m src.eval.run_eval --prompt-file src/agents/prompts/task_planner_prompt.md

    # Evaluate with specific test cases
    python -m src.eval.run_eval --prompt-file X --test-cases tests/eval/task_planner_cases.yaml

    # Run optimization loop
    python -m src.eval.run_eval --prompt-file X --optimize --max-iterations 5

    # Validate template syntax only (quick mode)
    python -m src.eval.run_eval --validate-syntax --input "{{step_1.output}}"
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import List, Optional

from src.eval.format_validators import validate_template_syntax_quick
from src.eval.models import OptimizationConfig, TestCase
from src.eval.optimization_loop import OptimizationLoopController
from src.eval.prompt_eval_agent import PromptEvalAgent
from src.eval.test_case_library import get_library, get_task_planner_test_cases


def print_header(text: str) -> None:
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(f" {text}")
    print("=" * 60)


def print_result(label: str, value: str, color: Optional[str] = None) -> None:
    """Print a formatted result line."""
    colors = {
        "green": "\033[92m",
        "red": "\033[91m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "reset": "\033[0m",
    }
    if color and color in colors:
        print(f"  {label}: {colors[color]}{value}{colors['reset']}")
    else:
        print(f"  {label}: {value}")


async def evaluate_prompt(
    prompt_path: Path,
    test_cases_path: Optional[Path],
    prompt_type: str,
    tags: Optional[List[str]],
    model: str = "anthropic/claude-3-5-haiku-20241022",
) -> int:
    """
    Evaluate a prompt file against test cases.

    Returns exit code (0 = pass, 1 = fail).
    """
    print_header("Prompt Evaluation")

    # Load prompt
    prompt_text = prompt_path.read_text()
    print(f"  Loaded prompt: {prompt_path}")
    print(f"  Prompt length: {len(prompt_text)} chars")

    # Load test cases
    library = get_library()

    if test_cases_path:
        library.load_from_yaml(test_cases_path)
        print(f"  Loaded test cases from: {test_cases_path}")

    test_cases = library.get_for_prompt_type(prompt_type, tags=tags)
    if not test_cases:
        # Fallback to built-in task planner tests
        test_cases = get_task_planner_test_cases()
        print(f"  Using built-in test cases: {len(test_cases)}")
    else:
        print(f"  Test cases found: {len(test_cases)}")

    # Run evaluation
    print(f"  Model: {model}")
    print("\n  Running evaluation...")
    agent = PromptEvalAgent(default_model=model)
    result = await agent.evaluate(prompt_text, test_cases, llm_model=model)

    # Print results
    print_header("Results")
    print_result("Overall", "PASS" if result.passed else "FAIL", "green" if result.passed else "red")
    print_result("Overall Score", f"{result.overall_score:.2f}")
    print_result("Content Score", f"{result.content_score:.2f}")
    print_result("Format Score", f"{result.format_score:.2f}")
    print_result("Tests Passed", f"{result.tests_passed}/{result.total_tests}")
    print_result("Execution Time", f"{result.execution_time_ms}ms")

    # Print failed tests
    failed_tests = result.get_failed_tests()
    if failed_tests:
        print_header("Failed Tests")
        for test_result in failed_tests:
            print(f"\n  [{test_result.test_case_id}] {test_result.test_case_name}")
            print(f"    Content Score: {test_result.content_score:.2f}")
            print(f"    Format Score: {test_result.format_score:.2f}")
            if test_result.format_violations:
                print("    Violations:")
                for v in test_result.format_violations[:5]:  # Limit to 5
                    print(f"      - {v}")
            if test_result.error:
                print(f"    Error: {test_result.error}")

    return 0 if result.passed else 1


async def optimize_prompt(
    prompt_path: Path,
    test_cases_path: Optional[Path],
    prompt_type: str,
    tags: Optional[List[str]],
    max_iterations: int,
    output_file: Optional[Path],
    model: str = "openai/gpt-4o-mini",
) -> int:
    """
    Run optimization loop on a prompt file.

    Returns exit code (0 = success, 1 = fail).
    """
    print_header("Prompt Optimization")

    # Load prompt
    prompt_text = prompt_path.read_text()
    print(f"  Loaded prompt: {prompt_path}")
    print(f"  Prompt length: {len(prompt_text)} chars")

    # Load test cases
    library = get_library()

    if test_cases_path:
        library.load_from_yaml(test_cases_path)
        print(f"  Loaded test cases from: {test_cases_path}")

    test_cases = library.get_for_prompt_type(prompt_type, tags=tags)
    if not test_cases:
        test_cases = get_task_planner_test_cases()
        print(f"  Using built-in test cases: {len(test_cases)}")
    else:
        print(f"  Test cases found: {len(test_cases)}")

    # Configure optimization
    config = OptimizationConfig(
        max_iterations=max_iterations,
        pass_threshold=0.9,
        format_threshold=0.95,
        eval_model=model,
    )
    print(f"  Max iterations: {config.max_iterations}")
    print(f"  Pass threshold: {config.pass_threshold}")
    print(f"  Model: {config.eval_model}")

    # Run optimization
    print("\n  Starting optimization loop...")
    controller = OptimizationLoopController(config=config)
    result = await controller.run(prompt_text, test_cases, prompt_type)

    # Print results
    print_header("Optimization Results")
    print_result("Success", "YES" if result.success else "NO", "green" if result.success else "red")
    print_result("Iterations", str(result.iterations))
    print_result("Original Score", f"{result.original_score:.2f}")
    print_result("Final Score", f"{result.final_score:.2f}")
    print_result("Improvement", f"{result.final_score - result.original_score:+.2f}")
    print_result("Execution Time", f"{result.execution_time_ms}ms")

    print(f"\n  Summary: {result.improvement_summary}")

    # Print iteration history
    if result.history:
        print_header("Iteration History")
        for attempt in result.history:
            status = "PASS" if attempt.eval_result.passed else "FAIL"
            print(f"  Iteration {attempt.iteration + 1}: Score {attempt.eval_result.overall_score:.2f} ({status})")
            if attempt.changes_made:
                for change in attempt.changes_made[:3]:
                    print(f"    - {change}")
            if attempt.notes:
                print(f"    Note: {attempt.notes}")

    # Save optimized prompt if requested
    if output_file:
        output_file.write_text(result.final_prompt)
        print(f"\n  Optimized prompt saved to: {output_file}")

    return 0 if result.success else 1


def validate_syntax(input_text: str) -> int:
    """
    Quick validation of template syntax.

    Returns exit code (0 = valid, 1 = invalid).
    """
    print_header("Template Syntax Validation")

    valid, errors = validate_template_syntax_quick(input_text)

    print(f"  Input: {input_text}")
    print_result("Valid", "YES" if valid else "NO", "green" if valid else "red")

    if errors:
        print("  Errors:")
        for error in errors:
            print(f"    - {error}")

    return 0 if valid else 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Prompt evaluation and optimization CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--prompt-file",
        type=Path,
        help="Path to prompt file to evaluate/optimize",
    )
    parser.add_argument(
        "--test-cases",
        type=Path,
        help="Path to test cases YAML file",
    )
    parser.add_argument(
        "--prompt-type",
        default="task_planner",
        help="Type of prompt (default: task_planner)",
    )
    parser.add_argument(
        "--tags",
        nargs="*",
        help="Filter test cases by tags",
    )
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Run optimization loop instead of just evaluation",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=5,
        help="Maximum optimization iterations (default: 5)",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        help="Write optimized prompt to file",
    )
    parser.add_argument(
        "--validate-syntax",
        action="store_true",
        help="Quick syntax validation mode",
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Input text for syntax validation",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="openai/gpt-4o-mini",
        help="LLM model to use for evaluation (default: openai/gpt-4o-mini)",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.validate_syntax:
        if not args.input:
            parser.error("--input required when using --validate-syntax")
        return validate_syntax(args.input)

    if not args.prompt_file:
        parser.error("--prompt-file required")

    if not args.prompt_file.exists():
        print(f"Error: Prompt file not found: {args.prompt_file}")
        return 1

    if args.test_cases and not args.test_cases.exists():
        print(f"Error: Test cases file not found: {args.test_cases}")
        return 1

    # Run async operation
    if args.optimize:
        return asyncio.run(
            optimize_prompt(
                prompt_path=args.prompt_file,
                test_cases_path=args.test_cases,
                prompt_type=args.prompt_type,
                tags=args.tags,
                max_iterations=args.max_iterations,
                output_file=args.output_file,
                model=args.model,
            )
        )
    else:
        return asyncio.run(
            evaluate_prompt(
                prompt_path=args.prompt_file,
                test_cases_path=args.test_cases,
                prompt_type=args.prompt_type,
                tags=args.tags,
                model=args.model,
            )
        )


if __name__ == "__main__":
    sys.exit(main())
