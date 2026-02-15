"""Compatibility wrapper for plugin executor.

This module preserves legacy patch points used by tests and older call sites
while delegating implementation to the infrastructure-owned runtime module.
"""

from __future__ import annotations

from typing import Optional

from src.infrastructure.execution_runtime import plugin_executor as _impl

ExecutionResult = _impl.ExecutionResult
PLUGIN_REGISTRY = _impl.PLUGIN_REGISTRY
available_types = _impl.available_types
is_plugin_type = _impl.is_plugin_type
_ORIGINAL_TRACK = _impl.track_capability_usage


async def track_capability_usage(
    agent_type: str,
    success: bool,
    organization_id: Optional[str] = None,
) -> None:
    """Compatibility export for usage tracking."""
    await _ORIGINAL_TRACK(
        agent_type=agent_type,
        success=success,
        organization_id=organization_id,
    )


async def execute_step(
    step,
    llm_client=None,
    model: str = "x-ai/grok-4.1-fast",
    organization_id: Optional[str] = None,
    context=None,
):
    """Execute a step while preserving patchable tracking hook semantics."""
    original_track = _impl.track_capability_usage
    _impl.track_capability_usage = track_capability_usage
    try:
        return await _impl.execute_step(
            step=step,
            llm_client=llm_client,
            model=model,
            organization_id=organization_id,
            context=context,
        )
    finally:
        _impl.track_capability_usage = original_track
