from __future__ import annotations

import asyncio

import pytest

from flux_agent import Agent, AgentOptions
from flux_agent.types import (
    AgentTool,
    AgentToolResult,
    AssistantStartEvent,
    TextContent,
    UserMessage,
)

from .helpers import (
    MockAssistantStream,
    create_assistant_message,
    create_model,
    push_done,
    push_error,
)


@pytest.mark.asyncio
async def test_agent_default_state() -> None:
    agent = Agent()
    assert agent.state.system_prompt == ""
    assert agent.state.model is not None
    assert agent.state.thinking_level == "off"
    assert agent.state.tools == []
    assert agent.state.messages == []
    assert agent.state.is_streaming is False
    assert agent.state.stream_message is None
    assert agent.state.pending_tool_calls == set()
    assert agent.state.error is None


@pytest.mark.asyncio
async def test_agent_custom_initial_state() -> None:
    custom_model = create_model()
    custom_model.id = "custom"
    custom_model.name = "custom"

    agent = Agent(
        AgentOptions(
            initial_state={
                "system_prompt": "You are a helpful assistant.",
                "model": custom_model,
                "thinking_level": "low",
            }
        )
    )

    assert agent.state.system_prompt == "You are a helpful assistant."
    assert agent.state.model == custom_model
    assert agent.state.thinking_level == "low"


@pytest.mark.asyncio
async def test_agent_subscribe() -> None:
    agent = Agent()
    event_count = {"value": 0}

    unsubscribe = agent.subscribe(lambda _event: event_count.__setitem__("value", event_count["value"] + 1))

    assert event_count["value"] == 0
    agent.set_system_prompt("Test prompt")
    assert event_count["value"] == 0

    unsubscribe()
    agent.set_system_prompt("Another prompt")
    assert event_count["value"] == 0


@pytest.mark.asyncio
async def test_agent_state_mutators() -> None:
    agent = Agent()
    agent.set_system_prompt("Custom prompt")
    assert agent.state.system_prompt == "Custom prompt"

    new_model = create_model()
    new_model.id = "new-model"
    agent.set_model(new_model)
    assert agent.state.model == new_model

    agent.set_thinking_level("high")
    assert agent.state.thinking_level == "high"

    tools = [AgentTool(name="test", label="Test", description="tool", execute=_noop_tool)]
    agent.set_tools(tools)
    assert agent.state.tools == tools

    messages = [UserMessage(content="Hello")]
    agent.replace_messages(messages)
    assert agent.state.messages == messages
    assert agent.state.messages is not messages

    new_message = create_assistant_message(text="Hi")
    agent.append_message(new_message)
    assert len(agent.state.messages) == 2
    assert agent.state.messages[1] == new_message

    agent.clear_messages()
    assert agent.state.messages == []


@pytest.mark.asyncio
async def test_agent_queue_methods() -> None:
    agent = Agent()
    steering = UserMessage(content="steering")
    follow_up = UserMessage(content="follow up")

    agent.steer(steering)
    agent.follow_up(follow_up)

    assert steering not in agent.state.messages
    assert follow_up not in agent.state.messages


@pytest.mark.asyncio
async def test_agent_prompt_throws_when_streaming() -> None:
    abort_signal = {"signal": None}

    def stream_fn(_model, _context, options):
        abort_signal["signal"] = options.signal
        stream = MockAssistantStream()

        def _start() -> None:
            stream.push(AssistantStartEvent(partial=create_assistant_message(text="")))

            async def _watch() -> None:
                while True:
                    if abort_signal["signal"].aborted:
                        push_error(stream, create_assistant_message(text="Aborted", stop_reason="aborted"))
                        return
                    await asyncio.sleep(0.005)

            asyncio.create_task(_watch())

        asyncio.get_running_loop().call_soon(_start)
        return stream

    agent = Agent(AgentOptions(stream_fn=stream_fn))
    first_prompt = asyncio.create_task(agent.prompt("First message"))

    await asyncio.sleep(0.02)
    assert agent.state.is_streaming is True

    with pytest.raises(
        RuntimeError,
        match=r"Agent is already processing a prompt. Use steer\(\) or follow_up\(\) to queue messages, or wait for completion.",
    ):
        await agent.prompt("Second message")

    agent.abort()
    await first_prompt


@pytest.mark.asyncio
async def test_agent_continue_throws_when_streaming() -> None:
    abort_signal = {"signal": None}

    def stream_fn(_model, _context, options):
        abort_signal["signal"] = options.signal
        stream = MockAssistantStream()

        def _start() -> None:
            stream.push(AssistantStartEvent(partial=create_assistant_message(text="")))

            async def _watch() -> None:
                while True:
                    if abort_signal["signal"].aborted:
                        push_error(stream, create_assistant_message(text="Aborted", stop_reason="aborted"))
                        return
                    await asyncio.sleep(0.005)

            asyncio.create_task(_watch())

        asyncio.get_running_loop().call_soon(_start)
        return stream

    agent = Agent(AgentOptions(stream_fn=stream_fn))
    first_prompt = asyncio.create_task(agent.prompt("First message"))
    await asyncio.sleep(0.02)

    with pytest.raises(RuntimeError, match="Agent is already processing. Wait for completion before continuing."):
        await agent.continue_()

    agent.abort()
    await first_prompt


@pytest.mark.asyncio
async def test_agent_continue_processes_follow_up_after_assistant() -> None:
    def stream_fn(_model, _context, _options):
        stream = MockAssistantStream()
        asyncio.get_running_loop().call_soon(
            lambda: push_done(stream, create_assistant_message(text="Processed"))
        )
        return stream

    agent = Agent(AgentOptions(stream_fn=stream_fn))
    agent.replace_messages([
        UserMessage(content=[TextContent(text="Initial")]),
        create_assistant_message(text="Initial response"),
    ])

    agent.follow_up(UserMessage(content=[TextContent(text="Queued follow-up")]))

    await agent.continue_()

    has_queued = any(
        getattr(message, "role", None) == "user"
        and (
            message.content == "Queued follow-up"
            or any(
                getattr(part, "type", None) == "text" and getattr(part, "text", "") == "Queued follow-up"
                for part in (message.content if isinstance(message.content, list) else [])
            )
        )
        for message in agent.state.messages
    )
    assert has_queued is True
    assert getattr(agent.state.messages[-1], "role", None) == "assistant"


@pytest.mark.asyncio
async def test_agent_continue_keeps_one_at_a_time_steering() -> None:
    response_count = {"value": 0}

    def stream_fn(_model, _context, _options):
        stream = MockAssistantStream()

        def _push() -> None:
            response_count["value"] += 1
            push_done(stream, create_assistant_message(text=f"Processed {response_count['value']}"))

        asyncio.get_running_loop().call_soon(_push)
        return stream

    agent = Agent(AgentOptions(stream_fn=stream_fn))
    agent.replace_messages([
        UserMessage(content=[TextContent(text="Initial")]),
        create_assistant_message(text="Initial response"),
    ])

    agent.steer(UserMessage(content=[TextContent(text="Steering 1")]))
    agent.steer(UserMessage(content=[TextContent(text="Steering 2")]))

    await agent.continue_()

    recent = agent.state.messages[-4:]
    assert [getattr(msg, "role", None) for msg in recent] == ["user", "assistant", "user", "assistant"]
    assert response_count["value"] == 2


@pytest.mark.asyncio
async def test_agent_forwards_session_id_to_stream_options() -> None:
    received_session = {"value": None}

    def stream_fn(_model, _context, options):
        received_session["value"] = options.session_id
        stream = MockAssistantStream()
        asyncio.get_running_loop().call_soon(lambda: push_done(stream, create_assistant_message(text="ok")))
        return stream

    agent = Agent(AgentOptions(session_id="session-abc", stream_fn=stream_fn))

    await agent.prompt("hello")
    assert received_session["value"] == "session-abc"

    agent.session_id = "session-def"
    await agent.prompt("hello again")
    assert received_session["value"] == "session-def"


async def _noop_tool(_tool_call_id, _params, _signal, _on_update):
    return AgentToolResult(content=[TextContent(text="ok")], details={})
