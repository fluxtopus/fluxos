"""
Observer Multi-Failure Test

Tests that the Observer can choose DIFFERENT strategies for DIFFERENT failures:
1. API timeout -> RETRY
2. API unavailable -> FALLBACK
3. Non-critical step fails -> SKIP
4. Critical step fails with no fallback -> ABORT

This validates the Observer's decision-making, not just fallback detection.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import structlog

from src.llm.openrouter_client import OpenRouterClient, ModelRouting
from src.interfaces.llm import LLMMessage

logger = structlog.get_logger(__name__)


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class FailureType(str, Enum):
    TIMEOUT = "timeout"           # Transient - should retry
    UNAVAILABLE = "unavailable"   # Service down - should fallback
    NON_CRITICAL = "non_critical" # Nice-to-have - should skip
    CRITICAL = "critical"         # Must succeed - should abort


@dataclass
class TaskStep:
    id: str
    name: str
    description: str
    is_critical: bool = True
    status: StepStatus = StepStatus.PENDING
    output: Optional[dict] = None
    error: Optional[str] = None
    failure_type: Optional[FailureType] = None
    fallback_step_id: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 2


@dataclass
class ObserverProposal:
    proposal_type: str  # "retry", "fallback", "skip", "abort"
    step_id: str
    reason: str
    confidence: float = 0.0


@dataclass
class Task:
    id: str
    goal: str
    steps: list[TaskStep] = field(default_factory=list)
    status: str = "running"
    findings: list[str] = field(default_factory=list)
    modifications: list[str] = field(default_factory=list)


@dataclass
class TestScenario:
    name: str
    description: str
    failure_type: FailureType
    has_fallback: bool
    is_critical: bool
    expected_action: str  # What the Observer SHOULD do


# =============================================================================
# TEST SCENARIOS
# =============================================================================

TEST_SCENARIOS = [
    TestScenario(
        name="timeout_with_retries",
        description="API timed out - transient failure",
        failure_type=FailureType.TIMEOUT,
        has_fallback=False,
        is_critical=True,
        expected_action="retry",
    ),
    TestScenario(
        name="service_down_with_fallback",
        description="Primary service unavailable, backup exists",
        failure_type=FailureType.UNAVAILABLE,
        has_fallback=True,
        is_critical=True,
        expected_action="fallback",
    ),
    TestScenario(
        name="non_critical_failure",
        description="Optional enrichment step failed",
        failure_type=FailureType.NON_CRITICAL,
        has_fallback=False,
        is_critical=False,
        expected_action="skip",
    ),
    TestScenario(
        name="critical_no_options",
        description="Critical step failed, no fallback, retries exhausted",
        failure_type=FailureType.CRITICAL,
        has_fallback=False,
        is_critical=True,
        expected_action="abort",
    ),
]


# =============================================================================
# LLM-POWERED OBSERVER
# =============================================================================

class SmartObserver:
    """Observer that uses LLM reasoning to choose the right action."""

    def __init__(self, llm_client: OpenRouterClient):
        self.llm_client = llm_client

    async def analyze_failure(
        self,
        plan: Task,
        failed_step: TaskStep,
        scenario: TestScenario,
    ) -> ObserverProposal:
        """Use LLM to analyze failure and propose action."""

        prompt = f"""<context>
You are an Observer agent monitoring plan execution.
A step has failed and you must decide what to do.
</context>

<plan>
Goal: {plan.goal}
</plan>

<failed_step>
Name: {failed_step.name}
Description: {failed_step.description}
Error type: {scenario.failure_type.value}
Error message: {failed_step.error}
Is critical: {failed_step.is_critical}
Has fallback: {failed_step.fallback_step_id is not None}
Retry count: {failed_step.retry_count}/{failed_step.max_retries}
</failed_step>

<decision_rules>
- RETRY: Use when failure is transient (timeout, rate limit) and retries remain
- FALLBACK: Use when a fallback exists and the failure seems permanent
- SKIP: Use when the step is non-critical and plan can continue without it
- ABORT: Use when the step is critical, has no fallback, and retries are exhausted
</decision_rules>

<task>
Choose ONE action: RETRY, FALLBACK, SKIP, or ABORT
Explain your reasoning briefly.
Format your response as: ACTION: reason
</task>"""

        response = await self.llm_client.create_completion(
            messages=[LLMMessage(role="user", content=prompt)],
            routing=ModelRouting.single("anthropic/claude-sonnet-4"),
            temperature=0.0,
            max_tokens=150,
        )

        result = response.content.strip()

        # Parse the action - look at the FIRST word/phrase only
        # Expected formats: "ACTION: RETRY", "RETRY:", "FALLBACK: reason"
        first_line = result.split('\n')[0].upper()
        first_word = first_line.split(':')[0].split()[0] if first_line else ""

        # Also check for "ACTION: X" format
        if "ACTION:" in first_line:
            # Extract word after "ACTION:"
            action_part = first_line.split("ACTION:")[1].strip()
            first_word = action_part.split()[0] if action_part else ""

        if first_word == "RETRY":
            action = "retry"
        elif first_word == "FALLBACK":
            action = "fallback"
        elif first_word == "SKIP":
            action = "skip"
        elif first_word == "ABORT":
            action = "abort"
        else:
            # Fallback: check first line for keywords
            if "RETRY" in first_line.split(':')[0]:
                action = "retry"
            elif "FALLBACK" in first_line.split(':')[0]:
                action = "fallback"
            elif "SKIP" in first_line.split(':')[0]:
                action = "skip"
            else:
                action = "abort"

        return ObserverProposal(
            proposal_type=action,
            step_id=failed_step.id,
            reason=response.content.strip(),
            confidence=0.9,
        )


# =============================================================================
# TEST RUNNER
# =============================================================================

async def run_scenario_test(
    scenario: TestScenario,
    observer: SmartObserver,
) -> tuple[bool, str]:
    """
    Run a single test scenario.
    Returns (passed, details).
    """

    # Create a minimal plan for testing
    plan = Task(
        id=f"test_{scenario.name}",
        goal="Complete the workflow",
    )

    # Create the failed step
    failed_step = TaskStep(
        id="step_failed",
        name=scenario.name,
        description=scenario.description,
        is_critical=scenario.is_critical,
        status=StepStatus.FAILED,
        error=f"Simulated {scenario.failure_type.value} error",
        failure_type=scenario.failure_type,
        fallback_step_id="step_fallback" if scenario.has_fallback else None,
        retry_count=2 if scenario.failure_type == FailureType.CRITICAL else 0,
        max_retries=2,
    )

    # Get Observer's decision
    proposal = await observer.analyze_failure(plan, failed_step, scenario)

    # Check if decision matches expected
    passed = proposal.proposal_type == scenario.expected_action

    details = (
        f"Expected: {scenario.expected_action.upper()}, "
        f"Got: {proposal.proposal_type.upper()}\n"
        f"Reasoning: {proposal.reason}"
    )

    return passed, details


async def run_all_tests():
    """Run all test scenarios and report results."""

    print("\n" + "=" * 70)
    print("OBSERVER MULTI-FAILURE DECISION TEST")
    print("=" * 70)
    print("\nTesting that the Observer chooses the RIGHT action for each failure type.\n")

    results = []

    async with OpenRouterClient() as client:
        observer = SmartObserver(llm_client=client)

        for scenario in TEST_SCENARIOS:
            print(f"\n--- Scenario: {scenario.name} ---")
            print(f"Failure type: {scenario.failure_type.value}")
            print(f"Has fallback: {scenario.has_fallback}")
            print(f"Is critical: {scenario.is_critical}")
            print(f"Expected action: {scenario.expected_action.upper()}")

            passed, details = await run_scenario_test(scenario, observer)
            results.append((scenario, passed, details))

            status = "[PASS]" if passed else "[FAIL]"
            print(f"\nResult: {status}")
            print(details)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    passed_count = sum(1 for _, passed, _ in results if passed)
    total = len(results)

    print(f"\nResults: {passed_count}/{total} scenarios passed\n")

    for scenario, passed, _ in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {scenario.name}: {scenario.failure_type.value} -> {scenario.expected_action}")

    print("\n" + "=" * 70)
    if passed_count == total:
        print("ALL TESTS PASSED: Observer correctly chose different actions for different failures")
    else:
        print(f"SOME TESTS FAILED: {total - passed_count} scenarios did not match expected behavior")
    print("=" * 70 + "\n")

    return passed_count == total


async def main():
    success = await run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
