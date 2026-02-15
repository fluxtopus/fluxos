"""Flux chat handler with tool calling support.

This module contains the main chat orchestration logic that:
- Manages conversations with tool calling
- Handles multi-turn tool execution
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import structlog

logger = structlog.get_logger(__name__)


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
