"""
Sub-Agent Generator Interface

This module defines the interface for generating and managing sub-agents
dynamically based on specifications and requirements.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.core.execution_tree import ExecutionNode, NodeType, ExecutionStatus, ExecutionPriority
from src.interfaces.context_manager import ContextIsolationLevel


class AgentType(Enum):
    """Types of agents that can be generated"""
    WORKER = "worker"
    DATA_PROCESSOR = "data_processor"
    API_CALLER = "api_caller"
    FILE_HANDLER = "file_handler"
    ANALYZER = "analyzer"
    VALIDATOR = "validator"
    TRANSFORMER = "transformer"
    AGGREGATOR = "aggregator"
    NOTIFIER = "notifier"
    CUSTOM = "custom"


class GenerationStrategy(Enum):
    """Strategies for sub-agent generation"""
    IMMEDIATE = "immediate"        # Generate immediately
    LAZY = "lazy"                 # Generate when needed
    BATCH = "batch"               # Generate in batches
    DYNAMIC = "dynamic"           # Generate based on runtime conditions


@dataclass
class AgentSpecification:
    """Specification for generating a sub-agent"""
    
    name: str
    agent_type: AgentType
    task_description: str
    
    # Configuration
    parameters: Dict[str, Any] = field(default_factory=dict)
    environment: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    
    # Resource constraints
    max_memory_mb: Optional[int] = None
    max_cpu_percent: Optional[int] = None
    timeout_seconds: Optional[int] = None
    
    # Execution preferences
    priority: ExecutionPriority = ExecutionPriority.NORMAL
    isolation_level: ContextIsolationLevel = ContextIsolationLevel.SHALLOW
    retry_count: int = 0
    
    # Metadata
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class GenerationRequest:
    """Request for generating sub-agents"""
    
    parent_agent_id: str
    parent_context_id: str
    tree_id: str
    
    specifications: List[AgentSpecification]
    generation_strategy: GenerationStrategy = GenerationStrategy.IMMEDIATE
    
    # Parallel execution options
    max_parallel: Optional[int] = None
    batch_size: Optional[int] = None
    
    # Global constraints
    global_timeout_seconds: Optional[int] = None
    resource_limits: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    request_id: str = field(default_factory=lambda: f"req_{datetime.utcnow().timestamp()}")
    requested_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class GenerationResult:
    """Result of sub-agent generation"""
    
    request_id: str
    success: bool
    
    # Generated agents
    generated_agents: List[Dict[str, Any]] = field(default_factory=list)
    execution_nodes: List[ExecutionNode] = field(default_factory=list)
    
    # Execution information
    generation_time_seconds: float = 0.0
    total_agents_created: int = 0
    failed_generations: List[Dict[str, Any]] = field(default_factory=list)
    
    # Error information
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Metadata
    completed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SubAgentStatus:
    """Status information for a sub-agent"""
    
    agent_id: str
    name: str
    agent_type: AgentType
    status: ExecutionStatus
    
    # Execution information
    node_id: str
    context_id: str
    parent_agent_id: str
    
    # Progress information
    progress_percent: float = 0.0
    current_step: Optional[str] = None
    steps_completed: int = 0
    total_steps: Optional[int] = None
    
    # Resource usage
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    
    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Results
    result_data: Dict[str, Any] = field(default_factory=dict)
    error_data: Optional[Dict[str, Any]] = None


class SubAgentGeneratorInterface(ABC):
    """
    Abstract interface for sub-agent generation and management
    """
    
    @abstractmethod
    async def generate_sub_agents(self, request: GenerationRequest) -> GenerationResult:
        """
        Generate sub-agents based on specifications
        
        Args:
            request: Generation request with specifications and options
            
        Returns:
            GenerationResult with created agents and execution information
        """
        pass
    
    @abstractmethod
    async def get_sub_agent_status(self, agent_id: str) -> Optional[SubAgentStatus]:
        """
        Get current status of a sub-agent
        
        Args:
            agent_id: Unique identifier of the sub-agent
            
        Returns:
            SubAgentStatus if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def list_sub_agents(self, parent_agent_id: str) -> List[SubAgentStatus]:
        """
        List all sub-agents for a parent agent
        
        Args:
            parent_agent_id: Parent agent identifier
            
        Returns:
            List of sub-agent status information
        """
        pass
    
    @abstractmethod
    async def terminate_sub_agent(self, agent_id: str, reason: Optional[str] = None) -> bool:
        """
        Terminate a running sub-agent
        
        Args:
            agent_id: Sub-agent identifier
            reason: Optional termination reason
            
        Returns:
            True if termination was successful
        """
        pass
    
    @abstractmethod
    async def pause_sub_agent(self, agent_id: str) -> bool:
        """
        Pause a running sub-agent
        
        Args:
            agent_id: Sub-agent identifier
            
        Returns:
            True if pause was successful
        """
        pass
    
    @abstractmethod
    async def resume_sub_agent(self, agent_id: str) -> bool:
        """
        Resume a paused sub-agent
        
        Args:
            agent_id: Sub-agent identifier
            
        Returns:
            True if resume was successful
        """
        pass
    
    @abstractmethod
    async def get_generation_templates(self) -> Dict[AgentType, Dict[str, Any]]:
        """
        Get available agent generation templates
        
        Returns:
            Dictionary mapping agent types to their templates
        """
        pass
    
    @abstractmethod
    async def validate_specification(self, spec: AgentSpecification) -> List[str]:
        """
        Validate an agent specification
        
        Args:
            spec: Agent specification to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        pass
    
    @abstractmethod
    async def estimate_resource_usage(self, specs: List[AgentSpecification]) -> Dict[str, Any]:
        """
        Estimate resource usage for generating specified agents
        
        Args:
            specs: List of agent specifications
            
        Returns:
            Resource usage estimates (memory, CPU, time)
        """
        pass
    
    @abstractmethod
    async def cleanup_completed_agents(self, max_age_hours: int = 24) -> int:
        """
        Clean up completed sub-agents older than specified age
        
        Args:
            max_age_hours: Maximum age in hours for completed agents
            
        Returns:
            Number of agents cleaned up
        """
        pass


class SubAgentGeneratorError(Exception):
    """Base exception for sub-agent generator errors"""
    pass


class InvalidSpecificationError(SubAgentGeneratorError):
    """Raised when agent specification is invalid"""
    pass


class ResourceLimitExceededError(SubAgentGeneratorError):
    """Raised when resource limits are exceeded"""
    pass


class GenerationTimeoutError(SubAgentGeneratorError):
    """Raised when generation times out"""
    pass


class SubAgentNotFoundError(SubAgentGeneratorError):
    """Raised when sub-agent is not found"""
    pass
