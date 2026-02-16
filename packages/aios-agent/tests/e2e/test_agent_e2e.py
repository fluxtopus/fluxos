from __future__ import annotations

import asyncio

import pytest

from aios_agent import Agent, AgentOptions
from aios_agent.types import (
    AssistantDoneEvent,
    AssistantErrorEvent,
    AssistantMessage,
    AssistantStartEvent,
    AssistantTextDeltaEvent,
    AssistantTextEndEvent,
    AssistantTextStartEvent,
    Model,
    TextContent,
    ToolCallContent,
    ToolResultMessage,
    Usage,
    UsageCost,
    UserMessage,
)
from tests.unit.helpers import MockAssistantStream
from tests.utils.calculate import calculate_tool

pytestmark = pytest.mark.e2e


def _model(model_id: str = "mock") -> Model:
    return Model(
        id=model_id,
        name=model_id,
        api="mock-api",
        provider="mock",
        reasoning=False,
    )


def _usage() -> Usage:
    return Usage(cost=UsageCost())


def _assistant_message(text: str, *, stop_reason: str = "stop") -> AssistantMessage:
    return AssistantMessage(
        content=[TextContent(text=text)],
        api="mock-api",
        provider="mock",
        model="mock",
        usage=_usage(),
        stop_reason=stop_reason,  # type: ignore[arg-type]
    )


def _extract_text(message) -> str:
    content = message.get("content", "") if isinstance(message, dict) else getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for part in content:
            if getattr(part, "type", None) == "text":
                texts.append(getattr(part, "text", ""))
        return " ".join(texts)
    return ""


def _role(message) -> str:
    if isinstance(message, dict):
        return str(message.get("role", ""))
    return str(getattr(message, "role", ""))


def _smart_stream_fn(_model_obj, context, _options):
    stream = MockAssistantStream()

    def _push() -> None:
        messages = context.messages
        last = messages[-1]

        tool_results = [msg for msg in messages if _role(msg) == "toolResult"]
        if tool_results:
            result_text = _extract_text(tool_results[-1])
            stream.push(
                AssistantDoneEvent(
                    reason="stop",
                    message=_assistant_message(f"Done. {result_text}"),
                )
            )
            return

        user_text = _extract_text(last)
        if "123 * 456" in user_text:
            tool_call_message = AssistantMessage(
                content=[
                    ToolCallContent(
                        id="calc-1",
                        name="calculate",
                        arguments={"expression": "123 * 456"},
                    )
                ],
                api="mock-api",
                provider="mock",
                model="mock",
                usage=_usage(),
                stop_reason="toolUse",
            )
            stream.push(AssistantDoneEvent(reason="toolUse", message=tool_call_message))
            return

        if "My name is Alice" in user_text:
            stream.push(AssistantDoneEvent(reason="stop", message=_assistant_message("Nice to meet you, Alice.")))
            return

        if "What is my name" in user_text:
            stream.push(AssistantDoneEvent(reason="stop", message=_assistant_message("Your name is Alice.")))
            return

        if "2+2" in user_text:
            stream.push(AssistantDoneEvent(reason="stop", message=_assistant_message("4")))
            return

        stream.push(AssistantDoneEvent(reason="stop", message=_assistant_message("OK")))

    asyncio.get_running_loop().call_soon(_push)
    return stream


@pytest.mark.asyncio
async def test_basic_prompt() -> None:
    agent = Agent(
        AgentOptions(
            stream_fn=_smart_stream_fn,
            initial_state={
                "system_prompt": "You are a helpful assistant.",
                "model": _model(),
                "thinking_level": "off",
                "tools": [],
            },
        )
    )

    await agent.prompt("What is 2+2? Answer with just the number.")

    assert agent.state.is_streaming is False
    assert len(agent.state.messages) == 2
    assert _role(agent.state.messages[0]) == "user"
    assert _role(agent.state.messages[1]) == "assistant"
    assert "4" in _extract_text(agent.state.messages[1])


@pytest.mark.asyncio
async def test_tool_execution() -> None:
    agent = Agent(
        AgentOptions(
            stream_fn=_smart_stream_fn,
            initial_state={
                "system_prompt": "Use tools for math.",
                "model": _model(),
                "thinking_level": "off",
                "tools": [calculate_tool],
            },
        )
    )

    await agent.prompt("Calculate 123 * 456 using the calculator tool.")

    assert agent.state.is_streaming is False
    assert len(agent.state.messages) >= 3

    tool_result_msg = next((m for m in agent.state.messages if getattr(m, "role", None) == "toolResult"), None)
    assert tool_result_msg is not None
    assert "56088" in _extract_text(tool_result_msg)

    final_message = agent.state.messages[-1]
    assert getattr(final_message, "role", None) == "assistant"
    assert "56088" in _extract_text(final_message)


@pytest.mark.asyncio
async def test_abort_execution() -> None:
    def abortable_stream_fn(_model_obj, _context, options):
        stream = MockAssistantStream()

        def _start() -> None:
            partial = AssistantMessage(
                content=[TextContent(text="")],
                api="mock-api",
                provider="mock",
                model="mock",
                usage=_usage(),
            )
            stream.push(AssistantStartEvent(partial=partial))

            async def _watch_abort() -> None:
                while True:
                    if options.signal and options.signal.aborted:
                        error_message = AssistantMessage(
                            content=[TextContent(text="")],
                            api="mock-api",
                            provider="mock",
                            model="mock",
                            usage=_usage(),
                            stop_reason="aborted",
                            error_message="Aborted",
                        )
                        stream.push(AssistantErrorEvent(reason="aborted", error=error_message))
                        return
                    await asyncio.sleep(0.01)

            asyncio.create_task(_watch_abort())

        asyncio.get_running_loop().call_soon(_start)
        return stream

    agent = Agent(
        AgentOptions(
            stream_fn=abortable_stream_fn,
            initial_state={
                "system_prompt": "You are helpful.",
                "model": _model(),
                "thinking_level": "off",
                "tools": [calculate_tool],
            },
        )
    )

    prompt_task = asyncio.create_task(agent.prompt("Calculate a lot of things."))
    await asyncio.sleep(0.05)
    agent.abort()
    await prompt_task

    assert agent.state.is_streaming is False
    assert len(agent.state.messages) >= 2
    last_message = agent.state.messages[-1]
    assert getattr(last_message, "role", None) == "assistant"
    assert getattr(last_message, "stop_reason", None) == "aborted"
    assert agent.state.error is not None


@pytest.mark.asyncio
async def test_state_updates_during_streaming() -> None:
    def streaming_fn(_model_obj, _context, _options):
        stream = MockAssistantStream()

        def _push() -> None:
            partial = AssistantMessage(
                content=[TextContent(text="")],
                api="mock-api",
                provider="mock",
                model="mock",
                usage=_usage(),
            )
            stream.push(AssistantStartEvent(partial=partial))
            stream.push(AssistantTextStartEvent(content_index=0, partial=partial))
            partial.content[0].text += "Hello"
            stream.push(AssistantTextDeltaEvent(content_index=0, delta="Hello", partial=partial))
            stream.push(AssistantTextEndEvent(content_index=0, content="Hello", partial=partial))
            stream.push(AssistantDoneEvent(reason="stop", message=partial))

        asyncio.get_running_loop().call_soon(_push)
        return stream

    agent = Agent(
        AgentOptions(
            stream_fn=streaming_fn,
            initial_state={
                "system_prompt": "You are helpful.",
                "model": _model(),
                "thinking_level": "off",
                "tools": [],
            },
        )
    )

    events = []
    agent.subscribe(lambda event: events.append(event.type))

    await agent.prompt("Count from 1 to 5.")

    assert "agent_start" in events
    assert "agent_end" in events
    assert "message_start" in events
    assert "message_end" in events
    assert "message_update" in events


@pytest.mark.asyncio
async def test_multi_turn_conversation() -> None:
    agent = Agent(
        AgentOptions(
            stream_fn=_smart_stream_fn,
            initial_state={
                "system_prompt": "You are helpful.",
                "model": _model(),
                "thinking_level": "off",
                "tools": [],
            },
        )
    )

    await agent.prompt("My name is Alice.")
    assert len(agent.state.messages) == 2

    await agent.prompt("What is my name?")
    assert len(agent.state.messages) == 4
    assert "alice" in _extract_text(agent.state.messages[-1]).lower()


@pytest.mark.asyncio
async def test_continue_validation_no_messages() -> None:
    agent = Agent(
        AgentOptions(
            stream_fn=_smart_stream_fn,
            initial_state={"system_prompt": "Test", "model": _model()},
        )
    )

    with pytest.raises(RuntimeError, match="No messages to continue from"):
        await agent.continue_()


@pytest.mark.asyncio
async def test_continue_validation_last_assistant() -> None:
    agent = Agent(
        AgentOptions(
            stream_fn=_smart_stream_fn,
            initial_state={"system_prompt": "Test", "model": _model()},
        )
    )

    agent.replace_messages([_assistant_message("Hello")])

    with pytest.raises(RuntimeError, match="Cannot continue from message role: assistant"):
        await agent.continue_()


@pytest.mark.asyncio
async def test_continue_from_user_message() -> None:
    agent = Agent(
        AgentOptions(
            stream_fn=_smart_stream_fn,
            initial_state={
                "system_prompt": "Follow instructions exactly.",
                "model": _model(),
                "thinking_level": "off",
                "tools": [],
            },
        )
    )

    agent.replace_messages([
        UserMessage(content=[TextContent(text="Say exactly: HELLO WORLD")]),
    ])

    await agent.continue_()

    assert agent.state.is_streaming is False
    assert len(agent.state.messages) == 2
    assert getattr(agent.state.messages[0], "role", None) == "user"
    assert getattr(agent.state.messages[1], "role", None) == "assistant"


@pytest.mark.asyncio
async def test_continue_from_tool_result() -> None:
    def continue_stream_fn(_model_obj, context, _options):
        stream = MockAssistantStream()

        def _push() -> None:
            has_tool_result = any(getattr(m, "role", None) == "toolResult" for m in context.messages)
            if has_tool_result:
                stream.push(AssistantDoneEvent(reason="stop", message=_assistant_message("The answer is 8.")))
            else:
                stream.push(AssistantDoneEvent(reason="stop", message=_assistant_message("OK")))

        asyncio.get_running_loop().call_soon(_push)
        return stream

    agent = Agent(
        AgentOptions(
            stream_fn=continue_stream_fn,
            initial_state={
                "system_prompt": "After getting a result, state the answer.",
                "model": _model(),
                "thinking_level": "off",
                "tools": [calculate_tool],
            },
        )
    )

    assistant_message = AssistantMessage(
        content=[
            TextContent(text="Let me calculate that."),
            ToolCallContent(id="calc-1", name="calculate", arguments={"expression": "5 + 3"}),
        ],
        api="mock-api",
        provider="mock",
        model="mock",
        usage=_usage(),
        stop_reason="toolUse",
    )

    tool_result = ToolResultMessage(
        tool_call_id="calc-1",
        tool_name="calculate",
        content=[TextContent(text="5 + 3 = 8")],
        is_error=False,
    )

    agent.replace_messages([
        UserMessage(content=[TextContent(text="What is 5 + 3?")]),
        assistant_message,
        tool_result,
    ])

    await agent.continue_()

    assert agent.state.is_streaming is False
    assert len(agent.state.messages) >= 4
    last = agent.state.messages[-1]
    assert getattr(last, "role", None) == "assistant"
    assert "8" in _extract_text(last)
