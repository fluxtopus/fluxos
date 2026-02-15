"""Unit tests for multimodal prompt building in DatabaseConfiguredAgent."""

import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from src.agents.db_configured_agent import DatabaseConfiguredAgent
from src.infrastructure.execution_runtime.file_resolver import (
    ResolvedFile,
    StepFileContext,
)


def _make_config(**overrides):
    """Create a minimal AgentCapability mock."""
    config = MagicMock()
    config.agent_type = overrides.get("agent_type", "analyze")
    config.task_type = overrides.get("task_type", "reasoning")
    config.domain = overrides.get("domain", "content")
    config.system_prompt = overrides.get("system_prompt", "You are an analyst.")
    config.inputs_schema = overrides.get("inputs_schema", {
        "text": {"type": "string", "description": "Content to analyze", "required": True},
    })
    config.outputs_schema = overrides.get("outputs_schema", {
        "insights": {"type": "array", "description": "Key insights"},
    })
    config.examples = overrides.get("examples", [])
    config.execution_hints = overrides.get("execution_hints", {})
    return config


def _make_step(inputs=None):
    """Create a minimal TaskStep mock."""
    step = MagicMock()
    step.id = "step-1"
    step.name = "Analyze Document"
    step.description = "Analyze the provided content"
    step.agent_type = "analyze"
    step.inputs = inputs or {"text": "Some content to analyze"}
    return step


# ---------------------------------------------------------------------------
# _build_prompt tests
# ---------------------------------------------------------------------------


class TestBuildPromptWithoutFileContext:
    def test_returns_string_without_file_context(self):
        agent = DatabaseConfiguredAgent(config=_make_config())
        step = _make_step()
        result = agent._build_prompt(step.inputs, step)

        assert isinstance(result, str)
        assert "Analyze Document" in result
        assert "Some content to analyze" in result

    def test_returns_string_with_empty_file_context(self):
        agent = DatabaseConfiguredAgent(config=_make_config())
        step = _make_step()
        ctx = StepFileContext(resolved_files=[])

        result = agent._build_prompt(step.inputs, step, file_context=ctx)

        assert isinstance(result, str)

    def test_returns_string_with_none_file_context(self):
        agent = DatabaseConfiguredAgent(config=_make_config())
        step = _make_step()

        result = agent._build_prompt(step.inputs, step, file_context=None)

        assert isinstance(result, str)


class TestBuildPromptWithTextFiles:
    def test_inlines_text_file_into_string(self):
        agent = DatabaseConfiguredAgent(config=_make_config())
        step = _make_step()

        text_file = ResolvedFile(
            file_id="f1",
            name="notes.txt",
            content_type="text/plain",
            content_bytes=b"These are my notes about AI.",
        )
        ctx = StepFileContext(resolved_files=[text_file])

        result = agent._build_prompt(step.inputs, step, file_context=ctx)

        assert isinstance(result, str)
        assert "--- File: notes.txt ---" in result
        assert "These are my notes about AI." in result

    def test_inlines_multiple_text_files(self):
        agent = DatabaseConfiguredAgent(config=_make_config())
        step = _make_step()

        files = [
            ResolvedFile(file_id="f1", name="a.txt", content_type="text/plain", content_bytes=b"File A"),
            ResolvedFile(file_id="f2", name="b.csv", content_type="text/csv", content_bytes=b"col1,col2"),
        ]
        ctx = StepFileContext(resolved_files=files)

        result = agent._build_prompt(step.inputs, step, file_context=ctx)

        assert isinstance(result, str)
        assert "--- File: a.txt ---" in result
        assert "--- File: b.csv ---" in result
        assert "File A" in result
        assert "col1,col2" in result


class TestBuildPromptWithImageFiles:
    def test_returns_list_with_image(self):
        agent = DatabaseConfiguredAgent(config=_make_config())
        step = _make_step()

        image_bytes = b"\x89PNG\r\n\x1a\n"  # PNG magic bytes
        img = ResolvedFile(
            file_id="f1",
            name="chart.png",
            content_type="image/png",
            content_bytes=image_bytes,
        )
        ctx = StepFileContext(resolved_files=[img])

        result = agent._build_prompt(step.inputs, step, file_context=ctx)

        assert isinstance(result, list)
        assert len(result) == 2  # text part + image part

        # First part is text
        assert result[0]["type"] == "text"
        assert "Analyze Document" in result[0]["text"]

        # Second part is image
        assert result[1]["type"] == "image_url"
        expected_b64 = base64.b64encode(image_bytes).decode("ascii")
        assert result[1]["image_url"]["url"] == f"data:image/png;base64,{expected_b64}"

    def test_returns_list_with_mixed_files(self):
        agent = DatabaseConfiguredAgent(config=_make_config())
        step = _make_step()

        text_file = ResolvedFile(
            file_id="f1", name="notes.txt", content_type="text/plain",
            content_bytes=b"My notes",
        )
        img_file = ResolvedFile(
            file_id="f2", name="photo.jpeg", content_type="image/jpeg",
            content_bytes=b"\xff\xd8\xff",
        )
        ctx = StepFileContext(resolved_files=[text_file, img_file])

        result = agent._build_prompt(step.inputs, step, file_context=ctx)

        assert isinstance(result, list)
        # Text file should be inlined in the text part
        assert "--- File: notes.txt ---" in result[0]["text"]
        assert "My notes" in result[0]["text"]
        # Image should be a separate part
        assert result[1]["type"] == "image_url"


class TestBuildPromptWithMultipleImages:
    def test_all_images_included(self):
        agent = DatabaseConfiguredAgent(config=_make_config())
        step = _make_step()

        images = [
            ResolvedFile(
                file_id=f"f{i}", name=f"img{i}.png", content_type="image/png",
                content_bytes=b"\x89PNG",
            )
            for i in range(3)
        ]
        ctx = StepFileContext(resolved_files=images)

        result = agent._build_prompt(step.inputs, step, file_context=ctx)

        assert isinstance(result, list)
        # 1 text part + 3 image parts
        assert len(result) == 4
        image_parts = [p for p in result if p["type"] == "image_url"]
        assert len(image_parts) == 3


# ---------------------------------------------------------------------------
# execute() tests — verify file_context is threaded
# ---------------------------------------------------------------------------


class TestExecuteWithFileContext:
    @pytest.mark.asyncio
    async def test_execute_passes_file_context_to_build_prompt(self):
        agent = DatabaseConfiguredAgent(config=_make_config())
        agent.llm_client = AsyncMock()

        # Mock LLM response
        mock_response = MagicMock()
        mock_response.content = '{"insights": ["finding 1"]}'
        mock_response.model = "test-model"
        agent.llm_client.create_completion = AsyncMock(return_value=mock_response)

        step = _make_step()

        text_file = ResolvedFile(
            file_id="f1", name="data.json", content_type="application/json",
            content_bytes=b'{"key": "value"}',
        )
        ctx = StepFileContext(resolved_files=[text_file])

        result = await agent.execute(step, file_context=ctx)

        assert result.success is True
        # Verify the LLM was called — the prompt should contain the inlined file
        call_args = agent.llm_client.create_completion.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0]
        user_msg = [m for m in messages if m.role == "user"][0]
        # Text file is inlined, so content should be a string containing the file
        assert isinstance(user_msg.content, str)
        assert "data.json" in user_msg.content

    @pytest.mark.asyncio
    async def test_execute_without_file_context(self):
        agent = DatabaseConfiguredAgent(config=_make_config())
        agent.llm_client = AsyncMock()

        mock_response = MagicMock()
        mock_response.content = '{"insights": ["finding 1"]}'
        mock_response.model = "test-model"
        agent.llm_client.create_completion = AsyncMock(return_value=mock_response)

        step = _make_step()

        result = await agent.execute(step)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_with_image_sends_multimodal(self):
        agent = DatabaseConfiguredAgent(config=_make_config())
        agent.llm_client = AsyncMock()

        mock_response = MagicMock()
        mock_response.content = '{"insights": ["image shows a chart"]}'
        mock_response.model = "test-model"
        agent.llm_client.create_completion = AsyncMock(return_value=mock_response)

        step = _make_step()

        img = ResolvedFile(
            file_id="f1", name="chart.png", content_type="image/png",
            content_bytes=b"\x89PNG\r\n",
        )
        ctx = StepFileContext(resolved_files=[img])

        result = await agent.execute(step, file_context=ctx)

        assert result.success is True
        # The user message should be multimodal (list)
        call_args = agent.llm_client.create_completion.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0]
        user_msg = [m for m in messages if m.role == "user"][0]
        assert isinstance(user_msg.content, list)
        assert user_msg.content[0]["type"] == "text"
        assert user_msg.content[1]["type"] == "image_url"
