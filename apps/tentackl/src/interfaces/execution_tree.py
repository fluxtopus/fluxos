"""Abstract interface for execution tree management."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any


class ExecutionTreeInterface(ABC):
    """Interface for managing agent execution trees."""
    
    @abstractmethod
    async def create_tree(self, tree_id: str, root_agent_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Create a new execution tree."""
        pass
    
    @abstractmethod
    async def add_node(self, tree_id: str, node_id: str, parent_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add a node to the execution tree."""
        pass
    
    @abstractmethod
    async def add_edge(self, tree_id: str, from_node: str, to_node: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add an edge between nodes in the tree."""
        pass
    
    @abstractmethod
    async def get_tree(self, tree_id: str) -> Optional[Dict[str, Any]]:
        """Get the complete execution tree."""
        pass
    
    @abstractmethod
    async def get_node(self, tree_id: str, node_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific node from the tree."""
        pass
    
    @abstractmethod
    async def get_children(self, tree_id: str, node_id: str) -> List[str]:
        """Get all children of a node."""
        pass
    
    @abstractmethod
    async def get_parent(self, tree_id: str, node_id: str) -> Optional[str]:
        """Get the parent of a node."""
        pass
    
    @abstractmethod
    async def update_node(self, tree_id: str, node_id: str, updates: Dict[str, Any]) -> None:
        """Update node metadata."""
        pass
    
    @abstractmethod
    async def delete_tree(self, tree_id: str) -> None:
        """Delete an entire execution tree."""
        pass
    
    @abstractmethod
    async def list_trees(self) -> List[str]:
        """List all execution tree IDs."""
        pass
    
    @abstractmethod
    async def get_tree_metadata(self, tree_id: str) -> Optional[Dict[str, Any]]:
        """Get tree-level metadata."""
        pass
    
    @abstractmethod
    async def update_tree_metadata(self, tree_id: str, metadata: Dict[str, Any]) -> None:
        """Update tree-level metadata."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the execution tree service is healthy."""
        pass