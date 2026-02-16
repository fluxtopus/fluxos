from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable

from .agent_loop import agent_loop, agent_loop_continue, build_error_message
from .types import (
    AgentContext,
    AgentEndEvent,
    AgentEvent,
    AgentLoopConfig,
    AgentMessage,
    AgentState,
    AgentTool,
    ImageContent,
    Message,
    Model,
    TextContent,
    ThinkingBudgets,
    ThinkingLevel,
    Transport,
    message_role,
)


class _AbortSignal:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    @property
    def aborted(self) -> bool:
        return self._event.is_set()


class AbortController:
    def __init__(self) -> None:
        self.signal = _AbortSignal()

    def abort(self) -> None:
        self.signal._event.set()


def default_convert_to_llm(messages: list[AgentMessage]) -> list[Message]:
    return [
        message
        for message in messages
        if message_role(message) in {"user", "assistant", "toolResult"}
    ]


def default_stream_fn(_model: Model, _context: Any, _options: Any):
    raise RuntimeError("No stream function configured. Provide Agent(stream_fn=...) with a provider implementation.")


@dataclass
class AgentOptions:
    initial_state: AgentState | dict[str, Any] | None = None
    convert_to_llm: Callable[[list[AgentMessage]], list[Message] | Any] | None = None
    transform_context: Callable[[list[AgentMessage], Any | None], Any] | None = None
    steering_mode: str = "one-at-a-time"
    follow_up_mode: str = "one-at-a-time"
    stream_fn: Callable[..., Any] | None = None
    session_id: str | None = None
    get_api_key: Callable[[str], Any] | None = None
    thinking_budgets: ThinkingBudgets | None = None
    transport: Transport = "sse"
    max_retry_delay_ms: int | None = None


class Agent:
    def __init__(self, opts: AgentOptions | None = None, **kwargs: Any) -> None:
        options = opts or AgentOptions(**kwargs)

        self._state = AgentState()
        if isinstance(options.initial_state, AgentState):
            self._state = options.initial_state
        elif isinstance(options.initial_state, dict):
            for key, value in options.initial_state.items():
                if hasattr(self._state, key):
                    setattr(self._state, key, value)

        self._listeners: set[Callable[[AgentEvent], None]] = set()
        self._abort_controller: AbortController | None = None
        self._convert_to_llm = options.convert_to_llm or default_convert_to_llm
        self._transform_context = options.transform_context
        self._steering_queue: list[AgentMessage] = []
        self._follow_up_queue: list[AgentMessage] = []
        self._steering_mode = options.steering_mode
        self._follow_up_mode = options.follow_up_mode
        self.stream_fn = options.stream_fn or default_stream_fn
        self._session_id = options.session_id
        self.get_api_key = options.get_api_key
        self._thinking_budgets = options.thinking_budgets
        self._transport: Transport = options.transport
        self._max_retry_delay_ms = options.max_retry_delay_ms
        self._running_prompt: asyncio.Task[None] | None = None

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @session_id.setter
    def session_id(self, value: str | None) -> None:
        self._session_id = value

    @property
    def thinking_budgets(self) -> ThinkingBudgets | None:
        return self._thinking_budgets

    @thinking_budgets.setter
    def thinking_budgets(self, value: ThinkingBudgets | None) -> None:
        self._thinking_budgets = value

    @property
    def transport(self) -> Transport:
        return self._transport

    @property
    def max_retry_delay_ms(self) -> int | None:
        return self._max_retry_delay_ms

    @max_retry_delay_ms.setter
    def max_retry_delay_ms(self, value: int | None) -> None:
        self._max_retry_delay_ms = value

    def subscribe(self, fn: Callable[[AgentEvent], None]) -> Callable[[], None]:
        self._listeners.add(fn)

        def _unsubscribe() -> None:
            self._listeners.discard(fn)

        return _unsubscribe

    def set_system_prompt(self, value: str) -> None:
        self._state.system_prompt = value

    def set_model(self, model: Model) -> None:
        self._state.model = model

    def set_thinking_level(self, level: ThinkingLevel) -> None:
        self._state.thinking_level = level

    def set_steering_mode(self, mode: str) -> None:
        self._steering_mode = mode

    def get_steering_mode(self) -> str:
        return self._steering_mode

    def set_follow_up_mode(self, mode: str) -> None:
        self._follow_up_mode = mode

    def get_follow_up_mode(self) -> str:
        return self._follow_up_mode

    def set_tools(self, tools: list[AgentTool]) -> None:
        self._state.tools = tools

    def set_transport(self, value: Transport) -> None:
        self._transport = value

    def replace_messages(self, messages: list[AgentMessage]) -> None:
        self._state.messages = list(messages)

    def append_message(self, message: AgentMessage) -> None:
        self._state.messages = [*self._state.messages, message]

    def steer(self, message: AgentMessage) -> None:
        self._steering_queue.append(message)

    def follow_up(self, message: AgentMessage) -> None:
        self._follow_up_queue.append(message)

    def clear_steering_queue(self) -> None:
        self._steering_queue = []

    def clear_follow_up_queue(self) -> None:
        self._follow_up_queue = []

    def clear_all_queues(self) -> None:
        self._steering_queue = []
        self._follow_up_queue = []

    def has_queued_messages(self) -> bool:
        return bool(self._steering_queue or self._follow_up_queue)

    def clear_messages(self) -> None:
        self._state.messages = []

    def abort(self) -> None:
        if self._abort_controller:
            self._abort_controller.abort()

    async def wait_for_idle(self) -> None:
        if self._running_prompt:
            await self._running_prompt

    def reset(self) -> None:
        self._state.messages = []
        self._state.is_streaming = False
        self._state.stream_message = None
        self._state.pending_tool_calls = set()
        self._state.error = None
        self.clear_all_queues()

    async def prompt(self, input_message: str | AgentMessage | list[AgentMessage], images: list[ImageContent] | None = None) -> None:
        if self._state.is_streaming:
            raise RuntimeError(
                "Agent is already processing a prompt. Use steer() or follow_up() to queue messages, or wait for completion."
            )

        if isinstance(input_message, list):
            messages = input_message
        elif isinstance(input_message, str):
            content: list[TextContent | ImageContent] = [TextContent(text=input_message)]
            if images:
                content.extend(images)
            messages = [{"role": "user", "content": content, "timestamp": _now_ms()}]
        else:
            messages = [input_message]

        await self._run_loop(messages)

    async def continue_(self) -> None:
        if self._state.is_streaming:
            raise RuntimeError("Agent is already processing. Wait for completion before continuing.")

        messages = self._state.messages
        if not messages:
            raise RuntimeError("No messages to continue from")

        if message_role(messages[-1]) == "assistant":
            queued_steering = self._dequeue_steering_messages()
            if queued_steering:
                await self._run_loop(queued_steering, skip_initial_steering_poll=True)
                return

            queued_follow_up = self._dequeue_follow_up_messages()
            if queued_follow_up:
                await self._run_loop(queued_follow_up)
                return

            raise RuntimeError("Cannot continue from message role: assistant")

        await self._run_loop(None)

    async def _run_loop(self, messages: list[AgentMessage] | None, skip_initial_steering_poll: bool = False) -> None:
        model = self._state.model

        async def _runner() -> None:
            self._abort_controller = AbortController()
            self._state.is_streaming = True
            self._state.stream_message = None
            self._state.error = None

            reasoning = None if self._state.thinking_level == "off" else self._state.thinking_level
            context = AgentContext(
                system_prompt=self._state.system_prompt,
                messages=list(self._state.messages),
                tools=self._state.tools,
            )

            local_skip = skip_initial_steering_poll

            async def _get_steering_messages() -> list[AgentMessage]:
                nonlocal local_skip
                if local_skip:
                    local_skip = False
                    return []
                return self._dequeue_steering_messages()

            config = AgentLoopConfig(
                model=model,
                reasoning=reasoning,
                session_id=self._session_id,
                transport=self._transport,
                thinking_budgets=self._thinking_budgets,
                max_retry_delay_ms=self._max_retry_delay_ms,
                convert_to_llm=self._convert_to_llm,
                transform_context=self._transform_context,
                get_api_key=self.get_api_key,
                get_steering_messages=_get_steering_messages,
                get_follow_up_messages=self._dequeue_follow_up_messages,
            )

            partial: AgentMessage | None = None

            try:
                stream = (
                    agent_loop(messages, context, config, self._abort_controller.signal, self.stream_fn)
                    if messages is not None
                    else agent_loop_continue(context, config, self._abort_controller.signal, self.stream_fn)
                )

                async for event in stream:
                    event_type = getattr(event, "type", "")

                    if event_type in {"message_start", "message_update"}:
                        partial = event.message
                        self._state.stream_message = event.message
                    elif event_type == "message_end":
                        partial = None
                        self._state.stream_message = None
                        self.append_message(event.message)
                    elif event_type == "tool_execution_start":
                        pending = set(self._state.pending_tool_calls)
                        pending.add(event.tool_call_id)
                        self._state.pending_tool_calls = pending
                    elif event_type == "tool_execution_end":
                        pending = set(self._state.pending_tool_calls)
                        pending.discard(event.tool_call_id)
                        self._state.pending_tool_calls = pending
                    elif event_type == "turn_end":
                        if message_role(event.message) == "assistant" and getattr(event.message, "error_message", None):
                            self._state.error = str(getattr(event.message, "error_message"))
                    elif event_type == "agent_end":
                        self._state.is_streaming = False
                        self._state.stream_message = None

                    self._emit(event)

                if partial and message_role(partial) == "assistant":
                    content = getattr(partial, "content", [])
                    only_empty = not any(_has_non_empty_content(part) for part in content)
                    if not only_empty:
                        self.append_message(partial)
                    elif self._abort_controller and self._abort_controller.signal.aborted:
                        raise RuntimeError("Request was aborted")

            except Exception as exc:
                error_message = build_error_message(
                    model,
                    exc,
                    aborted=bool(self._abort_controller and self._abort_controller.signal.aborted),
                )
                self.append_message(error_message)
                self._state.error = str(exc)
                self._emit(AgentEndEvent(messages=[error_message]))
            finally:
                self._state.is_streaming = False
                self._state.stream_message = None
                self._state.pending_tool_calls = set()
                self._abort_controller = None

        task = asyncio.create_task(_runner())
        self._running_prompt = task
        try:
            await task
        finally:
            self._running_prompt = None

    def _dequeue_steering_messages(self) -> list[AgentMessage]:
        if self._steering_mode == "one-at-a-time":
            if self._steering_queue:
                first = self._steering_queue[0]
                self._steering_queue = self._steering_queue[1:]
                return [first]
            return []

        queued = list(self._steering_queue)
        self._steering_queue = []
        return queued

    def _dequeue_follow_up_messages(self) -> list[AgentMessage]:
        if self._follow_up_mode == "one-at-a-time":
            if self._follow_up_queue:
                first = self._follow_up_queue[0]
                self._follow_up_queue = self._follow_up_queue[1:]
                return [first]
            return []

        queued = list(self._follow_up_queue)
        self._follow_up_queue = []
        return queued

    def _emit(self, event: AgentEvent) -> None:
        for listener in list(self._listeners):
            listener(event)

    # TypeScript API aliases for easier migration.
    setSystemPrompt = set_system_prompt
    setModel = set_model
    setThinkingLevel = set_thinking_level
    setSteeringMode = set_steering_mode
    getSteeringMode = get_steering_mode
    setFollowUpMode = set_follow_up_mode
    getFollowUpMode = get_follow_up_mode
    setTools = set_tools
    setTransport = set_transport
    replaceMessages = replace_messages
    appendMessage = append_message
    followUp = follow_up
    clearSteeringQueue = clear_steering_queue
    clearFollowUpQueue = clear_follow_up_queue
    clearAllQueues = clear_all_queues
    hasQueuedMessages = has_queued_messages
    clearMessages = clear_messages
    waitForIdle = wait_for_idle


continue_conversation = Agent.continue_


def _has_non_empty_content(part: Any) -> bool:
    if isinstance(part, dict):
        part_type = part.get("type")
        if part_type == "thinking":
            return bool(str(part.get("thinking", "")).strip())
        if part_type == "text":
            return bool(str(part.get("text", "")).strip())
        if part_type == "toolCall":
            return bool(str(part.get("name", "")).strip())
        return False

    part_type = getattr(part, "type", None)
    if part_type == "thinking":
        return bool(str(getattr(part, "thinking", "")).strip())
    if part_type == "text":
        return bool(str(getattr(part, "text", "")).strip())
    if part_type == "toolCall":
        return bool(str(getattr(part, "name", "")).strip())
    return False


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)

