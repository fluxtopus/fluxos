"""
Observer Course Correction Test

Tests the hypothesis: Can an Observer agent detect failures and propose
plan modifications that the Orchestrator can execute?

Scenario:
1. Plan: Fetch weather data -> Analyze -> Send alert
2. Failure: Weather API returns error (simulated)
3. Observer: Detects failure, proposes fallback to backup API
4. Orchestrator: Modifies plan, retries with fallback
5. Result: Plan completes successfully despite initial failure

This validates the core delegation principle: autonomous adaptation.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import structlog
import random

from src.llm.openrouter_client import OpenRouterClient, ModelRouting

logger = structlog.get_logger(__name__)


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskStep:
    id: str
    name: str
    description: str
    status: StepStatus = StepStatus.PENDING
    output: Optional[dict] = None
    error: Optional[str] = None
    fallback_step_id: Optional[str] = None


@dataclass
class ObserverProposal:
    """A proposal from the Observer to modify the plan."""
    proposal_type: str  # "retry", "fallback", "skip", "abort"
    step_id: str
    reason: str
    new_step: Optional[TaskStep] = None
    confidence: float = 0.0


@dataclass
class Task:
    """The persistent plan that survives across agent invocations."""
    id: str
    goal: str
    steps: list[TaskStep] = field(default_factory=list)
    status: str = "running"
    findings: list[str] = field(default_factory=list)
    modifications: list[str] = field(default_factory=list)


# =============================================================================
# SIMULATED SERVICES (would be real in production)
# =============================================================================

class WeatherAPISimulator:
    """Simulates a weather API that sometimes fails."""

    def __init__(self, failure_rate: float = 0.0):
        self.failure_rate = failure_rate
        self.call_count = 0

    async def fetch_weather(self, location: str) -> dict:
        self.call_count += 1

        # Simulate failure based on rate
        if random.random() < self.failure_rate:
            raise ConnectionError(f"Primary weather API unavailable (attempt {self.call_count})")

        return {
            "location": location,
            "temperature": 72,
            "conditions": "sunny",
            "source": "primary_api"
        }


class BackupWeatherAPI:
    """Backup weather service."""

    async def fetch_weather(self, location: str) -> dict:
        # Backup always works (for this test)
        return {
            "location": location,
            "temperature": 71,
            "conditions": "partly cloudy",
            "source": "backup_api"
        }


# =============================================================================
# OBSERVER AGENT
# =============================================================================

class ObserverAgent:
    """
    Watches plan execution and proposes modifications when things go wrong.

    Key principle: Observer PROPOSES, never ACTS directly.
    """

    def __init__(self, llm_client: Optional[OpenRouterClient] = None):
        self.llm_client = llm_client

    async def analyze_failure(
        self,
        plan: Task,
        failed_step: TaskStep
    ) -> ObserverProposal:
        """
        Analyze a step failure and propose a course of action.

        Uses LLM reasoning to determine the best response.
        """

        # Build context for LLM
        context = f"""
<plan>
Goal: {plan.goal}
Current status: Step "{failed_step.name}" failed
Error: {failed_step.error}
</plan>

<failed_step>
ID: {failed_step.id}
Name: {failed_step.name}
Description: {failed_step.description}
Has fallback: {failed_step.fallback_step_id is not None}
</failed_step>

<available_actions>
1. RETRY - Try the same step again (transient failure)
2. FALLBACK - Use the fallback step if available
3. SKIP - Skip this step and continue (non-critical)
4. ABORT - Stop the entire plan (critical failure)
</available_actions>

<instructions>
Analyze the failure and recommend ONE action.
Consider:
- Is this a transient or permanent failure?
- Is there a fallback available?
- Can the plan succeed without this step?
- What's the risk of each action?

Respond with ONLY the action name and a brief reason.
Format: ACTION: reason
</instructions>
"""

        if self.llm_client:
            # Use LLM for intelligent analysis
            from src.interfaces.llm import LLMMessage

            response = await self.llm_client.create_completion(
                messages=[LLMMessage(role="user", content=context)],
                routing=ModelRouting.single("anthropic/claude-sonnet-4"),
                temperature=0.0,
                max_tokens=200,
            )

            result = response.content.strip()
            logger.info("Observer LLM analysis", result=result)

            # Parse response
            if "FALLBACK" in result.upper():
                return ObserverProposal(
                    proposal_type="fallback",
                    step_id=failed_step.id,
                    reason=result,
                    confidence=0.9,
                )
            elif "RETRY" in result.upper():
                return ObserverProposal(
                    proposal_type="retry",
                    step_id=failed_step.id,
                    reason=result,
                    confidence=0.7,
                )
            elif "SKIP" in result.upper():
                return ObserverProposal(
                    proposal_type="skip",
                    step_id=failed_step.id,
                    reason=result,
                    confidence=0.6,
                )
            else:
                return ObserverProposal(
                    proposal_type="abort",
                    step_id=failed_step.id,
                    reason=result,
                    confidence=0.5,
                )
        else:
            # Rule-based fallback (no LLM)
            if failed_step.fallback_step_id:
                return ObserverProposal(
                    proposal_type="fallback",
                    step_id=failed_step.id,
                    reason="Fallback available, switching to backup",
                    confidence=0.9,
                )
            else:
                return ObserverProposal(
                    proposal_type="retry",
                    step_id=failed_step.id,
                    reason="No fallback, attempting retry",
                    confidence=0.5,
                )


# =============================================================================
# ORCHESTRATOR
# =============================================================================

class Orchestrator:
    """
    Executes plan steps and responds to Observer proposals.

    Key principle: Stateless per cycle. Reads plan, executes ONE step, exits.
    """

    def __init__(self):
        self.primary_api = WeatherAPISimulator(failure_rate=1.0)  # Always fails for test
        self.backup_api = BackupWeatherAPI()
        self.observer = ObserverAgent()

    async def execute_step(self, plan: Task, step: TaskStep) -> bool:
        """Execute a single step. Returns True if successful."""

        step.status = StepStatus.RUNNING
        logger.info("Executing step", step_id=step.id, step_name=step.name)

        try:
            if step.name == "fetch_weather":
                result = await self.primary_api.fetch_weather("San Francisco")
                step.output = result
                step.status = StepStatus.COMPLETED
                return True

            elif step.name == "fetch_weather_backup":
                result = await self.backup_api.fetch_weather("San Francisco")
                step.output = result
                step.status = StepStatus.COMPLETED
                return True

            elif step.name == "analyze_weather":
                # Get weather from previous step
                weather_step = next(
                    (s for s in plan.steps if s.name in ["fetch_weather", "fetch_weather_backup"]
                     and s.status == StepStatus.COMPLETED),
                    None
                )
                if not weather_step or not weather_step.output:
                    raise ValueError("No weather data available")

                weather = weather_step.output
                analysis = {
                    "alert_needed": weather["temperature"] > 90 or weather["temperature"] < 32,
                    "summary": f"{weather['conditions']} at {weather['temperature']}F in {weather['location']}",
                    "source": weather.get("source", "unknown"),
                }
                step.output = analysis
                step.status = StepStatus.COMPLETED
                return True

            elif step.name == "send_alert":
                # Simulate sending alert
                analyze_step = next(
                    (s for s in plan.steps if s.name == "analyze_weather"
                     and s.status == StepStatus.COMPLETED),
                    None
                )
                if analyze_step and analyze_step.output:
                    step.output = {
                        "sent": True,
                        "message": analyze_step.output["summary"],
                    }
                else:
                    step.output = {"sent": True, "message": "Weather check complete"}
                step.status = StepStatus.COMPLETED
                return True

            else:
                raise ValueError(f"Unknown step: {step.name}")

        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            logger.error("Step failed", step_id=step.id, error=str(e))
            return False

    async def apply_proposal(
        self,
        plan: Task,
        proposal: ObserverProposal
    ) -> bool:
        """Apply an Observer's proposal to modify the plan."""

        logger.info(
            "Applying observer proposal",
            proposal_type=proposal.proposal_type,
            step_id=proposal.step_id,
            reason=proposal.reason,
        )

        plan.modifications.append(
            f"Observer proposed {proposal.proposal_type} for step {proposal.step_id}: {proposal.reason}"
        )

        if proposal.proposal_type == "fallback":
            # Find the failed step and activate its fallback
            failed_step = next((s for s in plan.steps if s.id == proposal.step_id), None)
            if failed_step and failed_step.fallback_step_id:
                # Find or create fallback step
                fallback_exists = any(s.id == failed_step.fallback_step_id for s in plan.steps)
                if not fallback_exists:
                    # Insert fallback step
                    fallback_step = TaskStep(
                        id=failed_step.fallback_step_id,
                        name="fetch_weather_backup",
                        description="Fetch weather from backup API",
                        status=StepStatus.PENDING,
                    )
                    # Insert after failed step
                    idx = plan.steps.index(failed_step)
                    plan.steps.insert(idx + 1, fallback_step)
                    logger.info("Inserted fallback step", step_id=fallback_step.id)
                return True

        elif proposal.proposal_type == "retry":
            # Reset step status for retry
            step = next((s for s in plan.steps if s.id == proposal.step_id), None)
            if step:
                step.status = StepStatus.PENDING
                step.error = None
                return True

        elif proposal.proposal_type == "skip":
            step = next((s for s in plan.steps if s.id == proposal.step_id), None)
            if step:
                step.status = StepStatus.SKIPPED
                return True

        elif proposal.proposal_type == "abort":
            plan.status = "aborted"
            return False

        return False

    async def run_plan(self, plan: Task, use_llm: bool = False) -> Task:
        """
        Execute the plan with Observer monitoring.

        Returns the completed/modified plan.
        """

        if use_llm:
            async with OpenRouterClient() as client:
                self.observer = ObserverAgent(llm_client=client)
                return await self._execute_plan_loop(plan)
        else:
            self.observer = ObserverAgent(llm_client=None)
            return await self._execute_plan_loop(plan)

    async def _execute_plan_loop(self, plan: Task) -> Task:
        """Main execution loop."""

        max_iterations = 10  # Prevent infinite loops
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # Find next pending step
            next_step = next(
                (s for s in plan.steps if s.status == StepStatus.PENDING),
                None
            )

            if not next_step:
                # All steps completed or skipped
                plan.status = "completed"
                break

            if plan.status == "aborted":
                break

            # Execute the step
            success = await self.execute_step(plan, next_step)

            if not success:
                # Step failed - consult Observer
                proposal = await self.observer.analyze_failure(plan, next_step)
                plan.findings.append(
                    f"Observer detected failure in {next_step.name}: {proposal.reason}"
                )

                # Apply the proposal
                should_continue = await self.apply_proposal(plan, proposal)

                if not should_continue:
                    break

        return plan


# =============================================================================
# TEST RUNNER
# =============================================================================

async def run_test(use_llm: bool = False):
    """
    Run the Observer course correction test.

    Expected behavior:
    1. Step 1 (fetch_weather) fails - primary API is down
    2. Observer detects failure, proposes fallback
    3. Orchestrator inserts fallback step
    4. Step 1b (fetch_weather_backup) succeeds
    5. Remaining steps complete
    6. Plan succeeds despite initial failure
    """

    print("\n" + "=" * 70)
    print("OBSERVER COURSE CORRECTION TEST")
    print("=" * 70)
    print(f"\nUsing LLM for Observer: {use_llm}")

    # Create the plan
    plan = Task(
        id="test_plan_001",
        goal="Check weather and send alert if needed",
        steps=[
            TaskStep(
                id="step_1",
                name="fetch_weather",
                description="Fetch current weather from primary API",
                fallback_step_id="step_1b",  # Has a fallback!
            ),
            TaskStep(
                id="step_2",
                name="analyze_weather",
                description="Analyze weather data for alerts",
            ),
            TaskStep(
                id="step_3",
                name="send_alert",
                description="Send weather summary notification",
            ),
        ],
    )

    print("\n--- INITIAL PLAN ---")
    for step in plan.steps:
        print(f"  [{step.id}] {step.name}: {step.description}")

    print("\n--- EXECUTION LOG ---")

    # Run the orchestrator
    orchestrator = Orchestrator()
    result = await orchestrator.run_plan(plan, use_llm=use_llm)

    print("\n--- FINAL PLAN STATE ---")
    print(f"Status: {result.status}")
    print(f"\nSteps:")
    for step in result.steps:
        status_icon = {
            StepStatus.COMPLETED: "[OK]",
            StepStatus.FAILED: "[FAIL]",
            StepStatus.SKIPPED: "[SKIP]",
            StepStatus.PENDING: "[...]",
            StepStatus.RUNNING: "[>>>]",
        }.get(step.status, "[?]")

        output_summary = ""
        if step.output:
            if "source" in step.output:
                output_summary = f" (source: {step.output['source']})"
            elif "summary" in step.output:
                output_summary = f" ({step.output['summary']})"
            elif "sent" in step.output:
                output_summary = " (notification sent)"

        error_info = f" ERROR: {step.error}" if step.error else ""

        print(f"  {status_icon} {step.id} - {step.name}{output_summary}{error_info}")

    print(f"\nFindings:")
    for finding in result.findings:
        print(f"  - {finding}")

    print(f"\nModifications:")
    for mod in result.modifications:
        print(f"  - {mod}")

    # Verify success
    print("\n--- TEST RESULT ---")

    success_criteria = [
        ("Plan completed", result.status == "completed"),
        ("Fallback was used", any(s.name == "fetch_weather_backup" for s in result.steps)),
        ("Weather fetched from backup", any(
            s.output and s.output.get("source") == "backup_api"
            for s in result.steps
        )),
        ("Observer detected failure", len(result.findings) > 0),
        ("Plan was modified", len(result.modifications) > 0),
    ]

    all_passed = True
    for criteria, passed in success_criteria:
        icon = "[PASS]" if passed else "[FAIL]"
        print(f"  {icon} {criteria}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("TEST PASSED: Observer successfully corrected course on failure")
    else:
        print("TEST FAILED: Some criteria not met")
    print("=" * 70 + "\n")

    return all_passed


async def main():
    """Run tests with and without LLM."""

    print("\n" + "#" * 70)
    print("# RUNNING OBSERVER COURSE CORRECTION TESTS")
    print("#" * 70)

    # Test 1: Rule-based Observer (no LLM)
    print("\n\n### TEST 1: Rule-based Observer (no LLM) ###")
    rule_based_passed = await run_test(use_llm=False)

    # Test 2: LLM-powered Observer
    print("\n\n### TEST 2: LLM-powered Observer ###")
    llm_passed = await run_test(use_llm=True)

    # Summary
    print("\n" + "#" * 70)
    print("# SUMMARY")
    print("#" * 70)
    print(f"  Rule-based Observer: {'PASSED' if rule_based_passed else 'FAILED'}")
    print(f"  LLM-powered Observer: {'PASSED' if llm_passed else 'FAILED'}")
    print("#" * 70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
