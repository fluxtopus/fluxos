"""
Plugin Executor - Unified step execution via plugins and DB-configured agents.

This module replaces the legacy task_subagent.py architecture with a simpler
plugin-based approach. Infrastructure operations (http_fetch, notify, etc.)
are handled by deterministic plugins, while LLM-based agents (summarize,
compose, analyze) are loaded from the database via UnifiedCapabilityRegistry.

Usage:
    from src.infrastructure.execution_runtime.plugin_executor import execute_step, ExecutionResult

    result = await execute_step(step, llm_client=client, model="grok-4.1-fast")
    if result.success:
        print(result.output)
"""

import importlib
import structlog
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

logger = structlog.get_logger(__name__)


@dataclass
class ExecutionResult:
    """
    Result from step execution.

    This replaces the legacy SubagentResult class with an identical interface
    for backward compatibility.
    """

    status: str  # "success" | "error" | "checkpoint"
    output: Any
    error: Optional[str] = None
    execution_time_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Check if execution was successful."""
        return self.status == "success"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata,
        }


# Maps agent_type → (module_path, handler_name)
# Infrastructure plugins that don't require LLM reasoning
PLUGIN_REGISTRY: Dict[str, Tuple[str, str]] = {
    # HTTP and networking
    "http_fetch": ("src.plugins.http_plugin", "http_request_handler"),

    # Notifications
    "notify": ("src.plugins.notify_plugin", "notify_handler"),

    # Email (deterministic via Mimic)
    "send_email": ("src.plugins.send_email_plugin", "send_email_handler"),

    # Data transformation
    "transform": ("src.plugins.transform_plugin", "transform_handler"),

    # File storage (Den)
    "file_storage": ("src.plugins.den_file_plugin", "upload_file_handler"),

    # Image generation
    "generate_image": ("src.plugins.image_generation_plugin", "generate_image_handler"),

    # PDF generation
    "html_to_pdf": ("src.plugins.playwright_plugin", "html_to_pdf_handler"),
    "pdf_composer": ("src.plugins.pdf_composer_plugin", "pdf_composer_handler"),

    # Markdown document creation
    "markdown_composer": ("src.plugins.markdown_composer_plugin", "markdown_composer_handler"),

    # Document and storage operations
    "document_db": ("src.plugins.document_db_plugin", "insert_document_handler"),
    "agent_storage": ("src.plugins.agent_storage_plugin", "save_handler"),

    # Scheduling
    "schedule_job": ("src.plugins.schedule_job_plugin", "schedule_handler"),

    # Workspace operations (deterministic, no LLM needed)
    "workspace_create": ("src.plugins.workspace_plugin", "workspace_create_handler"),
    "workspace_query": ("src.plugins.workspace_plugin", "workspace_query_handler"),
    "workspace_search": ("src.plugins.workspace_plugin", "workspace_search_handler"),

    # Agent creation (capability generation)
    "create_agent": ("src.plugins.agent_creation_plugin", "create_agent_handler"),

    # Integration management (via Mimic)
    "list_integrations": ("src.plugins.integration_plugin", "list_integrations_handler"),
    "execute_outbound_action": ("src.plugins.integration_plugin", "execute_outbound_action_handler"),

    # Memory operations
    "memory_store": ("src.plugins.memory_plugin", "memory_store_handler"),
    "memory_query": ("src.plugins.memory_plugin", "memory_query_handler"),

    # Cross-task data flow
    "task_output_retrieval": ("src.plugins.task_output_retrieval_plugin", "task_output_retrieval_handler"),

    # Discord integrations
    "discord_followup": ("src.plugins.discord_followup_plugin", "discord_followup_handler"),
    "discord_edit_followup": ("src.plugins.discord_followup_plugin", "discord_edit_followup_handler"),
    "discord_delete_followup": ("src.plugins.discord_followup_plugin", "discord_delete_followup_handler"),

    # CSV generation and workspace CSV I/O
    "csv_composer": ("src.plugins.csv_composer_plugin", "csv_composer_handler"),
    "workspace_export_csv": ("src.plugins.workspace_csv_plugin", "workspace_export_csv_handler"),
    "workspace_import_csv": ("src.plugins.workspace_csv_plugin", "workspace_import_csv_handler"),
}


def _wrap_plugin_result(result: Dict[str, Any], start_time: datetime) -> ExecutionResult:
    """Wrap a plugin handler result in ExecutionResult format."""
    execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)

    if "error" in result and result["error"]:
        return ExecutionResult(
            status="error",
            output=None,
            error=result["error"],
            execution_time_ms=execution_time,
            metadata=result.get("metadata", {}),
        )

    return ExecutionResult(
        status="success",
        output=result,
        error=None,
        execution_time_ms=execution_time,
        metadata=result.get("metadata", {}),
    )


async def execute_step(
    step,  # TaskStep - imported dynamically to avoid circular imports
    llm_client=None,  # Optional[OpenRouterClient]
    model: str = "x-ai/grok-4.1-fast",
    organization_id: Optional[str] = None,
    context=None,  # Optional[ExecutionContext]
    file_references: Optional[List[Dict[str, Any]]] = None,
) -> ExecutionResult:
    """
    Execute a step using the appropriate plugin or DB-configured agent.

    Resolution order:
    1. Check PLUGIN_REGISTRY for infrastructure plugins
    2. Fall back to UnifiedCapabilityRegistry for LLM-based agents

    Args:
        step: TaskStep with agent_type, inputs, id, etc.
        llm_client: Optional shared LLM client for efficiency
        model: Model to use for LLM-based agents
        organization_id: Optional organization ID for tracking and org-scoped resolution
        context: ExecutionContext built from the plan (trusted source).
                 Required for plugin handlers; carries org_id, user_id, etc.

    Returns:
        ExecutionResult with status, output, error, execution_time_ms, metadata
    """
    start_time = datetime.utcnow()
    agent_type = step.agent_type

    logger.debug("execute_step_start", agent_type=agent_type, step_id=step.id)

    # Check plugin registry first (infrastructure operations)
    if agent_type in PLUGIN_REGISTRY:
        try:
            module_path, handler_name = PLUGIN_REGISTRY[agent_type]
            module = importlib.import_module(module_path)
            handler = getattr(module, handler_name)

            logger.debug("executing_plugin", agent_type=agent_type, handler=handler_name)
            result = await handler(step.inputs, context)

            return _wrap_plugin_result(result, start_time)

        except ImportError as e:
            logger.error("plugin_import_failed", agent_type=agent_type, error=str(e))
            return ExecutionResult(
                status="error",
                output=None,
                error=f"Plugin import failed: {str(e)}",
                execution_time_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
            )
        except Exception as e:
            logger.error("plugin_execution_failed", agent_type=agent_type, error=str(e))
            return ExecutionResult(
                status="error",
                output=None,
                error=f"Plugin execution failed: {str(e)}",
                execution_time_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
            )

    # Check the central plugin registry (src.plugins.registry) as fallback
    # This consolidates all plugins into one source of truth
    try:
        from src.plugins.registry import registry as central_registry
        plugin_def = central_registry.get(agent_type)
        if plugin_def:
            logger.debug("executing_central_plugin", agent_type=agent_type)
            result = await central_registry.execute(agent_type, step.inputs)
            return _wrap_plugin_result(result, start_time)
    except Exception as e:
        logger.debug("central_plugin_not_found", agent_type=agent_type, error=str(e))

    # Fall back to UnifiedCapabilityRegistry for LLM-based agents
    try:
        from src.capabilities.unified_registry import get_registry

        logger.debug("executing_db_agent", agent_type=agent_type)
        registry = await get_registry()
        agent = await registry.create_agent(agent_type, llm_client=llm_client, model=model)

        # Initialize agent if needed
        if hasattr(agent, "initialize"):
            await agent.initialize()

        # Resolve file references for LLM agents
        # Errors propagate — a 422/403/network failure should fail the step,
        # not silently run the LLM without the files.
        file_context = None
        if file_references and organization_id:
            from src.infrastructure.execution_runtime.file_resolver import (
                resolve_file_references,
                StepFileContext,
            )

            resolved = await resolve_file_references(file_references, organization_id)
            if resolved:
                file_context = StepFileContext(resolved_files=resolved)

        execution_success = False
        try:
            # Execute via validated method if available
            if hasattr(agent, "execute_validated"):
                result = await agent.execute_validated(step, file_context=file_context)
            else:
                result = await agent.execute(step, file_context=file_context)

            # Handle different result types
            if isinstance(result, ExecutionResult):
                execution_success = result.success
                # Track usage after execution
                await track_capability_usage(
                    agent_type=agent_type,
                    success=execution_success,
                    organization_id=organization_id,
                )
                return result
            elif hasattr(result, "success"):
                # llm_subagent.SubagentResult has success: bool
                execution_success = result.success
                exec_result = ExecutionResult(
                    status="success" if result.success else "error",
                    output=result.output,
                    error=result.error,
                    execution_time_ms=getattr(result, "execution_time_ms", 0),
                    metadata=getattr(result, "metadata", {}) or {},
                )
                # Track usage after execution
                await track_capability_usage(
                    agent_type=agent_type,
                    success=execution_success,
                    organization_id=organization_id,
                )
                return exec_result
            elif hasattr(result, "to_dict"):
                # Legacy SubagentResult with to_dict()
                d = result.to_dict()
                execution_success = d.get("status", "success") == "success"
                exec_result = ExecutionResult(
                    status=d.get("status", "success"),
                    output=d.get("output"),
                    error=d.get("error"),
                    execution_time_ms=d.get("execution_time_ms", 0),
                    metadata=d.get("metadata", {}),
                )
                # Track usage after execution
                await track_capability_usage(
                    agent_type=agent_type,
                    success=execution_success,
                    organization_id=organization_id,
                )
                return exec_result
            else:
                # Raw dict result
                execution_success = True
                exec_result = _wrap_plugin_result(result if isinstance(result, dict) else {"output": result}, start_time)
                # Track usage after execution
                await track_capability_usage(
                    agent_type=agent_type,
                    success=execution_success,
                    organization_id=organization_id,
                )
                return exec_result

        except Exception as exec_error:
            # Track as failure for execution errors and return error result
            await track_capability_usage(
                agent_type=agent_type,
                success=False,
                organization_id=organization_id,
            )
            error_str = str(exec_error) or repr(exec_error)
            logger.error("db_agent_execution_failed", agent_type=agent_type, error=error_str)
            return ExecutionResult(
                status="error",
                output=None,
                error=f"Agent execution failed: {error_str}",
                execution_time_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
            )

        finally:
            # Cleanup agent
            if hasattr(agent, "cleanup"):
                await agent.cleanup()

    except ValueError as e:
        # Agent type not found in registry - track as failure
        await track_capability_usage(
            agent_type=agent_type,
            success=False,
            organization_id=organization_id,
        )
        logger.error("agent_type_not_found", agent_type=agent_type, error=str(e))
        return ExecutionResult(
            status="error",
            output=None,
            error=f"Unknown agent type: {agent_type}",
            execution_time_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
        )
    except Exception as e:
        # Outer errors (registry creation, initialization) - track as failure
        await track_capability_usage(
            agent_type=agent_type,
            success=False,
            organization_id=organization_id,
        )
        logger.error("db_agent_setup_failed", agent_type=agent_type, error=str(e))
        return ExecutionResult(
            status="error",
            output=None,
            error=f"Agent setup failed: {str(e)}",
            execution_time_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
        )


def available_types() -> list:
    """
    List all available agent types.

    Returns both plugin-based types and DB-configured types.
    """
    plugin_types = list(PLUGIN_REGISTRY.keys())

    # Try to get DB-configured types
    try:
        import asyncio
        from src.capabilities.unified_registry import get_registry

        async def _get_db_types():
            registry = await get_registry()
            return list(registry._agents.keys())

        try:
            loop = asyncio.get_running_loop()
            # Can't easily get DB types from sync context with running loop
            return plugin_types
        except RuntimeError:
            db_types = asyncio.run(_get_db_types())
            return list(set(plugin_types + db_types))

    except Exception:
        return plugin_types


def is_plugin_type(agent_type: str) -> bool:
    """Check if an agent type is handled by a plugin (vs DB-configured)."""
    return agent_type in PLUGIN_REGISTRY


async def track_capability_usage(
    agent_type: str,
    success: bool,
    organization_id: Optional[str] = None,
) -> None:
    """
    Track capability usage by updating analytics columns in capabilities_agents.

    Updates: usage_count, success_count/failure_count, last_used_at.

    Resolution order when organization_id is provided:
    1. Try to find org-specific capability first
    2. Fall back to system capability if not found

    Args:
        agent_type: The agent type that was executed
        success: Whether the execution was successful
        organization_id: Optional organization ID for org-scoped capabilities
    """
    # Skip plugin registry types - they're code-based, not in DB
    if agent_type in PLUGIN_REGISTRY:
        logger.debug("skipping_usage_tracking_for_plugin", agent_type=agent_type)
        return

    try:
        from sqlalchemy import select
        from src.interfaces.database import Database
        from src.database.capability_models import AgentCapability

        db = Database()
        await db.connect()

        try:
            async with db.get_session() as session:
                capability = None

                # Try org-specific capability first if organization_id provided
                if organization_id:
                    try:
                        org_uuid = UUID(organization_id)
                        query = (
                            select(AgentCapability)
                            .where(
                                AgentCapability.agent_type == agent_type,
                                AgentCapability.organization_id == org_uuid,
                                AgentCapability.is_latest == True,
                                AgentCapability.is_active == True,
                            )
                            .limit(1)
                        )
                        result = await session.execute(query)
                        capability = result.scalar_one_or_none()
                    except (ValueError, TypeError):
                        # Invalid UUID format - skip org lookup
                        pass

                # Fall back to system capability if no org capability found
                if capability is None:
                    query = (
                        select(AgentCapability)
                        .where(
                            AgentCapability.agent_type == agent_type,
                            AgentCapability.is_system == True,
                            AgentCapability.is_latest == True,
                            AgentCapability.is_active == True,
                        )
                        .limit(1)
                    )
                    result = await session.execute(query)
                    capability = result.scalar_one_or_none()

                if capability is None:
                    logger.debug(
                        "capability_not_found_for_tracking",
                        agent_type=agent_type,
                        organization_id=organization_id,
                    )
                    return

                # Update analytics
                capability.usage_count = (capability.usage_count or 0) + 1
                if success:
                    capability.success_count = (capability.success_count or 0) + 1
                else:
                    capability.failure_count = (capability.failure_count or 0) + 1
                capability.last_used_at = datetime.now(timezone.utc)

                await session.commit()

                logger.debug(
                    "capability_usage_tracked",
                    agent_type=agent_type,
                    capability_id=str(capability.id),
                    success=success,
                    usage_count=capability.usage_count,
                )

        finally:
            await db.disconnect()

    except Exception as e:
        # Log but don't fail execution - tracking is non-critical
        logger.warning(
            "capability_usage_tracking_failed",
            agent_type=agent_type,
            error=str(e),
        )
