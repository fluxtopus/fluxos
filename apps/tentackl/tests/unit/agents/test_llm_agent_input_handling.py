"""Unit tests for LLM agent input handling fix."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.llm_agent import LLMAgent
from src.agents.base import AgentConfig
from src.interfaces.llm import LLMMessage, LLMResponse


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = AsyncMock()
    client.health_check = AsyncMock(return_value=True)
    return client


@pytest.fixture
async def llm_agent(mock_llm_client):
    """Create an LLM agent with mocked client."""
    config = AgentConfig(
        name="test_llm_agent",
        agent_type="llm_agent",
        metadata={
            "model": "openai/gpt-4o-mini",
            "temperature": 0.7,
            "system_prompt": "You are a test agent."
        }
    )

    agent = LLMAgent(config, llm_client=mock_llm_client, enable_conversation_tracking=False)

    # Initialize the agent
    await agent.initialize()

    yield agent

    # Cleanup
    await agent.cleanup()


class TestLLMAgentInputHandling:
    """Test suite for LLM agent input handling."""

    @pytest.mark.asyncio
    async def test_task_with_text_input_combines_both(self, llm_agent, mock_llm_client):
        """Test that task + text inputs are combined into the user message."""
        # Mock LLM response
        mock_response = LLMResponse(
            content='{"status": "success", "result": "Analysis complete"}',
            model="openai/gpt-4o-mini",
            usage=None
        )
        mock_llm_client.create_completion = AsyncMock(return_value=mock_response)

        # Execute task with both task and text inputs
        task = {
            "task": "Analyze the writing style of this text.",
            "text": "The brave knight rode through the dark forest."
        }

        result = await llm_agent.process_task(task)

        # Verify LLM was called
        assert mock_llm_client.create_completion.called

        # Get the messages passed to LLM
        call_args = mock_llm_client.create_completion.call_args
        messages = call_args[1]["messages"]

        # Find user message
        user_message = None
        for msg in messages:
            if msg.role == "user":
                user_message = msg.content
                break

        assert user_message is not None

        # Verify BOTH task and text are in the message
        assert "Analyze the writing style" in user_message
        assert "The brave knight rode through the dark forest" in user_message

        # Verify result
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_task_with_multiple_inputs(self, llm_agent, mock_llm_client):
        """Test that task + multiple other inputs are all combined."""
        # Mock LLM response
        mock_response = LLMResponse(
            content='{"status": "success", "result": "Done"}',
            model="openai/gpt-4o-mini",
            usage=None
        )
        mock_llm_client.create_completion = AsyncMock(return_value=mock_response)

        # Execute task with multiple inputs
        task = {
            "task": "Process this data",
            "text": "Some text content",
            "data": {"key": "value"},
            "context": "Additional context"
        }

        result = await llm_agent.process_task(task)

        # Get the messages
        call_args = mock_llm_client.create_completion.call_args
        messages = call_args[1]["messages"]
        user_message = next(msg.content for msg in messages if msg.role == "user")

        # Verify ALL inputs are in the message
        assert "Process this data" in user_message
        assert "Some text content" in user_message
        assert "value" in user_message
        assert "Additional context" in user_message

    @pytest.mark.asyncio
    async def test_task_without_other_inputs_works(self, llm_agent, mock_llm_client):
        """Test that task-only input still works."""
        mock_response = LLMResponse(
            content='{"status": "success", "result": "Done"}',
            model="openai/gpt-4o-mini",
            usage=None
        )
        mock_llm_client.create_completion = AsyncMock(return_value=mock_response)

        # Execute task with only task input
        task = {
            "task": "Do something"
        }

        result = await llm_agent.process_task(task)

        # Get the message
        call_args = mock_llm_client.create_completion.call_args
        messages = call_args[1]["messages"]
        user_message = next(msg.content for msg in messages if msg.role == "user")

        # Should just be the task
        assert user_message == "Do something"

    @pytest.mark.asyncio
    async def test_excludes_metadata_keys(self, llm_agent, mock_llm_client):
        """Test that metadata keys are excluded from inputs."""
        mock_response = LLMResponse(
            content='{"status": "success", "result": "Done"}',
            model="openai/gpt-4o-mini",
            usage=None
        )
        mock_llm_client.create_completion = AsyncMock(return_value=mock_response)

        # Execute task with metadata keys
        task = {
            "task": "Process this",
            "text": "Content",
            "id": "task-123",
            "node_id": "node-456",
            "workflow_id": "workflow-789",
            "max_tokens": 1000
        }

        result = await llm_agent.process_task(task)

        # Get the message
        call_args = mock_llm_client.create_completion.call_args
        messages = call_args[1]["messages"]
        user_message = next(msg.content for msg in messages if msg.role == "user")

        # Should have task and text, but not metadata
        assert "Process this" in user_message
        assert "Content" in user_message
        assert "task-123" not in user_message
        assert "node-456" not in user_message
        assert "workflow-789" not in user_message

    @pytest.mark.asyncio
    async def test_prompt_mode_unchanged(self, llm_agent, mock_llm_client):
        """Test that prompt mode still works as before."""
        mock_response = LLMResponse(
            content='{"status": "success", "result": "Done"}',
            model="openai/gpt-4o-mini",
            usage=None
        )
        mock_llm_client.create_completion = AsyncMock(return_value=mock_response)

        # Execute with prompt (takes precedence over task)
        task = {
            "prompt": "Direct prompt",
            "task": "This should be ignored",
            "text": "This should also be ignored"
        }

        result = await llm_agent.process_task(task)

        # Get the message
        call_args = mock_llm_client.create_completion.call_args
        messages = call_args[1]["messages"]
        user_message = next(msg.content for msg in messages if msg.role == "user")

        # Should only be the prompt
        assert user_message == "Direct prompt"
