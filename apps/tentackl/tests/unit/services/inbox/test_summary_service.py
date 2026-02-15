"""
Unit tests for SummaryGenerationService.

Tests fallback summaries for all status types, LLM summary generation,
and the safe wrapper that falls back on errors.
"""

import pytest
from unittest.mock import AsyncMock

from src.interfaces.llm import LLMMessage, LLMResponse
from src.infrastructure.inbox.summary_service import SummaryGenerationService


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = AsyncMock()
    client.create_completion = AsyncMock()
    return client


@pytest.fixture
def service_with_llm(mock_llm_client):
    """SummaryGenerationService with a mock LLM client."""
    return SummaryGenerationService(llm_client=mock_llm_client)


@pytest.fixture
def service_without_llm():
    """SummaryGenerationService without an LLM client."""
    return SummaryGenerationService()


# --- Fallback Summary Tests ---


class TestGenerateFallbackSummary:
    def test_completed_status(self, service_without_llm):
        result = service_without_llm.generate_fallback_summary(
            goal="Compile HN digest",
            status="completed",
            steps_completed=4,
            total_steps=4,
        )
        assert result == "Completed: Compile HN digest. 4/4 steps executed."

    def test_failed_status_with_error(self, service_without_llm):
        result = service_without_llm.generate_fallback_summary(
            goal="Compile HN digest",
            status="failed",
            steps_completed=2,
            total_steps=4,
            error="API rate limited",
        )
        assert result == (
            "Failed: Compile HN digest. Error: API rate limited. "
            "2/4 steps completed before failure."
        )

    def test_failed_status_without_error(self, service_without_llm):
        result = service_without_llm.generate_fallback_summary(
            goal="Compile HN digest",
            status="failed",
            steps_completed=2,
            total_steps=4,
        )
        assert result == (
            "Failed: Compile HN digest. "
            "2/4 steps completed before failure."
        )

    def test_checkpoint_status(self, service_without_llm):
        result = service_without_llm.generate_fallback_summary(
            goal="Deploy production",
            status="checkpoint",
            steps_completed=3,
            total_steps=5,
        )
        assert result == (
            "Awaiting approval: Deploy production. "
            "3/5 steps completed so far."
        )

    def test_unknown_status(self, service_without_llm):
        result = service_without_llm.generate_fallback_summary(
            goal="Do something",
            status="paused",
            steps_completed=1,
            total_steps=3,
        )
        assert result == "Do something. Status: paused. 1/3 steps."


# --- LLM Summary Tests ---


class TestGenerateSummary:
    @pytest.mark.asyncio
    async def test_calls_llm_with_correct_messages(self, service_with_llm, mock_llm_client):
        mock_llm_client.create_completion.return_value = LLMResponse(
            content="I compiled your HN digest with 25 top stories.",
            model="openai/gpt-4o-mini",
        )

        result = await service_with_llm.generate_summary(
            goal="Compile HN digest",
            status="completed",
            steps_completed=4,
            total_steps=4,
            key_outputs={"stories_count": 25},
            findings=["Top story: AI advances"],
        )

        assert result == "I compiled your HN digest with 25 top stories."
        mock_llm_client.create_completion.assert_called_once()
        call_kwargs = mock_llm_client.create_completion.call_args
        messages = call_kwargs.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert "Compile HN digest" in messages[1].content
        assert "4/4" in messages[1].content

    @pytest.mark.asyncio
    async def test_raises_without_llm_client(self, service_without_llm):
        with pytest.raises(RuntimeError, match="No LLM client configured"):
            await service_without_llm.generate_summary(
                goal="test",
                status="completed",
                steps_completed=1,
                total_steps=1,
                key_outputs={},
                findings=[],
            )

    @pytest.mark.asyncio
    async def test_includes_error_in_prompt(self, service_with_llm, mock_llm_client):
        mock_llm_client.create_completion.return_value = LLMResponse(
            content="I failed to compile the digest.",
            model="openai/gpt-4o-mini",
        )

        await service_with_llm.generate_summary(
            goal="Compile HN digest",
            status="failed",
            steps_completed=2,
            total_steps=4,
            key_outputs={},
            findings=[],
            error="API rate limited",
        )

        call_kwargs = mock_llm_client.create_completion.call_args
        user_msg = call_kwargs.kwargs["messages"][1].content
        assert "API rate limited" in user_msg

    @pytest.mark.asyncio
    async def test_strips_whitespace_from_response(self, service_with_llm, mock_llm_client):
        mock_llm_client.create_completion.return_value = LLMResponse(
            content="  Summary with spaces.  \n",
            model="openai/gpt-4o-mini",
        )

        result = await service_with_llm.generate_summary(
            goal="test",
            status="completed",
            steps_completed=1,
            total_steps=1,
            key_outputs={},
            findings=[],
        )
        assert result == "Summary with spaces."

    @pytest.mark.asyncio
    async def test_includes_findings_in_prompt(self, service_with_llm, mock_llm_client):
        mock_llm_client.create_completion.return_value = LLMResponse(
            content="Done.", model="openai/gpt-4o-mini"
        )

        await service_with_llm.generate_summary(
            goal="Research",
            status="completed",
            steps_completed=3,
            total_steps=3,
            key_outputs={"report": "generated"},
            findings=["Finding A", "Finding B"],
        )

        call_kwargs = mock_llm_client.create_completion.call_args
        user_msg = call_kwargs.kwargs["messages"][1].content
        assert "Finding A" in user_msg
        assert "Finding B" in user_msg
        assert "report: generated" in user_msg


# --- Safe Summary Tests ---


class TestGenerateSummarySafe:
    @pytest.mark.asyncio
    async def test_returns_llm_summary_on_success(self, service_with_llm, mock_llm_client):
        mock_llm_client.create_completion.return_value = LLMResponse(
            content="I found 25 stories for your digest.",
            model="openai/gpt-4o-mini",
        )

        result = await service_with_llm.generate_summary_safe(
            goal="Compile HN digest",
            status="completed",
            steps_completed=4,
            total_steps=4,
            key_outputs={},
            findings=[],
        )
        assert result == "I found 25 stories for your digest."

    @pytest.mark.asyncio
    async def test_returns_fallback_on_llm_error(self, service_with_llm, mock_llm_client):
        mock_llm_client.create_completion.side_effect = Exception("LLM timeout")

        result = await service_with_llm.generate_summary_safe(
            goal="Compile HN digest",
            status="completed",
            steps_completed=4,
            total_steps=4,
            key_outputs={},
            findings=[],
        )
        assert result == "Completed: Compile HN digest. 4/4 steps executed."

    @pytest.mark.asyncio
    async def test_returns_fallback_when_no_client(self, service_without_llm):
        result = await service_without_llm.generate_summary_safe(
            goal="Deploy app",
            status="failed",
            steps_completed=1,
            total_steps=3,
            key_outputs={},
            findings=[],
            error="Permission denied",
        )
        assert result == (
            "Failed: Deploy app. Error: Permission denied. "
            "1/3 steps completed before failure."
        )

    @pytest.mark.asyncio
    async def test_never_raises(self, service_with_llm, mock_llm_client):
        mock_llm_client.create_completion.side_effect = RuntimeError("Catastrophic failure")

        # Should not raise
        result = await service_with_llm.generate_summary_safe(
            goal="test",
            status="checkpoint",
            steps_completed=2,
            total_steps=5,
            key_outputs={},
            findings=[],
        )
        assert "Awaiting approval" in result
