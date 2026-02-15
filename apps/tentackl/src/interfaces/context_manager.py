"""
Context Manager Interface for Agent Execution Isolation

This module defines interfaces for managing agent execution contexts
and ensuring proper isolation between sub-agents.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid


class ContextIsolationLevel(Enum):
    """Levels of context isolation"""
    NONE = "none"               # No isolation, shared context
    SHALLOW = "shallow"         # Shallow copy of context
    DEEP = "deep"              # Deep copy of context
    SANDBOXED = "sandboxed"    # Completely isolated sandbox


class ContextState(Enum):
    """Context lifecycle states"""
    CREATED = "created"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


@dataclass
class AgentContext:
    """
    Represents an isolated execution context for an agent
    Contains all data and configuration needed for agent execution
    """
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    parent_context_id: Optional[str] = None
    isolation_level: ContextIsolationLevel = ContextIsolationLevel.DEEP
    state: ContextState = ContextState.CREATED
    
    # Context data
    variables: Dict[str, Any] = field(default_factory=dict)
    shared_resources: Dict[str, Any] = field(default_factory=dict)
    private_resources: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    
    # Execution constraints
    max_execution_time: Optional[int] = None  # seconds
    max_memory_mb: Optional[int] = None
    allowed_operations: Set[str] = field(default_factory=set)
    restricted_operations: Set[str] = field(default_factory=set)
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate context after creation"""
        if not self.agent_id:
            raise ValueError("agent_id is required")
    
    def is_operation_allowed(self, operation: str) -> bool:
        """Check if an operation is allowed in this context"""
        if operation in self.restricted_operations:
            return False
        if self.allowed_operations and operation not in self.allowed_operations:
            return False
        return True
    
    def update_state(self, new_state: ContextState) -> None:
        """Update context state with timestamp"""
        self.state = new_state
        self.updated_at = datetime.utcnow()
    
    def add_variable(self, key: str, value: Any) -> None:
        """Add or update a context variable"""
        self.variables[key] = value
        self.updated_at = datetime.utcnow()
    
    def get_variable(self, key: str, default: Any = None) -> Any:
        """Get a context variable with optional default"""
        return self.variables.get(key, default)
    
    def remove_variable(self, key: str) -> bool:
        """Remove a context variable"""
        if key in self.variables:
            del self.variables[key]
            self.updated_at = datetime.utcnow()
            return True
        return False


@dataclass
class ContextForkOptions:
    """Options for context forking operations"""
    
    isolation_level: ContextIsolationLevel = ContextIsolationLevel.DEEP
    inherit_variables: bool = True
    inherit_shared_resources: bool = True
    inherit_constraints: bool = True
    copy_metadata: bool = False
    
    # Override constraints for child context
    max_execution_time_override: Optional[int] = None
    max_memory_mb_override: Optional[int] = None
    allowed_operations_override: Optional[Set[str]] = None
    restricted_operations_override: Optional[Set[str]] = None


class ContextManagerInterface(ABC):
    """
    Abstract interface for context management operations
    Follows SRP - handles only context lifecycle and isolation
    """
    
    @abstractmethod
    async def create_context(
        self, 
        agent_id: str, 
        isolation_level: ContextIsolationLevel = ContextIsolationLevel.DEEP,
        **context_data
    ) -> str:
        """
        Create a new execution context for an agent
        
        Args:
            agent_id: The agent identifier
            isolation_level: Level of isolation for the context
            **context_data: Initial context data
            
        Returns:
            str: The created context ID
        """
        pass
    
    @abstractmethod
    async def fork_context(
        self, 
        parent_context_id: str, 
        child_agent_id: str,
        fork_options: Optional[ContextForkOptions] = None
    ) -> str:
        """
        Fork an existing context for a sub-agent
        
        Args:
            parent_context_id: The parent context to fork from
            child_agent_id: The child agent identifier
            fork_options: Options controlling the fork operation
            
        Returns:
            str: The new child context ID
        """
        pass
    
    @abstractmethod
    async def get_context(self, context_id: str) -> Optional[AgentContext]:
        """
        Retrieve a context by ID
        
        Args:
            context_id: The context identifier
            
        Returns:
            Optional[AgentContext]: The context or None if not found
        """
        pass
    
    @abstractmethod
    async def update_context(self, context_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update context data
        
        Args:
            context_id: The context identifier
            updates: Dictionary of updates to apply
            
        Returns:
            bool: True if update successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def suspend_context(self, context_id: str) -> bool:
        """
        Suspend a context (pause execution)
        
        Args:
            context_id: The context identifier
            
        Returns:
            bool: True if suspension successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def resume_context(self, context_id: str) -> bool:
        """
        Resume a suspended context
        
        Args:
            context_id: The context identifier
            
        Returns:
            bool: True if resumption successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def terminate_context(self, context_id: str, cleanup: bool = True) -> bool:
        """
        Terminate a context and optionally clean up resources
        
        Args:
            context_id: The context identifier
            cleanup: Whether to clean up context resources
            
        Returns:
            bool: True if termination successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_child_contexts(self, parent_context_id: str) -> List[AgentContext]:
        """
        Get all child contexts of a parent context
        
        Args:
            parent_context_id: The parent context identifier
            
        Returns:
            List[AgentContext]: List of child contexts
        """
        pass
    
    @abstractmethod
    async def cleanup_completed_contexts(self, retention_hours: int = 24) -> int:
        """
        Clean up completed contexts older than retention period
        
        Args:
            retention_hours: Hours to retain completed contexts
            
        Returns:
            int: Number of contexts cleaned up
        """
        pass
    
    @abstractmethod
    async def validate_operation(self, context_id: str, operation: str) -> bool:
        """
        Validate if an operation is allowed in the given context
        
        Args:
            context_id: The context identifier
            operation: The operation to validate
            
        Returns:
            bool: True if operation is allowed, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_context_metrics(self, context_id: str) -> Dict[str, Any]:
        """
        Get execution metrics for a context
        
        Args:
            context_id: The context identifier
            
        Returns:
            Dict[str, Any]: Context execution metrics
        """
        pass


class ContextManagerException(Exception):
    """Base exception for context manager operations"""
    pass


class ContextNotFoundError(ContextManagerException):
    """Raised when requested context is not found"""
    pass


class ContextIsolationError(ContextManagerException):
    """Raised when context isolation fails"""
    pass


class OperationNotAllowedError(ContextManagerException):
    """Raised when operation is not allowed in context"""
    pass


class ContextStateError(ContextManagerException):
    """Raised when context is in invalid state for operation"""
    pass
