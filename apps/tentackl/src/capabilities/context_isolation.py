"""
Context Isolation Capability Implementation

Provides context isolation for agents, especially for sub-agent creation.
Extracted from StatefulAgent context management code.
"""

from typing import Any, Dict, Optional
from datetime import datetime
import structlog

from src.capabilities.protocols import ContextIsolationCapability, IsolatedContext
from src.interfaces.context_manager import (
    ContextManagerInterface,
    ContextIsolationLevel,
    ContextForkOptions,
    AgentContext,
)

logger = structlog.get_logger(__name__)


class ContextIsolationImpl:
    """
    Implementation of context isolation capability.

    Wraps ContextManagerInterface to provide isolated execution contexts
    for agents and their sub-agents.
    """

    def __init__(self, context_manager: ContextManagerInterface):
        """
        Initialize context isolation.

        Args:
            context_manager: The underlying context manager (e.g., RedisContextManager)
        """
        self._manager = context_manager

    def _parse_isolation_level(self, level: str) -> ContextIsolationLevel:
        """Convert string isolation level to enum."""
        try:
            return ContextIsolationLevel[level.upper()]
        except KeyError:
            logger.warning(f"Unknown isolation level: {level}, defaulting to DEEP")
            return ContextIsolationLevel.DEEP

    async def create_context(
        self,
        agent_id: str,
        isolation_level: str = "DEEP",
        variables: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a new isolated context."""
        try:
            level = self._parse_isolation_level(isolation_level)

            context_id = await self._manager.create_context(
                agent_id=agent_id,
                isolation_level=level
            )

            # Set initial variables if provided
            if variables and context_id:
                context = await self._manager.get_context(context_id)
                if context:
                    context.variables.update(variables)
                    await self._manager.update_context(context_id, context)

            logger.debug(
                "Context created",
                context_id=context_id,
                agent_id=agent_id,
                isolation_level=isolation_level
            )

            return context_id

        except Exception as e:
            logger.error("Failed to create context", agent_id=agent_id, error=str(e))
            raise

    async def fork_context(
        self,
        parent_context_id: str,
        child_agent_id: str,
        isolation_level: Optional[str] = None
    ) -> str:
        """Fork a context for a child agent."""
        try:
            fork_options = None
            if isolation_level:
                fork_options = ContextForkOptions(
                    isolation_level=self._parse_isolation_level(isolation_level)
                )

            child_context_id = await self._manager.fork_context(
                parent_context_id=parent_context_id,
                child_agent_id=child_agent_id,
                fork_options=fork_options
            )

            logger.debug(
                "Context forked",
                parent_context_id=parent_context_id,
                child_context_id=child_context_id,
                child_agent_id=child_agent_id
            )

            return child_context_id

        except Exception as e:
            logger.error(
                "Failed to fork context",
                parent_context_id=parent_context_id,
                child_agent_id=child_agent_id,
                error=str(e)
            )
            raise

    async def get_context(self, context_id: str) -> Optional[IsolatedContext]:
        """Get context by ID."""
        try:
            context = await self._manager.get_context(context_id)
            if not context:
                return None

            return IsolatedContext(
                context_id=context_id,
                agent_id=context.agent_id,
                isolation_level=context.isolation_level.name if context.isolation_level else "DEEP",
                parent_context_id=context.parent_context_id,
                variables=dict(context.variables) if context.variables else None,
                created_at=context.created_at
            )

        except Exception as e:
            logger.error("Failed to get context", context_id=context_id, error=str(e))
            return None

    async def validate_operation(self, context_id: str, operation: str) -> bool:
        """Check if an operation is allowed in this context."""
        try:
            return await self._manager.validate_operation(context_id, operation)
        except Exception as e:
            logger.warning(
                "Failed to validate operation",
                context_id=context_id,
                operation=operation,
                error=str(e)
            )
            # Default to allowing the operation if validation fails
            return True

    async def terminate_context(self, context_id: str, cleanup: bool = True) -> bool:
        """Terminate a context."""
        try:
            await self._manager.terminate_context(context_id, cleanup=cleanup)
            logger.debug("Context terminated", context_id=context_id)
            return True

        except Exception as e:
            logger.error("Failed to terminate context", context_id=context_id, error=str(e))
            return False

    async def update_variables(
        self,
        context_id: str,
        variables: Dict[str, Any]
    ) -> bool:
        """Update context variables."""
        try:
            context = await self._manager.get_context(context_id)
            if not context:
                return False

            context.variables.update(variables)
            await self._manager.update_context(context_id, context)
            return True

        except Exception as e:
            logger.error("Failed to update context variables", context_id=context_id, error=str(e))
            return False

    @property
    def manager(self) -> ContextManagerInterface:
        """Access the underlying context manager."""
        return self._manager
