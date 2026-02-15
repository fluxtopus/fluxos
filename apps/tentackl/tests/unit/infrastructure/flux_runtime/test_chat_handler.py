from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from src.infrastructure.flux_runtime.chat_handler import (
    _run_with_aios_agent,
    handle_flux_chat_with_tools,
)


class _FakeToolExecutor:
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "mock_tool",
                    "description": "Mock tool",
                    "parameters": {
                        "type": "object",
                        "properties": {"value": {"type": "number"}},
                    },
                },
            }
        ]

    async def execute_tool_call(self, tool_call: Dict[str, Any], _context: Dict[str, Any]) -> Dict[str, Any]:
        args = json.loads(tool_call["function"]["arguments"])
        return {
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": json.dumps({"success": True, "echo": args.get("value")}),
        }

    async def execute_tool_calls(
        self, tool_calls: List[Dict[str, Any]], context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        return [await self.execute_tool_call(tool_call, context) for tool_call in tool_calls]


@pytest.mark.asyncio
async def test_run_with_aios_agent_executes_tool_round_trip() -> None:
    pytest.importorskip("aios_agent")

    tool_executor = _FakeToolExecutor()

    async def call_llm_func(
        *,
        system_prompt: str,
        user_message: str | None = None,
        conversation_history: List[Any] | None = None,
        tools: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        assert system_prompt
        assert tools is not None
        history = conversation_history or []
        has_tool_result = any(
            isinstance(item, dict)
            and item.get("role") == "tool"
            and item.get("tool_call_id") == "call_1"
            for item in history
        )
        if not has_tool_result:
            return {
                "message": "I will call a tool",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "mock_tool",
                            "arguments": json.dumps({"value": 7}),
                        },
                    }
                ],
                "finish_reason": "tool_calls",
            }
        return {
            "message": "Tool finished. Result received.",
            "tool_calls": [],
            "finish_reason": "stop",
        }

    result = await _run_with_aios_agent(
        system_prompt="You are helpful.",
        user_message="Run a tool.",
        conversation_history=[],
        tool_executor=tool_executor,
        call_llm_func=call_llm_func,
        workflow_context={"user_id": "u1"},
    )

    assert result["response"] == "Tool finished. Result received."
    assert len(result["tool_calls_made"]) == 1
    assert result["tool_calls_made"][0]["tool"] == "mock_tool"
    assert result["conversation_messages"][0]["role"] == "user"
    assert result["conversation_messages"][-1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_handle_flux_chat_with_tools_falls_back_to_legacy_loop(monkeypatch) -> None:
    tool_executor = _FakeToolExecutor()

    async def failing_aios(**_kwargs):
        raise RuntimeError("aios-agent unavailable")

    monkeypatch.setattr(
        "src.infrastructure.flux_runtime.chat_handler._run_with_aios_agent",
        failing_aios,
    )

    async def call_llm_func(
        *,
        system_prompt: str,
        user_message: str | None = None,
        conversation_history: List[Any] | None = None,
        tools: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        assert system_prompt
        assert tools is not None
        history = conversation_history or []
        has_tool_result = any(
            isinstance(item, dict)
            and item.get("role") == "tool"
            and item.get("tool_call_id") == "call_legacy"
            for item in history
        )
        if not has_tool_result:
            return {
                "message": "Calling legacy tool",
                "tool_calls": [
                    {
                        "id": "call_legacy",
                        "type": "function",
                        "function": {
                            "name": "mock_tool",
                            "arguments": json.dumps({"value": 9}),
                        },
                    }
                ],
                "finish_reason": "tool_calls",
            }
        return {"message": "Legacy final response", "tool_calls": [], "finish_reason": "stop"}

    result = await handle_flux_chat_with_tools(
        system_prompt="System",
        user_message="Hello",
        conversation_history=[],
        tool_executor=tool_executor,
        call_llm_func=call_llm_func,
        workflow_context={"user_id": "u2"},
    )

    assert result["response"] == "Legacy final response"
    assert len(result["tool_calls_made"]) == 1
    assert result["tool_calls_made"][0]["tool"] == "mock_tool"
    assert result["conversation_messages"][-1]["content"] == "Legacy final response"
