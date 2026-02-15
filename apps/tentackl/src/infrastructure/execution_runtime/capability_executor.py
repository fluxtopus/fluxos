"""
Capability Executor for Dynamic Agents.

This module provides a high-level interface for dynamic agents to execute
capabilities. It maps capability names (like "file_storage", "document_db")
to groups of plugin handlers and provides validation and usage tracking.

Capabilities are named groups of plugins that can be enabled for an agent:
- file_storage: agent_save, agent_load, agent_list, agent_delete
- document_db: doc_create_collection, doc_insert, doc_find, doc_update
- http_fetch: http_get, http_post
- image_generation: openai_dalle, flux_generate

Usage:
    executor = CapabilityExecutor(org_id="...")
    result = await executor.execute(
        capability="file_storage",
        operation="agent_save",
        inputs={"filename": "test.txt", "content": "..."}
    )
"""

from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
import structlog

from src.plugins.registry import registry, PluginDefinition

logger = structlog.get_logger(__name__)


# Capability to plugin mapping
CAPABILITY_PLUGINS: Dict[str, List[str]] = {
    # Agent storage capability
    "file_storage": [
        "agent_save",
        "agent_load",
        "agent_list",
        "agent_delete",
        "agent_search",
        "agent_get_context",
        "agent_set_context",
        "agent_list_my_files",
    ],
    # Document database capability
    "document_db": [
        "doc_create_collection",
        "doc_insert",
        "doc_find",
        "doc_update",
        "doc_delete",
        "doc_list_collections",
        "doc_get_schema",
        "doc_infer_schema",
    ],
    # HTTP fetch capability
    "http_fetch": [
        "http_get",
        "http_post",
        "http_put",
        "http_delete",
    ],
    # Den file storage capability (direct access)
    "den_files": [
        "den_upload",
        "den_download",
        "den_list",
        "den_delete",
        "den_get_file",
        "den_duplicate",
        "den_move",
        "den_save_json",
        "den_load_json",
    ],
    # Image generation capability
    "image_generation": [
        "openai_dalle",
        "flux_generate",
        "flux_schnell",
    ],
    # Text processing capability
    "text_processing": [
        "clean_yaml_fences",
        "extract_code_block",
    ],
    # Web automation capability
    "web_automation": [
        "playwright_open_page",
        "playwright_click",
        "playwright_type",
        "playwright_screenshot",
    ],
    # Twitter/X capability
    "twitter": [
        "twitter_post",
        "twitter_get_mentions",
    ],
    # Google services capability
    "google_services": [
        "gmail_send",
        "gmail_read",
        "calendar_create_event",
        "calendar_list_events",
        "google_oauth_start",
        "google_oauth_callback",
    ],
}


@dataclass
class CapabilityUsage:
    """Tracks capability usage for an agent execution."""
    capability: str
    operation: str
    timestamp: datetime
    duration_ms: float
    success: bool
    error: Optional[str] = None


@dataclass
class CapabilityExecutorContext:
    """Context for capability execution with org/agent scoping."""
    org_id: str
    agent_id: Optional[str] = None
    workflow_id: Optional[str] = None
    enabled_capabilities: Set[str] = field(default_factory=set)
    usage_history: List[CapabilityUsage] = field(default_factory=list)


class CapabilityExecutor:
    """
    Executes capabilities for dynamic agents.

    The executor validates that the agent has the capability enabled,
    maps the operation to the correct plugin, and tracks usage.

    Usage:
        executor = CapabilityExecutor(org_id="...", agent_id="...")
        executor.enable_capability("file_storage")

        result = await executor.execute(
            capability="file_storage",
            operation="agent_save",
            inputs={"filename": "test.txt", "content": "Hello"}
        )
    """

    def __init__(
        self,
        org_id: str,
        agent_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        enabled_capabilities: Optional[List[str]] = None,
    ):
        """
        Initialize capability executor.

        Args:
            org_id: Organization ID for scoping operations
            agent_id: Agent ID for tracking and scoping
            workflow_id: Workflow ID for context
            enabled_capabilities: List of capability names to enable
        """
        self.context = CapabilityExecutorContext(
            org_id=org_id,
            agent_id=agent_id,
            workflow_id=workflow_id,
            enabled_capabilities=set(enabled_capabilities or []),
        )

        logger.debug(
            "capability_executor_initialized",
            org_id=org_id,
            agent_id=agent_id,
            capabilities=list(self.context.enabled_capabilities),
        )

    def enable_capability(self, capability: str) -> None:
        """Enable a capability for this executor."""
        if capability not in CAPABILITY_PLUGINS:
            raise ValueError(f"Unknown capability: {capability}")
        self.context.enabled_capabilities.add(capability)

    def disable_capability(self, capability: str) -> None:
        """Disable a capability for this executor."""
        self.context.enabled_capabilities.discard(capability)

    def is_capability_enabled(self, capability: str) -> bool:
        """Check if a capability is enabled."""
        return capability in self.context.enabled_capabilities

    def get_available_operations(self, capability: str) -> List[str]:
        """Get the operations available for a capability."""
        return CAPABILITY_PLUGINS.get(capability, [])

    def get_operation_plugin(self, capability: str, operation: str) -> Optional[PluginDefinition]:
        """Get the plugin definition for an operation."""
        if operation not in CAPABILITY_PLUGINS.get(capability, []):
            return None
        return registry.get(operation)

    def validate_operation(self, capability: str, operation: str) -> None:
        """
        Validate that an operation can be executed.

        Raises:
            ValueError: If capability not enabled or operation not found
        """
        if capability not in CAPABILITY_PLUGINS:
            raise ValueError(f"Unknown capability: {capability}")

        if not self.is_capability_enabled(capability):
            raise ValueError(f"Capability not enabled: {capability}")

        available = CAPABILITY_PLUGINS[capability]
        if operation not in available:
            raise ValueError(
                f"Operation '{operation}' not available in capability '{capability}'. "
                f"Available operations: {available}"
            )

        plugin = registry.get(operation)
        if not plugin:
            raise ValueError(f"Plugin not registered: {operation}")

    async def execute(
        self,
        capability: str,
        operation: str,
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute a capability operation.

        Args:
            capability: Capability name (e.g., "file_storage")
            operation: Operation name (e.g., "agent_save")
            inputs: Operation inputs

        Returns:
            Operation outputs

        Raises:
            ValueError: If capability not enabled or operation not found
            Exception: If operation execution fails
        """
        start_time = datetime.utcnow()

        # Validate
        self.validate_operation(capability, operation)

        # Inject org_id and agent_id into inputs
        enriched_inputs = {
            **inputs,
            "org_id": self.context.org_id,
        }

        if self.context.agent_id:
            enriched_inputs["agent_id"] = self.context.agent_id

        if self.context.workflow_id:
            enriched_inputs["workflow_id"] = self.context.workflow_id

        try:
            # Execute via plugin registry
            result = await registry.execute(operation, enriched_inputs)

            # Track usage
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.context.usage_history.append(
                CapabilityUsage(
                    capability=capability,
                    operation=operation,
                    timestamp=start_time,
                    duration_ms=duration_ms,
                    success=True,
                )
            )

            logger.info(
                "capability_executed",
                capability=capability,
                operation=operation,
                duration_ms=duration_ms,
                agent_id=self.context.agent_id,
            )

            return result

        except Exception as e:
            # Track failed usage
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.context.usage_history.append(
                CapabilityUsage(
                    capability=capability,
                    operation=operation,
                    timestamp=start_time,
                    duration_ms=duration_ms,
                    success=False,
                    error=str(e),
                )
            )

            logger.error(
                "capability_execution_failed",
                capability=capability,
                operation=operation,
                error=str(e),
                agent_id=self.context.agent_id,
            )
            raise

    def get_usage_summary(self) -> Dict[str, Any]:
        """Get a summary of capability usage."""
        total_calls = len(self.context.usage_history)
        successful = sum(1 for u in self.context.usage_history if u.success)
        failed = total_calls - successful

        by_capability = {}
        for usage in self.context.usage_history:
            if usage.capability not in by_capability:
                by_capability[usage.capability] = {"calls": 0, "errors": 0, "total_ms": 0}
            by_capability[usage.capability]["calls"] += 1
            by_capability[usage.capability]["total_ms"] += usage.duration_ms
            if not usage.success:
                by_capability[usage.capability]["errors"] += 1

        return {
            "total_calls": total_calls,
            "successful": successful,
            "failed": failed,
            "by_capability": by_capability,
        }

    @classmethod
    def from_agent_spec(
        cls,
        agent_spec: Any,  # AgentSpec model
        org_id: str,
        workflow_id: Optional[str] = None,
    ) -> "CapabilityExecutor":
        """
        Create a CapabilityExecutor from an AgentSpec.

        Args:
            agent_spec: AgentSpec database model
            org_id: Organization ID
            workflow_id: Workflow ID

        Returns:
            Configured CapabilityExecutor
        """
        spec_compiled = agent_spec.spec_compiled or {}
        agent_config = spec_compiled.get("agent", {})
        capabilities = agent_config.get("capabilities", [])

        return cls(
            org_id=org_id,
            agent_id=agent_spec.name,
            workflow_id=workflow_id,
            enabled_capabilities=capabilities,
        )


# Convenience functions for listing available capabilities

def list_capabilities() -> List[str]:
    """List all available capability names."""
    return list(CAPABILITY_PLUGINS.keys())


def get_capability_operations(capability: str) -> List[str]:
    """Get operations available for a capability."""
    return CAPABILITY_PLUGINS.get(capability, [])


def get_all_capability_info() -> Dict[str, Any]:
    """Get detailed info about all capabilities."""
    result = {}
    for capability, operations in CAPABILITY_PLUGINS.items():
        result[capability] = {
            "operations": operations,
            "registered_count": sum(1 for op in operations if registry.get(op)),
        }
    return result
