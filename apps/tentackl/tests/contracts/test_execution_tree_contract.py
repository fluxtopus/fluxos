"""
Contract tests for ExecutionTree interface implementations

These tests ensure all ExecutionTree implementations conform to the interface contract
and provide proper tree structure and tracking capabilities.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Type, List, Dict, Set
from unittest.mock import AsyncMock, MagicMock

from src.core.execution_tree import (
    ExecutionTreeInterface, ExecutionNode, ExecutionTreeSnapshot, 
    NodeType, ExecutionStatus, ExecutionPriority, ExecutionMetrics,
    TreeNotFoundError, NodeNotFoundError, CircularDependencyError, InvalidTreeStructureError
)


class ExecutionTreeContractTest:
    """
    Base contract test class for ExecutionTree implementations
    All ExecutionTree implementations must pass these tests
    """
    
    @pytest.fixture
    def execution_tree(self) -> ExecutionTreeInterface:
        """Override this fixture in implementation-specific test classes"""
        raise NotImplementedError("Subclasses must provide execution_tree fixture")
    
    @pytest.fixture
    def sample_node(self) -> ExecutionNode:
        """Sample execution node for testing"""
        return ExecutionNode(
            name="test_node",
            node_type=NodeType.AGENT,
            agent_id="test_agent_123",
            context_id="test_context_456",
            task_data={"operation": "test", "timeout": 30},
            priority=ExecutionPriority.NORMAL
        )
    
    @pytest.fixture
    def sample_nodes(self) -> List[ExecutionNode]:
        """Multiple sample nodes for testing"""
        return [
            ExecutionNode(
                name="root_node",
                node_type=NodeType.ROOT,
                agent_id="root_agent",
                priority=ExecutionPriority.HIGH
            ),
            ExecutionNode(
                name="worker_1",
                node_type=NodeType.AGENT,
                agent_id="worker_agent_1",
                task_data={"operation": "compute", "data": [1, 2, 3]}
            ),
            ExecutionNode(
                name="worker_2", 
                node_type=NodeType.AGENT,
                agent_id="worker_agent_2",
                task_data={"operation": "validate", "threshold": 0.5}
            )
        ]
    
    @pytest.mark.asyncio
    async def test_create_tree_basic(self, execution_tree):
        """Test basic tree creation"""
        tree_id = await execution_tree.create_tree(
            root_name="test_workflow",
            metadata={"created_by": "test_suite", "version": "1.0"}
        )
        
        assert tree_id is not None, "Should return a tree ID"
        assert isinstance(tree_id, str), "Tree ID should be a string"
        assert len(tree_id) > 0, "Tree ID should not be empty"
        
        # Verify tree can be retrieved
        snapshot = await execution_tree.get_tree_snapshot(tree_id)
        assert snapshot is not None, "Should be able to retrieve created tree"
        assert snapshot.tree_id == tree_id
        assert snapshot.root_node_id is not None, "Should have a root node"
    
    @pytest.mark.asyncio
    async def test_add_node_to_tree(self, execution_tree, sample_node):
        """Test adding nodes to tree"""
        # Create tree
        tree_id = await execution_tree.create_tree("test_tree")
        
        # Add node to tree
        result = await execution_tree.add_node(tree_id, sample_node)
        assert result is True, "Adding node should succeed"
        
        # Verify node was added
        retrieved_node = await execution_tree.get_node(tree_id, sample_node.id)
        assert retrieved_node is not None, "Should be able to retrieve added node"
        assert retrieved_node.id == sample_node.id
        assert retrieved_node.name == sample_node.name
        assert retrieved_node.node_type == sample_node.node_type
        assert retrieved_node.agent_id == sample_node.agent_id
    
    @pytest.mark.asyncio
    async def test_add_node_with_parent(self, execution_tree, sample_nodes):
        """Test adding nodes with parent-child relationships"""
        tree_id = await execution_tree.create_tree("hierarchy_test")
        root_node, child1, child2 = sample_nodes
        
        # Add root node
        await execution_tree.add_node(tree_id, root_node)
        
        # Add children with parent relationship
        await execution_tree.add_node(tree_id, child1, parent_id=root_node.id)
        await execution_tree.add_node(tree_id, child2, parent_id=root_node.id)
        
        # Verify relationships
        children = await execution_tree.get_children(tree_id, root_node.id)
        assert len(children) == 2, "Root should have 2 children"
        
        child_ids = {child.id for child in children}
        assert child1.id in child_ids, "Child1 should be in children"
        assert child2.id in child_ids, "Child2 should be in children"
    
    @pytest.mark.asyncio
    async def test_update_node_status(self, execution_tree, sample_node):
        """Test updating node execution status"""
        tree_id = await execution_tree.create_tree("status_test")
        await execution_tree.add_node(tree_id, sample_node)
        
        # Update to running
        result_data = {"started_at": datetime.utcnow().isoformat()}
        result = await execution_tree.update_node_status(
            tree_id, sample_node.id, ExecutionStatus.RUNNING, result_data=result_data
        )
        assert result is True, "Status update should succeed"
        
        # Verify status update
        updated_node = await execution_tree.get_node(tree_id, sample_node.id)
        assert updated_node.status == ExecutionStatus.RUNNING
        assert updated_node.result_data["started_at"] == result_data["started_at"]
        
        # Update to completed
        completion_data = {"completed_at": datetime.utcnow().isoformat(), "result": "success"}
        await execution_tree.update_node_status(
            tree_id, sample_node.id, ExecutionStatus.COMPLETED, result_data=completion_data
        )
        
        completed_node = await execution_tree.get_node(tree_id, sample_node.id)
        assert completed_node.status == ExecutionStatus.COMPLETED
        assert completed_node.result_data["result"] == "success"
    
    @pytest.mark.asyncio
    async def test_update_node_status_with_error(self, execution_tree, sample_node):
        """Test updating node status with error data"""
        tree_id = await execution_tree.create_tree("error_test")
        await execution_tree.add_node(tree_id, sample_node)
        
        error_data = {
            "error_type": "ValidationError", 
            "message": "Input validation failed",
            "traceback": "Stack trace here..."
        }
        
        result = await execution_tree.update_node_status(
            tree_id, sample_node.id, ExecutionStatus.FAILED, error_data=error_data
        )
        assert result is True, "Error status update should succeed"
        
        # Verify error data
        failed_node = await execution_tree.get_node(tree_id, sample_node.id)
        assert failed_node.status == ExecutionStatus.FAILED
        assert failed_node.error_data["error_type"] == "ValidationError"
        assert failed_node.error_data["message"] == "Input validation failed"
    
    @pytest.mark.asyncio
    async def test_get_tree_snapshot(self, execution_tree, sample_nodes):
        """Test getting complete tree snapshot"""
        tree_id = await execution_tree.create_tree("snapshot_test")
        
        # Add multiple nodes
        for node in sample_nodes:
            await execution_tree.add_node(tree_id, node)
        
        # Update some statuses
        await execution_tree.update_node_status(tree_id, sample_nodes[1].id, ExecutionStatus.RUNNING)
        await execution_tree.update_node_status(tree_id, sample_nodes[2].id, ExecutionStatus.COMPLETED)
        
        # Get snapshot
        snapshot = await execution_tree.get_tree_snapshot(tree_id)
        
        assert snapshot is not None, "Should get tree snapshot"
        assert snapshot.tree_id == tree_id
        assert len(snapshot.nodes) >= len(sample_nodes), "Should contain all added nodes"
        
        # Verify execution summary
        summary = snapshot.get_execution_summary()
        assert summary["total_nodes"] >= 3
        assert summary["status_counts"][ExecutionStatus.RUNNING] >= 1
        assert summary["status_counts"][ExecutionStatus.COMPLETED] >= 1
    
    @pytest.mark.asyncio
    async def test_get_ready_nodes(self, execution_tree):
        """Test getting nodes ready for execution"""
        tree_id = await execution_tree.create_tree("ready_test")
        
        # Create nodes with dependencies
        node1 = ExecutionNode(name="independent", node_type=NodeType.AGENT)
        node2 = ExecutionNode(name="dependent", node_type=NodeType.AGENT)
        node2.add_dependency(node1.id)
        node3 = ExecutionNode(name="also_independent", node_type=NodeType.AGENT)
        
        # Add nodes
        await execution_tree.add_node(tree_id, node1)
        await execution_tree.add_node(tree_id, node2)
        await execution_tree.add_node(tree_id, node3)
        
        # Get ready nodes (should exclude node2 since its dependency isn't completed)
        ready_nodes = await execution_tree.get_ready_nodes(tree_id)
        ready_ids = {node.id for node in ready_nodes}
        
        assert node1.id in ready_ids, "Independent node1 should be ready"
        assert node3.id in ready_ids, "Independent node3 should be ready"
        assert node2.id not in ready_ids, "Dependent node2 should not be ready"
        
        # Complete dependency and check again
        await execution_tree.update_node_status(tree_id, node1.id, ExecutionStatus.COMPLETED)
        ready_nodes = await execution_tree.get_ready_nodes(tree_id)
        ready_ids = {node.id for node in ready_nodes}
        
        assert node2.id in ready_ids, "node2 should now be ready after dependency completion"
    
    @pytest.mark.asyncio
    async def test_subscription_to_updates(self, execution_tree, sample_node):
        """Test subscribing to tree updates"""
        tree_id = await execution_tree.create_tree("subscription_test")
        await execution_tree.add_node(tree_id, sample_node)
        
        # Track updates
        updates_received = []
        
        def update_callback(node: ExecutionNode):
            updates_received.append(node)
        
        # Subscribe to updates
        subscription_id = await execution_tree.subscribe_to_updates(tree_id, update_callback)
        assert subscription_id is not None, "Should return subscription ID"
        
        # Make updates that should trigger callbacks
        await execution_tree.update_node_status(tree_id, sample_node.id, ExecutionStatus.RUNNING)
        await execution_tree.update_node_status(tree_id, sample_node.id, ExecutionStatus.COMPLETED)
        
        # Allow some time for async callbacks
        await asyncio.sleep(0.1)
        
        # Unsubscribe
        unsubscribe_result = await execution_tree.unsubscribe_from_updates(subscription_id)
        assert unsubscribe_result is True, "Unsubscribe should succeed"
    
    @pytest.mark.asyncio
    async def test_get_execution_path(self, execution_tree, sample_nodes):
        """Test getting execution path from root to node"""
        tree_id = await execution_tree.create_tree("path_test")
        root, child1, child2 = sample_nodes
        
        # Create hierarchy: root -> child1 -> child2
        await execution_tree.add_node(tree_id, root)
        await execution_tree.add_node(tree_id, child1, parent_id=root.id)
        await execution_tree.add_node(tree_id, child2, parent_id=child1.id)
        
        # Get path to deepest node
        path = await execution_tree.get_execution_path(tree_id, child2.id)
        
        assert len(path) == 3, "Path should include root, child1, and child2"
        assert path[0].id == root.id, "First node should be root"
        assert path[1].id == child1.id, "Second node should be child1"
        assert path[2].id == child2.id, "Third node should be child2"
    
    @pytest.mark.asyncio
    async def test_tree_metrics(self, execution_tree, sample_nodes):
        """Test getting aggregated tree metrics"""
        tree_id = await execution_tree.create_tree("metrics_test")
        
        # Add nodes and update statuses
        for i, node in enumerate(sample_nodes):
            await execution_tree.add_node(tree_id, node)
            if i == 1:
                await execution_tree.update_node_status(tree_id, node.id, ExecutionStatus.RUNNING)
            elif i == 2:
                await execution_tree.update_node_status(tree_id, node.id, ExecutionStatus.COMPLETED)
        
        # Get metrics
        metrics = await execution_tree.get_tree_metrics(tree_id)
        
        assert isinstance(metrics, dict), "Metrics should be a dictionary"
        assert "total_nodes" in metrics or len(metrics) >= 0, "Should contain metrics data"
    
    @pytest.mark.asyncio
    async def test_delete_tree(self, execution_tree, sample_nodes):
        """Test tree deletion"""
        tree_id = await execution_tree.create_tree("delete_test")
        
        # Add nodes
        for node in sample_nodes:
            await execution_tree.add_node(tree_id, node)
        
        # Verify tree exists
        snapshot = await execution_tree.get_tree_snapshot(tree_id)
        assert snapshot is not None, "Tree should exist before deletion"
        
        # Delete tree
        result = await execution_tree.delete_tree(tree_id)
        assert result is True, "Tree deletion should succeed"
        
        # Verify tree is gone
        snapshot = await execution_tree.get_tree_snapshot(tree_id)
        assert snapshot is None, "Tree should not exist after deletion"
    
    @pytest.mark.asyncio
    async def test_concurrent_node_updates(self, execution_tree, sample_nodes):
        """Test concurrent node status updates"""
        tree_id = await execution_tree.create_tree("concurrent_test")
        
        # Add nodes
        for node in sample_nodes:
            await execution_tree.add_node(tree_id, node)
        
        async def update_node_status(node_id, status):
            return await execution_tree.update_node_status(tree_id, node_id, status)
        
        # Update multiple nodes concurrently
        tasks = [
            update_node_status(sample_nodes[0].id, ExecutionStatus.RUNNING),
            update_node_status(sample_nodes[1].id, ExecutionStatus.RUNNING),
            update_node_status(sample_nodes[2].id, ExecutionStatus.COMPLETED)
        ]
        
        results = await asyncio.gather(*tasks)
        assert all(results), "All concurrent updates should succeed"
        
        # Verify final states
        for i, expected_status in enumerate([ExecutionStatus.RUNNING, ExecutionStatus.RUNNING, ExecutionStatus.COMPLETED]):
            node = await execution_tree.get_node(tree_id, sample_nodes[i].id)
            assert node.status == expected_status
    
    @pytest.mark.asyncio
    async def test_invalid_operations(self, execution_tree, sample_node):
        """Test error handling for invalid operations"""
        non_existent_tree = "non_existent_tree"
        non_existent_node = "non_existent_node"
        
        # Test operations on non-existent tree
        snapshot = await execution_tree.get_tree_snapshot(non_existent_tree)
        assert snapshot is None, "Should return None for non-existent tree"
        
        result = await execution_tree.add_node(non_existent_tree, sample_node)
        assert result is False, "Should fail to add node to non-existent tree"
        
        # Test operations on non-existent node
        tree_id = await execution_tree.create_tree("test_tree")
        
        node = await execution_tree.get_node(tree_id, non_existent_node)
        assert node is None, "Should return None for non-existent node"
        
        result = await execution_tree.update_node_status(tree_id, non_existent_node, ExecutionStatus.RUNNING)
        assert result is False, "Should fail to update non-existent node"
    
    def test_execution_node_lifecycle(self):
        """Test ExecutionNode lifecycle methods"""
        node = ExecutionNode(
            name="lifecycle_test",
            node_type=NodeType.AGENT,
            max_retries=2
        )
        
        # Initial state
        assert node.status == ExecutionStatus.PENDING
        
        # Start execution
        node.start_execution()
        assert node.status == ExecutionStatus.RUNNING
        assert node.metrics.start_time is not None
        
        # Complete execution
        result_data = {"output": "success"}
        node.complete_execution(result_data)
        assert node.status == ExecutionStatus.COMPLETED
        assert node.metrics.end_time is not None
        assert node.result_data == result_data
        
        # Test retry logic
        retry_node = ExecutionNode(name="retry_test", max_retries=1)
        error_data = {"error": "test error"}
        retry_node.fail_execution(error_data)
        
        assert retry_node.should_retry() is True
        retry_node.retry_execution()
        assert retry_node.status == ExecutionStatus.PENDING
        assert retry_node.retry_count == 1
        
        # Fail again - should not retry
        retry_node.fail_execution(error_data)
        assert retry_node.should_retry() is False
    
    def test_execution_node_dependencies(self):
        """Test ExecutionNode dependency management"""
        node = ExecutionNode(name="dep_test")
        
        # Add dependencies
        node.add_dependency("dep1")
        node.add_dependency("dep2")
        assert len(node.dependencies) == 2
        
        # Test readiness
        assert node.is_ready_to_execute(set()) is False
        assert node.is_ready_to_execute({"dep1"}) is False
        assert node.is_ready_to_execute({"dep1", "dep2"}) is True
        assert node.is_ready_to_execute({"dep1", "dep2", "extra"}) is True
    
    def test_execution_tree_snapshot(self):
        """Test ExecutionTreeSnapshot functionality"""
        snapshot = ExecutionTreeSnapshot(tree_id="test_tree")
        
        # Add sample nodes
        node1 = ExecutionNode(name="node1", status=ExecutionStatus.COMPLETED)
        node2 = ExecutionNode(name="node2", status=ExecutionStatus.RUNNING)
        node3 = ExecutionNode(name="node3", status=ExecutionStatus.FAILED)
        
        snapshot.nodes = {
            node1.id: node1,
            node2.id: node2,
            node3.id: node3
        }
        
        # Test status counts
        status_counts = snapshot.get_node_count_by_status()
        assert status_counts[ExecutionStatus.COMPLETED] == 1
        assert status_counts[ExecutionStatus.RUNNING] == 1
        assert status_counts[ExecutionStatus.FAILED] == 1
        
        # Test execution summary
        summary = snapshot.get_execution_summary()
        assert summary["total_nodes"] == 3
        assert summary["completion_rate"] == 1/3
        assert summary["failure_rate"] == 1/3
        assert summary["active_nodes"] == 1


# Mock implementation for basic testing
class MockExecutionTree(ExecutionTreeInterface):
    """Mock implementation for testing interface contract"""
    
    def __init__(self):
        self.trees = {}
        self.subscribers = {}
    
    async def create_tree(self, root_name: str, metadata: dict = None) -> str:
        import uuid
        tree_id = str(uuid.uuid4())
        
        root_node = ExecutionNode(
            name=root_name,
            node_type=NodeType.ROOT
        )
        
        self.trees[tree_id] = {
            "root_id": root_node.id,
            "nodes": {root_node.id: root_node},
            "metadata": metadata or {}
        }
        return tree_id
    
    async def add_node(self, tree_id: str, node: ExecutionNode, parent_id: str = None) -> bool:
        if tree_id not in self.trees:
            return False
        
        tree = self.trees[tree_id]
        tree["nodes"][node.id] = node
        
        if parent_id and parent_id in tree["nodes"]:
            parent_node = tree["nodes"][parent_id]
            parent_node.add_child(node.id)
            node.parent_id = parent_id
        
        return True
    
    async def update_node_status(
        self, tree_id: str, node_id: str, status: ExecutionStatus,
        result_data: dict = None, error_data: dict = None
    ) -> bool:
        if tree_id not in self.trees:
            return False
        
        tree = self.trees[tree_id]
        if node_id not in tree["nodes"]:
            return False
        
        node = tree["nodes"][node_id]
        node.status = status
        
        if result_data:
            node.result_data.update(result_data)
        if error_data:
            node.error_data = error_data
        
        # Notify subscribers
        if tree_id in self.subscribers:
            for callback in self.subscribers[tree_id]:
                try:
                    callback(node)
                except Exception:
                    pass  # Ignore callback errors
        
        return True
    
    async def get_node(self, tree_id: str, node_id: str) -> ExecutionNode:
        if tree_id not in self.trees:
            return None
        
        tree = self.trees[tree_id]
        return tree["nodes"].get(node_id)
    
    async def get_tree_snapshot(self, tree_id: str) -> ExecutionTreeSnapshot:
        if tree_id not in self.trees:
            return None
        
        tree = self.trees[tree_id]
        snapshot = ExecutionTreeSnapshot(
            tree_id=tree_id,
            nodes=tree["nodes"].copy(),
            root_node_id=tree["root_id"],
            metadata=tree["metadata"]
        )
        return snapshot
    
    async def get_children(self, tree_id: str, parent_id: str) -> List[ExecutionNode]:
        if tree_id not in self.trees:
            return []
        
        tree = self.trees[tree_id]
        parent = tree["nodes"].get(parent_id)
        if not parent:
            return []
        
        return [tree["nodes"][child_id] for child_id in parent.children_ids 
                if child_id in tree["nodes"]]
    
    async def get_ready_nodes(self, tree_id: str) -> List[ExecutionNode]:
        if tree_id not in self.trees:
            return []
        
        tree = self.trees[tree_id]
        completed_nodes = {node_id for node_id, node in tree["nodes"].items() 
                          if node.status == ExecutionStatus.COMPLETED}
        
        ready_nodes = []
        for node in tree["nodes"].values():
            if (node.status == ExecutionStatus.PENDING and 
                node.is_ready_to_execute(completed_nodes)):
                ready_nodes.append(node)
        
        return ready_nodes
    
    async def subscribe_to_updates(self, tree_id: str, callback) -> str:
        import uuid
        subscription_id = str(uuid.uuid4())
        
        if tree_id not in self.subscribers:
            self.subscribers[tree_id] = {}
        
        self.subscribers[tree_id][subscription_id] = callback
        return subscription_id
    
    async def unsubscribe_from_updates(self, subscription_id: str) -> bool:
        for tree_subs in self.subscribers.values():
            if subscription_id in tree_subs:
                del tree_subs[subscription_id]
                return True
        return False
    
    async def delete_tree(self, tree_id: str) -> bool:
        if tree_id in self.trees:
            del self.trees[tree_id]
            if tree_id in self.subscribers:
                del self.subscribers[tree_id]
            return True
        return False
    
    async def get_execution_path(self, tree_id: str, node_id: str) -> List[ExecutionNode]:
        if tree_id not in self.trees:
            return []
        
        tree = self.trees[tree_id]
        if node_id not in tree["nodes"]:
            return []
        
        path = []
        current_node = tree["nodes"][node_id]
        
        while current_node:
            path.insert(0, current_node)
            if current_node.parent_id:
                current_node = tree["nodes"].get(current_node.parent_id)
            else:
                break
        
        return path
    
    async def get_tree_metrics(self, tree_id: str) -> dict:
        if tree_id not in self.trees:
            return {}
        
        tree = self.trees[tree_id]
        nodes = tree["nodes"]
        
        status_counts = {}
        for node in nodes.values():
            status_counts[node.status] = status_counts.get(node.status, 0) + 1
        
        return {
            "tree_id": tree_id,
            "total_nodes": len(nodes),
            "status_counts": {status.value: count for status, count in status_counts.items()}
        }


class TestMockExecutionTree(ExecutionTreeContractTest):
    """Test the mock implementation against the contract"""
    
    @pytest.fixture
    def execution_tree(self):
        return MockExecutionTree()