from __future__ import annotations

import asyncio

from flux_agent import EventStream
from flux_agent.types import (
    AssistantDoneEvent,
    AssistantErrorEvent,
    AssistantMessage,
    AssistantMessageEvent,
    Model,
    TextContent,
    Usage,
    UsageCost,
)


class MockAssistantStream(EventStream[AssistantMessageEvent, AssistantMessage]):
    def __init__(self) -> None:
        super().__init__(
            lambda event: getattr(event, "type", "") in {"done", "error"},
            lambda event: event.message if getattr(event, "type", "") == "done" else event.error,
        )


def create_usage() -> Usage:
    return Usage(
        input=0,
        output=0,
        cache_read=0,
        cache_write=0,
        total_tokens=0,
        cost=UsageCost(input=0, output=0, cache_read=0, cache_write=0, total=0),
    )


def create_model() -> Model:
    return Model(
        id="mock",
        name="mock",
        api="openai-responses",
        provider="openai",
        base_url="https://example.invalid",
        reasoning=False,
        max_tokens=2048,
    )


def create_assistant_message(
    text: str | None = None,
    content: list | None = None,
    stop_reason: str = "stop",
) -> AssistantMessage:
    payload = content or [TextContent(text=text or "")]
    return AssistantMessage(
        content=payload,
        api="openai-responses",
        provider="openai",
        model="mock",
        usage=create_usage(),
        stop_reason=stop_reason,  # type: ignore[arg-type]
    )


def push_done(stream: MockAssistantStream, message: AssistantMessage) -> None:
    stream.push(AssistantDoneEvent(reason=message.stop_reason if message.stop_reason in {"stop", "length", "toolUse"} else "stop", message=message))


def push_error(stream: MockAssistantStream, message: AssistantMessage) -> None:
    stream.push(AssistantErrorEvent(reason="aborted" if message.stop_reason == "aborted" else "error", error=message))


async def schedule_push(callback) -> None:
    await asyncio.sleep(0)
    callback()

