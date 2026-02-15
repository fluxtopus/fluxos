# REVIEW: AgentCapability enum is hard-coded here and may drift from the
# REVIEW: unified capabilities system stored in the database. Consider deriving
# REVIEW: capabilities from registry data instead of static enums.
"""
Agent Interface

This module defines the core interfaces for agents in the Tentackl system.
"""

from abc import ABC, abstractmethod
from typing import Any, List, Optional, Dict
from enum import Enum
from dataclasses import dataclass
from datetime import datetime


class AgentState(Enum):
    """Agent execution states"""
    IDLE = "idle"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentCapability(Enum):
    """Standard agent capabilities"""
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    API_CALL = "api_call"
    DATABASE = "database"
    LLM_QUERY = "llm_query"
    DATA_TRANSFORM = "data_transform"
    VALIDATION = "validation"
    NOTIFICATION = "notification"
    CACHING = "caching"
    SCHEDULING = "scheduling"
    MONITORING = "monitoring"
    CUSTOM = "custom"


@dataclass
class AgentResult:
    """Result from agent execution"""
    agent_id: str
    result: Any
    state: AgentState
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class AgentInterface(ABC):
    """Core interface for all agents"""
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the agent.
        This method should set up any required resources.
        """
        pass
    
    @abstractmethod
    async def execute(self, task: Any) -> AgentResult:
        """
        Execute a task.
        
        Args:
            task: The task to execute
            
        Returns:
            AgentResult with execution outcome
        """
        pass
    
    @abstractmethod
    async def get_state(self) -> AgentState:
        """
        Get current agent state.
        
        Returns:
            Current AgentState
        """
        pass
    
    @abstractmethod
    async def get_capabilities(self) -> List[AgentCapability]:
        """
        Get agent capabilities.
        
        Returns:
            List of AgentCapability enums
        """
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """
        Cleanup agent resources.
        This method should release any held resources.
        """
        pass
