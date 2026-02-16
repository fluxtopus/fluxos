from __future__ import annotations

from dataclasses import dataclass

from flux_agent.types import AgentTool, AgentToolResult, TextContent


@dataclass
class CalculateResult:
    content: list[TextContent]
    details: None


def calculate(expression: str) -> CalculateResult:
    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return CalculateResult(content=[TextContent(text=f"{expression} = {result}")], details=None)
    except Exception as exc:  # pragma: no cover - error path validated via tool flows
        raise RuntimeError(str(exc)) from exc


async def _execute(_tool_call_id: str, args: dict, _signal, _on_update) -> AgentToolResult:
    calculated = calculate(str(args.get("expression", "")))
    return AgentToolResult(content=calculated.content, details=calculated.details)


calculate_tool = AgentTool(
    label="Calculator",
    name="calculate",
    description="Evaluate mathematical expressions",
    parameters={"expression": "string"},
    execute=_execute,
)
