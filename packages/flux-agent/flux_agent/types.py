from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Literal,
    Protocol,
    TypeAlias,
    TypeVar,
    cast,
)

if TYPE_CHECKING:
    from .event_stream import EventStream


ThinkingLevel: TypeAlias = Literal["off", "minimal", "low", "medium", "high", "xhigh"]
Transport: TypeAlias = Literal["sse", "websocket", "auto"]
StopReason: TypeAlias = Literal["stop", "length", "toolUse", "aborted", "error"]


def now_ms() -> int:
    import time

    return int(time.time() * 1000)


@dataclass
class UsageCost:
    input: float = 0.0
    output: float = 0.0
    cache_read: float = 0.0
    cache_write: float = 0.0
    total: float = 0.0


@dataclass
class Usage:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    total_tokens: int = 0
    cost: UsageCost = field(default_factory=UsageCost)


@dataclass
class TextContent:
    text: str
    type: Literal["text"] = "text"


@dataclass
class ImageContent:
    data: str
    mime_type: str
    type: Literal["image"] = "image"


@dataclass
class ThinkingContent:
    thinking: str
    thinking_signature: str | None = None
    type: Literal["thinking"] = "thinking"


@dataclass
class ToolCallContent:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    type: Literal["toolCall"] = "toolCall"


UserContentPart: TypeAlias = TextContent | ImageContent
AssistantContentPart: TypeAlias = TextContent | ThinkingContent | ToolCallContent
ToolResultContentPart: TypeAlias = TextContent | ImageContent


@dataclass
class UserMessage:
    content: str | list[UserContentPart]
    timestamp: int = field(default_factory=now_ms)
    role: Literal["user"] = "user"


@dataclass
class AssistantMessage:
    content: list[AssistantContentPart]
    api: str
    provider: str
    model: str
    usage: Usage = field(default_factory=Usage)
    stop_reason: StopReason = "stop"
    timestamp: int = field(default_factory=now_ms)
    error_message: str | None = None
    role: Literal["assistant"] = "assistant"


@dataclass
class ToolResultMessage:
    tool_call_id: str
    tool_name: str
    content: list[ToolResultContentPart]
    details: Any = None
    is_error: bool = False
    timestamp: int = field(default_factory=now_ms)
    role: Literal["toolResult"] = "toolResult"


Message: TypeAlias = UserMessage | AssistantMessage | ToolResultMessage
AgentMessage: TypeAlias = Message | dict[str, Any] | Any


@dataclass
class Model:
    id: str
    name: str
    api: str
    provider: str
    base_url: str | None = None
    reasoning: bool = False
    max_tokens: int | None = None


ThinkingBudgets: TypeAlias = dict[Literal["minimal", "low", "medium", "high"], int]


class AbortSignal(Protocol):
    @property
    def aborted(self) -> bool:
        ...


@dataclass
class SimpleStreamOptions:
    api_key: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    reasoning: ThinkingLevel | None = None
    signal: AbortSignal | None = None
    session_id: str | None = None
    thinking_budgets: ThinkingBudgets | None = None
    transport: Transport = "sse"
    max_retry_delay_ms: int | None = None


@dataclass
class AgentToolResult:
    content: list[ToolResultContentPart]
    details: Any


AgentToolUpdateCallback: TypeAlias = Callable[[AgentToolResult], None]
AgentToolExecute: TypeAlias = Callable[
    [str, dict[str, Any], AbortSignal | None, AgentToolUpdateCallback | None],
    Awaitable[AgentToolResult],
]


@dataclass
class AgentTool:
    name: str
    label: str
    description: str
    execute: AgentToolExecute
    parameters: Any = None
    validate: Callable[[dict[str, Any]], dict[str, Any]] | None = None


@dataclass
class Context:
    system_prompt: str
    messages: list[Message]
    tools: list[AgentTool] | None = None


@dataclass
class AgentContext:
    system_prompt: str
    messages: list[AgentMessage]
    tools: list[AgentTool] | None = None


ConvertToLlm: TypeAlias = Callable[[list[AgentMessage]], list[Message] | Awaitable[list[Message]]]
TransformContext: TypeAlias = Callable[[list[AgentMessage], AbortSignal | None], Awaitable[list[AgentMessage]]]
QueuedMessagesCallback: TypeAlias = Callable[[], list[AgentMessage] | Awaitable[list[AgentMessage]]]
ApiKeyCallback: TypeAlias = Callable[[str], str | None | Awaitable[str | None]]


@dataclass
class AgentLoopConfig(SimpleStreamOptions):
    model: Model | None = None
    convert_to_llm: ConvertToLlm | None = None
    transform_context: TransformContext | None = None
    get_api_key: ApiKeyCallback | None = None
    get_steering_messages: QueuedMessagesCallback | None = None
    get_follow_up_messages: QueuedMessagesCallback | None = None


# Assistant stream events
@dataclass
class AssistantStartEvent:
    partial: AssistantMessage
    type: Literal["start"] = "start"


@dataclass
class AssistantTextStartEvent:
    content_index: int
    partial: AssistantMessage
    type: Literal["text_start"] = "text_start"


@dataclass
class AssistantTextDeltaEvent:
    content_index: int
    delta: str
    partial: AssistantMessage
    type: Literal["text_delta"] = "text_delta"


@dataclass
class AssistantTextEndEvent:
    content_index: int
    content: str
    partial: AssistantMessage
    type: Literal["text_end"] = "text_end"


@dataclass
class AssistantThinkingStartEvent:
    content_index: int
    partial: AssistantMessage
    type: Literal["thinking_start"] = "thinking_start"


@dataclass
class AssistantThinkingDeltaEvent:
    content_index: int
    delta: str
    partial: AssistantMessage
    type: Literal["thinking_delta"] = "thinking_delta"


@dataclass
class AssistantThinkingEndEvent:
    content_index: int
    content: str
    partial: AssistantMessage
    type: Literal["thinking_end"] = "thinking_end"


@dataclass
class AssistantToolCallStartEvent:
    content_index: int
    partial: AssistantMessage
    type: Literal["toolcall_start"] = "toolcall_start"


@dataclass
class AssistantToolCallDeltaEvent:
    content_index: int
    delta: str
    partial: AssistantMessage
    type: Literal["toolcall_delta"] = "toolcall_delta"


@dataclass
class AssistantToolCallEndEvent:
    content_index: int
    tool_call: ToolCallContent
    partial: AssistantMessage
    type: Literal["toolcall_end"] = "toolcall_end"


@dataclass
class AssistantDoneEvent:
    reason: Literal["stop", "length", "toolUse"]
    message: AssistantMessage
    type: Literal["done"] = "done"


@dataclass
class AssistantErrorEvent:
    reason: Literal["aborted", "error"]
    error: AssistantMessage
    type: Literal["error"] = "error"


AssistantMessageEvent: TypeAlias = (
    AssistantStartEvent
    | AssistantTextStartEvent
    | AssistantTextDeltaEvent
    | AssistantTextEndEvent
    | AssistantThinkingStartEvent
    | AssistantThinkingDeltaEvent
    | AssistantThinkingEndEvent
    | AssistantToolCallStartEvent
    | AssistantToolCallDeltaEvent
    | AssistantToolCallEndEvent
    | AssistantDoneEvent
    | AssistantErrorEvent
)


# Agent events
@dataclass
class AgentStartEvent:
    type: Literal["agent_start"] = "agent_start"


@dataclass
class AgentEndEvent:
    messages: list[AgentMessage]
    type: Literal["agent_end"] = "agent_end"


@dataclass
class TurnStartEvent:
    type: Literal["turn_start"] = "turn_start"


@dataclass
class TurnEndEvent:
    message: AgentMessage
    tool_results: list[ToolResultMessage]
    type: Literal["turn_end"] = "turn_end"


@dataclass
class MessageStartEvent:
    message: AgentMessage
    type: Literal["message_start"] = "message_start"


@dataclass
class MessageUpdateEvent:
    message: AgentMessage
    assistant_message_event: AssistantMessageEvent
    type: Literal["message_update"] = "message_update"


@dataclass
class MessageEndEvent:
    message: AgentMessage
    type: Literal["message_end"] = "message_end"


@dataclass
class ToolExecutionStartEvent:
    tool_call_id: str
    tool_name: str
    args: Any
    type: Literal["tool_execution_start"] = "tool_execution_start"


@dataclass
class ToolExecutionUpdateEvent:
    tool_call_id: str
    tool_name: str
    args: Any
    partial_result: AgentToolResult
    type: Literal["tool_execution_update"] = "tool_execution_update"


@dataclass
class ToolExecutionEndEvent:
    tool_call_id: str
    tool_name: str
    result: AgentToolResult
    is_error: bool
    type: Literal["tool_execution_end"] = "tool_execution_end"


AgentEvent: TypeAlias = (
    AgentStartEvent
    | AgentEndEvent
    | TurnStartEvent
    | TurnEndEvent
    | MessageStartEvent
    | MessageUpdateEvent
    | MessageEndEvent
    | ToolExecutionStartEvent
    | ToolExecutionUpdateEvent
    | ToolExecutionEndEvent
)


class _AwaitableStream(Protocol):
    def __await__(self):
        ...


StreamFn: TypeAlias = Callable[
    [Model, Context, SimpleStreamOptions],
    "EventStream[AssistantMessageEvent, AssistantMessage]"
    | Awaitable["EventStream[AssistantMessageEvent, AssistantMessage]"],
]


@dataclass
class AgentState:
    system_prompt: str = ""
    model: Model = field(
        default_factory=lambda: Model(
            id="mock-model",
            name="Mock Model",
            api="mock-api",
            provider="mock-provider",
        )
    )
    thinking_level: ThinkingLevel = "off"
    tools: list[AgentTool] = field(default_factory=list)
    messages: list[AgentMessage] = field(default_factory=list)
    is_streaming: bool = False
    stream_message: AgentMessage | None = None
    pending_tool_calls: set[str] = field(default_factory=set)
    error: str | None = None


def message_role(message: AgentMessage) -> str:
    if isinstance(message, dict):
        return str(message.get("role", ""))
    return str(getattr(message, "role", ""))


def is_assistant_message(message: AgentMessage) -> bool:
    return message_role(message) == "assistant"


def as_assistant_message(message: AgentMessage) -> AssistantMessage:
    if not isinstance(message, AssistantMessage):
        raise TypeError("Expected AssistantMessage")
    return message


T = TypeVar("T")


def coerce_awaitable(value: T | Awaitable[T]) -> Awaitable[T]:
    import inspect

    if inspect.isawaitable(value):
        return cast(Awaitable[T], value)

    async def _wrap() -> T:
        return value

    return _wrap()


def validate_tool_arguments(tool: AgentTool, tool_call: ToolCallContent) -> dict[str, Any]:
    args = dict(tool_call.arguments)
    if tool.validate:
        return tool.validate(args)
    return args
