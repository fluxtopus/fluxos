"""Flux chat handler with tool calling support.

This module contains the main chat orchestration logic that:
- Manages conversations with tool calling
- Handles multi-turn tool execution
"""

from __future__ import annotations
from typing import Any, Dict, List
import json
import structlog

logger = structlog.get_logger(__name__)


def _safe_json_loads(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}


def _message_text(message: Any) -> str:
    def _chunk_text(item: Any) -> str:
        if isinstance(item, dict):
            if item.get("type") == "text":
                return str(item.get("text", ""))
            return ""
        if getattr(item, "type", None) == "text":
            return str(getattr(item, "text", ""))
        return ""

    if isinstance(message, dict):
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: List[str] = []
            for item in content:
                text = _chunk_text(item)
                if text:
                    chunks.append(text)
            return "".join(chunks)
        return ""

    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: List[str] = []
        for item in content:
            text = _chunk_text(item)
            if text:
                chunks.append(text)
        return "".join(chunks)
    return ""


def _convert_history_for_llm(messages: List[Any]) -> List[Dict[str, Any]]:
    history: List[Dict[str, Any]] = []
    for message in messages:
        if isinstance(message, dict):
            role = message.get("role")
            if role == "toolResult":
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": message.get("tool_call_id") or message.get("toolCallId"),
                        "content": _message_text(message),
                    }
                )
                continue
            if role in {"user", "assistant", "tool"}:
                payload: Dict[str, Any] = {"role": role, "content": _message_text(message)}
                if role == "assistant" and message.get("tool_calls"):
                    payload["tool_calls"] = message.get("tool_calls")
                history.append(payload)
            continue

        role = getattr(message, "role", "")
        if role == "toolResult":
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": getattr(message, "tool_call_id", None),
                    "content": _message_text(message),
                }
            )
        elif role in {"user", "assistant", "tool"}:
            payload = {"role": role, "content": _message_text(message)}
            if role == "assistant":
                tool_calls: List[Dict[str, Any]] = []
                for part in getattr(message, "content", []):
                    if getattr(part, "type", None) == "toolCall":
                        tool_calls.append(
                            {
                                "id": getattr(part, "id", ""),
                                "type": "function",
                                "function": {
                                    "name": getattr(part, "name", ""),
                                    "arguments": json.dumps(getattr(part, "arguments", {})),
                                },
                            }
                        )
                if tool_calls:
                    payload["tool_calls"] = tool_calls
            history.append(payload)
    return history


async def _run_with_aios_agent(
    system_prompt: str,
    user_message: str,
    conversation_history: List[Any],
    tool_executor: Any,
    call_llm_func: Any,
    workflow_context: Dict[str, Any],
) -> Dict[str, Any]:
    from aios_agent import Agent, AgentOptions
    from aios_agent.event_stream import EventStream
    from aios_agent.types import (
        AgentTool,
        AgentToolResult,
        AssistantDoneEvent,
        AssistantErrorEvent,
        AssistantMessage,
        Context,
        Model,
        TextContent,
        ToolCallContent,
        Usage,
        UsageCost,
        UserMessage,
    )

    model = Model(
        id="flux-openrouter",
        name="Flux OpenRouter",
        api="openrouter-chat-completions",
        provider="openrouter",
    )

    tool_definitions = tool_executor.get_tool_definitions()
    tool_context = {**workflow_context, "tool_executor": tool_executor}

    tools: List[AgentTool] = []
    for definition in tool_definitions:
        function = definition.get("function", {})
        tool_name = function.get("name", "")
        if not tool_name:
            continue

        async def _execute_tool(
            tool_call_id: str,
            params: Dict[str, Any],
            _signal,
            _on_update,
            *,
            tool_name: str = tool_name,
        ) -> AgentToolResult:
            openrouter_tool_call = {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(params),
                },
            }
            response = await tool_executor.execute_tool_call(openrouter_tool_call, tool_context)
            return AgentToolResult(
                content=[TextContent(text=str(response.get("content", "")))],
                details={
                    "arguments": params,
                    "response": response,
                },
            )

        tools.append(
            AgentTool(
                name=tool_name,
                label=tool_name,
                description=function.get("description", ""),
                parameters=function.get("parameters"),
                execute=_execute_tool,
            )
        )

    def _stream_fn(_model: Model, context: Context, _options: Any):
        stream = EventStream(
            lambda event: getattr(event, "type", "") in {"done", "error"},
            lambda event: event.message if getattr(event, "type", "") == "done" else event.error,
        )

        async def _run() -> None:
            try:
                llm_result = await call_llm_func(
                    system_prompt=context.system_prompt,
                    user_message=None,
                    conversation_history=_convert_history_for_llm(context.messages),
                    tools=tool_definitions or None,
                )

                text = str(llm_result.get("message", "") or "")
                raw_tool_calls = llm_result.get("tool_calls", []) or []

                content: List[Any] = [TextContent(text=text)]
                for raw_tool_call in raw_tool_calls:
                    function_payload = raw_tool_call.get("function", {}) if isinstance(raw_tool_call, dict) else {}
                    content.append(
                        ToolCallContent(
                            id=str(raw_tool_call.get("id", "")),
                            name=str(function_payload.get("name", "")),
                            arguments=_safe_json_loads(function_payload.get("arguments", {})),
                        )
                    )

                message = AssistantMessage(
                    content=content,
                    api=model.api,
                    provider=model.provider,
                    model=model.id,
                    usage=Usage(cost=UsageCost()),
                    stop_reason="toolUse" if raw_tool_calls else "stop",
                )
                stream.push(
                    AssistantDoneEvent(
                        reason="toolUse" if raw_tool_calls else "stop",
                        message=message,
                    )
                )
            except Exception as exc:  # pragma: no cover - exercised via integration fallback
                error_message = AssistantMessage(
                    content=[TextContent(text="")],
                    api=model.api,
                    provider=model.provider,
                    model=model.id,
                    usage=Usage(cost=UsageCost()),
                    stop_reason="error",
                    error_message=str(exc),
                )
                stream.push(
                    AssistantErrorEvent(
                        reason="error",
                        error=error_message,
                    )
                )

        import asyncio

        asyncio.create_task(_run())
        return stream

    agent = Agent(
        AgentOptions(
            stream_fn=_stream_fn,
            initial_state={
                "system_prompt": system_prompt,
                "model": model,
                "thinking_level": "off",
                "tools": tools,
                "messages": list(conversation_history or []),
            },
        )
    )

    turn_messages: List[Dict[str, Any]] = []
    tool_calls_made: List[Dict[str, Any]] = []

    def _on_event(event: Any) -> None:
        event_type = getattr(event, "type", "")
        if event_type == "tool_execution_end":
            details = getattr(event.result, "details", {})
            arguments: Any = None
            if isinstance(details, dict):
                arguments = details.get("arguments")
            tool_calls_made.append(
                {
                    "tool": event.tool_name,
                    "arguments": arguments,
                    "result": _message_text(
                        {
                            "role": "tool",
                            "content": event.result.content,
                        }
                    ),
                }
            )
        if event_type != "message_end":
            return

        message = event.message
        role = getattr(message, "role", message.get("role") if isinstance(message, dict) else "")
        if role == "user":
            turn_messages.append({"role": "user", "content": _message_text(message)})
        elif role == "assistant":
            assistant_payload: Dict[str, Any] = {"role": "assistant", "content": _message_text(message)}
            tool_calls: List[Dict[str, Any]] = []
            for part in getattr(message, "content", []):
                if getattr(part, "type", None) != "toolCall":
                    continue
                tool_calls.append(
                    {
                        "id": getattr(part, "id", ""),
                        "type": "function",
                        "function": {
                            "name": getattr(part, "name", ""),
                            "arguments": json.dumps(getattr(part, "arguments", {})),
                        },
                    }
                )
            if tool_calls:
                assistant_payload["tool_calls"] = tool_calls
            turn_messages.append(assistant_payload)
        elif role == "toolResult":
            turn_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": getattr(message, "tool_call_id", None),
                    "content": _message_text(message),
                }
            )

    unsubscribe = agent.subscribe(_on_event)
    try:
        await agent.prompt(UserMessage(content=user_message))
    finally:
        unsubscribe()

    if agent.state.error:
        raise RuntimeError(agent.state.error)

    final_response = ""
    for message in reversed(turn_messages):
        if message.get("role") == "assistant" and not message.get("tool_calls"):
            final_response = str(message.get("content", ""))
            break
    if not final_response and turn_messages and turn_messages[-1].get("role") == "assistant":
        final_response = str(turn_messages[-1].get("content", ""))

    return {
        "response": final_response,
        "tool_calls_made": tool_calls_made,
        "yaml": None,
        "conversation_messages": turn_messages,
    }


async def handle_arrow_chat_with_tools(
    system_prompt: str,
    user_message: str,
    conversation_history: List[Any],
    tool_executor: Any,  # ToolExecutor
    call_llm_func: Any,  # LLM calling function
    workflow_context: Dict[str, Any],
    max_tool_rounds: int = 5
) -> Dict[str, Any]:
    """Handle Flux chat with tool calling support.

    This orchestrates the conversation, allowing the LLM to:
    1. Use tools (start_task, get_task_status, create_agent, etc.)

    Args:
        system_prompt: System prompt for the LLM
        user_message: User's message
        conversation_history: Previous messages
        tool_executor: ToolExecutor instance
        call_llm_func: Function to call LLM
        workflow_context: Context for tool execution (injected services)
        max_tool_rounds: Maximum number of tool calling rounds

    Returns:
        Dict with:
        - 'response': Final LLM response
        - 'tool_calls_made': List of tool calls that were executed
        - 'yaml': Extracted YAML (if any)
        - 'conversation_messages': All messages including tool calls (for saving)
    """
    try:
        return await _run_with_aios_agent(
            system_prompt=system_prompt,
            user_message=user_message,
            conversation_history=conversation_history,
            tool_executor=tool_executor,
            call_llm_func=call_llm_func,
            workflow_context=workflow_context,
        )
    except Exception as e:
        logger.warning(
            "Falling back to legacy Flux chat loop",
            error=str(e),
        )

    # Get tool definitions
    tool_definitions = tool_executor.get_tool_definitions()

    # Track all messages for this turn (for conversation storage)
    turn_messages = []

    # Working conversation (includes tool messages)
    working_history = list(conversation_history) if conversation_history else []

    # Track tool calls made
    tool_calls_made = []

    # Initial LLM call with tools enabled
    logger.info("Calling LLM with tools enabled", tool_count=len(tool_definitions))

    llm_result = await call_llm_func(
        system_prompt=system_prompt,
        user_message=user_message,
        conversation_history=working_history,
        tools=tool_definitions if tool_definitions else None
    )

    # Add user message to turn
    turn_messages.append({"role": "user", "content": user_message})

    # Tool calling loop
    rounds = 0
    while llm_result.get("tool_calls") and rounds < max_tool_rounds:
        rounds += 1
        logger.info("LLM requested tool calls", round=rounds, tool_call_count=len(llm_result["tool_calls"]))

        # Add assistant message with tool calls to turn
        assistant_msg_with_tools = {
            "role": "assistant",
            "content": llm_result.get("message", ""),
            "tool_calls": llm_result["tool_calls"]
        }
        turn_messages.append(assistant_msg_with_tools)

        # Also add to working history for next LLM call
        working_history.append(assistant_msg_with_tools)

        # Execute tool calls
        tool_results = await tool_executor.execute_tool_calls(
            llm_result["tool_calls"],
            workflow_context
        )

        # Track tool calls
        for tc, tr in zip(llm_result["tool_calls"], tool_results):
            tool_calls_made.append({
                "tool": tc.get("function", {}).get("name"),
                "arguments": tc.get("function", {}).get("arguments"),
                "result": tr.get("content")
            })

        # Add tool results to turn and working history
        turn_messages.extend(tool_results)
        working_history.extend(tool_results)

        # Call LLM again with tool results
        logger.info("Calling LLM with tool results", round=rounds)
        llm_result = await call_llm_func(
            system_prompt=system_prompt,
            user_message=None,  # No new user message, continuing from tool results
            conversation_history=working_history,
            tools=tool_definitions if tool_definitions else None
        )

    # Final response (no more tool calls, or max rounds reached)
    final_response = llm_result.get("message", "")

    # Add final assistant response to turn
    turn_messages.append({"role": "assistant", "content": final_response})

    logger.info(
        "Chat turn completed",
        tool_rounds=rounds,
        tool_calls_count=len(tool_calls_made),
        response_length=len(final_response)
    )

    return {
        "response": final_response,
        "tool_calls_made": tool_calls_made,
        "yaml": None,  # YAML extraction can be done by caller if needed
        "conversation_messages": turn_messages
    }


# Preferred active-layer alias.
handle_flux_chat_with_tools = handle_arrow_chat_with_tools
