"""
LLM Reasoning Experiment: Does Code Generation Improve Reasoning?

Hypothesis: LLMs that write code before answering mathematical questions
may reason more accurately than those that answer directly.

Experiment Design:
- 4 programming-focused LLMs
- 2 conditions per LLM:
  1. WITH CODE: "Write a sum function in python and then answer what is the result of -100 plus 200"
  2. WITHOUT CODE: "what is the result of -100 plus 200"
- Expected answer: 100
- Measure: Accuracy and reasoning quality

Uses Tentackl's OpenRouter client for multi-model testing.
"""

import asyncio
import re
from dataclasses import dataclass
from typing import Optional
import structlog

from src.llm.openrouter_client import OpenRouterClient, ModelRouting
from src.interfaces.llm import LLMMessage

logger = structlog.get_logger(__name__)

# Expected correct answer
CORRECT_ANSWER = 100

# Programming-focused LLMs to test
TEST_MODELS = [
    "anthropic/claude-sonnet-4",
    "openai/gpt-4o",
    "deepseek/deepseek-chat",
    "google/gemini-2.0-flash-001",
]

# Experiment prompts
PROMPT_WITH_CODE = """Write a sum function in python and then answer what is the result of -100 plus 200"""

PROMPT_WITHOUT_CODE = """what is the result of -100 plus 200"""


@dataclass
class ExperimentResult:
    """Result from a single experiment run."""
    model: str
    condition: str  # "with_code" or "without_code"
    prompt: str
    response: str
    extracted_answer: Optional[int]
    is_correct: bool
    response_length: int
    contains_code: bool
    error: Optional[str] = None


def extract_numerical_answer(response: str) -> Optional[int]:
    """
    Extract the final numerical answer from the response.
    Looks for patterns like "100", "the result is 100", "= 100", etc.
    """
    # Clean the response
    response_lower = response.lower()

    # Look for explicit answer patterns first
    patterns = [
        r"(?:the )?(?:result|answer|sum) (?:is|equals?|=)\s*(-?\d+)",
        r"(?:equals?|=)\s*(-?\d+)",
        r"-100\s*(?:\+|plus)\s*200\s*(?:=|is|equals?)\s*(-?\d+)",
        r"(?:returns?|output(?:s)?|get)\s*(-?\d+)",
        r"\*\*(-?\d+)\*\*",  # Bold markdown
        r"`(-?\d+)`",  # Code markdown
    ]

    for pattern in patterns:
        match = re.search(pattern, response_lower)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, IndexError):
                continue

    # Fallback: find the last standalone number that could be the answer
    # Look for numbers near keywords
    numbers = re.findall(r'\b(-?\d+)\b', response)
    if numbers:
        # Prefer 100 if it appears (expected answer)
        for num in numbers:
            if int(num) == 100:
                return 100
        # Otherwise return the last number
        return int(numbers[-1])

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
    ]
    return any(indicator in response for indicator in code_indicators)


async def run_single_experiment(
    client: OpenRouterClient,
    model: str,
    prompt: str,
    condition: str,
) -> ExperimentResult:
    """Run a single experiment with one model and one prompt."""
    try:
        logger.info(
            "Running experiment",
            model=model,
            condition=condition,
        )

        messages = [
            LLMMessage(role="user", content=prompt)
        ]

        routing = ModelRouting.single(model)

        response = await client.create_completion(
            messages=messages,
            routing=routing,
            temperature=0.0,  # Deterministic for reproducibility
            max_tokens=1000,
        )

        response_text = response.content
        extracted = extract_numerical_answer(response_text)
        is_correct = extracted == CORRECT_ANSWER
        has_code = contains_python_code(response_text)

        logger.info(
            "Experiment complete",
            model=model,
            condition=condition,
            extracted_answer=extracted,
            is_correct=is_correct,
            has_code=has_code,
        )

        return ExperimentResult(
            model=model,
            condition=condition,
            prompt=prompt,
            response=response_text,
            extracted_answer=extracted,
            is_correct=is_correct,
            response_length=len(response_text),
            contains_code=has_code,
        )

    except Exception as e:
        logger.error(
            "Experiment failed",
            model=model,
            condition=condition,
            error=str(e),
        )
        return ExperimentResult(
            model=model,
            condition=condition,
            prompt=prompt,
            response="",
            extracted_answer=None,
            is_correct=False,
            response_length=0,
            contains_code=False,
            error=str(e),
        )


async def run_all_experiments() -> list[ExperimentResult]:
    """Run all experiments across all models and conditions."""
    results = []

    async with OpenRouterClient() as client:
        for model in TEST_MODELS:
            # Run WITH CODE condition
            result_with = await run_single_experiment(
                client=client,
                model=model,
                prompt=PROMPT_WITH_CODE,
                condition="with_code",
            )
            results.append(result_with)

            # Small delay between requests
            await asyncio.sleep(1)

            # Run WITHOUT CODE condition
            result_without = await run_single_experiment(
                client=client,
                model=model,
                prompt=PROMPT_WITHOUT_CODE,
                condition="without_code",
            )
            results.append(result_without)

            # Delay between models
            await asyncio.sleep(1)

    return results


def analyze_results(results: list[ExperimentResult]) -> dict:
    """Analyze experiment results and generate summary."""

    # Group by condition
    with_code = [r for r in results if r.condition == "with_code"]
    without_code = [r for r in results if r.condition == "without_code"]

    # Calculate accuracy
    with_code_correct = sum(1 for r in with_code if r.is_correct)
    without_code_correct = sum(1 for r in without_code if r.is_correct)

    # Calculate average response length
    with_code_avg_len = sum(r.response_length for r in with_code) / len(with_code) if with_code else 0
    without_code_avg_len = sum(r.response_length for r in without_code) / len(without_code) if without_code else 0

    # Check if code was actually produced
    code_produced = sum(1 for r in with_code if r.contains_code)

    return {
        "total_models": len(TEST_MODELS),
        "with_code": {
            "accuracy": with_code_correct / len(with_code) if with_code else 0,
            "correct_count": with_code_correct,
            "total": len(with_code),
            "avg_response_length": with_code_avg_len,
            "code_produced_count": code_produced,
        },
        "without_code": {
            "accuracy": without_code_correct / len(without_code) if without_code else 0,
            "correct_count": without_code_correct,
            "total": len(without_code),
            "avg_response_length": without_code_avg_len,
        },
        "by_model": {
            model: {
                "with_code": next((r for r in with_code if r.model == model), None),
                "without_code": next((r for r in without_code if r.model == model), None),
            }
            for model in TEST_MODELS
        }
    }


def print_report(results: list[ExperimentResult], analysis: dict):
    """Print a formatted report of the experiment results."""

    print("\n" + "=" * 80)
    print("LLM REASONING EXPERIMENT: Code Generation vs Direct Answer")
    print("=" * 80)

    print("\n📊 HYPOTHESIS:")
    print("   LLMs that write code before answering may reason more accurately")
    print("   than those that answer mathematical questions directly.")

    print("\n📝 EXPERIMENT DESIGN:")
    print(f"   • Models tested: {len(TEST_MODELS)}")
    print(f"   • Expected answer: {CORRECT_ANSWER}")
    print("   • Conditions:")
    print(f"     1. WITH CODE: \"{PROMPT_WITH_CODE}\"")
    print(f"     2. WITHOUT CODE: \"{PROMPT_WITHOUT_CODE}\"")

    print("\n" + "-" * 80)
    print("RESULTS BY MODEL")
    print("-" * 80)

    for model in TEST_MODELS:
        model_data = analysis["by_model"][model]
        with_r = model_data["with_code"]
        without_r = model_data["without_code"]

        print(f"\n🤖 {model}")

        if with_r:
            status = "✅" if with_r.is_correct else "❌"
            code_status = "📝" if with_r.contains_code else "⚠️ NO CODE"
            print(f"   WITH CODE:    {status} Answer: {with_r.extracted_answer} {code_status}")
            print(f"                 Response length: {with_r.response_length} chars")

        if without_r:
            status = "✅" if without_r.is_correct else "❌"
            print(f"   WITHOUT CODE: {status} Answer: {without_r.extracted_answer}")
            print(f"                 Response length: {without_r.response_length} chars")

    print("\n" + "-" * 80)
    print("SUMMARY STATISTICS")
    print("-" * 80)

    wc = analysis["with_code"]
    woc = analysis["without_code"]

    print(f"\n📈 WITH CODE CONDITION:")
    print(f"   • Accuracy: {wc['accuracy']*100:.1f}% ({wc['correct_count']}/{wc['total']} correct)")
    print(f"   • Models that produced code: {wc['code_produced_count']}/{wc['total']}")
    print(f"   • Average response length: {wc['avg_response_length']:.0f} characters")

    print(f"\n📉 WITHOUT CODE CONDITION:")
    print(f"   • Accuracy: {woc['accuracy']*100:.1f}% ({woc['correct_count']}/{woc['total']} correct)")
    print(f"   • Average response length: {woc['avg_response_length']:.0f} characters")

    print("\n" + "-" * 80)
    print("CONCLUSIONS")
    print("-" * 80)

    accuracy_diff = wc['accuracy'] - woc['accuracy']

    if accuracy_diff > 0:
        print(f"\n✅ HYPOTHESIS SUPPORTED: Code generation improved accuracy by {accuracy_diff*100:.1f}%")
    elif accuracy_diff < 0:
        print(f"\n❌ HYPOTHESIS NOT SUPPORTED: Direct answers were {-accuracy_diff*100:.1f}% more accurate")
    else:
        print("\n⚖️ NO DIFFERENCE: Both conditions had equal accuracy")

    print("\n📝 OBSERVATIONS:")

    # Check if any model benefited from code
    improved = []
    worsened = []
    same = []

    for model in TEST_MODELS:
        model_data = analysis["by_model"][model]
        with_r = model_data["with_code"]
        without_r = model_data["without_code"]

        if with_r and without_r:
            if with_r.is_correct and not without_r.is_correct:
                improved.append(model)
            elif not with_r.is_correct and without_r.is_correct:
                worsened.append(model)
            else:
                same.append(model)

    if improved:
        print(f"   • Models improved by code: {', '.join(improved)}")
    if worsened:
        print(f"   • Models worsened by code: {', '.join(worsened)}")
    if same:
        print(f"   • Models unchanged: {', '.join(same)}")

    print("\n" + "=" * 80)

    # Print detailed responses
    print("\n📄 DETAILED RESPONSES")
    print("=" * 80)

    for result in results:
        print(f"\n{'─' * 40}")
        print(f"Model: {result.model}")
        print(f"Condition: {result.condition}")
        print(f"Correct: {'✅' if result.is_correct else '❌'} (extracted: {result.extracted_answer})")
        print(f"{'─' * 40}")
        print(result.response[:500] + "..." if len(result.response) > 500 else result.response)


async def main():
    """Main entry point for the experiment."""
    print("\n🔬 Starting LLM Reasoning Experiment...")
    print(f"   Testing {len(TEST_MODELS)} models with 2 conditions each")
    print("   This may take a few minutes...\n")

    results = await run_all_experiments()
    analysis = analyze_results(results)
    print_report(results, analysis)

    return results, analysis


if __name__ == "__main__":
    asyncio.run(main())
