"""
Real-World Observer Course Correction Test

A REAL scenario where failures can actually happen:

1. Fetch top stories from HackerNews API (real HTTP call)
2. Summarize using a PRIMARY LLM model
3. If primary model fails (rate limit, unavailable, timeout):
   - Observer detects failure
   - Proposes fallback to BACKUP model
   - Plan continues with backup
4. Format and output the digest

This uses:
- Real HackerNews API calls
- Real LLM calls via OpenRouter
- Real failure scenarios (model unavailable, rate limits)
"""

import asyncio
import httpx
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum
import structlog
import time

from src.llm.openrouter_client import OpenRouterClient, ModelRouting
from src.interfaces.llm import LLMMessage

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
    agent_type: str  # "http_fetch", "llm_summarize", "format"
    inputs: dict = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    output: Optional[Any] = None
    error: Optional[str] = None
    fallback_config: Optional[dict] = None  # Fallback options
    retry_count: int = 0
    max_retries: int = 2
    execution_time_ms: int = 0


@dataclass
class ObserverProposal:
    proposal_type: str
    step_id: str
    reason: str
    fallback_config: Optional[dict] = None
    confidence: float = 0.0


@dataclass
class Task:
    id: str
    goal: str
    steps: list[TaskStep] = field(default_factory=list)
    status: str = "running"
    findings: list[str] = field(default_factory=list)
    modifications: list[str] = field(default_factory=list)
    total_time_ms: int = 0


# =============================================================================
# REAL API CLIENTS
# =============================================================================

class HackerNewsClient:
    """Real HackerNews API client."""

    BASE_URL = "https://hacker-news.firebaseio.com/v0"

    async def get_top_stories(self, limit: int = 3) -> list[dict]:
        """Fetch top stories from HackerNews."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Get top story IDs
            response = await client.get(f"{self.BASE_URL}/topstories.json")
            response.raise_for_status()
            story_ids = response.json()[:limit]

            # Fetch each story
            stories = []
            for story_id in story_ids:
                story_response = await client.get(f"{self.BASE_URL}/item/{story_id}.json")
                story_response.raise_for_status()
                story = story_response.json()
                stories.append({
                    "id": story["id"],
                    "title": story.get("title", "No title"),
                    "url": story.get("url", f"https://news.ycombinator.com/item?id={story['id']}"),
                    "score": story.get("score", 0),
                    "by": story.get("by", "unknown"),
                })

            return stories


# =============================================================================
# LLM SUMMARIZER WITH REAL MODELS
# =============================================================================

class LLMSummarizer:
    """
    Summarizes content using LLMs.
    Supports primary and fallback models.
    """

    # Model tiers - primary is more capable but might fail
    PRIMARY_MODEL = "anthropic/claude-sonnet-4"
    FALLBACK_MODELS = [
        "openai/gpt-4o-mini",
        "google/gemini-2.0-flash-001",
        "deepseek/deepseek-chat",
    ]

    # For testing failures - use an invalid model
    FAILING_MODEL = "invalid/model-that-does-not-exist"

    def __init__(self, llm_client: OpenRouterClient):
        self.client = llm_client

    async def summarize(
        self,
        content: str,
        model: str,
        max_tokens: int = 300,
    ) -> str:
        """Summarize content using specified model."""

        prompt = f"""<task>
Summarize the following content in 2-3 concise sentences.
Focus on the key points and make it engaging.
</task>

<content>
{content}
</content>

<format>
Return ONLY the summary, no preamble.
</format>"""

        response = await self.client.create_completion(
            messages=[LLMMessage(role="user", content=prompt)],
            routing=ModelRouting.single(model),
            temperature=0.3,
            max_tokens=max_tokens,
        )

        return response.content.strip()


# =============================================================================
# OBSERVER AGENT (REAL LLM-POWERED)
# =============================================================================

class RealObserver:
    """Observer that uses LLM reasoning for real failure scenarios."""

    def __init__(self, llm_client: OpenRouterClient):
        self.client = llm_client

    async def analyze_failure(
        self,
        plan: Task,
        failed_step: TaskStep,
    ) -> ObserverProposal:
        """Analyze a real failure and propose action."""

        # Build context
        fallback_info = ""
        if failed_step.fallback_config:
            fallback_info = f"Available fallbacks: {failed_step.fallback_config}"

        prompt = f"""<context>
You are monitoring a workflow execution. A step has failed.
</context>

<plan_goal>
{plan.goal}
</plan_goal>

<failed_step>
Name: {failed_step.name}
Type: {failed_step.agent_type}
Error: {failed_step.error}
Retries: {failed_step.retry_count}/{failed_step.max_retries}
{fallback_info}
</failed_step>

<decision_rules>
- RETRY: Transient errors (timeout, rate limit) and retries remain
- FALLBACK: Permanent failure but fallback exists (e.g., alternative model/API)
- SKIP: Non-critical step, plan can continue without it
- ABORT: Critical failure, no recovery possible
</decision_rules>

<task>
Choose ONE action and explain briefly.
If choosing FALLBACK, specify which fallback to use.
Format: ACTION: reason [FALLBACK_TARGET: value if applicable]
</task>"""

        response = await self.client.create_completion(
            messages=[LLMMessage(role="user", content=prompt)],
            routing=ModelRouting.single("anthropic/claude-sonnet-4"),
            temperature=0.0,
            max_tokens=150,
        )

        result = response.content.strip()
        first_line = result.split('\n')[0].upper()

        # Parse action - handle "ACTION: X" format
        first_word = first_line.split(':')[0].split()[0] if first_line else ""

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
            # Fallback: check first part before colon
            before_colon = first_line.split(':')[0]
            if "RETRY" in before_colon:
                action = "retry"
            elif "FALLBACK" in before_colon:
                action = "fallback"
            elif "SKIP" in before_colon:
                action = "skip"
            else:
                action = "abort"

        # Extract fallback target if present
        fallback_config = None
        if action == "fallback" and failed_step.fallback_config:
            # Use first available fallback
            if "models" in failed_step.fallback_config:
                fallback_config = {"model": failed_step.fallback_config["models"][0]}

        return ObserverProposal(
            proposal_type=action,
            step_id=failed_step.id,
            reason=result,
            fallback_config=fallback_config,
            confidence=0.9,
        )


# =============================================================================
# ORCHESTRATOR
# =============================================================================

class RealOrchestrator:
    """Orchestrator that executes real steps with real failures."""

    def __init__(self, llm_client: OpenRouterClient, simulate_failure: bool = False):
        self.llm_client = llm_client
        self.hn_client = HackerNewsClient()
        self.summarizer = LLMSummarizer(llm_client)
        self.observer = RealObserver(llm_client)
        self.simulate_failure = simulate_failure

    async def execute_step(self, plan: Task, step: TaskStep) -> bool:
        """Execute a single step. Returns True if successful."""

        step.status = StepStatus.RUNNING
        start_time = time.time()

        logger.info("Executing step", step_id=step.id, step_name=step.name, agent_type=step.agent_type)

        try:
            if step.agent_type == "http_fetch":
                # Real HackerNews API call
                stories = await self.hn_client.get_top_stories(
                    limit=step.inputs.get("limit", 3)
                )
                step.output = {"stories": stories}
                step.status = StepStatus.COMPLETED

            elif step.agent_type == "llm_summarize":
                # Real LLM summarization
                model = step.inputs.get("model", LLMSummarizer.PRIMARY_MODEL)

                # Simulate failure if requested (use invalid model)
                if self.simulate_failure and step.retry_count == 0:
                    model = LLMSummarizer.FAILING_MODEL
                    logger.info("Simulating failure with invalid model", model=model)

                stories = step.inputs.get("stories", [])
                content = "\n".join([
                    f"- {s['title']} (score: {s['score']}, by: {s['by']})"
                    for s in stories
                ])

                summary = await self.summarizer.summarize(content, model)
                step.output = {
                    "summary": summary,
                    "model_used": model,
                    "stories_count": len(stories),
                }
                step.status = StepStatus.COMPLETED

            elif step.agent_type == "format_digest":
                # Format the final digest
                summary = step.inputs.get("summary", "")
                stories = step.inputs.get("stories", [])

                digest = f"""
===== HACKERNEWS DIGEST =====

{summary}

----- TOP STORIES -----
"""
                for i, story in enumerate(stories, 1):
                    digest += f"\n{i}. {story['title']}\n   Score: {story['score']} | By: {story['by']}\n   {story['url']}\n"

                digest += "\n" + "=" * 30

                step.output = {"digest": digest}
                step.status = StepStatus.COMPLETED

            else:
                raise ValueError(f"Unknown agent type: {step.agent_type}")

            step.execution_time_ms = int((time.time() - start_time) * 1000)
            return True

        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.execution_time_ms = int((time.time() - start_time) * 1000)
            logger.error("Step failed", step_id=step.id, error=str(e))
            return False

    async def apply_proposal(
        self,
        plan: Task,
        step: TaskStep,
        proposal: ObserverProposal,
    ) -> bool:
        """Apply an Observer's proposal."""

        logger.info(
            "Applying observer proposal",
            proposal_type=proposal.proposal_type,
            step_id=proposal.step_id,
        )

        plan.modifications.append(
            f"[{proposal.proposal_type.upper()}] {step.name}: {proposal.reason}"
        )

        if proposal.proposal_type == "retry":
            step.status = StepStatus.PENDING
            step.retry_count += 1
            step.error = None
            return True

        elif proposal.proposal_type == "fallback":
            step.status = StepStatus.PENDING
            step.retry_count += 1
            step.error = None

            # Apply fallback configuration
            if proposal.fallback_config and "model" in proposal.fallback_config:
                step.inputs["model"] = proposal.fallback_config["model"]
                logger.info("Switched to fallback model", model=proposal.fallback_config["model"])

            return True

        elif proposal.proposal_type == "skip":
            step.status = StepStatus.SKIPPED
            return True

        elif proposal.proposal_type == "abort":
            plan.status = "aborted"
            return False

        return False

    async def run_plan(self, plan: Task) -> Task:
        """Execute the plan with Observer monitoring."""

        start_time = time.time()
        max_iterations = 15
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # Find next pending step
            next_step = next(
                (s for s in plan.steps if s.status == StepStatus.PENDING),
                None
            )

            if not next_step:
                plan.status = "completed"
                break

            if plan.status == "aborted":
                break

            # Populate inputs from previous steps
            self._resolve_step_inputs(plan, next_step)

            # Execute
            success = await self.execute_step(plan, next_step)

            if not success:
                # Consult Observer
                proposal = await self.observer.analyze_failure(plan, next_step)
                plan.findings.append(
                    f"Observer: {next_step.name} failed -> {proposal.proposal_type}: {proposal.reason}"
                )

                should_continue = await self.apply_proposal(plan, next_step, proposal)
                if not should_continue:
                    break

        plan.total_time_ms = int((time.time() - start_time) * 1000)
        return plan

    def _resolve_step_inputs(self, plan: Task, step: TaskStep):
        """Resolve step inputs from previous step outputs."""

        if step.agent_type == "llm_summarize":
            # Get stories from fetch step
            fetch_step = next(
                (s for s in plan.steps if s.agent_type == "http_fetch" and s.status == StepStatus.COMPLETED),
                None
            )
            if fetch_step and fetch_step.output:
                step.inputs["stories"] = fetch_step.output["stories"]

        elif step.agent_type == "format_digest":
            # Get summary from summarize step
            summarize_step = next(
                (s for s in plan.steps if s.agent_type == "llm_summarize" and s.status == StepStatus.COMPLETED),
                None
            )
            fetch_step = next(
                (s for s in plan.steps if s.agent_type == "http_fetch" and s.status == StepStatus.COMPLETED),
                None
            )
            if summarize_step and summarize_step.output:
                step.inputs["summary"] = summarize_step.output["summary"]
            if fetch_step and fetch_step.output:
                step.inputs["stories"] = fetch_step.output["stories"]


# =============================================================================
# TEST RUNNER
# =============================================================================

async def run_real_world_test(simulate_failure: bool = True):
    """
    Run the real-world Observer test.

    Args:
        simulate_failure: If True, force the primary LLM to fail to test recovery.
    """

    print("\n" + "=" * 70)
    print("REAL-WORLD OBSERVER COURSE CORRECTION TEST")
    print("=" * 70)
    print(f"\nSimulating primary model failure: {simulate_failure}")
    print("This test uses REAL APIs: HackerNews + OpenRouter LLMs\n")

    # Create the plan
    plan = Task(
        id="real_world_test_001",
        goal="Fetch top HackerNews stories and create a summarized digest",
        steps=[
            TaskStep(
                id="step_1",
                name="fetch_hackernews",
                description="Fetch top 3 stories from HackerNews API",
                agent_type="http_fetch",
                inputs={"limit": 3},
            ),
            TaskStep(
                id="step_2",
                name="summarize_stories",
                description="Summarize the stories using LLM",
                agent_type="llm_summarize",
                inputs={"model": LLMSummarizer.PRIMARY_MODEL},
                fallback_config={
                    "models": LLMSummarizer.FALLBACK_MODELS,
                },
            ),
            TaskStep(
                id="step_3",
                name="format_digest",
                description="Format the final digest output",
                agent_type="format_digest",
            ),
        ],
    )

    print("--- PLAN ---")
    for step in plan.steps:
        fallback = f" [fallbacks: {step.fallback_config}]" if step.fallback_config else ""
        print(f"  [{step.id}] {step.name}: {step.description}{fallback}")

    print("\n--- EXECUTION LOG ---\n")

    # Run with real LLM client
    async with OpenRouterClient() as client:
        orchestrator = RealOrchestrator(
            llm_client=client,
            simulate_failure=simulate_failure,
        )
        result = await orchestrator.run_plan(plan)

    # Results
    print("\n--- FINAL PLAN STATE ---")
    print(f"Status: {result.status}")
    print(f"Total time: {result.total_time_ms}ms")

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
            if "stories" in step.output:
                output_summary = f" ({len(step.output['stories'])} stories fetched)"
            elif "summary" in step.output:
                output_summary = f" (model: {step.output.get('model_used', 'unknown')})"
            elif "digest" in step.output:
                output_summary = " (digest formatted)"

        time_info = f" [{step.execution_time_ms}ms]"
        error_info = f" ERROR: {step.error}" if step.error else ""

        print(f"  {status_icon} {step.id} - {step.name}{output_summary}{time_info}{error_info}")

    if result.findings:
        print(f"\nObserver Findings:")
        for finding in result.findings:
            print(f"  - {finding}")

    if result.modifications:
        print(f"\nPlan Modifications:")
        for mod in result.modifications:
            print(f"  - {mod}")

    # Print the actual digest if successful
    if result.status == "completed":
        format_step = next((s for s in result.steps if s.name == "format_digest"), None)
        if format_step and format_step.output:
            print("\n" + format_step.output["digest"])

    # Verify
    print("\n--- TEST RESULT ---")

    if simulate_failure:
        success_criteria = [
            ("Plan completed", result.status == "completed"),
            ("Observer detected failure", len(result.findings) > 0),
            ("Fallback model was used", any(
                s.output and s.output.get("model_used") != LLMSummarizer.PRIMARY_MODEL
                for s in result.steps if s.agent_type == "llm_summarize"
            )),
            ("Digest was generated", any(
                s.output and "digest" in s.output
                for s in result.steps
            )),
        ]
    else:
        success_criteria = [
            ("Plan completed", result.status == "completed"),
            ("Primary model was used", any(
                s.output and s.output.get("model_used") == LLMSummarizer.PRIMARY_MODEL
                for s in result.steps if s.agent_type == "llm_summarize"
            )),
            ("Digest was generated", any(
                s.output and "digest" in s.output
                for s in result.steps
            )),
        ]

    all_passed = True
    for criteria, passed in success_criteria:
        icon = "[PASS]" if passed else "[FAIL]"
        print(f"  {icon} {criteria}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        if simulate_failure:
            print("TEST PASSED: Observer detected real LLM failure and recovered via fallback")
        else:
            print("TEST PASSED: Plan executed successfully with primary model")
    else:
        print("TEST FAILED: Some criteria not met")
    print("=" * 70 + "\n")

    return all_passed


async def main():
    """Run both scenarios: with and without simulated failure."""

    print("\n" + "#" * 70)
    print("# REAL-WORLD OBSERVER TESTS")
    print("#" * 70)

    # Test 1: With simulated failure (primary model fails)
    print("\n\n### TEST 1: Primary Model Fails -> Observer Recovers ###")
    failure_test = await run_real_world_test(simulate_failure=True)

    # Small delay between tests
    await asyncio.sleep(2)

    # Test 2: Normal operation (no failure)
    print("\n\n### TEST 2: Normal Operation (No Failure) ###")
    normal_test = await run_real_world_test(simulate_failure=False)

    # Summary
    print("\n" + "#" * 70)
    print("# SUMMARY")
    print("#" * 70)
    print(f"  Failure Recovery Test: {'PASSED' if failure_test else 'FAILED'}")
    print(f"  Normal Operation Test: {'PASSED' if normal_test else 'FAILED'}")
    print("#" * 70 + "\n")

    return failure_test and normal_test


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
