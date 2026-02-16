from __future__ import annotations

import asyncio
import inspect
from dataclasses import replace
from typing import Any

from .event_stream import EventStream
from .types import (
    AgentContext,
    AgentEndEvent,
    AgentEvent,
    AgentLoopConfig,
    AgentMessage,
    AgentStartEvent,
    AgentTool,
    AgentToolResult,
    AssistantErrorEvent,
    AssistantMessage,
    AssistantStartEvent,
    Context,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    Model,
    TextContent,
    ToolCallContent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
    ToolResultMessage,
    TurnEndEvent,
    TurnStartEvent,
    validate_tool_arguments,
)


def agent_loop(
    prompts: list[AgentMessage],
    context: AgentContext,
    config: AgentLoopConfig,
    signal: Any | None = None,
    stream_fn: Any | None = None,
) -> EventStream[AgentEvent, list[AgentMessage]]:
    stream = _create_agent_stream()

    async def _run() -> None:
        new_messages: list[AgentMessage] = list(prompts)
        current_context = AgentContext(
            system_prompt=context.system_prompt,
            messages=[*context.messages, *prompts],
            tools=context.tools,
        )

        try:
            stream.push(AgentStartEvent())
            stream.push(TurnStartEvent())
            for prompt in prompts:
                stream.push(MessageStartEvent(message=prompt))
                stream.push(MessageEndEvent(message=prompt))

            await _run_loop(current_context, new_messages, config, signal, stream, stream_fn)
        except Exception:
            stream.push(AgentEndEvent(messages=new_messages))
            stream.end(new_messages)

    asyncio.create_task(_run())
    return stream


def agent_loop_continue(
    context: AgentContext,
    config: AgentLoopConfig,
    signal: Any | None = None,
    stream_fn: Any | None = None,
) -> EventStream[AgentEvent, list[AgentMessage]]:
    if not context.messages:
        raise ValueError("Cannot continue: no messages in context")

    last = context.messages[-1]
    if _message_role(last) == "assistant":
        raise ValueError("Cannot continue from message role: assistant")

    stream = _create_agent_stream()

    async def _run() -> None:
        new_messages: list[AgentMessage] = []
        current_context = AgentContext(
            system_prompt=context.system_prompt,
            messages=list(context.messages),
            tools=context.tools,
        )

        try:
            stream.push(AgentStartEvent())
            stream.push(TurnStartEvent())
            await _run_loop(current_context, new_messages, config, signal, stream, stream_fn)
        except Exception:
            stream.push(AgentEndEvent(messages=new_messages))
            stream.end(new_messages)

    asyncio.create_task(_run())
    return stream


def _create_agent_stream() -> EventStream[AgentEvent, list[AgentMessage]]:
    return EventStream[AgentEvent, list[AgentMessage]](
        lambda event: getattr(event, "type", "") == "agent_end",
        lambda event: event.messages if isinstance(event, AgentEndEvent) else [],
    )


async def _run_loop(
    current_context: AgentContext,
    new_messages: list[AgentMessage],
    config: AgentLoopConfig,
    signal: Any | None,
    stream: EventStream[AgentEvent, list[AgentMessage]],
    stream_fn: Any | None,
) -> None:
    first_turn = True
    pending_messages = await _get_messages(config.get_steering_messages)

    while True:
        has_more_tool_calls = True
        steering_after_tools: list[AgentMessage] | None = None

        while has_more_tool_calls or pending_messages:
            if not first_turn:
                stream.push(TurnStartEvent())
            else:
                first_turn = False

            if pending_messages:
                for message in pending_messages:
                    stream.push(MessageStartEvent(message=message))
                    stream.push(MessageEndEvent(message=message))
                    current_context.messages.append(message)
                    new_messages.append(message)
                pending_messages = []

            message = await _stream_assistant_response(current_context, config, signal, stream, stream_fn)
            new_messages.append(message)

            if message.stop_reason in ("error", "aborted"):
                stream.push(TurnEndEvent(message=message, tool_results=[]))
                stream.push(AgentEndEvent(messages=new_messages))
                stream.end(new_messages)
                return

            tool_calls = [part for part in message.content if _is_tool_call(part)]
            has_more_tool_calls = len(tool_calls) > 0

            tool_results: list[ToolResultMessage] = []
            if has_more_tool_calls:
                tool_execution = await _execute_tool_calls(
                    current_context.tools,
                    message,
                    signal,
                    stream,
                    config.get_steering_messages,
                )
                tool_results.extend(tool_execution["tool_results"])
                steering_after_tools = tool_execution.get("steering_messages")

                for result in tool_results:
                    current_context.messages.append(result)
                    new_messages.append(result)

            stream.push(TurnEndEvent(message=message, tool_results=tool_results))

            if steering_after_tools:
                pending_messages = steering_after_tools
                steering_after_tools = None
            else:
                pending_messages = await _get_messages(config.get_steering_messages)

        follow_up_messages = await _get_messages(config.get_follow_up_messages)
        if follow_up_messages:
            pending_messages = follow_up_messages
            continue

        break

    stream.push(AgentEndEvent(messages=new_messages))
    stream.end(new_messages)


async def _stream_assistant_response(
    context: AgentContext,
    config: AgentLoopConfig,
    signal: Any | None,
    stream: EventStream[AgentEvent, list[AgentMessage]],
    stream_fn: Any | None,
) -> AssistantMessage:
    if not config.model:
        raise ValueError("AgentLoopConfig.model is required")
    if not config.convert_to_llm:
        raise ValueError("AgentLoopConfig.convert_to_llm is required")

    messages = context.messages
    if config.transform_context:
        transformed = config.transform_context(messages, signal)
        messages = await _maybe_await(transformed)

    llm_messages = await _maybe_await(config.convert_to_llm(messages))

    llm_context = Context(
        system_prompt=context.system_prompt,
        messages=llm_messages,
        tools=context.tools,
    )

    selected_stream_fn = stream_fn
    if selected_stream_fn is None:
        raise RuntimeError("No stream function provided. Set Agent.stream_fn or pass stream_fn to agent_loop().")

    resolved_api_key = config.api_key
    if config.get_api_key:
        resolved_api_key = await _maybe_await(config.get_api_key(config.model.provider)) or config.api_key

    options = replace(config)
    options.api_key = resolved_api_key
    options.signal = signal

    response_candidate = selected_stream_fn(config.model, llm_context, options)
    response = await _maybe_await(response_candidate)

    partial_message: AssistantMessage | None = None
    added_partial = False

    async for event in response:
        event_type = getattr(event, "type", "")

        if event_type == "start":
            if not isinstance(event, AssistantStartEvent):
                partial_message = getattr(event, "partial")
            else:
                partial_message = event.partial
            context.messages.append(partial_message)
            added_partial = True
            stream.push(MessageStartEvent(message=partial_message))
            continue

        if event_type in {
            "text_start",
            "text_delta",
            "text_end",
            "thinking_start",
            "thinking_delta",
            "thinking_end",
            "toolcall_start",
            "toolcall_delta",
            "toolcall_end",
        }:
            if partial_message is not None:
                partial_message = getattr(event, "partial", partial_message)
                context.messages[-1] = partial_message
                stream.push(
                    MessageUpdateEvent(
                        assistant_message_event=event,
                        message=partial_message,
                    )
                )
            continue

        if event_type in {"done", "error"}:
            final_message = await response.result()
            if added_partial:
                context.messages[-1] = final_message
            else:
                context.messages.append(final_message)
                stream.push(MessageStartEvent(message=final_message))
            stream.push(MessageEndEvent(message=final_message))
            return final_message

    return await response.result()


async def _execute_tool_calls(
    tools: list[AgentTool] | None,
    assistant_message: AssistantMessage,
    signal: Any | None,
    stream: EventStream[AgentEvent, list[AgentMessage]],
    get_steering_messages: Any | None,
) -> dict[str, Any]:
    tool_calls = [_to_tool_call(part) for part in assistant_message.content if _is_tool_call(part)]
    results: list[ToolResultMessage] = []
    steering_messages: list[AgentMessage] | None = None

    for index, tool_call in enumerate(tool_calls):
        tool = None
        if tools:
            tool = next((candidate for candidate in tools if candidate.name == tool_call.name), None)

        stream.push(
            ToolExecutionStartEvent(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                args=tool_call.arguments,
            )
        )

        is_error = False
        try:
            if tool is None:
                raise RuntimeError(f"Tool {tool_call.name} not found")

            validated_args = validate_tool_arguments(tool, tool_call)

            def _on_update(partial_result: AgentToolResult) -> None:
                stream.push(
                    ToolExecutionUpdateEvent(
                        tool_call_id=tool_call.id,
                        tool_name=tool_call.name,
                        args=tool_call.arguments,
                        partial_result=partial_result,
                    )
                )

            result = await tool.execute(tool_call.id, validated_args, signal, _on_update)
        except Exception as exc:
            result = AgentToolResult(
                content=[TextContent(text=str(exc))],
                details={},
            )
            is_error = True

        stream.push(
            ToolExecutionEndEvent(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                result=result,
                is_error=is_error,
            )
        )

        tool_result_message = ToolResultMessage(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            content=result.content,
            details=result.details,
            is_error=is_error,
        )

        results.append(tool_result_message)
        stream.push(MessageStartEvent(message=tool_result_message))
        stream.push(MessageEndEvent(message=tool_result_message))

        if get_steering_messages:
            steering = await _get_messages(get_steering_messages)
            if steering:
                steering_messages = steering
                for skipped in tool_calls[index + 1 :]:
                    results.append(_skip_tool_call(skipped, stream))
                break

    return {
        "tool_results": results,
        "steering_messages": steering_messages,
    }


def _skip_tool_call(
    tool_call: ToolCallContent,
    stream: EventStream[AgentEvent, list[AgentMessage]],
) -> ToolResultMessage:
    result = AgentToolResult(
        content=[TextContent(text="Skipped due to queued user message.")],
        details={},
    )

    stream.push(
        ToolExecutionStartEvent(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            args=tool_call.arguments,
        )
    )
    stream.push(
        ToolExecutionEndEvent(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            result=result,
            is_error=True,
        )
    )

    message = ToolResultMessage(
        tool_call_id=tool_call.id,
        tool_name=tool_call.name,
        content=result.content,
        details={},
        is_error=True,
    )
    stream.push(MessageStartEvent(message=message))
    stream.push(MessageEndEvent(message=message))
    return message


async def _get_messages(callback: Any | None) -> list[AgentMessage]:
    if not callback:
        return []
    result = callback()
    messages = await _maybe_await(result)
    return list(messages or [])


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _is_tool_call(part: Any) -> bool:
    if isinstance(part, ToolCallContent):
        return True
    if isinstance(part, dict):
        return part.get("type") == "toolCall"
    return getattr(part, "type", None) == "toolCall"


def _to_tool_call(part: Any) -> ToolCallContent:
    if isinstance(part, ToolCallContent):
        return part
    if isinstance(part, dict):
        return ToolCallContent(
            id=str(part.get("id", "")),
            name=str(part.get("name", "")),
            arguments=dict(part.get("arguments", {})),
        )
    return ToolCallContent(
        id=str(getattr(part, "id", "")),
        name=str(getattr(part, "name", "")),
        arguments=dict(getattr(part, "arguments", {})),
    )


def _message_role(message: AgentMessage) -> str:
    if isinstance(message, dict):
        return str(message.get("role", ""))
    return str(getattr(message, "role", ""))


def build_error_message(model: Model, error: Exception | str, aborted: bool = False) -> AssistantMessage:
    return AssistantMessage(
        content=[TextContent(text="")],
        api=model.api,
        provider=model.provider,
        model=model.id,
        stop_reason="aborted" if aborted else "error",
        error_message=str(error),
    )


def as_error_event(message: AssistantMessage) -> AssistantErrorEvent:
    return AssistantErrorEvent(reason="aborted" if message.stop_reason == "aborted" else "error", error=message)

