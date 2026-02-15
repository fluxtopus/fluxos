"""
Agent Runtime

Infrastructure container for agent capabilities.
NOT an agent itself - provides capabilities TO agents.

The AgentRuntime manages the lifecycle of capabilities and provides
a clean interface for agents to access them.
"""

from typing import Optional, Dict, Any
import structlog

from src.capabilities.container import AgentCapabilities

logger = structlog.get_logger(__name__)


class AgentRuntime:
    """
    Infrastructure runtime for agents.

    NOT an agent itself - provides capabilities to agents via composition.
    This replaces the monolithic StatefulAgent inheritance pattern.

    Features:
    - Manages capability lifecycle (initialize/shutdown)
    - Provides clean access to capabilities
    - Handles capability dependencies
    - Thread-safe capability access

    Example:
        # Create runtime with specific capabilities
        runtime = AgentRuntime(
            capabilities=AgentCapabilities(
                conversations=ConversationTrackingImpl(db),
                state=StatePersistenceImpl(redis_store)
            )
        )

        # Initialize all capabilities
        await runtime.initialize()

        # Use with agent
        agent = LLMAgent(config, runtime=runtime)
        result = await agent.execute(task)

        # Shutdown when done
        await runtime.shutdown()
    """

    def __init__(self, capabilities: Optional[AgentCapabilities] = None):
        """
        Initialize the runtime with capabilities.

        Args:
            capabilities: Optional capabilities container. If None, creates empty.
        """
        self.capabilities = capabilities or AgentCapabilities()
        self._initialized = False
        self._shutting_down = False

    async def initialize(self) -> None:
        """
        Initialize all capabilities.

        Should be called before using the runtime with agents.
        Idempotent - safe to call multiple times.
        """
        if self._initialized:
            logger.debug("AgentRuntime already initialized")
            return

        logger.info(
            "Initializing AgentRuntime",
            capabilities=self.capabilities.enabled_capabilities()
        )

        try:
            # Initialize conversation tracking (needs DB connection)
            if self.capabilities.conversations:
                await self.capabilities.conversations.initialize()
                logger.debug("Conversation tracking initialized")

            # Other capabilities typically don't need explicit initialization
            # since they use existing Redis/Postgres connections

            self._initialized = True
            logger.info("AgentRuntime initialized successfully")

        except Exception as e:
            logger.error("Failed to initialize AgentRuntime", error=str(e))
            raise

    async def shutdown(self) -> None:
        """
        Shutdown all capabilities and cleanup resources.

        Should be called when the runtime is no longer needed.
        Idempotent - safe to call multiple times.
        """
        if self._shutting_down:
            logger.debug("AgentRuntime already shutting down")
            return

        self._shutting_down = True

        logger.info("Shutting down AgentRuntime")

        try:
            # Shutdown sub-agents first
            if self.capabilities.subagents:
                await self.capabilities.subagents.shutdown_all()
                logger.debug("Sub-agents shutdown complete")

            # Stop auto-save if running
            if self.capabilities.state:
                await self.capabilities.state.stop_auto_save()
                logger.debug("Auto-save stopped")

            # Shutdown conversation tracking (closes DB connection)
            if self.capabilities.conversations:
                await self.capabilities.conversations.shutdown()
                logger.debug("Conversation tracking shutdown complete")

            self._initialized = False
            logger.info("AgentRuntime shutdown complete")

        except Exception as e:
            logger.error("Error during AgentRuntime shutdown", error=str(e))
            # Don't re-raise - shutdown should be best-effort

        finally:
            self._shutting_down = False

    @property
    def is_initialized(self) -> bool:
        """Check if the runtime is initialized."""
        return self._initialized

    # ========================================================================
    # Capability Access Methods
    # ========================================================================

    @property
    def state(self):
        """Access state persistence capability."""
        return self.capabilities.state

    @property
    def context(self):
        """Access context isolation capability."""
        return self.capabilities.context

    @property
    def tracking(self):
        """Access execution tracking capability."""
        return self.capabilities.tracking

    @property
    def conversations(self):
        """Access conversation tracking capability."""
        return self.capabilities.conversations

    @property
    def subagents(self):
        """Access sub-agent management capability."""
        return self.capabilities.subagents

    # ========================================================================
    # Convenience Methods
    # ========================================================================

    async def save_state(self, agent_id: str, state: Dict[str, Any]) -> bool:
        """
        Save agent state if state persistence is enabled.

        Returns False if capability not available.
        """
        if not self.capabilities.state:
            return False
        return await self.capabilities.state.save_state(agent_id, state)

    async def load_state(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Load agent state if state persistence is enabled.

        Returns None if capability not available or no state found.
        """
        if not self.capabilities.state:
            return None
        return await self.capabilities.state.load_state(agent_id)

    async def start_conversation(
        self,
        workflow_id: str,
        agent_id: str,
        **kwargs
    ) -> Optional[str]:
        """
        Start a conversation if tracking is enabled.

        Returns None if capability not available.
        """
        if not self.capabilities.conversations:
            return None
        return await self.capabilities.conversations.start_conversation(
            workflow_id=workflow_id,
            agent_id=agent_id,
            **kwargs
        )

    async def end_conversation(self, conversation_id: str, status: str) -> bool:
        """
        End a conversation if tracking is enabled.

        Returns False if capability not available.
        """
        if not self.capabilities.conversations:
            return False
        return await self.capabilities.conversations.end_conversation(
            conversation_id, status
        )

    def wrap_llm_client(self, client: Any, agent_id: str, model: str) -> Any:
        """
        Wrap an LLM client for conversation tracking if enabled.

        Returns the original client if capability not available.
        """
        if not self.capabilities.conversations:
            return client
        return self.capabilities.conversations.wrap_llm_client(client, agent_id, model)

    async def create_context(
        self,
        agent_id: str,
        isolation_level: str = "DEEP"
    ) -> Optional[str]:
        """
        Create an isolated context if capability is enabled.

        Returns None if capability not available.
        """
        if not self.capabilities.context:
            return None
        return await self.capabilities.context.create_context(
            agent_id=agent_id,
            isolation_level=isolation_level
        )

    async def add_execution_node(
        self,
        tree_id: str,
        agent_id: str,
        name: str,
        **kwargs
    ) -> Optional[str]:
        """
        Add an execution node if tracking is enabled.

        Returns None if capability not available.
        """
        if not self.capabilities.tracking:
            return None
        return await self.capabilities.tracking.add_node(
            tree_id=tree_id,
            agent_id=agent_id,
            name=name,
            **kwargs
        )

    def __repr__(self) -> str:
        status = "initialized" if self._initialized else "not initialized"
        return f"AgentRuntime({self.capabilities}, {status})"
