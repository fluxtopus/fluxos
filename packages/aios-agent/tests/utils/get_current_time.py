from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aios_agent.types import AgentTool, AgentToolResult, TextContent


async def get_current_time(timezone: str | None = None) -> AgentToolResult:
    now = datetime.utcnow()
    if timezone:
        try:
            local = datetime.now(ZoneInfo(timezone))
            time_str = local.strftime("%A, %B %d, %Y at %I:%M:%S %p %Z")
            return AgentToolResult(content=[TextContent(text=time_str)], details={"utcTimestamp": int(now.timestamp() * 1000)})
        except Exception as exc:
            raise RuntimeError(f"Invalid timezone: {timezone}. Current UTC time: {now.isoformat()}Z") from exc

    time_str = now.strftime("%A, %B %d, %Y at %I:%M:%S %p UTC")
    return AgentToolResult(content=[TextContent(text=time_str)], details={"utcTimestamp": int(now.timestamp() * 1000)})


async def _execute(_tool_call_id: str, args: dict, _signal, _on_update) -> AgentToolResult:
    return await get_current_time(args.get("timezone"))


get_current_time_tool = AgentTool(
    label="Current Time",
    name="get_current_time",
    description="Get the current date and time",
    parameters={"timezone": "optional-string"},
    execute=_execute,
)
