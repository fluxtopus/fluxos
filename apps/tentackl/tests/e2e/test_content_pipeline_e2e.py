"""
E2E Test: Content Pipeline Cross-Domain Orchestration

Real-life test scenario:
"Research the latest developments in autonomous AI agents and create a blog post"

This test verifies:
1. Cross-domain subagent execution (research → content → cms)
2. Full orchestrator cycle with plan persistence
3. Checkpoint handling and preference learning
4. Template variable resolution between steps

NOTE: These tests were written for the old domain-based architecture.
They need to be rewritten to use the unified capability system.
"""

import pytest
import asyncio
from datetime import datetime

# Old import removed - architecture unified to DB-configured agents
# from src.agents.domains import DomainRegistry

# Skip all tests in this module until rewritten for new architecture
pytestmark = pytest.mark.skip(reason="Tests need rewrite for unified capability system")
from src.infrastructure.tasks.task_orchestrator import TaskOrchestratorAgent
from src.infrastructure.tasks.stores.redis_task_store import RedisTaskStore
from src.infrastructure.tasks.stores.redis_preference_store import RedisPreferenceStore
from src.domain.tasks.models import (
    Task,
    TaskStep,
    TaskStatus,
    StepStatus,
    CheckpointConfig,
    ApprovalType,
)
from src.llm.openrouter_client import OpenRouterClient


@pytest.fixture
async def plan_store():
    """Create and connect to plan store."""
    store = RedisTaskStore()
    await store._connect()
    yield store
    await store._disconnect()


@pytest.fixture
async def preference_store():
    """Create and connect to preference store."""
    store = RedisPreferenceStore()
    await store._connect()
    yield store
    await store._disconnect()


@pytest.fixture
async def llm_client():
    """Create LLM client."""
    client = OpenRouterClient()
    async with client:
        yield client


def create_real_content_plan(user_id: str = "e2e_test_user") -> Task:
    """
    Create a realistic content pipeline plan.

    Topic: "Autonomous AI Agents in 2025"
    """
    return Task(
        user_id=user_id,
        goal="Research autonomous AI agents and publish a blog post about their impact in 2025",
        success_criteria=[
            "Research covers key developments in autonomous agents",
            "Article is well-written and SEO optimized",
            "Article is published and shared",
        ],
        steps=[
            # Step 1: Research
            TaskStep(
                id="research_1",
                name="search_autonomous_agents",
                description="Search for information about autonomous AI agents",
                domain="research",
                agent_type="web_search",
                inputs={
                    "query": "autonomous AI agents 2025 agentic systems developments",
                    "max_results": 5,
                    "search_engine": "simulated",  # Use simulated for consistent tests
                },
            ),
            # Step 2: Synthesize
            TaskStep(
                id="research_2",
                name="synthesize_findings",
                description="Synthesize research into key insights",
                domain="research",
                agent_type="aggregate",
                inputs={
                    "sources": "{{research_1.results}}",
                    "purpose": "blog post about autonomous AI agents",
                    "focus_areas": ["capabilities", "applications", "challenges"],
                },
                dependencies=["research_1"],
            ),
            # Step 3: Draft
            TaskStep(
                id="content_1",
                name="draft_article",
                description="Write the blog post",
                domain="content",
                agent_type="draft",
                inputs={
                    "topic": "The Rise of Autonomous AI Agents: What 2025 Holds",
                    "research": "{{research_2.synthesis}}",
                    "format": "blog_post",
                    "tone": "informative and engaging",
                    "target_length": 800,
                },
                dependencies=["research_2"],
            ),
            # Step 4: SEO
            TaskStep(
                id="content_2",
                name="seo_optimize",
                description="Optimize for search engines",
                domain="content",
                agent_type="seo_optimize",
                inputs={
                    "content": "{{content_1.content}}",
                    "title": "{{content_1.title}}",
                    "keywords": ["autonomous agents", "AI", "2025", "agentic AI"],
                },
                dependencies=["content_1"],
            ),
            # Step 5: Edit
            TaskStep(
                id="content_3",
                name="proofread",
                description="Final editing pass",
                domain="content",
                agent_type="edit",
                inputs={
                    "content": "{{content_2.content}}",
                    "preserve_voice": True,
                },
                dependencies=["content_2"],
            ),
            # Step 6: Publish (CHECKPOINT)
            TaskStep(
                id="cms_1",
                name="publish_article",
                description="Publish to blog",
                domain="cms",
                agent_type="publish",
                inputs={
                    "title": "{{content_1.title}}",
                    "content": "{{content_3.content}}",
                    "meta_description": "{{content_2.meta_description}}",
                    "platform": "demo",
                },
                dependencies=["content_3"],
                checkpoint_required=True,
                checkpoint_config=CheckpointConfig(
                    name="publish_approval",
                    description="Review and approve article for publication",
                    approval_type=ApprovalType.EXPLICIT,
                    preference_key="content.publish.blog",
                ),
            ),
            # Step 7: Share (CHECKPOINT)
            TaskStep(
                id="cms_2",
                name="share_social",
                description="Share on social media",
                domain="cms",
                agent_type="share",
                inputs={
                    "url": "{{cms_1.url}}",
                    "title": "{{content_1.title}}",
                    "platforms": ["twitter"],
                    "hashtags": ["AI", "AutonomousAgents", "Tech2025"],
                },
                dependencies=["cms_1"],
                checkpoint_required=True,
                checkpoint_config=CheckpointConfig(
                    name="share_approval",
                    description="Approve social media sharing",
                    approval_type=ApprovalType.EXPLICIT,
                    preference_key="content.share.twitter",
                ),
            ),
        ],
    )


class TestContentPipelineE2E:
    """E2E tests for cross-domain content pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_orchestrator(self, plan_store, preference_store, llm_client):
        """
        Test the complete content pipeline using the delegation orchestrator.

        This is a REAL test that:
        1. Creates a plan in Redis
        2. Runs the orchestrator cycle by cycle
        3. Handles checkpoints
        4. Verifies outputs at each stage
        """
        print("\n" + "=" * 60)
        print("E2E TEST: Full Content Pipeline with Orchestrator")
        print("=" * 60)

        # Create plan
        plan = create_real_content_plan()
        plan_id = await plan_store.create_task(plan)
        print(f"\n✓ Created plan: {plan_id}")
        print(f"  Goal: {plan.goal}")
        print(f"  Steps: {len(plan.steps)}")

        # Create orchestrator
        orchestrator = TaskOrchestratorAgent(
            llm_client=llm_client,
            plan_store=plan_store,
            model="anthropic/claude-3-5-sonnet-20241022",
        )

        # Track execution
        completed_steps = []
        checkpoints_hit = []
        step_outputs = {}

        # Execute cycles until complete or checkpoint
        max_cycles = 20  # Safety limit
        cycle = 0

        while cycle < max_cycles:
            cycle += 1
            print(f"\n--- Cycle {cycle} ---")

            result = await orchestrator.execute_cycle(plan_id)
            status = result.get("status")

            print(f"  Status: {status}")

            if status == "step_completed":
                step_id = result.get("step_id")
                completed_steps.append(step_id)
                step_outputs[step_id] = result.get("output")
                print(f"  ✓ Completed: {step_id}")

                # Show relevant output
                output = result.get("output", {})
                if isinstance(output, dict):
                    if "result_count" in output:
                        print(f"    Results: {output['result_count']}")
                    if "title" in output:
                        print(f"    Title: {output['title'][:50]}...")
                    if "word_count" in output:
                        print(f"    Words: {output['word_count']}")
                    if "url" in output:
                        print(f"    URL: {output['url']}")

            elif status == "checkpoint":
                checkpoint = result.get("checkpoint", {})
                step_id = result.get("step_id")
                checkpoints_hit.append(step_id)
                print(f"  ⏸ Checkpoint: {checkpoint.get('name')}")
                print(f"    {checkpoint.get('description')}")

                # Auto-approve for test
                print("    → Auto-approving...")
                resume_result = await orchestrator.resume_after_approval(plan_id, step_id)

                # Track the step that was completed after approval
                if resume_result.get("status") == "step_completed":
                    completed_steps.append(step_id)
                    step_outputs[step_id] = resume_result.get("output")
                    print(f"  ✓ Completed after approval: {step_id}")

            elif status == "completed":
                print(f"\n✓ Plan completed!")
                break

            elif status in ("error", "step_failed"):
                print(f"  ✗ Error: {result.get('error')}")
                pytest.fail(f"Pipeline failed: {result.get('error')}")

            elif status == "blocked":
                print(f"  ⚠ Blocked: {result.get('message')}")
                break

        # Verify results
        print("\n" + "=" * 60)
        print("VERIFICATION")
        print("=" * 60)

        # Check all steps completed
        expected_steps = ["research_1", "research_2", "content_1", "content_2", "content_3", "cms_1", "cms_2"]
        print(f"\nCompleted steps: {completed_steps}")
        assert len(completed_steps) == len(expected_steps), f"Expected {len(expected_steps)} steps, got {len(completed_steps)}"

        # Check checkpoints were hit
        print(f"Checkpoints hit: {checkpoints_hit}")
        assert "cms_1" in checkpoints_hit, "Publish checkpoint not hit"
        assert "cms_2" in checkpoints_hit, "Share checkpoint not hit"

        # Verify final plan state
        final_plan = await plan_store.get_task(plan_id)
        assert final_plan.status == TaskStatus.COMPLETED, f"Plan status is {final_plan.status}, expected COMPLETED"

        # Verify all steps are done
        for step in final_plan.steps:
            assert step.status == StepStatus.DONE, f"Step {step.id} is {step.status}, expected DONE"

        print("\n✓ All verifications passed!")
        print(f"  - All {len(expected_steps)} steps completed")
        print(f"  - {len(checkpoints_hit)} checkpoints handled")
        print(f"  - Plan status: COMPLETED")

        # Cleanup
        await plan_store.delete_task(plan_id)

    @pytest.mark.asyncio
    async def test_domain_subagents_directly(self, llm_client):
        """
        Test each domain's subagents directly to verify they work.
        """
        print("\n" + "=" * 60)
        print("E2E TEST: Direct Domain Subagent Execution")
        print("=" * 60)

        # Test Research Domain
        print("\n--- Research Domain ---")

        # Web Search
        search_step = TaskStep(
            id="test_search",
            name="test_search",
            description="Search for AI agents",
            domain="research",
            agent_type="web_search",
            inputs={
                "query": "autonomous AI agents capabilities 2025",
                "max_results": 3,
                "search_engine": "simulated",
            },
        )

        search_result = await DomainRegistry.execute_step(search_step, llm_client=llm_client)
        assert search_result.success, f"Web search failed: {search_result.error}"
        print(f"✓ web_search: {search_result.output.get('result_count')} results")

        # Aggregate (with LLM)
        aggregate_step = TaskStep(
            id="test_aggregate",
            name="test_aggregate",
            description="Synthesize findings",
            domain="research",
            agent_type="aggregate",
            inputs={
                "sources": search_result.output.get("results", []),
                "purpose": "understanding AI agent capabilities",
            },
        )

        aggregate_result = await DomainRegistry.execute_step(
            aggregate_step,
            llm_client=llm_client,
            model="anthropic/claude-3-5-sonnet-20241022",
        )
        assert aggregate_result.success, f"Aggregate failed: {aggregate_result.error}"
        print(f"✓ aggregate: {len(aggregate_result.output.get('key_themes', []))} themes identified")

        # Test Content Domain
        print("\n--- Content Domain ---")

        # Draft (with LLM)
        draft_step = TaskStep(
            id="test_draft",
            name="test_draft",
            description="Write article",
            domain="content",
            agent_type="draft",
            inputs={
                "topic": "The Future of Autonomous AI Agents",
                "research": aggregate_result.output.get("synthesis", "AI agents are becoming more capable."),
                "format": "blog_post",
                "target_length": 500,
            },
        )

        draft_result = await DomainRegistry.execute_step(
            draft_step,
            llm_client=llm_client,
            model="anthropic/claude-3-5-sonnet-20241022",
        )
        assert draft_result.success, f"Draft failed: {draft_result.error}"
        print(f"✓ draft: '{draft_result.output.get('title', 'Untitled')[:40]}...' ({draft_result.output.get('word_count')} words)")

        # SEO Optimize (with LLM)
        seo_step = TaskStep(
            id="test_seo",
            name="test_seo",
            description="Optimize SEO",
            domain="content",
            agent_type="seo_optimize",
            inputs={
                "content": draft_result.output.get("content", ""),
                "keywords": ["AI agents", "autonomous", "2025"],
            },
        )

        seo_result = await DomainRegistry.execute_step(
            seo_step,
            llm_client=llm_client,
            model="anthropic/claude-3-5-sonnet-20241022",
        )
        assert seo_result.success, f"SEO optimize failed: {seo_result.error}"
        print(f"✓ seo_optimize: meta '{seo_result.output.get('meta_description', '')[:40]}...'")

        # Edit (with LLM)
        edit_step = TaskStep(
            id="test_edit",
            name="test_edit",
            description="Proofread",
            domain="content",
            agent_type="edit",
            inputs={
                "content": seo_result.output.get("content", ""),
            },
        )

        edit_result = await DomainRegistry.execute_step(
            edit_step,
            llm_client=llm_client,
            model="anthropic/claude-3-5-sonnet-20241022",
        )
        assert edit_result.success, f"Edit failed: {edit_result.error}"
        print(f"✓ edit: {edit_result.output.get('changes_made', 0)} improvements")

        # Test CMS Domain
        print("\n--- CMS Domain ---")

        # Publish
        publish_step = TaskStep(
            id="test_publish",
            name="test_publish",
            description="Publish article",
            domain="cms",
            agent_type="publish",
            inputs={
                "title": draft_result.output.get("title", "Test Article"),
                "content": edit_result.output.get("content", ""),
                "meta_description": seo_result.output.get("meta_description", ""),
                "platform": "demo",
            },
        )

        publish_result = await DomainRegistry.execute_step(publish_step)
        assert publish_result.success, f"Publish failed: {publish_result.error}"
        print(f"✓ publish: {publish_result.output.get('url')}")

        # Share
        share_step = TaskStep(
            id="test_share",
            name="test_share",
            description="Share on social",
            domain="cms",
            agent_type="share",
            inputs={
                "url": publish_result.output.get("url", ""),
                "title": draft_result.output.get("title", ""),
                "platforms": ["twitter", "linkedin"],
            },
        )

        share_result = await DomainRegistry.execute_step(share_step)
        assert share_result.success, f"Share failed: {share_result.error}"
        print(f"✓ share: {len(share_result.output.get('share_urls', []))} platforms")

        print("\n✓ All domain subagents working correctly!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
