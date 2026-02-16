"""flux-agent - Stateful agent loop and runtime for Python."""

from .agent import Agent, AgentOptions
from .agent_loop import agent_loop, agent_loop_continue
from .event_stream import EventStream
from .proxy import ProxyMessageEventStream, ProxyStreamOptions, stream_proxy
from .types import (
    AgentContext,
    AgentLoopConfig,
    AgentMessage,
    AgentState,
    AgentTool,
    AgentToolResult,
    AssistantMessage,
    AssistantMessageEvent,
    Context,
    ImageContent,
    Message,
    Model,
    TextContent,
    ThinkingBudgets,
    ThinkingContent,
    ThinkingLevel,
    ToolCallContent,
    ToolResultMessage,
)
from .version import __version__

__all__ = [
    "Agent",
    "AgentOptions",
    "EventStream",
    "agent_loop",
    "agent_loop_continue",
    "stream_proxy",
    "ProxyMessageEventStream",
    "ProxyStreamOptions",
    "Model",
    "Context",
    "Message",
    "AgentMessage",
    "AssistantMessage",
    "ToolResultMessage",
    "AgentContext",
    "AgentLoopConfig",
    "AgentState",
    "AgentTool",
    "AgentToolResult",
    "TextContent",
    "ImageContent",
    "ThinkingContent",
    "ToolCallContent",
    "AssistantMessageEvent",
    "ThinkingLevel",
    "ThinkingBudgets",
    "__version__",
]
