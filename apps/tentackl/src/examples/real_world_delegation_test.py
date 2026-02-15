"""
Real-World Delegation System Test

Tests the core delegation system with Observer-based course correction
using REAL LLM calls and simulated API failures.

This validates that the Observer integration works in the actual system,
not just in isolated example files.

Scenario: HackerNews Digest Pipeline
1. Fetch top stories (will succeed)
2. Summarize with invalid model (will fail -> Observer proposes FALLBACK)
3. After fallback, summarize succeeds
4. Optional enrichment fails (non-critical -> Observer proposes SKIP)
5. Send email (checkpoint, auto-approved for test)

Expected behavior:
- Step 2 fails, Observer analyzes and proposes FALLBACK
- System switches to backup model
- Step 4 is non-critical, Observer proposes SKIP
- Plan completes successfully despite failures
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any, Optional
import httpx
import structlog

from src.domain.tasks.models import (
    Task,
    TaskStep,
    TaskStatus,
    StepStatus,
    FallbackConfig,
    CheckpointConfig,
)
from src.infrastructure.tasks.task_orchestrator import TaskOrchestratorAgent
from src.infrastructure.tasks.task_observer import TaskObserverAgent
from src.infrastructure.execution_runtime.plugin_executor import execute_step, ExecutionResult
from src.llm.openrouter_client import OpenRouterClient, ModelRouting
from src.interfaces.llm import LLMMessage

logger = structlog.get_logger(__name__)


# =============================================================================
# MOCK PLAN STORE (In-memory for testing)
# =============================================================================

class InMemoryPlanStore:
    """Simple in-memory plan store for testing."""

    def __init__(self):
        self.plans: Dict[str, Task] = {}
        self.findings = []

    async def create_plan(self, plan: Task) -> str:
        self.plans[plan.id] = plan
        return plan.id

    async def get_plan(self, plan_id: str) -> Optional[Task]:
        return self.plans.get(plan_id)

    async def update_plan(self, plan_id: str, updates: Dict[str, Any]) -> bool:
        plan = self.plans.get(plan_id)
        if not plan:
            return False
        for key, value in updates.items():
            if key == "status" and isinstance(value, TaskStatus):
                plan.status = value
            elif hasattr(plan, key):
                setattr(plan, key, value)
        plan.updated_at = datetime.utcnow()
        return True

    async def update_step(self, plan_id: str, step_id: str, updates: Dict[str, Any]) -> bool:
        plan = self.plans.get(plan_id)
        if not plan:
            return False
        step = plan.get_step_by_id(step_id)
        if not step:
            return False
        for key, value in updates.items():
            if key == "status":
                step.status = StepStatus(value) if isinstance(value, str) else value
            elif key == "fallback_config" and isinstance(value, dict):
                # Deserialize fallback_config from dict
                step.fallback_config = FallbackConfig.from_dict(value) if value else None
            elif hasattr(step, key):
                setattr(step, key, value)
        return True

    async def add_finding(self, plan_id: str, finding) -> bool:
        self.findings.append(finding)
        plan = self.plans.get(plan_id)
        if plan:
            plan.accumulated_findings.append(finding)
        return True

    async def _connect(self):
        pass

    async def _disconnect(self):
        pass


# =============================================================================
# CUSTOM SUBAGENTS FOR TESTING
# =============================================================================

class TestHttpFetchSubagent:
    """Fetches real data from HackerNews API."""

    @staticmethod
    async def execute(step: TaskStep, **kwargs) -> ExecutionResult:
        url = step.inputs.get("url", "https://hacker-news.firebaseio.com/v0/topstories.json")
        limit = step.inputs.get("limit", 3)

        start_time = asyncio.get_event_loop().time()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                story_ids = response.json()[:limit]

                # Fetch story details
                stories = []
                for story_id in story_ids:
                    story_url = f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
                    story_resp = await client.get(story_url)
                    if story_resp.status_code == 200:
                        story = story_resp.json()
                        stories.append({
                            "id": story.get("id"),
                            "title": story.get("title"),
                            "url": story.get("url", ""),
                            "score": story.get("score", 0),
                        })

            execution_time = int((asyncio.get_event_loop().time() - start_time) * 1000)

            return ExecutionResult(
                status="success",
                output={"stories": stories, "count": len(stories)},
                execution_time_ms=execution_time,
                metadata={"source": "hackernews"},
            )

        except Exception as e:
            return ExecutionResult(
                status="error",
                output=None,
                error=str(e),
                execution_time_ms=0,
            )


class TestSummarizeSubagent:
    """Summarizes content using LLM - can be configured to fail."""

    def __init__(self, llm_client: OpenRouterClient):
        self.llm_client = llm_client

    async def execute(self, step: TaskStep, **kwargs) -> ExecutionResult:
        stories = step.inputs.get("stories", [])

        # Check for fallback model (set by Observer)
        model = step.inputs.get("fallback_model") or step.inputs.get("model", "anthropic/claude-3-5-haiku-20241022")

        # Simulate failure for invalid model
        if model == "invalid/model-that-does-not-exist":
            return ExecutionResult(
                status="error",
                output=None,
                error=f"Model not found: {model}",
                execution_time_ms=100,
            )

        start_time = asyncio.get_event_loop().time()

        try:
            # Build summary prompt
            story_text = "\n".join([
                f"- {s['title']} (score: {s['score']})"
                for s in stories
            ])

            prompt = f"""Summarize these HackerNews stories in 2-3 sentences:

{story_text}

Provide a brief, engaging summary."""

            response = await self.llm_client.create_completion(
                messages=[LLMMessage(role="user", content=prompt)],
                routing=ModelRouting.single(model),
                temperature=0.3,
                max_tokens=200,
            )

            execution_time = int((asyncio.get_event_loop().time() - start_time) * 1000)

            return ExecutionResult(
                status="success",
                output={
                    "summary": response.content,
                    "model_used": model,
                    "story_count": len(stories),
                },
                execution_time_ms=execution_time,
                metadata={"model": model},
            )

        except Exception as e:
            return ExecutionResult(
                status="error",
                output=None,
                error=str(e),
                execution_time_ms=0,
            )


class TestEnrichSubagent:
    """Optional enrichment - configured to always fail for testing SKIP."""

    @staticmethod
    async def execute(step: TaskStep, **kwargs) -> ExecutionResult:
        # Simulate enrichment service failure
        return ExecutionResult(
            status="error",
            output=None,
            error="Enrichment service temporarily unavailable (503)",
            execution_time_ms=50,
        )


class TestNotifySubagent:
    """Simulates sending notification."""

    @staticmethod
    async def execute(step: TaskStep, **kwargs) -> ExecutionResult:
        to = step.inputs.get("to", "user@example.com")
        subject = step.inputs.get("subject", "Digest")
        body = step.inputs.get("body", "")

        # Simulate successful send
        return ExecutionResult(
            status="success",
            output={
                "sent": True,
                "to": to,
                "subject": subject,
                "body_preview": body[:100] if body else "",
            },
            execution_time_ms=200,
            metadata={"channel": "email"},
        )


# =============================================================================
# TEST RUNNER
# =============================================================================

async def run_real_world_test():
    """Run the full real-world delegation test."""

    print("\n" + "=" * 70)
    print("REAL-WORLD DELEGATION SYSTEM TEST")
    print("=" * 70)
    print("\nThis test validates Observer-based course correction in the CORE SYSTEM")
    print("using REAL LLM calls and simulated failures.\n")

    # Create plan store
    store = InMemoryPlanStore()

    # Create LLM client
    llm_client = OpenRouterClient()
    await llm_client.__aenter__()

    try:
        # Create the plan
        plan = Task(
            id="real_world_test_001",
            user_id="test_user",
            goal="Fetch HackerNews stories, summarize them, and send a digest email",
            status=TaskStatus.READY,
            steps=[
                # Step 1: Fetch stories (will succeed)
                TaskStep(
                    id="step_fetch",
                    name="fetch_hn_stories",
                    description="Fetch top 3 stories from HackerNews",
                    agent_type="http_fetch",
                    inputs={
                        "url": "https://hacker-news.firebaseio.com/v0/topstories.json",
                        "limit": 3,
                    },
                    is_critical=True,
                ),
                # Step 2: Summarize (will fail with invalid model, then fallback)
                TaskStep(
                    id="step_summarize",
                    name="summarize_stories",
                    description="Summarize stories using LLM",
                    agent_type="summarize",
                    inputs={
                        "stories": "{{step_fetch.output.stories}}",
                        "model": "invalid/model-that-does-not-exist",  # Will fail!
                    },
                    dependencies=["step_fetch"],
                    is_critical=True,
                    fallback_config=FallbackConfig(
                        models=["google/gemini-2.0-flash-001"],  # Backup model (less rate-limited)
                    ),
                ),
                # Step 3: Optional enrichment (will fail, should be skipped)
                TaskStep(
                    id="step_enrich",
                    name="enrich_with_metadata",
                    description="Add metadata enrichment (optional)",
                    agent_type="enrich",
                    inputs={"data": "{{step_summarize.output}}"},
                    dependencies=["step_summarize"],
                    is_critical=False,  # Non-critical!
                ),
                # Step 4: Send notification
                TaskStep(
                    id="step_notify",
                    name="send_digest",
                    description="Send digest email",
                    agent_type="notify",
                    inputs={
                        "to": "user@example.com",
                        "subject": "Your HackerNews Digest",
                        "body": "{{step_summarize.output.summary}}",
                    },
                    dependencies=["step_summarize"],  # Note: depends on summarize, not enrich
                    is_critical=True,
                    checkpoint_required=False,  # Skip checkpoint for test
                ),
            ],
        )

        await store.create_task(plan)

        # Create custom subagent executor
        summarize_subagent = TestSummarizeSubagent(llm_client)

        def resolve_step_inputs(plan: Task, step: TaskStep) -> Dict[str, Any]:
            """Resolve template references in step inputs."""
            resolved = {}
            for key, value in step.inputs.items():
                if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                    # Parse template: {{step_id.output.field}}
                    template = value[2:-2].strip()
                    parts = template.split(".")
                    if len(parts) >= 2:
                        ref_step_id = parts[0]
                        ref_step = plan.get_step_by_id(ref_step_id)
                        if ref_step and ref_step.outputs:
                            # Navigate the output path
                            result_val = ref_step.outputs
                            for part in parts[1:]:
                                if part == "output":
                                    continue  # Skip 'output' as it's already the outputs dict
                                if isinstance(result_val, dict) and part in result_val:
                                    result_val = result_val[part]
                                else:
                                    result_val = None
                                    break
                            resolved[key] = result_val
                        else:
                            resolved[key] = None
                    else:
                        resolved[key] = value
                else:
                    resolved[key] = value
            return resolved

        async def custom_execute_step(plan: Task, step: TaskStep) -> Dict[str, Any]:
            """Route to appropriate test subagent and return dict format."""
            # Resolve template references in inputs
            resolved_inputs = resolve_step_inputs(plan, step)
            step.inputs.update(resolved_inputs)

            if step.agent_type == "http_fetch":
                result = await TestHttpFetchSubagent.execute(step)
            elif step.agent_type == "summarize":
                result = await summarize_subagent.execute(step)
            elif step.agent_type == "enrich":
                result = await TestEnrichSubagent.execute(step)
            elif step.agent_type == "notify":
                result = await TestNotifySubagent.execute(step)
            else:
                result = ExecutionResult(
                    status="error",
                    output=None,
                    error=f"Unknown agent type: {step.agent_type}",
                )

            # Convert ExecutionResult to dict format expected by orchestrator
            if result.success:
                return {
                    "status": "success",
                    "output": result.output,
                    "findings": [{"type": step.agent_type, **result.metadata}] if result.metadata else [],
                    "execution_time_ms": result.execution_time_ms,
                }
            else:
                return {
                    "status": "error",
                    "error": result.error or "Subagent execution failed",
                    "output": result.output,
                    "execution_time_ms": result.execution_time_ms,
                }

        # Create orchestrator with our store
        # Create a custom observer with a non-rate-limited model
        custom_observer = TaskObserverAgent(
            llm_client=llm_client,
            plan_store=store,
            model="google/gemini-2.0-flash-001",  # Less likely to be rate-limited
        )

        orchestrator = TaskOrchestratorAgent(
            llm_client=llm_client,
            plan_store=store,
            observer=custom_observer,
        )

        # Replace the execute_step method to use our custom subagents
        async def patched_execute_step(self, plan: Task, step: TaskStep):
            return await custom_execute_step(plan, step)

        import types
        orchestrator._execute_step = types.MethodType(patched_execute_step, orchestrator)

        # Run execution cycles
        print("Starting execution...\n")

        results = []
        max_cycles = 10
        cycle = 0

        while cycle < max_cycles:
            cycle += 1
            print(f"--- Cycle {cycle} ---")

            result = await orchestrator.execute_cycle(plan.id)
            results.append(result)

            status = result.get("status")
            step_id = result.get("step_id", "N/A")
            observer_action = result.get("observer_action", "")

            print(f"Status: {status}")
            print(f"Step: {step_id}")
            if observer_action:
                print(f"Observer Action: {observer_action}")
            if result.get("fallback_target"):
                print(f"Fallback Target: {result.get('fallback_target')}")
            if result.get("error"):
                print(f"Error: {result.get('error')[:100]}")
            print()

            # Check terminal states
            if status == "completed":
                print("✅ PLAN COMPLETED SUCCESSFULLY!")
                break
            elif status in ("failed", "error", "plan_aborted"):
                print(f"❌ PLAN FAILED: {result.get('error', result.get('abort_reason'))}")
                break
            elif status == "blocked":
                print("⚠️ PLAN BLOCKED")
                break

        # Print summary
        print("\n" + "=" * 70)
        print("EXECUTION SUMMARY")
        print("=" * 70)

        # Get final plan state
        final_plan = await store.get_task(plan.id)

        print(f"\nFinal Status: {final_plan.status.value}")
        print(f"Total Cycles: {cycle}")
        print("\nStep Results:")

        for step in final_plan.steps:
            status_icon = {
                StepStatus.DONE: "✅",
                StepStatus.FAILED: "❌",
                StepStatus.SKIPPED: "⏭️",
                StepStatus.PENDING: "⏳",
                StepStatus.RUNNING: "🔄",
            }.get(step.status, "❓")

            print(f"  {status_icon} {step.name}: {step.status.value}")
            if step.outputs:
                if step.agent_type == "summarize":
                    summary = step.outputs.get("summary", "")[:100]
                    print(f"      Summary: {summary}...")
                elif step.agent_type == "http_fetch":
                    count = step.outputs.get("count", 0)
                    print(f"      Fetched {count} stories")

        # Print Observer findings
        print("\nObserver Findings:")
        observer_findings = [f for f in store.findings if f.type == "observer_proposal"]
        for finding in observer_findings:
            content = finding.content
            print(f"  • Step: {finding.step_id}")
            print(f"    Action: {content.get('proposal_type', 'N/A').upper()}")
            print(f"    Reason: {content.get('reason', 'N/A')[:80]}")
            if content.get("fallback_target"):
                print(f"    Fallback: {content.get('fallback_target')}")
            print()

        # Validate test expectations
        print("=" * 70)
        print("TEST VALIDATION")
        print("=" * 70)

        expectations = [
            ("Plan completed", final_plan.status == TaskStatus.COMPLETED),
            ("Fetch step succeeded", final_plan.steps[0].status == StepStatus.DONE),
            ("Summarize step succeeded (after fallback)", final_plan.steps[1].status == StepStatus.DONE),
            ("Enrich step was skipped (non-critical)", final_plan.steps[2].status == StepStatus.SKIPPED),
            ("Notify step succeeded", final_plan.steps[3].status == StepStatus.DONE),
            ("Observer proposed FALLBACK", any(
                f.content.get("proposal_type") == "fallback"
                for f in observer_findings
            )),
            ("Observer proposed SKIP", any(
                f.content.get("proposal_type") == "skip"
                for f in observer_findings
            )),
        ]

        all_passed = True
        for name, passed in expectations:
            status_icon = "✅" if passed else "❌"
            print(f"  {status_icon} {name}")
            if not passed:
                all_passed = False

        print("\n" + "=" * 70)
        if all_passed:
            print("🎉 ALL TESTS PASSED!")
            print("Observer-based course correction is working in the CORE SYSTEM.")
        else:
            print("⚠️ SOME TESTS FAILED")
            print("Check the output above for details.")
        print("=" * 70 + "\n")

        return all_passed

    finally:
        await llm_client.__aexit__(None, None, None)


async def main():
    success = await run_real_world_test()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
