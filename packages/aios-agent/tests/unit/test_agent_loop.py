from __future__ import annotations

import asyncio

import pytest

from aios_agent import agent_loop, agent_loop_continue
from aios_agent.types import (
    AgentContext,
    AgentLoopConfig,
    AgentTool,
    AgentToolResult,
    TextContent,
    ToolCallContent,
    UserMessage,
)

from .helpers import MockAssistantStream, create_assistant_message, create_model, push_done


def identity_converter(messages):
    return [m for m in messages if getattr(m, "role", m.get("role") if isinstance(m, dict) else None) in {"user", "assistant", "toolResult"}]


@pytest.mark.asyncio
async def test_agent_loop_emits_lifecycle_events() -> None:
    context = AgentContext(system_prompt="You are helpful.", messages=[], tools=[])
    prompt = UserMessage(content="Hello")

    config = AgentLoopConfig(model=create_model(), convert_to_llm=identity_converter)

    def stream_fn(_model, _context, _options):
        stream = MockAssistantStream()
        asyncio.get_running_loop().call_soon(
            lambda: push_done(stream, create_assistant_message(text="Hi there!"))
        )
        return stream

    events = []
    stream = agent_loop([prompt], context, config, None, stream_fn)
    async for event in stream:
        events.append(event)

    messages = await stream.result()

    assert len(messages) == 2
    assert getattr(messages[0], "role", None) == "user"
    assert getattr(messages[1], "role", None) == "assistant"

    event_types = [event.type for event in events]
    assert "agent_start" in event_types
    assert "turn_start" in event_types
    assert "message_start" in event_types
    assert "message_end" in event_types
    assert "turn_end" in event_types
    assert "agent_end" in event_types


@pytest.mark.asyncio
async def test_agent_loop_applies_transform_before_convert() -> None:
    context = AgentContext(
        system_prompt="You are helpful.",
        messages=[
            UserMessage(content="old 1"),
            create_assistant_message(text="old response 1"),
            UserMessage(content="old 2"),
            create_assistant_message(text="old response 2"),
        ],
        tools=[],
    )
    prompt = UserMessage(content="new")

    transformed = []
    converted = []

    async def transform_context(messages, _signal):
        transformed[:] = messages[-2:]
        return transformed

    def convert_to_llm(messages):
        converted[:] = messages
        return [m for m in messages if getattr(m, "role", None) in {"user", "assistant", "toolResult"}]

    config = AgentLoopConfig(
        model=create_model(),
        transform_context=transform_context,
        convert_to_llm=convert_to_llm,
    )

    def stream_fn(_model, _context, _options):
        stream = MockAssistantStream()
        asyncio.get_running_loop().call_soon(
            lambda: push_done(stream, create_assistant_message(text="Response"))
        )
        return stream

    stream = agent_loop([prompt], context, config, None, stream_fn)
    async for _ in stream:
        pass

    assert len(transformed) == 2
    assert len(converted) == 2


@pytest.mark.asyncio
async def test_agent_loop_executes_tools() -> None:
    executed = []

    async def execute(_tool_call_id, params, _signal, _on_update):
        executed.append(params["value"])
        return AgentToolResult(content=[TextContent(text=f"echoed: {params['value']}")], details={"value": params["value"]})

    tool = AgentTool(
        name="echo",
        label="Echo",
        description="Echo tool",
        execute=execute,
    )

    context = AgentContext(system_prompt="", messages=[], tools=[tool])
    prompt = UserMessage(content="echo something")
    config = AgentLoopConfig(model=create_model(), convert_to_llm=identity_converter)

    call_index = {"value": 0}

    def stream_fn(_model, _context, _options):
        stream = MockAssistantStream()

        def _push():
            if call_index["value"] == 0:
                msg = create_assistant_message(
                    content=[ToolCallContent(id="tool-1", name="echo", arguments={"value": "hello"})],
                    stop_reason="toolUse",
                )
                push_done(stream, msg)
            else:
                push_done(stream, create_assistant_message(text="done"))
            call_index["value"] += 1

        asyncio.get_running_loop().call_soon(_push)
        return stream

    events = []
    stream = agent_loop([prompt], context, config, None, stream_fn)
    async for event in stream:
        events.append(event)

    assert executed == ["hello"]
    tool_start = [e for e in events if e.type == "tool_execution_start"]
    tool_end = [e for e in events if e.type == "tool_execution_end"]
    assert tool_start
    assert tool_end
    assert tool_end[0].is_error is False


@pytest.mark.asyncio
async def test_agent_loop_skips_remaining_tools_when_steered() -> None:
    executed = []

    async def execute(_tool_call_id, params, _signal, _on_update):
        executed.append(params["value"])
        return AgentToolResult(content=[TextContent(text=f"ok:{params['value']}")], details={"value": params["value"]})

    tool = AgentTool(name="echo", label="Echo", description="Echo tool", execute=execute)

    context = AgentContext(system_prompt="", messages=[], tools=[tool])
    prompt = UserMessage(content="start")
    queued_message = UserMessage(content="interrupt")

    queued_delivered = {"value": False}
    call_index = {"value": 0}
    saw_interrupt = {"value": False}

    async def get_steering_messages():
        if len(executed) == 1 and not queued_delivered["value"]:
            queued_delivered["value"] = True
            return [queued_message]
        return []

    config = AgentLoopConfig(
        model=create_model(),
        convert_to_llm=identity_converter,
        get_steering_messages=get_steering_messages,
    )

    def stream_fn(_model, llm_context, _options):
        stream = MockAssistantStream()

        def _push():
            if call_index["value"] == 1:
                saw_interrupt["value"] = any(
                    getattr(msg, "role", None) == "user"
                    and (
                        msg.content == "interrupt"
                        or any(
                            getattr(part, "type", None) == "text"
                            and getattr(part, "text", "") == "interrupt"
                            for part in (msg.content if isinstance(msg.content, list) else [])
                        )
                    )
                    for msg in llm_context.messages
                )

            if call_index["value"] == 0:
                msg = create_assistant_message(
                    content=[
                        ToolCallContent(id="tool-1", name="echo", arguments={"value": "first"}),
                        ToolCallContent(id="tool-2", name="echo", arguments={"value": "second"}),
                    ],
                    stop_reason="toolUse",
                )
                push_done(stream, msg)
            else:
                push_done(stream, create_assistant_message(text="done"))
            call_index["value"] += 1

        asyncio.get_running_loop().call_soon(_push)
        return stream

    events = []
    stream = agent_loop([prompt], context, config, None, stream_fn)
    async for event in stream:
        events.append(event)

    assert executed == ["first"]
    tool_ends = [event for event in events if event.type == "tool_execution_end"]
    assert len(tool_ends) == 2
    assert tool_ends[0].is_error is False
    assert tool_ends[1].is_error is True
    assert "Skipped due to queued user message" in tool_ends[1].result.content[0].text
    assert saw_interrupt["value"] is True


def test_agent_loop_continue_validates_empty_context() -> None:
    context = AgentContext(system_prompt="", messages=[], tools=[])
    config = AgentLoopConfig(model=create_model(), convert_to_llm=identity_converter)

    with pytest.raises(ValueError, match="Cannot continue: no messages in context"):
        agent_loop_continue(context, config)


@pytest.mark.asyncio
async def test_agent_loop_continue_processes_existing_context() -> None:
    user = UserMessage(content="Hello")
    context = AgentContext(system_prompt="", messages=[user], tools=[])
    config = AgentLoopConfig(model=create_model(), convert_to_llm=identity_converter)

    def stream_fn(_model, _context, _options):
        stream = MockAssistantStream()
        asyncio.get_running_loop().call_soon(
            lambda: push_done(stream, create_assistant_message(text="Response"))
        )
        return stream

    events = []
    stream = agent_loop_continue(context, config, None, stream_fn)
    async for event in stream:
        events.append(event)

    messages = await stream.result()
    assert len(messages) == 1
    assert getattr(messages[0], "role", None) == "assistant"
    message_end_events = [event for event in events if event.type == "message_end"]
    assert len(message_end_events) == 1
    assert getattr(message_end_events[0].message, "role", None) == "assistant"

