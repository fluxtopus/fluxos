"""
Visualization API Interfaces for Real-time Sub-Agent Monitoring

This module defines the interfaces for real-time visualization of sub-agent
execution trees, including WebSocket communication and REST API endpoints.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid

from src.core.execution_tree import ExecutionNode, ExecutionTreeSnapshot, ExecutionStatus


class VisualizationEventType(Enum):
    """Types of visualization events"""
    NODE_CREATED = "node_created"
    NODE_UPDATED = "node_updated"
    NODE_STATUS_CHANGED = "node_status_changed"
    NODE_DELETED = "node_deleted"
    TREE_CREATED = "tree_created"
    TREE_UPDATED = "tree_updated"
    TREE_DELETED = "tree_deleted"
    METRICS_UPDATED = "metrics_updated"
    ERROR_OCCURRED = "error_occurred"


class VisualizationLayout(Enum):
    """Layout types for tree visualization"""
    HIERARCHICAL = "hierarchical"
    FORCE_DIRECTED = "force_directed"
    CIRCULAR = "circular"
    TREE_MAP = "tree_map"
    TIMELINE = "timeline"


@dataclass
class VisualizationEvent:
    """Event data for real-time visualization updates"""
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: VisualizationEventType = VisualizationEventType.NODE_UPDATED
    tree_id: str = ""
    node_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "event_type": self.event_type.value,
            "tree_id": self.tree_id,
            "node_id": self.node_id,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "metadata": self.metadata
        }


@dataclass
class NodeVisualizationData:
    """Visualization-specific data for execution nodes"""
    
    node_id: str = ""
    name: str = ""
    status: ExecutionStatus = ExecutionStatus.PENDING
    node_type: str = ""
    
    # Position and layout
    x: Optional[float] = None
    y: Optional[float] = None
    width: float = 100.0
    height: float = 50.0
    
    # Visual properties
    color: str = "#3498db"
    border_color: str = "#2980b9"
    text_color: str = "#ffffff"
    opacity: float = 1.0
    
    # Metrics for visualization
    progress_percent: float = 0.0
    execution_time_ms: Optional[int] = None
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    
    # Relationships
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    
    # Animation and interaction
    is_highlighted: bool = False
    is_selected: bool = False
    animation_state: str = "static"
    tooltip_data: Dict[str, Any] = field(default_factory=dict)
    
    def get_status_color(self) -> str:
        """Get color based on execution status"""
        status_colors = {
            ExecutionStatus.PENDING: "#95a5a6",
            ExecutionStatus.RUNNING: "#3498db",
            ExecutionStatus.PAUSED: "#f39c12",
            ExecutionStatus.COMPLETED: "#27ae60",
            ExecutionStatus.FAILED: "#e74c3c",
            ExecutionStatus.CANCELLED: "#7f8c8d",
            ExecutionStatus.TIMEOUT: "#e67e22"
        }
        return status_colors.get(self.status, self.color)
    
    def update_from_node(self, node: ExecutionNode) -> None:
        """Update visualization data from execution node"""
        self.node_id = node.id
        self.name = node.name
        self.status = node.status
        self.node_type = node.node_type.value
        self.parent_id = node.parent_id
        self.children_ids = list(node.children_ids)
        self.color = self.get_status_color()
        
        # Update metrics
        if node.metrics.duration:
            self.execution_time_ms = int(node.metrics.duration.total_seconds() * 1000)
        self.cpu_usage = node.metrics.cpu_usage_percent
        self.memory_usage = node.metrics.memory_usage_mb
        
        # Update tooltip data
        self.tooltip_data = {
            "agent_id": node.agent_id,
            "created_at": node.created_at.isoformat(),
            "retry_count": node.retry_count,
            "errors_count": node.metrics.errors_count,
            "warnings_count": node.metrics.warnings_count
        }


@dataclass
class TreeVisualizationData:
    """Complete visualization data for an execution tree"""
    
    tree_id: str = ""
    name: str = ""
    nodes: Dict[str, NodeVisualizationData] = field(default_factory=dict)
    edges: List[Dict[str, str]] = field(default_factory=list)
    layout: VisualizationLayout = VisualizationLayout.HIERARCHICAL
    
    # Tree-level metrics
    total_nodes: int = 0
    completed_nodes: int = 0
    failed_nodes: int = 0
    running_nodes: int = 0
    
    # Visualization settings
    zoom_level: float = 1.0
    center_x: float = 0.0
    center_y: float = 0.0
    auto_layout: bool = True
    
    # Animation settings
    animation_enabled: bool = True
    transition_duration_ms: int = 500
    
    def update_from_snapshot(self, snapshot: ExecutionTreeSnapshot) -> None:
        """Update visualization data from tree snapshot"""
        self.tree_id = snapshot.tree_id
        self.nodes.clear()
        self.edges.clear()
        
        # Convert nodes
        for node in snapshot.nodes.values():
            viz_node = NodeVisualizationData()
            viz_node.update_from_node(node)
            self.nodes[node.id] = viz_node
            
            # Create edges for parent-child relationships
            if node.parent_id:
                self.edges.append({
                    "source": node.parent_id,
                    "target": node.id,
                    "type": "parent_child"
                })
            
            # Create edges for dependencies
            for dep_id in node.dependencies:
                self.edges.append({
                    "source": dep_id,
                    "target": node.id,
                    "type": "dependency"
                })
        
        # Update metrics
        summary = snapshot.get_execution_summary()
        self.total_nodes = summary["total_nodes"]
        status_counts = summary["status_counts"]
        self.completed_nodes = status_counts.get(ExecutionStatus.COMPLETED, 0)
        self.failed_nodes = status_counts.get(ExecutionStatus.FAILED, 0)
        self.running_nodes = status_counts.get(ExecutionStatus.RUNNING, 0)
    
    def get_node_positions(self) -> Dict[str, Dict[str, float]]:
        """Get current node positions for layout"""
        positions = {}
        for node_id, node in self.nodes.items():
            if node.x is not None and node.y is not None:
                positions[node_id] = {"x": node.x, "y": node.y}
        return positions
    
    def update_node_positions(self, positions: Dict[str, Dict[str, float]]) -> None:
        """Update node positions from layout algorithm"""
        for node_id, pos in positions.items():
            if node_id in self.nodes:
                self.nodes[node_id].x = pos["x"]
                self.nodes[node_id].y = pos["y"]


class VisualizationWebSocketInterface(ABC):
    """
    Abstract interface for WebSocket-based real-time visualization
    Follows SRP - handles only WebSocket communication for visualization
    """
    
    @abstractmethod
    async def connect_client(self, client_id: str, tree_id: str) -> bool:
        """
        Connect a client to tree visualization updates
        
        Args:
            client_id: Unique client identifier
            tree_id: Tree to subscribe to updates
            
        Returns:
            bool: True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def disconnect_client(self, client_id: str) -> bool:
        """
        Disconnect a client from visualization updates
        
        Args:
            client_id: Client identifier to disconnect
            
        Returns:
            bool: True if disconnection successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def broadcast_event(self, tree_id: str, event: VisualizationEvent) -> int:
        """
        Broadcast an event to all connected clients for a tree
        
        Args:
            tree_id: Tree identifier
            event: Visualization event to broadcast
            
        Returns:
            int: Number of clients the event was sent to
        """
        pass
    
    @abstractmethod
    async def send_to_client(self, client_id: str, event: VisualizationEvent) -> bool:
        """
        Send an event to a specific client
        
        Args:
            client_id: Target client identifier
            event: Visualization event to send
            
        Returns:
            bool: True if send successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def get_connected_clients(self, tree_id: Optional[str] = None) -> List[str]:
        """
        Get list of connected client IDs
        
        Args:
            tree_id: Optional tree filter, if None returns all clients
            
        Returns:
            List[str]: List of connected client IDs
        """
        pass
    
    @abstractmethod
    async def ping_clients(self, tree_id: str) -> Dict[str, bool]:
        """
        Ping all clients for a tree to check connectivity
        
        Args:
            tree_id: Tree identifier
            
        Returns:
            Dict[str, bool]: Client ID to ping response mapping
        """
        pass


class VisualizationAPIInterface(ABC):
    """
    Abstract interface for REST API visualization endpoints
    Follows SRP - handles only HTTP API operations for visualization
    """
    
    @abstractmethod
    async def get_tree_visualization(self, tree_id: str) -> Optional[TreeVisualizationData]:
        """
        Get complete visualization data for a tree
        
        Args:
            tree_id: Tree identifier
            
        Returns:
            Optional[TreeVisualizationData]: Visualization data or None if not found
        """
        pass
    
    @abstractmethod
    async def get_node_details(self, tree_id: str, node_id: str) -> Optional[NodeVisualizationData]:
        """
        Get detailed visualization data for a specific node
        
        Args:
            tree_id: Tree identifier
            node_id: Node identifier
            
        Returns:
            Optional[NodeVisualizationData]: Node visualization data or None if not found
        """
        pass
    
    @abstractmethod
    async def update_layout(
        self, 
        tree_id: str, 
        layout: VisualizationLayout,
        layout_options: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update the layout algorithm for a tree
        
        Args:
            tree_id: Tree identifier
            layout: New layout type
            layout_options: Optional layout-specific options
            
        Returns:
            bool: True if update successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def export_visualization(
        self, 
        tree_id: str, 
        format_type: str = "svg",
        options: Optional[Dict[str, Any]] = None
    ) -> Optional[bytes]:
        """
        Export tree visualization to image format
        
        Args:
            tree_id: Tree identifier
            format_type: Export format (svg, png, pdf)
            options: Optional export options
            
        Returns:
            Optional[bytes]: Exported visualization data or None if failed
        """
        pass
    
    @abstractmethod
    async def get_tree_metrics(self, tree_id: str) -> Dict[str, Any]:
        """
        Get aggregated metrics for visualization
        
        Args:
            tree_id: Tree identifier
            
        Returns:
            Dict[str, Any]: Tree metrics for visualization
        """
        pass
    
    @abstractmethod
    async def search_nodes(
        self, 
        tree_id: str, 
        query: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[NodeVisualizationData]:
        """
        Search for nodes in the tree
        
        Args:
            tree_id: Tree identifier
            query: Search query string
            filters: Optional additional filters
            
        Returns:
            List[NodeVisualizationData]: List of matching nodes
        """
        pass


class VisualizationLayoutInterface(ABC):
    """
    Abstract interface for layout algorithms
    Follows SRP - handles only layout calculation operations
    """
    
    @abstractmethod
    async def calculate_layout(
        self, 
        visualization_data: TreeVisualizationData,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Dict[str, float]]:
        """
        Calculate optimal positions for nodes
        
        Args:
            visualization_data: Current tree visualization data
            options: Optional layout-specific options
            
        Returns:
            Dict[str, Dict[str, float]]: Node ID to position mapping
        """
        pass
    
    @abstractmethod
    async def update_incremental(
        self, 
        current_positions: Dict[str, Dict[str, float]], 
        new_nodes: List[NodeVisualizationData],
        updated_nodes: List[NodeVisualizationData]
    ) -> Dict[str, Dict[str, float]]:
        """
        Update layout incrementally with new/updated nodes
        
        Args:
            current_positions: Current node positions
            new_nodes: Newly added nodes
            updated_nodes: Updated existing nodes
            
        Returns:
            Dict[str, Dict[str, float]]: Updated node positions
        """
        pass
    
    @abstractmethod
    def get_layout_options(self) -> Dict[str, Any]:
        """
        Get available options for this layout algorithm
        
        Returns:
            Dict[str, Any]: Available layout options and their types
        """
        pass


class VisualizationException(Exception):
    """Base exception for visualization operations"""
    pass


class ClientNotFoundError(VisualizationException):
    """Raised when client is not found"""
    pass


class LayoutCalculationError(VisualizationException):
    """Raised when layout calculation fails"""
    pass


class ExportError(VisualizationException):
    """Raised when visualization export fails"""
    pass