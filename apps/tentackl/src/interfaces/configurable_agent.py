"""
Configurable Agent Interface

This module defines the abstract interface for agents that can be configured
and instantiated at runtime from declarative specifications.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Type
from dataclasses import dataclass
from enum import Enum

from .agent import AgentInterface, AgentCapability
from .budget_controller import BudgetControllerInterface
from .state_store import StateStoreInterface
from .context_manager import ContextManagerInterface


class ExecutionStrategy(Enum):
    """Agent execution strategies"""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"
    ITERATIVE = "iterative"


@dataclass
class CapabilityConfig:
    """Configuration for a specific capability"""
    tool: str
    config: Dict[str, Any]
    permissions: Optional[Dict[str, Any]] = None
    sandbox: bool = False


@dataclass
class StateSchema:
    """Schema definition for agent state"""
    required: List[str]
    output: List[str]
    checkpoint: Optional[Dict[str, Any]] = None
    validation_rules: Optional[Dict[str, Any]] = None


@dataclass
class ResourceConstraints:
    """Resource constraints for agent execution"""
    model: str
    max_tokens: int
    timeout: int
    max_retries: int = 3
    memory_mb: Optional[int] = None
    cpu_cores: Optional[float] = None
    # Optional LLM controls
    temperature: float = 0.7
    response_format: Optional[Dict[str, Any]] = None


@dataclass
class SuccessMetric:
    """Success metric definition"""
    metric: str
    threshold: float
    operator: str = "gte"  # gte, lte, eq, neq


@dataclass
class AgentConfig:
    """Complete agent configuration"""
    # Identity
    name: str
    type: str
    version: str
    
    # Capabilities
    capabilities: List[CapabilityConfig]
    
    # Behavior
    prompt_template: str
    execution_strategy: ExecutionStrategy
    
    # State Management
    state_schema: StateSchema
    
    # Constraints
    resources: ResourceConstraints
    
    # Success Criteria
    success_metrics: List[SuccessMetric]
    
    # Optional fields with defaults
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    parent_config: Optional[str] = None  # For inheritance
    hooks: Optional[Dict[str, str]] = None  # Event hooks


class ConfigParserInterface(ABC):
    """Interface for parsing and validating configurations"""
    
    @abstractmethod
    async def parse(self, config_data: Dict[str, Any]) -> AgentConfig:
        """
        Parse raw configuration data into AgentConfig
        
        Args:
            config_data: Raw configuration dictionary
            
        Returns:
            Parsed and validated AgentConfig
        """
        pass
    
    @abstractmethod
    async def validate(self, config: AgentConfig) -> Dict[str, Any]:
        """
        Validate an agent configuration
        
        Args:
            config: Agent configuration to validate
            
        Returns:
            Validation result with any errors/warnings
        """
        pass
    
    @abstractmethod
    async def merge_configs(
        self,
        base: AgentConfig,
        override: Dict[str, Any]
    ) -> AgentConfig:
        """
        Merge configurations with inheritance
        
        Args:
            base: Base configuration
            override: Override values
            
        Returns:
            Merged configuration
        """
        pass


class CapabilityBinderInterface(ABC):
    """Interface for binding capabilities to agents"""
    
    @abstractmethod
    async def bind_capability(
        self,
        agent: AgentInterface,
        capability: CapabilityConfig
    ) -> None:
        """
        Bind a capability to an agent
        
        Args:
            agent: Agent to bind to
            capability: Capability configuration
        """
        pass
    
    @abstractmethod
    async def validate_capability(
        self,
        capability: CapabilityConfig
    ) -> bool:
        """
        Validate that a capability can be bound
        
        Args:
            capability: Capability to validate
            
        Returns:
            True if capability is valid and available
        """
        pass
    
    @abstractmethod
    async def get_available_tools(self) -> List[str]:
        """
        Get list of available tools
        
        Returns:
            List of tool names
        """
        pass


class PromptExecutorInterface(ABC):
    """Interface for executing prompts through LLM"""
    
    @abstractmethod
    async def execute_prompt(
        self,
        prompt_template: str,
        context: Dict[str, Any],
        model: str,
        max_tokens: int,
        temperature: float = 0.7
    ) -> str:
        """
        Execute a prompt with the LLM
        
        Args:
            prompt_template: Template with placeholders
            context: Values to fill template
            model: Model to use
            max_tokens: Maximum tokens
            temperature: Sampling temperature
            
        Returns:
            LLM response
        """
        pass
    
    @abstractmethod
    async def stream_prompt(
        self,
        prompt_template: str,
        context: Dict[str, Any],
        model: str,
        max_tokens: int,
        temperature: float = 0.7
    ):
        """
        Stream prompt execution
        
        Yields:
            Response chunks
        """
        pass


class ConfigurableAgentInterface(AgentInterface):
    """Interface for configurable agents"""
    
    @abstractmethod
    async def load_config(self, config: AgentConfig) -> None:
        """
        Load configuration into the agent
        
        Args:
            config: Agent configuration
        """
        pass
    
    @abstractmethod
    async def reload_config(self, config: AgentConfig) -> None:
        """
        Reload configuration (hot reload)
        
        Args:
            config: New agent configuration
        """
        pass
    
    @abstractmethod
    async def get_config(self) -> AgentConfig:
        """
        Get current configuration
        
        Returns:
            Current agent configuration
        """
        pass
    
    @abstractmethod
    async def validate_state(
        self,
        state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate state against schema
        
        Args:
            state: State to validate
            
        Returns:
            Validation result
        """
        pass
    
    @abstractmethod
    async def check_success_metrics(
        self,
        execution_result: Any
    ) -> Dict[str, bool]:
        """
        Check if success metrics are met
        
        Args:
            execution_result: Result from execution
            
        Returns:
            Metric results
        """
        pass
    
    @abstractmethod
    async def execute_with_strategy(
        self,
        task: Any,
        context: Dict[str, Any]
    ) -> Any:
        """
        Execute task with configured strategy
        
        Args:
            task: Task to execute
            context: Execution context
            
        Returns:
            Execution result
        """
        pass


class ConfigurableAgentFactoryInterface(ABC):
    """Interface for creating configurable agents"""
    
    @abstractmethod
    async def create_agent(
        self,
        config: AgentConfig,
        budget_controller: Optional[BudgetControllerInterface] = None,
        state_store: Optional[StateStoreInterface] = None,
        context_manager: Optional[ContextManagerInterface] = None
    ) -> ConfigurableAgentInterface:
        """
        Create a configurable agent from config
        
        Args:
            config: Agent configuration
            budget_controller: Optional budget controller
            state_store: Optional state store
            context_manager: Optional context manager
            
        Returns:
            Configured agent instance
        """
        pass
    
    @abstractmethod
    async def create_from_template(
        self,
        template_id: str,
        parameters: Dict[str, Any],
        version: Optional[str] = None
    ) -> ConfigurableAgentInterface:
        """
        Create agent from template
        
        Args:
            template_id: Template identifier
            parameters: Template parameters
            version: Template version (latest if None)
            
        Returns:
            Configured agent instance
        """
        pass
    
    @abstractmethod
    def register_parser(
        self,
        parser: ConfigParserInterface
    ) -> None:
        """
        Register a config parser
        
        Args:
            parser: Parser to register
        """
        pass
    
    @abstractmethod
    def register_capability_binder(
        self,
        binder: CapabilityBinderInterface
    ) -> None:
        """
        Register a capability binder
        
        Args:
            binder: Binder to register
        """
        pass
    
    @abstractmethod
    def register_prompt_executor(
        self,
        executor: PromptExecutorInterface
    ) -> None:
        """
        Register a prompt executor
        
        Args:
            executor: Executor to register
        """
        pass
