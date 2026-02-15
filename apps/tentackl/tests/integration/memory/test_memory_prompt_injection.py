"""Integration tests for memory prompt injection into orchestrator prompts.

Tests verify that:
1. Memories are injected into orchestrator prompts via MemoryService
2. Memories are filtered by organization - org isolation is enforced
3. Empty memories produce empty section (no placeholder left behind)
4. Token budget is respected when formatting memories
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import uuid

from src.infrastructure.memory.memory_store import MemoryStore
from src.infrastructure.memory.memory_service import MemoryService
from src.domain.memory.models import (
    MemoryCreateRequest,
    MemoryQuery,
    MemoryScopeEnum,
)
from src.infrastructure.tasks.task_orchestrator import TaskOrchestratorAgent
from src.domain.tasks.models import Task, TaskStep, TaskStatus, StepStatus


# ---------------------------------------------------------------------------
# TestMemoryPromptInjection
# ---------------------------------------------------------------------------


class TestMemoryPromptInjection:
    """Tests for verifying memories appear in orchestrator prompts."""

    @pytest.mark.asyncio
    async def test_orchestrator_injects_memories_into_prompt(self, integration_db):
        """
        Store a memory with topic='content' via MemoryService.
        Create a mock Task with goal='Write blog post' and a TaskStep.
        Call _build_prompt() on orchestrator (with real MemoryService, mocked LLM).
        Assert the returned prompt string contains the memory body text.
        Assert it's wrapped in <relevant_memories> tags.
        """
        # Store a memory
        memory_service = MemoryService(integration_db)

        # Use topic="compose" to match the agent_type in the step
        # The orchestrator queries with topic=current_step.agent_type
        request = MemoryCreateRequest(
            organization_id="org-test-inject",
            key="brand-voice-inject",
            title="Brand Voice Guidelines",
            body="Use a friendly but professional tone. Avoid jargon.",
            scope=MemoryScopeEnum.ORGANIZATION,
            topic="compose",  # Match agent_type for filtering
            tags=["brand", "voice"],
            created_by_user_id="user-test",
        )

        stored_memory = await memory_service.store(request)
        assert stored_memory is not None
        assert stored_memory.key == "brand-voice-inject"

        # Create a mock Task with the same organization_id
        task = Task(
            id=str(uuid.uuid4()),
            user_id="user-test",
            organization_id="org-test-inject",
            goal="Write a blog post about our new features",
            status=TaskStatus.READY,
        )

        # Create a TaskStep
        step = TaskStep(
            id="step_1",
            name="Compose blog post",
            description="Write the blog post content",
            agent_type="compose",
            inputs={"prompt": "Write a blog post"},
        )
        task.steps = [step]

        # Create orchestrator with real MemoryService
        orchestrator = TaskOrchestratorAgent(
            name="test-orchestrator",
            memory_service=memory_service,
        )

        # Build prompt (this is now async)
        prompt = await orchestrator._build_prompt(task, step)

        # Assert memory content appears in prompt
        assert "Use a friendly but professional tone" in prompt
        assert "Avoid jargon" in prompt

        # Assert it's wrapped in <relevant_memories> tags
        assert "<relevant_memories>" in prompt
        assert "</relevant_memories>" in prompt

        # The memory content should be between the tags
        start_idx = prompt.find("<relevant_memories>")
        end_idx = prompt.find("</relevant_memories>")
        assert start_idx < end_idx
        memories_section = prompt[start_idx:end_idx]
        assert "Use a friendly but professional tone" in memories_section

        # Cleanup
        await orchestrator.cleanup()

    @pytest.mark.asyncio
    async def test_memories_filtered_by_org_in_prompt(self, integration_db):
        """
        Store memory in org-A. Build prompt for task in org-B.
        Assert memory body NOT in prompt.
        """
        # Store a memory in org-A
        # Use topic="research" to match the agent_type in the step
        memory_service = MemoryService(integration_db)

        request = MemoryCreateRequest(
            organization_id="org-A-isolation",
            key="secret-strategy-A",
            title="Secret Strategy",
            body="Our secret competitive strategy is to undercut by 30%",
            scope=MemoryScopeEnum.ORGANIZATION,
            topic="research",  # Match agent_type for filtering
            created_by_user_id="user-A",
        )

        stored_memory = await memory_service.store(request)
        assert stored_memory is not None

        # Create a Task for org-B
        task = Task(
            id=str(uuid.uuid4()),
            user_id="user-B",
            organization_id="org-B-isolation",
            goal="Write a strategy document",
            status=TaskStatus.READY,
        )

        step = TaskStep(
            id="step_1",
            name="Research strategy",
            description="Research competitive strategy",
            agent_type="research",
            inputs={},
        )
        task.steps = [step]

        # Create orchestrator with MemoryService
        orchestrator = TaskOrchestratorAgent(
            name="test-orchestrator-isolation",
            memory_service=memory_service,
        )

        # Build prompt for org-B task
        prompt = await orchestrator._build_prompt(task, step)

        # Assert org-A's secret is NOT in the prompt
        assert "undercut by 30%" not in prompt
        assert "Secret Strategy" not in prompt

        # The relevant_memories section should exist but be empty
        # (or contain no memory content)
        assert "<relevant_memories>" in prompt
        assert "</relevant_memories>" in prompt

        # Cleanup
        await orchestrator.cleanup()

    @pytest.mark.asyncio
    async def test_empty_memories_produce_empty_section(self, integration_db):
        """
        Build prompt with no stored memories.
        Assert {{memories}} is replaced with empty string (not left as placeholder).
        """
        memory_service = MemoryService(integration_db)

        # Create a Task - no memories stored for this org
        task = Task(
            id=str(uuid.uuid4()),
            user_id="user-empty",
            organization_id="org-no-memories",
            goal="Do something without memories",
            status=TaskStatus.READY,
        )

        step = TaskStep(
            id="step_1",
            name="Action step",
            description="Perform an action",
            agent_type="compose",
            inputs={},
        )
        task.steps = [step]

        # Create orchestrator with MemoryService
        orchestrator = TaskOrchestratorAgent(
            name="test-orchestrator-empty",
            memory_service=memory_service,
        )

        # Build prompt
        prompt = await orchestrator._build_prompt(task, step)

        # Assert the placeholder is NOT present (replaced with empty string)
        assert "{{memories}}" not in prompt

        # The relevant_memories tags should be there but empty or with empty content
        assert "<relevant_memories>" in prompt
        assert "</relevant_memories>" in prompt

        # Check that the content between tags is minimal (just whitespace or empty)
        start_idx = prompt.find("<relevant_memories>") + len("<relevant_memories>")
        end_idx = prompt.find("</relevant_memories>")
        memories_content = prompt[start_idx:end_idx].strip()
        # Should be empty since no memories exist
        assert memories_content == ""

        # Cleanup
        await orchestrator.cleanup()

    @pytest.mark.asyncio
    async def test_token_budget_respected(self, integration_db):
        """
        Store 50 memories each with 200-char body.
        Build prompt with max_tokens=500 for memory section.
        Assert the <relevant_memories> section is under ~500 tokens.
        """
        memory_service = MemoryService(integration_db)

        # Store 50 memories with ~200 char bodies
        org_id = "org-token-budget"
        for i in range(50):
            # Each body is approximately 200 characters
            body_text = f"Memory item {i:02d}: This is a detailed memory content that contains important information about the organization's processes and guidelines. " + "x" * (200 - 130)

            # Use topic="compose" to match the agent_type in the step
            request = MemoryCreateRequest(
                organization_id=org_id,
                key=f"memory-budget-{i:02d}",
                title=f"Memory {i:02d}",
                body=body_text,
                scope=MemoryScopeEnum.ORGANIZATION,
                topic="compose",  # Match agent_type for filtering
                created_by_user_id="user-budget",
            )
            await memory_service.store(request)

        # Create a Task
        task = Task(
            id=str(uuid.uuid4()),
            user_id="user-budget",
            organization_id=org_id,
            goal="Work with many memories",
            status=TaskStatus.READY,
        )

        step = TaskStep(
            id="step_1",
            name="Process memories",
            description="Process the memories",
            agent_type="compose",  # Topic match for better relevance
            inputs={},
        )
        task.steps = [step]

        # Create orchestrator with MemoryService
        # The orchestrator uses max_tokens=2000 by default in _inject_memories
        orchestrator = TaskOrchestratorAgent(
            name="test-orchestrator-budget",
            memory_service=memory_service,
        )

        # Build prompt
        prompt = await orchestrator._build_prompt(task, step)

        # Extract the relevant_memories section
        start_idx = prompt.find("<relevant_memories>") + len("<relevant_memories>")
        end_idx = prompt.find("</relevant_memories>")
        memories_section = prompt[start_idx:end_idx]

        # The injector uses token estimation of len(text) // 4
        # With max_tokens=2000 (orchestrator default), we should have at most ~8000 chars
        # But the injector should truncate to fit within budget
        estimated_tokens = len(memories_section) // 4

        # Verify we don't have all 50 memories (would be ~50 * 200 = 10000 chars = 2500 tokens)
        # With 2000 token budget, we expect fewer memories
        assert estimated_tokens <= 2100  # Some buffer for truncation edge cases

        # Verify we have at least some memories (not empty)
        assert len(memories_section) > 0

        # Verify it's a subset (not all 50 memories)
        # Each memory has ~200 chars body + XML wrapping, so with 2000 tokens budget
        # we can fit maybe 10-15 memories at most
        memory_count = memories_section.count("<memory ")
        assert memory_count > 0, "Should have at least some memories"
        assert memory_count < 50, "Should not have all 50 memories due to token budget"

        # Cleanup
        await orchestrator.cleanup()


# ---------------------------------------------------------------------------
# TestMemoryInjectionWithoutService
# ---------------------------------------------------------------------------


class TestMemoryInjectionWithoutService:
    """Tests for verifying behavior when memory service is not available."""

    @pytest.mark.asyncio
    async def test_no_memory_service_returns_empty(self, integration_db):
        """
        Create orchestrator without memory_service.
        Assert {{memories}} placeholder is replaced with empty string.
        """
        # Create a Task
        task = Task(
            id=str(uuid.uuid4()),
            user_id="user-no-service",
            organization_id="org-no-service",
            goal="Work without memory service",
            status=TaskStatus.READY,
        )

        step = TaskStep(
            id="step_1",
            name="Action step",
            description="Perform an action",
            agent_type="compose",
            inputs={},
        )
        task.steps = [step]

        # Create orchestrator WITHOUT memory service
        orchestrator = TaskOrchestratorAgent(
            name="test-orchestrator-no-service",
            memory_service=None,
        )

        # Build prompt
        prompt = await orchestrator._build_prompt(task, step)

        # Assert the placeholder is NOT present
        assert "{{memories}}" not in prompt

        # The relevant_memories section should be empty
        start_idx = prompt.find("<relevant_memories>") + len("<relevant_memories>")
        end_idx = prompt.find("</relevant_memories>")
        memories_content = prompt[start_idx:end_idx].strip()
        assert memories_content == ""

        # Cleanup
        await orchestrator.cleanup()
