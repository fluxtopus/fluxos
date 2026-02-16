"""Bedrock compatibility test scaffolding for the Python agent port."""

from __future__ import annotations

import os

import pytest

from aios_agent import Agent, AgentOptions
from aios_agent.types import AssistantDoneEvent, Model
from tests.bedrock_utils import has_bedrock_credentials
from tests.unit.helpers import MockAssistantStream

pytestmark = pytest.mark.e2e


REQUIRES_INFERENCE_PROFILE = {
    "anthropic.claude-3-5-haiku-20241022-v1:0",
    "anthropic.claude-3-5-sonnet-20241022-v2:0",
}

INVALID_MODEL_ID = {
    "deepseek.v3-v1:0",
    "qwen.qwen3-coder-480b-a35b-v1:0",
}

MAX_TOKENS_EXCEEDED = {
    "us.meta.llama4-maverick-17b-instruct-v1:0",
}


def is_model_unavailable(model_id: str) -> bool:
    return model_id in REQUIRES_INFERENCE_PROFILE | INVALID_MODEL_ID | MAX_TOKENS_EXCEEDED


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("anthropic.claude-3-5-haiku-20241022-v1:0", True),
        ("deepseek.v3-v1:0", True),
        ("us.meta.llama4-maverick-17b-instruct-v1:0", True),
        ("global.anthropic.claude-sonnet-4-5-20250929-v1:0", False),
    ],
)
def test_is_model_unavailable(model_id: str, expected: bool) -> None:
    assert is_model_unavailable(model_id) is expected


@pytest.mark.skipif(
    not (has_bedrock_credentials() and os.getenv("BEDROCK_EXTENSIVE_MODEL_TEST")),
    reason="Set AWS credentials and BEDROCK_EXTENSIVE_MODEL_TEST=1 to run",
)
@pytest.mark.asyncio
async def test_bedrock_extensive_gate_smoke() -> None:
    model = Model(
        id="global.anthropic.claude-sonnet-4-5-20250929-v1:0",
        name="claude-sonnet-4-5",
        api="bedrock-converse-stream",
        provider="amazon-bedrock",
        reasoning=False,
    )

    def stream_fn(_model, _context, _options):
        stream = MockAssistantStream()
        from tests.unit.helpers import create_assistant_message

        stream.push(AssistantDoneEvent(reason="stop", message=create_assistant_message(text="OK")))
        return stream

    agent = Agent(
        AgentOptions(
            stream_fn=stream_fn,
            initial_state={
                "system_prompt": "You are concise.",
                "model": model,
                "thinking_level": "off",
                "tools": [],
            },
        )
    )

    await agent.prompt("Reply with exactly: OK")
    assert agent.state.error is None
    assert agent.state.is_streaming is False
    assert len(agent.state.messages) == 2
    assert getattr(agent.state.messages[1], "role", None) == "assistant"
    text_parts = [p.text for p in agent.state.messages[1].content if getattr(p, "type", None) == "text"]
    assert any("OK" in text for text in text_parts)
