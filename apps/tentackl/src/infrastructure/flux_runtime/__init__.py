"""Infrastructure-owned import surface for Flux runtime helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = [
    "ToolCall",
    "ToolExecutor",
    "ToolRegistry",
    "get_registry",
    "handle_arrow_chat_with_tools",
    "handle_flux_chat_with_tools",
    "build_world_state",
    "build_similar_tasks_context",
    "CapabilityMatch",
    "CapabilityRecommender",
]

if TYPE_CHECKING:
    from src.infrastructure.flux_runtime.capability_recommender import (
        CapabilityMatch,
        CapabilityRecommender,
    )
    from src.infrastructure.flux_runtime.chat_handler import (
        handle_arrow_chat_with_tools,
        handle_flux_chat_with_tools,
    )
    from src.infrastructure.flux_runtime.tool_executor import ToolCall, ToolExecutor
    from src.infrastructure.flux_runtime.tool_registry import ToolRegistry, get_registry
    from src.infrastructure.flux_runtime.world_state import (
        build_similar_tasks_context,
        build_world_state,
    )


def __getattr__(name: str) -> Any:
    if name in {"handle_arrow_chat_with_tools", "handle_flux_chat_with_tools"}:
        from src.infrastructure.flux_runtime.chat_handler import (
            handle_arrow_chat_with_tools,
            handle_flux_chat_with_tools,
        )

        exports = {
            "handle_arrow_chat_with_tools": handle_arrow_chat_with_tools,
            "handle_flux_chat_with_tools": handle_flux_chat_with_tools,
        }
        return exports[name]

    if name in {"ToolCall", "ToolExecutor"}:
        from src.infrastructure.flux_runtime.tool_executor import ToolCall, ToolExecutor

        exports = {"ToolCall": ToolCall, "ToolExecutor": ToolExecutor}
        return exports[name]

    if name in {"ToolRegistry", "get_registry"}:
        from src.infrastructure.flux_runtime.tool_registry import ToolRegistry, get_registry

        exports = {"ToolRegistry": ToolRegistry, "get_registry": get_registry}
        return exports[name]

    if name in {"build_world_state", "build_similar_tasks_context"}:
        from src.infrastructure.flux_runtime.world_state import (
            build_similar_tasks_context,
            build_world_state,
        )

        exports = {
            "build_world_state": build_world_state,
            "build_similar_tasks_context": build_similar_tasks_context,
        }
        return exports[name]

    if name in {"CapabilityMatch", "CapabilityRecommender"}:
        from src.infrastructure.flux_runtime.capability_recommender import (
            CapabilityMatch,
            CapabilityRecommender,
        )

        exports = {
            "CapabilityMatch": CapabilityMatch,
            "CapabilityRecommender": CapabilityRecommender,
        }
        return exports[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
