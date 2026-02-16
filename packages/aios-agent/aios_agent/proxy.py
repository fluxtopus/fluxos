from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any

import httpx

from .event_stream import EventStream
from .types import (
    AssistantDoneEvent,
    AssistantErrorEvent,
    AssistantMessage,
    AssistantMessageEvent,
    AssistantStartEvent,
    AssistantTextDeltaEvent,
    AssistantTextEndEvent,
    AssistantTextStartEvent,
    AssistantThinkingDeltaEvent,
    AssistantThinkingEndEvent,
    AssistantThinkingStartEvent,
    AssistantToolCallDeltaEvent,
    AssistantToolCallEndEvent,
    AssistantToolCallStartEvent,
    Context,
    Model,
    SimpleStreamOptions,
    StopReason,
    TextContent,
    ThinkingContent,
    ToolCallContent,
    Usage,
    UsageCost,
)


class ProxyError(RuntimeError):
    pass


class ProxyMessageEventStream(EventStream[AssistantMessageEvent, AssistantMessage]):
    def __init__(self) -> None:
        super().__init__(
            lambda event: getattr(event, "type", "") in {"done", "error"},
            lambda event: event.message if getattr(event, "type", "") == "done" else event.error,
        )


@dataclass
class ProxyStreamOptions(SimpleStreamOptions):
    auth_token: str = ""
    proxy_url: str = ""


def stream_proxy(model: Model, context: Context, options: ProxyStreamOptions) -> ProxyMessageEventStream:
    stream = ProxyMessageEventStream()

    async def _run() -> None:
        partial = AssistantMessage(
            content=[],
            api=model.api,
            provider=model.provider,
            model=model.id,
            usage=Usage(cost=UsageCost()),
        )
        partial_json: dict[int, str] = {}

        try:
            if not options.proxy_url:
                raise ProxyError("proxy_url is required")
            if not options.auth_token:
                raise ProxyError("auth_token is required")

            payload = {
                "model": _serialize(model),
                "context": _serialize_context(context),
                "options": {
                    "temperature": options.temperature,
                    "maxTokens": options.max_tokens,
                    "reasoning": options.reasoning,
                },
            }

            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{options.proxy_url.rstrip('/')}/api/stream",
                    headers={
                        "Authorization": f"Bearer {options.auth_token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        message = f"Proxy error: {response.status_code}"
                        try:
                            data = await response.aread()
                            parsed = json.loads(data.decode("utf-8"))
                            if isinstance(parsed, dict) and parsed.get("error"):
                                message = f"Proxy error: {parsed['error']}"
                        except Exception:
                            pass
                        raise ProxyError(message)

                    async for line in response.aiter_lines():
                        if options.signal and options.signal.aborted:
                            raise ProxyError("Request aborted by user")
                        if not line.startswith("data: "):
                            continue

                        data = line[6:].strip()
                        if not data:
                            continue

                        proxy_event = json.loads(data)
                        event = _process_proxy_event(proxy_event, partial, partial_json)
                        if event:
                            stream.push(event)

            if options.signal and options.signal.aborted:
                raise ProxyError("Request aborted by user")

            stream.end()
        except Exception as exc:
            reason: StopReason = "aborted" if options.signal and options.signal.aborted else "error"
            partial.stop_reason = reason
            partial.error_message = str(exc)
            stream.push(AssistantErrorEvent(reason="aborted" if reason == "aborted" else "error", error=partial))
            stream.end()

    asyncio.create_task(_run())
    return stream


def _process_proxy_event(
    proxy_event: dict[str, Any],
    partial: AssistantMessage,
    partial_json: dict[int, str],
) -> AssistantMessageEvent | None:
    event_type = proxy_event.get("type")

    if event_type == "start":
        return AssistantStartEvent(partial=partial)

    if event_type == "text_start":
        index = int(proxy_event["contentIndex"])
        _set_content(partial, index, TextContent(text=""))
        return AssistantTextStartEvent(content_index=index, partial=partial)

    if event_type == "text_delta":
        index = int(proxy_event["contentIndex"])
        content = _get_content(partial, index)
        if not isinstance(content, TextContent):
            raise ProxyError("Received text_delta for non-text content")
        content.text += str(proxy_event.get("delta", ""))
        return AssistantTextDeltaEvent(content_index=index, delta=str(proxy_event.get("delta", "")), partial=partial)

    if event_type == "text_end":
        index = int(proxy_event["contentIndex"])
        content = _get_content(partial, index)
        if not isinstance(content, TextContent):
            raise ProxyError("Received text_end for non-text content")
        return AssistantTextEndEvent(content_index=index, content=content.text, partial=partial)

    if event_type == "thinking_start":
        index = int(proxy_event["contentIndex"])
        _set_content(partial, index, ThinkingContent(thinking=""))
        return AssistantThinkingStartEvent(content_index=index, partial=partial)

    if event_type == "thinking_delta":
        index = int(proxy_event["contentIndex"])
        content = _get_content(partial, index)
        if not isinstance(content, ThinkingContent):
            raise ProxyError("Received thinking_delta for non-thinking content")
        content.thinking += str(proxy_event.get("delta", ""))
        return AssistantThinkingDeltaEvent(content_index=index, delta=str(proxy_event.get("delta", "")), partial=partial)

    if event_type == "thinking_end":
        index = int(proxy_event["contentIndex"])
        content = _get_content(partial, index)
        if not isinstance(content, ThinkingContent):
            raise ProxyError("Received thinking_end for non-thinking content")
        signature = proxy_event.get("contentSignature")
        if signature:
            content.thinking_signature = str(signature)
        return AssistantThinkingEndEvent(content_index=index, content=content.thinking, partial=partial)

    if event_type == "toolcall_start":
        index = int(proxy_event["contentIndex"])
        tool_call = ToolCallContent(
            id=str(proxy_event.get("id", "")),
            name=str(proxy_event.get("toolName", "")),
            arguments={},
        )
        _set_content(partial, index, tool_call)
        partial_json[index] = ""
        return AssistantToolCallStartEvent(content_index=index, partial=partial)

    if event_type == "toolcall_delta":
        index = int(proxy_event["contentIndex"])
        content = _get_content(partial, index)
        if not isinstance(content, ToolCallContent):
            raise ProxyError("Received toolcall_delta for non-toolCall content")
        delta = str(proxy_event.get("delta", ""))
        partial_json[index] = partial_json.get(index, "") + delta
        parsed = _parse_streaming_json(partial_json[index])
        if isinstance(parsed, dict):
            content.arguments = parsed
        return AssistantToolCallDeltaEvent(content_index=index, delta=delta, partial=partial)

    if event_type == "toolcall_end":
        index = int(proxy_event["contentIndex"])
        content = _get_content(partial, index)
        if not isinstance(content, ToolCallContent):
            return None
        partial_json.pop(index, None)
        return AssistantToolCallEndEvent(content_index=index, tool_call=content, partial=partial)

    if event_type == "done":
        partial.stop_reason = str(proxy_event.get("reason", "stop"))  # type: ignore[assignment]
        partial.usage = _deserialize_usage(proxy_event.get("usage"))
        return AssistantDoneEvent(reason=partial.stop_reason if partial.stop_reason in {"stop", "length", "toolUse"} else "stop", message=partial)

    if event_type == "error":
        reason = str(proxy_event.get("reason", "error"))
        partial.stop_reason = "aborted" if reason == "aborted" else "error"
        partial.error_message = proxy_event.get("errorMessage")
        partial.usage = _deserialize_usage(proxy_event.get("usage"))
        return AssistantErrorEvent(reason="aborted" if reason == "aborted" else "error", error=partial)

    return None


def _serialize_context(context: Context) -> dict[str, Any]:
    return {
        "systemPrompt": context.system_prompt,
        "messages": [_serialize(message) for message in context.messages],
        # Tool execution happens client-side in this package.
        "tools": None,
    }


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


def _deserialize_usage(value: Any) -> Usage:
    if not isinstance(value, dict):
        return Usage(cost=UsageCost())

    cost = value.get("cost", {}) if isinstance(value.get("cost"), dict) else {}
    return Usage(
        input=int(value.get("input", 0)),
        output=int(value.get("output", 0)),
        cache_read=int(value.get("cacheRead", value.get("cache_read", 0))),
        cache_write=int(value.get("cacheWrite", value.get("cache_write", 0))),
        total_tokens=int(value.get("totalTokens", value.get("total_tokens", 0))),
        cost=UsageCost(
            input=float(cost.get("input", 0)),
            output=float(cost.get("output", 0)),
            cache_read=float(cost.get("cacheRead", cost.get("cache_read", 0))),
            cache_write=float(cost.get("cacheWrite", cost.get("cache_write", 0))),
            total=float(cost.get("total", 0)),
        ),
    )


def _set_content(partial: AssistantMessage, index: int, content: Any) -> None:
    while len(partial.content) <= index:
        partial.content.append(TextContent(text=""))
    partial.content[index] = content


def _get_content(partial: AssistantMessage, index: int) -> Any:
    if index >= len(partial.content):
        raise ProxyError(f"Content index out of range: {index}")
    return partial.content[index]


def _parse_streaming_json(value: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None
