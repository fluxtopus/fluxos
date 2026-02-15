"""
Execution Tracking Capability Implementation

Provides execution tree tracking for agents.
Extracted from StatefulAgent execution tree usage.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid
import structlog

from src.capabilities.protocols import ExecutionTrackingCapability, ExecutionNode as CapabilityNode
from src.core.execution_tree import (
    ExecutionTreeInterface,
    ExecutionNode,
    NodeType,
    ExecutionStatus,
)

logger = structlog.get_logger(__name__)


class ExecutionTrackingImpl:
    """
    Implementation of execution tracking capability.

    Wraps ExecutionTreeInterface to provide execution tree tracking
    for agents and their sub-agents.
    """

    def __init__(self, execution_tree: ExecutionTreeInterface):
        """
        Initialize execution tracking.

        Args:
            execution_tree: The underlying execution tree (e.g., RedisExecutionTree)
        """
        self._tree = execution_tree

    def _parse_node_type(self, node_type: str) -> NodeType:
        """Convert string node type to enum."""
        try:
            return NodeType[node_type.upper()]
        except KeyError:
            return NodeType.AGENT

    def _parse_status(self, status: str) -> ExecutionStatus:
        """Convert string status to enum."""
        try:
            return ExecutionStatus[status.upper()]
        except KeyError:
            return ExecutionStatus.PENDING

    async def create_tree(self, tree_id: Optional[str] = None) -> str:
        """Create a new execution tree."""
        try:
            tid = tree_id or str(uuid.uuid4())
            await self._tree.create_tree(tid)
            logger.debug("Execution tree created", tree_id=tid)
            return tid

        except Exception as e:
            logger.error("Failed to create execution tree", error=str(e))
            raise

    async def add_node(
        self,
        tree_id: str,
        agent_id: str,
        name: str,
        node_type: str = "AGENT",
        parent_id: Optional[str] = None,
        context_id: Optional[str] = None,
        task_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Add a node to the execution tree."""
        try:
            node = ExecutionNode(
                name=name,
                node_type=self._parse_node_type(node_type),
                agent_id=agent_id,
                context_id=context_id,
                parent_id=parent_id,
                task_data=task_data
            )

            await self._tree.add_node(tree_id, node, parent_id=parent_id)

            logger.debug(
                "Execution node added",
                tree_id=tree_id,
                node_id=node.id,
                agent_id=agent_id,
                node_type=node_type
            )

            return node.id

        except Exception as e:
            logger.error(
                "Failed to add execution node",
                tree_id=tree_id,
                agent_id=agent_id,
                error=str(e)
            )
            raise

    async def update_status(
        self,
        tree_id: str,
        node_id: str,
        status: str,
        result_data: Optional[Dict[str, Any]] = None,
        error_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update the status of an execution node."""
        try:
            await self._tree.update_node_status(
                tree_id=tree_id,
                node_id=node_id,
                status=self._parse_status(status),
                result_data=result_data,
                error_data=error_data
            )

            logger.debug(
                "Execution node status updated",
                tree_id=tree_id,
                node_id=node_id,
                status=status
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to update node status",
                tree_id=tree_id,
                node_id=node_id,
                error=str(e)
            )
            return False

    async def get_node(self, tree_id: str, node_id: str) -> Optional[CapabilityNode]:
        """Get a specific node."""
        try:
            node = await self._tree.get_node(tree_id, node_id)
            if not node:
                return None

            return CapabilityNode(
                node_id=node.id,
                agent_id=node.agent_id,
                name=node.name,
                node_type=node.node_type.name if node.node_type else "AGENT",
                status=node.status.name if node.status else "PENDING",
                parent_id=node.parent_id,
                context_id=node.context_id,
                task_data=node.task_data,
                result_data=node.result_data,
                error_data=node.error_data,
                created_at=node.created_at,
                completed_at=node.completed_at
            )

        except Exception as e:
            logger.error(
                "Failed to get execution node",
                tree_id=tree_id,
                node_id=node_id,
                error=str(e)
            )
            return None

    async def get_tree(self, tree_id: str) -> List[CapabilityNode]:
        """Get all nodes in a tree."""
        try:
            nodes = await self._tree.get_all_nodes(tree_id)

            return [
                CapabilityNode(
                    node_id=node.id,
                    agent_id=node.agent_id,
                    name=node.name,
                    node_type=node.node_type.name if node.node_type else "AGENT",
                    status=node.status.name if node.status else "PENDING",
                    parent_id=node.parent_id,
                    context_id=node.context_id,
                    task_data=node.task_data,
                    result_data=node.result_data,
                    error_data=node.error_data,
                    created_at=node.created_at,
                    completed_at=node.completed_at
                )
                for node in nodes
            ]

        except Exception as e:
            logger.error("Failed to get execution tree", tree_id=tree_id, error=str(e))
            return []

    async def delete_tree(self, tree_id: str) -> bool:
        """Delete an execution tree."""
        try:
            await self._tree.delete_tree(tree_id)
            logger.debug("Execution tree deleted", tree_id=tree_id)
            return True

        except Exception as e:
            logger.error("Failed to delete execution tree", tree_id=tree_id, error=str(e))
            return False

    @property
    def tree(self) -> ExecutionTreeInterface:
        """Access the underlying execution tree."""
        return self._tree
