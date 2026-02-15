"""
LLM Reasoning Experiment V2: Does Code Generation Improve Reasoning?

Version 2: Uses MORE CHALLENGING problems that are more likely to reveal
differences in reasoning between code and non-code approaches.

Problems include:
1. Multi-step calculations
2. Edge cases (negative numbers, zeros)
3. Order of operations
4. Problems that humans commonly get wrong

Hypothesis: LLMs that write code before answering complex mathematical questions
may reason more accurately than those that answer directly.
"""

import asyncio
import re
from dataclasses import dataclass
from typing import Optional, List
import structlog

from src.llm.openrouter_client import OpenRouterClient, ModelRouting
from src.interfaces.llm import LLMMessage

logger = structlog.get_logger(__name__)


# Programming-focused LLMs to test
TEST_MODELS = [
    "anthropic/claude-sonnet-4",
    "openai/gpt-4o",
    "deepseek/deepseek-chat",
    "google/gemini-2.0-flash-001",
]


@dataclass
class TestCase:
    """A test case for the experiment."""
    name: str
    prompt_with_code: str
    prompt_without_code: str
    expected_answer: any
    difficulty: str  # "easy", "medium", "hard"


# Test cases designed to reveal reasoning differences
TEST_CASES = [
    # Medium: Order of operations
    TestCase(
        name="order_of_operations",
        prompt_with_code="Write a Python function to evaluate the expression, then answer: What is 8 + 2 * 3 - 4 / 2?",
        prompt_without_code="What is 8 + 2 * 3 - 4 / 2?",
        expected_answer=12.0,  # 8 + 6 - 2 = 12
        difficulty="medium",
    ),

    # Hard: Multi-step with parentheses
    TestCase(
        name="nested_parentheses",
        prompt_with_code="Write a Python function to calculate this expression step by step, then answer: What is ((15 - 7) * 3 + 10) / 2 - 4?",
        prompt_without_code="What is ((15 - 7) * 3 + 10) / 2 - 4?",
        expected_answer=13.0,  # ((8) * 3 + 10) / 2 - 4 = (24 + 10) / 2 - 4 = 34/2 - 4 = 17 - 4 = 13
        difficulty="hard",
    ),

    # Tricky: Integer division vs float division
    TestCase(
        name="division_precision",
        prompt_with_code="Write Python code to calculate precisely, then answer: If I have 7 pizzas and want to split them equally among 3 people, how many pizzas does each person get? Give the exact decimal answer.",
        prompt_without_code="If I have 7 pizzas and want to split them equally among 3 people, how many pizzas does each person get? Give the exact decimal answer.",
        expected_answer=2.333,  # 7/3 ≈ 2.333...
        difficulty="medium",
    ),

    # Hard: Compound percentage
    TestCase(
        name="compound_percentage",
        prompt_with_code="Write a Python function to calculate compound growth, then answer: If I invest $1000 at 10% annual interest compounded yearly, how much do I have after 3 years? Round to 2 decimal places.",
        prompt_without_code="If I invest $1000 at 10% annual interest compounded yearly, how much do I have after 3 years? Round to 2 decimal places.",
        expected_answer=1331.0,  # 1000 * (1.1)^3 = 1331
        difficulty="hard",
    ),

    # Tricky: Negative number handling
    TestCase(
        name="negative_power",
        prompt_with_code="Write Python code to verify your answer, then answer: What is (-2) raised to the power of 5?",
        prompt_without_code="What is (-2) raised to the power of 5?",
        expected_answer=-32,  # (-2)^5 = -32
        difficulty="medium",
    ),

    # Hard: Modular arithmetic
    TestCase(
        name="modulo_operation",
        prompt_with_code="Write Python code to demonstrate, then answer: What is 47 modulo 7 (the remainder when 47 is divided by 7)?",
        prompt_without_code="What is 47 modulo 7 (the remainder when 47 is divided by 7)?",
        expected_answer=5,  # 47 = 7*6 + 5, so remainder is 5
        difficulty="medium",
    ),

    # Hard: Sequence/pattern
    TestCase(
        name="fibonacci_sum",
        prompt_with_code="Write Python code to generate the Fibonacci sequence, then answer: What is the sum of the first 8 Fibonacci numbers (1, 1, 2, 3, 5, 8, 13, 21)?",
        prompt_without_code="What is the sum of the first 8 Fibonacci numbers (1, 1, 2, 3, 5, 8, 13, 21)?",
        expected_answer=54,  # 1+1+2+3+5+8+13+21 = 54
        difficulty="hard",
    ),

    # Tricky: Zero handling
    TestCase(
        name="zero_operations",
        prompt_with_code="Write Python code to verify, then answer: What is 0^0 (zero to the power of zero)?",
        prompt_without_code="What is 0^0 (zero to the power of zero)?",
        expected_answer=1,  # By convention in most programming languages
        difficulty="tricky",
    ),
]


@dataclass
class ExperimentResult:
    """Result from a single experiment run."""
    model: str
    test_case: str
    condition: str  # "with_code" or "without_code"
    prompt: str
    response: str
    extracted_answer: Optional[float]
    expected_answer: any
    is_correct: bool
    response_length: int
    contains_code: bool
    difficulty: str
    error: Optional[str] = None


def extract_numerical_answer(response: str, expected: any) -> Optional[float]:
    """
    Extract the numerical answer from the response.
    """
    response_lower = response.lower()

    # Special handling for 0^0 = 1
    if expected == 1 and ("0^0" in response or "0**0" in response):
        if "1" in response:
            # Check if the response indicates 1
            patterns = [
                r"(?:is|equals?|=)\s*1\b",
                r"\b1\b.*(?:convention|defined|result)",
                r"(?:answer|result).*\b1\b",
            ]
            for pattern in patterns:
                if re.search(pattern, response_lower):
                    return 1.0

    # Look for explicit answer patterns
    patterns = [
        r"(?:the )?(?:result|answer|sum|total|value) (?:is|equals?|=)\s*\$?([\d,]+\.?\d*)",
        r"(?:equals?|=)\s*\$?([\d,]+\.?\d*)",
        r"\$?([\d,]+\.?\d*)\s*(?:dollars?)?",
        r"\*\*([\d,]+\.?\d*)\*\*",  # Bold markdown
        r"`([\d,]+\.?\d*)`",  # Code markdown
        r"(?:returns?|outputs?|gets?)\s*\$?([\d,]+\.?\d*)",
    ]

    # Handle negative numbers
    negative_patterns = [
        r"(?:is|equals?|=)\s*(-[\d,]+\.?\d*)",
        r"\*\*(-[\d,]+\.?\d*)\*\*",
        r"`(-[\d,]+\.?\d*)`",
    ]

    for pattern in negative_patterns:
        match = re.search(pattern, response_lower)
        if match:
            try:
                val = float(match.group(1).replace(",", ""))
                return val
            except ValueError:
                continue

    for pattern in patterns:
        matches = re.findall(pattern, response_lower)
        if matches:
            # Find the best match
            for match in matches:
                try:
                    val = float(match.replace(",", ""))
                    # If this matches expected, return it
                    if abs(val - float(expected)) < 0.01:
                        return val
                except ValueError:
                    continue

    # Fallback: find all numbers and pick the most likely answer
    numbers = re.findall(r'(-?[\d,]+\.?\d*)', response)
    valid_numbers = []
    for num in numbers:
        try:
            val = float(num.replace(",", ""))
            valid_numbers.append(val)
        except ValueError:
            continue

    if valid_numbers:
        # Check if expected answer is in the numbers
        for val in valid_numbers:
            if abs(val - float(expected)) < 0.01:
                return val
        # Return the last significant number (often the final answer)
        for val in reversed(valid_numbers):
            if val != 0:
                return val

    return None


def contains_python_code(response: str) -> bool:
    """Check if the response contains Python code."""
    code_indicators = [
        "def ",
        "return ",
        "print(",
        "```python",
        "```py",
        ">>> ",
        "import ",
        "for ",
        "while ",
    ]
    return any(indicator in response for indicator in code_indicators)


def is_answer_correct(extracted: Optional[float], expected: any, tolerance: float = 0.01) -> bool:
    """Check if extracted answer matches expected."""
    if extracted is None:
        return False
    try:
        expected_float = float(expected)
        # For percentages and decimals, allow small tolerance
        if abs(extracted - expected_float) < tolerance:
            return True
        # For the pizza problem, check if it's approximately 2.33
        if abs(expected_float - 2.333) < 0.01:
            return abs(extracted - 2.333) < 0.05
        return False
    except (ValueError, TypeError):
        return False


async def run_single_experiment(
    client: OpenRouterClient,
    model: str,
    test_case: TestCase,
    condition: str,
) -> ExperimentResult:
    """Run a single experiment with one model, one test case, one condition."""
    prompt = test_case.prompt_with_code if condition == "with_code" else test_case.prompt_without_code

    try:
        logger.info(
            "Running experiment",
            model=model,
            test=test_case.name,
            condition=condition,
        )

        messages = [
            LLMMessage(role="user", content=prompt)
        ]

        routing = ModelRouting.single(model)

        response = await client.create_completion(
            messages=messages,
            routing=routing,
            temperature=0.0,
            max_tokens=1500,
        )

        response_text = response.content
        extracted = extract_numerical_answer(response_text, test_case.expected_answer)
        is_correct = is_answer_correct(extracted, test_case.expected_answer)
        has_code = contains_python_code(response_text)

        logger.info(
            "Experiment complete",
            model=model,
            test=test_case.name,
            condition=condition,
            extracted=extracted,
            expected=test_case.expected_answer,
            is_correct=is_correct,
        )

        return ExperimentResult(
            model=model,
            test_case=test_case.name,
            condition=condition,
            prompt=prompt,
            response=response_text,
            extracted_answer=extracted,
            expected_answer=test_case.expected_answer,
            is_correct=is_correct,
            response_length=len(response_text),
            contains_code=has_code,
            difficulty=test_case.difficulty,
        )

    except Exception as e:
        logger.error(
            "Experiment failed",
            model=model,
            test=test_case.name,
            condition=condition,
            error=str(e),
        )
        return ExperimentResult(
            model=model,
            test_case=test_case.name,
            condition=condition,
            prompt=prompt,
            response="",
            extracted_answer=None,
            expected_answer=test_case.expected_answer,
            is_correct=False,
            response_length=0,
            contains_code=False,
            difficulty=test_case.difficulty,
            error=str(e),
        )


async def run_all_experiments() -> List[ExperimentResult]:
    """Run all experiments across all models, test cases, and conditions."""
    results = []

    async with OpenRouterClient() as client:
        for model in TEST_MODELS:
            print(f"\n📍 Testing: {model}")
            for test_case in TEST_CASES:
                print(f"   🧪 {test_case.name} ({test_case.difficulty})")

                # Run WITH CODE condition
                result_with = await run_single_experiment(
                    client=client,
                    model=model,
                    test_case=test_case,
                    condition="with_code",
                )
                results.append(result_with)
                status = "✅" if result_with.is_correct else "❌"
                print(f"      WITH CODE:    {status} (got: {result_with.extracted_answer}, expected: {test_case.expected_answer})")

                await asyncio.sleep(0.5)

                # Run WITHOUT CODE condition
                result_without = await run_single_experiment(
                    client=client,
                    model=model,
                    test_case=test_case,
                    condition="without_code",
                )
                results.append(result_without)
                status = "✅" if result_without.is_correct else "❌"
                print(f"      WITHOUT CODE: {status} (got: {result_without.extracted_answer}, expected: {test_case.expected_answer})")

                await asyncio.sleep(0.5)

    return results


def analyze_results(results: List[ExperimentResult]) -> dict:
    """Analyze experiment results and generate summary."""

    # Group by condition
    with_code = [r for r in results if r.condition == "with_code"]
    without_code = [r for r in results if r.condition == "without_code"]

    # Overall accuracy
    with_code_correct = sum(1 for r in with_code if r.is_correct)
    without_code_correct = sum(1 for r in without_code if r.is_correct)

    # By difficulty
    difficulties = ["easy", "medium", "hard", "tricky"]
    by_difficulty = {}
    for diff in difficulties:
        wc = [r for r in with_code if r.difficulty == diff]
        woc = [r for r in without_code if r.difficulty == diff]
        if wc or woc:
            by_difficulty[diff] = {
                "with_code": sum(1 for r in wc if r.is_correct) / len(wc) if wc else 0,
                "without_code": sum(1 for r in woc if r.is_correct) / len(woc) if woc else 0,
            }

    # By model
    by_model = {}
    for model in TEST_MODELS:
        wc = [r for r in with_code if r.model == model]
        woc = [r for r in without_code if r.model == model]
        by_model[model] = {
            "with_code_correct": sum(1 for r in wc if r.is_correct),
            "with_code_total": len(wc),
            "without_code_correct": sum(1 for r in woc if r.is_correct),
            "without_code_total": len(woc),
        }

    # By test case
    by_test = {}
    for test in TEST_CASES:
        wc = [r for r in with_code if r.test_case == test.name]
        woc = [r for r in without_code if r.test_case == test.name]
        by_test[test.name] = {
            "with_code_correct": sum(1 for r in wc if r.is_correct),
            "without_code_correct": sum(1 for r in woc if r.is_correct),
            "total_models": len(TEST_MODELS),
            "difficulty": test.difficulty,
        }

    return {
        "overall": {
            "with_code": {
                "accuracy": with_code_correct / len(with_code) if with_code else 0,
                "correct": with_code_correct,
                "total": len(with_code),
            },
            "without_code": {
                "accuracy": without_code_correct / len(without_code) if without_code else 0,
                "correct": without_code_correct,
                "total": len(without_code),
            },
        },
        "by_difficulty": by_difficulty,
        "by_model": by_model,
        "by_test": by_test,
    }


def print_report(results: List[ExperimentResult], analysis: dict):
    """Print a formatted report of the experiment results."""

    print("\n" + "=" * 80)
    print("LLM REASONING EXPERIMENT V2: Code Generation vs Direct Answer")
    print("=" * 80)

    print("\n📊 HYPOTHESIS:")
    print("   LLMs that write code before answering COMPLEX mathematical questions")
    print("   may reason more accurately than those that answer directly.")

    print("\n📝 EXPERIMENT DESIGN:")
    print(f"   • Models tested: {len(TEST_MODELS)}")
    print(f"   • Test cases: {len(TEST_CASES)}")
    print(f"   • Total experiments: {len(results)}")
    print("   • Problem types: Order of operations, percentages, modular arithmetic,")
    print("     negative powers, sequences, edge cases")

    # Overall Results
    print("\n" + "=" * 80)
    print("OVERALL RESULTS")
    print("=" * 80)

    oa = analysis["overall"]
    wc = oa["with_code"]
    woc = oa["without_code"]

    print(f"\n📈 WITH CODE CONDITION:")
    print(f"   • Accuracy: {wc['accuracy']*100:.1f}% ({wc['correct']}/{wc['total']} correct)")

    print(f"\n📉 WITHOUT CODE CONDITION:")
    print(f"   • Accuracy: {woc['accuracy']*100:.1f}% ({woc['correct']}/{woc['total']} correct)")

    diff = wc['accuracy'] - woc['accuracy']
    if diff > 0:
        print(f"\n✅ Code generation improved accuracy by {diff*100:.1f}%")
    elif diff < 0:
        print(f"\n❌ Direct answers were {-diff*100:.1f}% more accurate")
    else:
        print("\n⚖️ Both conditions had equal accuracy")

    # Results by Difficulty
    print("\n" + "-" * 80)
    print("RESULTS BY DIFFICULTY")
    print("-" * 80)

    for diff, data in analysis["by_difficulty"].items():
        wc_acc = data["with_code"] * 100
        woc_acc = data["without_code"] * 100
        advantage = "CODE" if wc_acc > woc_acc else ("DIRECT" if woc_acc > wc_acc else "TIE")
        print(f"\n{diff.upper()}:")
        print(f"   With Code:    {wc_acc:.0f}%")
        print(f"   Without Code: {woc_acc:.0f}%")
        print(f"   Winner: {advantage}")

    # Results by Model
    print("\n" + "-" * 80)
    print("RESULTS BY MODEL")
    print("-" * 80)

    for model, data in analysis["by_model"].items():
        wc_acc = data["with_code_correct"] / data["with_code_total"] * 100 if data["with_code_total"] else 0
        woc_acc = data["without_code_correct"] / data["without_code_total"] * 100 if data["without_code_total"] else 0
        print(f"\n🤖 {model}")
        print(f"   With Code:    {wc_acc:.0f}% ({data['with_code_correct']}/{data['with_code_total']})")
        print(f"   Without Code: {woc_acc:.0f}% ({data['without_code_correct']}/{data['without_code_total']})")
        if wc_acc > woc_acc:
            print(f"   → Code helps (+{wc_acc - woc_acc:.0f}%)")
        elif woc_acc > wc_acc:
            print(f"   → Direct better (+{woc_acc - wc_acc:.0f}%)")
        else:
            print("   → No difference")

    # Results by Test Case
    print("\n" + "-" * 80)
    print("RESULTS BY TEST CASE")
    print("-" * 80)

    for test_name, data in analysis["by_test"].items():
        wc = data["with_code_correct"]
        woc = data["without_code_correct"]
        total = data["total_models"]
        diff = data["difficulty"]

        print(f"\n📋 {test_name} ({diff})")
        print(f"   With Code:    {wc}/{total} models correct")
        print(f"   Without Code: {woc}/{total} models correct")

    # Detailed failures
    print("\n" + "-" * 80)
    print("NOTABLE FAILURES")
    print("-" * 80)

    for result in results:
        if not result.is_correct:
            condition_emoji = "📝" if result.condition == "with_code" else "💬"
            print(f"\n{condition_emoji} {result.model} - {result.test_case}")
            print(f"   Expected: {result.expected_answer}")
            print(f"   Got: {result.extracted_answer}")
            # Show relevant part of response
            response_preview = result.response[:200].replace('\n', ' ')
            print(f"   Response: {response_preview}...")

    print("\n" + "=" * 80)
    print("CONCLUSIONS")
    print("=" * 80)

    # Calculate which models benefited from code
    code_helps = []
    code_hurts = []
    no_diff = []

    for model, data in analysis["by_model"].items():
        wc_acc = data["with_code_correct"] / data["with_code_total"] if data["with_code_total"] else 0
        woc_acc = data["without_code_correct"] / data["without_code_total"] if data["without_code_total"] else 0

        if wc_acc > woc_acc:
            code_helps.append((model, wc_acc - woc_acc))
        elif woc_acc > wc_acc:
            code_hurts.append((model, woc_acc - wc_acc))
        else:
            no_diff.append(model)

    if code_helps:
        print("\n✅ Models that improved with code generation:")
        for model, improvement in code_helps:
            print(f"   • {model}: +{improvement*100:.0f}%")

    if code_hurts:
        print("\n❌ Models that performed worse with code generation:")
        for model, degradation in code_hurts:
            print(f"   • {model}: -{degradation*100:.0f}%")

    if no_diff:
        print("\n⚖️ Models with no difference:")
        for model in no_diff:
            print(f"   • {model}")

    print("\n" + "=" * 80)


async def main():
    """Main entry point for the experiment."""
    print("\n🔬 Starting LLM Reasoning Experiment V2...")
    print(f"   Testing {len(TEST_MODELS)} models")
    print(f"   With {len(TEST_CASES)} challenging test cases")
    print(f"   Total experiments: {len(TEST_MODELS) * len(TEST_CASES) * 2}")
    print("   This may take several minutes...\n")

    results = await run_all_experiments()
    analysis = analyze_results(results)
    print_report(results, analysis)

    return results, analysis


if __name__ == "__main__":
    asyncio.run(main())
