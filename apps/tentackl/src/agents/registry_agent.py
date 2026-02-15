"""Registry Agent - Loads and executes agents from the unified capabilities system.

This agent uses the UnifiedCapabilityRegistry instead of the deprecated
AgentRegistryManager to load agent configurations.
"""

# REVIEW:
# - Builds ConfigurableAgent and OpenRouter client on initialize; no caching and heavy per-agent overhead.
# - Maps capability config into ConfigurableAgentConfig manually; risk of mismatch with schema changes.

from __future__ import annotations
from typing import Any, Dict, Optional
import structlog

from src.agents.base import Agent, AgentConfig
from src.agents.configurable_agent import ConfigurableAgent
from src.interfaces.configurable_agent import AgentConfig as ConfigurableAgentConfig

logger = structlog.get_logger(__name__)


class RegistryAgent(Agent):
    """Agent that loads its configuration from the unified capabilities registry.

    This agent:
    1. Looks up an agent capability from the registry by agent_type
    2. Uses the capability's configuration to execute using ConfigurableAgent
    3. Supports both system and user-defined capabilities

    Workflow usage:
        agent:
          agent_type: registry
          config:
            agent_name: "sentiment_analyzer"
    """

    def __init__(self, config: AgentConfig):
        """Initialize registry agent.

        Args:
            config: Agent configuration. Must include metadata with:
                - agent_name: Name (agent_type) of the registered capability
        """
        super().__init__(config)
        self.agent_name: Optional[str] = None
        self.loaded_agent: Optional[ConfigurableAgent] = None
        self._registry = None

    async def initialize(
        self,
        context_id: Optional[str] = None,
        tree_id: Optional[str] = None,
        execution_node_id: Optional[str] = None,
    ) -> None:
        """Initialize the agent by loading from unified capabilities registry.

        Args:
            context_id: Context identifier
            tree_id: Execution tree identifier
            execution_node_id: Node ID in execution tree
        """
        # Extract agent_name from config metadata
        self.agent_name = self.config.metadata.get("agent_name")

        if not self.agent_name:
            raise ValueError("RegistryAgent requires 'agent_name' in config.metadata")

        logger.info(
            "Loading agent from capabilities registry",
            agent_id=self.id,
            agent_name=self.agent_name
        )

        # Import here to avoid circular dependencies
        from src.capabilities.unified_registry import UnifiedCapabilityRegistry
        from src.interfaces.database import Database

        # Get database connection
        db = Database()
        await db.connect()

        # Initialize unified capabilities registry
        self._registry = UnifiedCapabilityRegistry(db=db)
        await self._registry.initialize()

        # Load agent capability from registry
        try:
            capability = await self._registry.resolve(
                self.agent_name,
                capability_type="agent"
            )

            if not capability:
                raise ValueError(
                    f"Agent '{self.agent_name}' not found in capabilities registry"
                )

            if not capability.config.is_active:
                raise ValueError(
                    f"Agent '{self.agent_name}' is not active"
                )

            agent_config = capability.config

            logger.info(
                "Loaded agent capability from registry",
                agent_id=self.id,
                agent_name=self.agent_name,
                capability_id=str(agent_config.id)
            )

            # Transform the capability config to ConfigurableAgentConfig format
            # Import needed classes
            from typing import List
            from src.interfaces.configurable_agent import (
                AgentConfig as ConfigAgentConfig,
                ExecutionStrategy,
                StateSchema,
                ResourceConstraints,
            )

            # Extract configuration from capability
            inputs_schema = agent_config.inputs_schema or {}
            outputs_schema = agent_config.outputs_schema or {}
            execution_hints = agent_config.execution_hints or {}

            # Extract model settings from execution_hints or use defaults
            model = execution_hints.get("model", "x-ai/grok-4.1-fast")
            temperature = execution_hints.get("temperature", 0.7)
            max_tokens = execution_hints.get("max_tokens", 2000)
            response_format = execution_hints.get("response_format", None)

            # Build required inputs list (fields marked as required in inputs_schema)
            required = [
                name for name, defn in inputs_schema.items()
                if isinstance(defn, dict) and defn.get("required", False)
            ]

            # Build outputs list
            output_names = list(outputs_schema.keys())

            # Create ConfigurableAgentConfig
            configurable_spec = ConfigAgentConfig(
                name=agent_config.name,
                type=agent_config.task_type or "general",
                version=str(agent_config.version),
                description=agent_config.description or "",
                capabilities=[],
                prompt_template=agent_config.system_prompt,
                execution_strategy=ExecutionStrategy.SEQUENTIAL,
                state_schema=StateSchema(
                    required=required,
                    output=output_names,
                    checkpoint=None,
                    validation_rules=None
                ),
                resources=ResourceConstraints(
                    model=model,
                    max_tokens=max_tokens,
                    timeout=300,
                    max_retries=3,
                    temperature=temperature,
                    response_format=response_format
                ),
                success_metrics=[],
                metadata={"capability_id": str(agent_config.id)}
            )

            # Create PromptExecutor with LLM client for the ConfigurableAgent
            from src.infrastructure.execution_runtime.prompt_executor import PromptExecutor
            from src.llm.openrouter_client import OpenRouterClient
            from src.infrastructure.flux_runtime.tool_executor import ToolExecutor
            from src.infrastructure.flux_runtime.tool_registry import get_registry

            # Create LLM client and initialize it
            llm_client = OpenRouterClient()
            self._llm_client_context = llm_client
            await self._llm_client_context.__aenter__()

            # Create tool executor for agents that need tools
            tool_executor = ToolExecutor(registry=get_registry())

            # Create prompt executor
            prompt_executor = PromptExecutor(
                llm_client=llm_client,
                default_model=model,
                default_temperature=temperature
            )

            # Store tool executor for use in agent execution
            self._tool_executor = tool_executor

            # Create a ConfigurableAgent with this spec, prompt executor, and tool executor
            self.loaded_agent = ConfigurableAgent(
                agent_id=None,  # Let it generate one
                config=configurable_spec,
                prompt_executor=prompt_executor,
                tool_executor=tool_executor
            )
            await self.loaded_agent.initialize()

        except Exception as e:
            logger.error(
                "Failed to load agent from capabilities registry",
                agent_id=self.id,
                agent_name=self.agent_name,
                error=str(e)
            )
            raise

    async def execute(self, task: Dict[str, Any]) -> Any:
        """Execute the loaded agent.

        Args:
            task: Task payload to execute

        Returns:
            Result from the loaded agent
        """
        if not self.loaded_agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        logger.info(
            "Executing registry agent",
            agent_id=self.id,
            agent_name=self.agent_name
        )

        # Execute the loaded configurable agent using execute method
        # ConfigurableAgent.execute returns AgentResult
        result = await self.loaded_agent.execute(task)

        # Log AgentResult structure for debugging
        from src.interfaces.agent import AgentResult
        if isinstance(result, AgentResult):
            logger.info(
                "Registry agent execution completed - AgentResult",
                agent_id=self.id,
                agent_name=self.agent_name,
                result_agent_id=result.agent_id,
                result_state=result.state.value if hasattr(result.state, 'value') else str(result.state),
                result_type=type(result.result).__name__,
                result_is_dict=isinstance(result.result, dict),
                result_keys=list(result.result.keys())[:10] if isinstance(result.result, dict) else None,
                result_size=len(result.result) if isinstance(result.result, dict) else None,
                result_empty=not result.result or (isinstance(result.result, dict) and len(result.result) == 0),
                metadata_keys=list(result.metadata.keys())[:10] if result.metadata else None,
                error=result.error
            )
            # Log full result value if it's empty or small
            if not result.result or (isinstance(result.result, dict) and len(result.result) == 0):
                logger.warning(
                    "Registry agent returned empty result",
                    agent_id=self.id,
                    agent_name=self.agent_name,
                    result_value=str(result.result)[:500],
                    result_type=type(result.result).__name__
                )
        else:
            logger.info(
                "Registry agent execution completed - non-AgentResult",
                agent_id=self.id,
                agent_name=self.agent_name,
                result_type=type(result).__name__
            )

        return result

    async def start(self, task: Dict[str, Any]) -> Any:
        """Start agent execution (delegates to execute via base class).

        Args:
            task: Task payload to execute

        Returns:
            Result from the loaded agent
        """
        # Base class start() will call execute()
        return await super().start(task)

    async def stop(self) -> None:
        """Stop the agent."""
        if self.loaded_agent:
            await self.loaded_agent.stop()

        # Clean up LLM client context if it was initialized
        if hasattr(self, '_llm_client_context') and self._llm_client_context:
            try:
                await self._llm_client_context.__aexit__(None, None, None)
            except Exception as e:
                logger.warning("Error closing LLM client context", error=str(e))

        # Clean up registry if it was initialized
        if self._registry:
            try:
                await self._registry.cleanup()
            except Exception as e:
                logger.warning("Error cleaning up registry", error=str(e))

        await super().stop()
