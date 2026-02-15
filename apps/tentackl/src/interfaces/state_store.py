"""
State Store Interface and State Management Abstractions

This module defines the core interfaces for state management in the sub-agent
generation system, following Single Responsibility Principle.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import uuid


class StateType(Enum):
    """Types of state that can be stored"""
    AGENT_STATE = "agent_state"
    EXECUTION_CONTEXT = "execution_context"
    WORKFLOW_STATE = "workflow_state"
    SUB_AGENT_STATE = "sub_agent_state"
    # Common aliases used by higher-level agents/tests
    CHECKPOINT = "checkpoint"
    FINAL = "final"
    # Delegation system state types
    PLAN_DOCUMENT = "plan_document"           # Persistent delegation plan
    CHECKPOINT_STATE = "checkpoint_state"     # Checkpoint approval state
    PREFERENCE_RECORD = "preference_record"   # User preference record
    OBSERVER_REPORT = "observer_report"       # Observer agent report


@dataclass
class StateSnapshot:
    """Immutable snapshot of agent state at a point in time"""
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    state_type: StateType = StateType.AGENT_STATE
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    parent_snapshot_id: Optional[str] = None
    version: int = 1
    
    def __post_init__(self):
        """Ensure immutability after creation"""
        if not self.agent_id:
            raise ValueError("agent_id is required")
    
    def with_data(self, new_data: Dict[str, Any]) -> 'StateSnapshot':
        """Create new snapshot with updated data"""
        return StateSnapshot(
            agent_id=self.agent_id,
            state_type=self.state_type,
            data={**self.data, **new_data},
            metadata=self.metadata.copy(),
            parent_snapshot_id=self.id,
            version=self.version + 1
        )
    
    def with_metadata(self, new_metadata: Dict[str, Any]) -> 'StateSnapshot':
        """Create new snapshot with updated metadata"""
        return StateSnapshot(
            agent_id=self.agent_id,
            state_type=self.state_type,
            data=self.data.copy(),
            metadata={**self.metadata, **new_metadata},
            parent_snapshot_id=self.id,
            version=self.version + 1
        )


@dataclass
class StateQuery:
    """Query parameters for state retrieval"""
    
    agent_id: Optional[str] = None
    state_type: Optional[StateType] = None
    # Optional list-based filters supported by some callers/tests
    agent_ids: Optional[List[str]] = None
    state_types: Optional[List[StateType]] = None
    timestamp_from: Optional[datetime] = None
    timestamp_to: Optional[datetime] = None
    version: Optional[int] = None
    snapshot_id: Optional[str] = None
    metadata_filter: Dict[str, Any] = field(default_factory=dict)
    limit: int = 100
    offset: int = 0


class StateStoreInterface(ABC):
    """
    Abstract interface for state storage operations
    Follows SRP - handles only state persistence operations
    """
    
    @abstractmethod
    async def save_state(self, snapshot: StateSnapshot) -> bool:
        """
        Save a state snapshot
        
        Args:
            snapshot: The state snapshot to save
            
        Returns:
            bool: True if save successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def load_state(self, query: StateQuery) -> List[StateSnapshot]:
        """
        Load state snapshots based on query parameters
        
        Args:
            query: Query parameters for state retrieval
            
        Returns:
            List[StateSnapshot]: List of matching state snapshots
        """
        pass
    
    @abstractmethod
    async def get_latest_state(self, agent_id: str, state_type: StateType) -> Optional[StateSnapshot]:
        """
        Get the most recent state snapshot for an agent
        
        Args:
            agent_id: The agent identifier
            state_type: The type of state to retrieve
            
        Returns:
            Optional[StateSnapshot]: Latest snapshot or None if not found
        """
        pass
    
    @abstractmethod
    async def delete_state(self, agent_id: str, state_type: Optional[StateType] = None) -> bool:
        """
        Delete state snapshots for an agent
        
        Args:
            agent_id: The agent identifier
            state_type: Optional state type filter, if None deletes all states
            
        Returns:
            bool: True if deletion successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_state_history(self, agent_id: str, limit: int = 100) -> List[StateSnapshot]:
        """
        Get state history for an agent in chronological order
        
        Args:
            agent_id: The agent identifier
            limit: Maximum number of snapshots to return
            
        Returns:
            List[StateSnapshot]: List of state snapshots ordered by timestamp
        """
        pass
    
    @abstractmethod
    async def cleanup_old_states(self, retention_days: int = 30) -> int:
        """
        Clean up old state snapshots beyond retention period
        
        Args:
            retention_days: Number of days to retain states
            
        Returns:
            int: Number of snapshots cleaned up
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the state store is healthy and accessible
        
        Returns:
            bool: True if healthy, False otherwise
        """
        pass


class StateStoreException(Exception):
    """Base exception for state store operations"""
    pass


class StateNotFoundError(StateStoreException):
    """Raised when requested state is not found"""
    pass


class StateValidationError(StateStoreException):
    """Raised when state data is invalid"""
    pass


class StateStoreConnectionError(StateStoreException):
    """Raised when state store is not accessible"""
    pass
