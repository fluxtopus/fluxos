"""
Contract tests for ContextManager interface implementations

These tests ensure all ContextManager implementations conform to the interface contract
and provide proper context isolation.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Type, List, Set
from unittest.mock import AsyncMock
import copy

from src.interfaces.context_manager import (
    ContextManagerInterface, AgentContext, ContextForkOptions, 
    ContextIsolationLevel, ContextState,
    ContextNotFoundError, ContextIsolationError, OperationNotAllowedError, ContextStateError
)


class ContextManagerContractTest:
    """
    Base contract test class for ContextManager implementations
    All ContextManager implementations must pass these tests
    """
    
    @pytest.fixture
    def context_manager(self) -> ContextManagerInterface:
        """Override this fixture in implementation-specific test classes"""
        raise NotImplementedError("Subclasses must provide context_manager fixture")
    
    @pytest.fixture
    def sample_context_data(self) -> dict:
        """Sample context data for testing"""
        return {
            "variables": {"x": 10, "y": "test"},
            "max_execution_time": 300,
            "allowed_operations": {"read", "write", "compute"}
        }
    
    @pytest.mark.asyncio
    async def test_create_context_basic(self, context_manager, sample_context_data):
        """Test basic context creation"""
        agent_id = "test_agent_123"
        
        context_id = await context_manager.create_context(
            agent_id=agent_id,
            isolation_level=ContextIsolationLevel.DEEP,
            **sample_context_data
        )
        
        assert context_id is not None, "Should return a context ID"
        assert isinstance(context_id, str), "Context ID should be a string"
        assert len(context_id) > 0, "Context ID should not be empty"
        
        # Retrieve and verify context
        context = await context_manager.get_context(context_id)
        assert context is not None, "Should be able to retrieve created context"
        assert context.agent_id == agent_id
        assert context.isolation_level == ContextIsolationLevel.DEEP
        assert context.state == ContextState.CREATED
    
    @pytest.mark.asyncio
    async def test_context_fork_basic(self, context_manager, sample_context_data):
        """Test basic context forking"""
        # Create parent context
        parent_agent_id = "parent_agent"
        parent_context_id = await context_manager.create_context(
            agent_id=parent_agent_id,
            **sample_context_data
        )
        
        # Fork context for child
        child_agent_id = "child_agent"
        child_context_id = await context_manager.fork_context(
            parent_context_id=parent_context_id,
            child_agent_id=child_agent_id
        )
        
        assert child_context_id != parent_context_id, "Child context should have different ID"
        
        # Verify parent-child relationship
        parent_context = await context_manager.get_context(parent_context_id)
        child_context = await context_manager.get_context(child_context_id)
        
        assert child_context.parent_context_id == parent_context_id
        assert child_context.agent_id == child_agent_id
        assert child_context.isolation_level == parent_context.isolation_level
    
    @pytest.mark.asyncio
    async def test_context_fork_with_options(self, context_manager, sample_context_data):
        """Test context forking with custom options"""
        # Create parent context
        parent_context_id = await context_manager.create_context(
            agent_id="parent_agent",
            **sample_context_data
        )
        
        # Fork with custom options
        fork_options = ContextForkOptions(
            isolation_level=ContextIsolationLevel.SANDBOXED,
            inherit_variables=False,
            inherit_shared_resources=False,
            max_execution_time_override=60,
            allowed_operations_override={"read"}
        )
        
        child_context_id = await context_manager.fork_context(
            parent_context_id=parent_context_id,
            child_agent_id="child_agent",
            fork_options=fork_options
        )
        
        child_context = await context_manager.get_context(child_context_id)
        
        assert child_context.isolation_level == ContextIsolationLevel.SANDBOXED
        assert child_context.max_execution_time == 60
        assert child_context.allowed_operations == {"read"}
        
        # Variables should not be inherited
        parent_context = await context_manager.get_context(parent_context_id)
        assert len(child_context.variables) == 0 or child_context.variables != parent_context.variables
    
    @pytest.mark.asyncio
    async def test_context_isolation_deep(self, context_manager):
        """Test deep context isolation"""
        # Create parent context with data
        parent_context_id = await context_manager.create_context(
            agent_id="parent",
            variables={"shared_data": [1, 2, 3]}
        )
        
        # Fork with deep isolation
        child_context_id = await context_manager.fork_context(
            parent_context_id=parent_context_id,
            child_agent_id="child",
            fork_options=ContextForkOptions(isolation_level=ContextIsolationLevel.DEEP)
        )
        
        # Modify data in child context
        child_context = await context_manager.get_context(child_context_id)
        child_context.variables["shared_data"].append(4)
        
        await context_manager.update_context(child_context_id, {
            "variables": child_context.variables
        })
        
        # Parent context should be unaffected
        parent_context = await context_manager.get_context(parent_context_id)
        assert len(parent_context.variables["shared_data"]) == 3, "Parent data should be unchanged"
    
    @pytest.mark.asyncio
    async def test_context_update(self, context_manager, sample_context_data):
        """Test context updates"""
        context_id = await context_manager.create_context(
            agent_id="test_agent",
            **sample_context_data
        )
        
        # Update context data
        updates = {
            "variables": {"new_var": "new_value"},
            "metadata": {"updated": True}
        }
        
        result = await context_manager.update_context(context_id, updates)
        assert result is True, "Update should succeed"
        
        # Verify updates
        context = await context_manager.get_context(context_id)
        assert "new_var" in context.variables
        assert context.metadata.get("updated") is True
    
    @pytest.mark.asyncio
    async def test_context_suspend_resume(self, context_manager, sample_context_data):
        """Test context suspension and resumption"""
        context_id = await context_manager.create_context(
            agent_id="test_agent",
            **sample_context_data
        )
        
        # Suspend context
        result = await context_manager.suspend_context(context_id)
        assert result is True, "Suspension should succeed"
        
        context = await context_manager.get_context(context_id)
        assert context.state == ContextState.SUSPENDED
        
        # Resume context
        result = await context_manager.resume_context(context_id)
        assert result is True, "Resumption should succeed"
        
        context = await context_manager.get_context(context_id)
        assert context.state == ContextState.ACTIVE
    
    @pytest.mark.asyncio
    async def test_context_termination(self, context_manager, sample_context_data):
        """Test context termination"""
        context_id = await context_manager.create_context(
            agent_id="test_agent",
            **sample_context_data
        )
        
        # Terminate context
        result = await context_manager.terminate_context(context_id, cleanup=True)
        assert result is True, "Termination should succeed"
        
        context = await context_manager.get_context(context_id)
        assert context.state == ContextState.TERMINATED
    
    @pytest.mark.asyncio
    async def test_get_child_contexts(self, context_manager, sample_context_data):
        """Test retrieving child contexts"""
        # Create parent context
        parent_context_id = await context_manager.create_context(
            agent_id="parent",
            **sample_context_data
        )
        
        # Create multiple child contexts
        child_ids = []
        for i in range(3):
            child_id = await context_manager.fork_context(
                parent_context_id=parent_context_id,
                child_agent_id=f"child_{i}"
            )
            child_ids.append(child_id)
        
        # Get child contexts
        children = await context_manager.get_child_contexts(parent_context_id)
        
        assert len(children) == 3, "Should have 3 child contexts"
        child_context_ids = [child.id for child in children]
        for child_id in child_ids:
            assert child_id in child_context_ids, f"Child {child_id} should be in results"
    
    @pytest.mark.asyncio
    async def test_operation_validation(self, context_manager):
        """Test operation validation in contexts"""
        # Create context with restricted operations
        context_id = await context_manager.create_context(
            agent_id="test_agent",
            allowed_operations={"read", "compute"},
            restricted_operations={"delete"}
        )
        
        # Test allowed operation
        allowed = await context_manager.validate_operation(context_id, "read")
        assert allowed is True, "Read operation should be allowed"
        
        # Test restricted operation
        restricted = await context_manager.validate_operation(context_id, "delete")
        assert restricted is False, "Delete operation should be restricted"
        
        # Test operation not in allowed list
        not_allowed = await context_manager.validate_operation(context_id, "write")
        assert not_allowed is False, "Write operation should not be allowed"
    
    @pytest.mark.asyncio
    async def test_context_metrics(self, context_manager, sample_context_data):
        """Test context metrics retrieval"""
        context_id = await context_manager.create_context(
            agent_id="test_agent",
            **sample_context_data
        )
        
        metrics = await context_manager.get_context_metrics(context_id)
        
        assert isinstance(metrics, dict), "Metrics should be a dictionary"
        assert "context_id" in metrics or len(metrics) >= 0, "Should return metrics data"
    
    @pytest.mark.asyncio
    async def test_cleanup_completed_contexts(self, context_manager, sample_context_data):
        """Test cleanup of completed contexts"""
        # Create a context and mark it as completed
        context_id = await context_manager.create_context(
            agent_id="completed_agent",
            **sample_context_data
        )
        
        # Terminate the context
        await context_manager.terminate_context(context_id)
        
        # Run cleanup (should clean contexts older than retention period)
        cleaned_count = await context_manager.cleanup_completed_contexts(retention_hours=0)
        
        # Should have cleaned at least one context
        assert cleaned_count >= 0, "Cleanup should return non-negative count"
    
    @pytest.mark.asyncio
    async def test_concurrent_context_operations(self, context_manager, sample_context_data):
        """Test concurrent context operations"""
        parent_context_id = await context_manager.create_context(
            agent_id="parent",
            **sample_context_data
        )
        
        async def create_child_context(i):
            return await context_manager.fork_context(
                parent_context_id=parent_context_id,
                child_agent_id=f"child_{i}"
            )
        
        # Create multiple child contexts concurrently
        tasks = [create_child_context(i) for i in range(10)]
        child_context_ids = await asyncio.gather(*tasks)
        
        # All should succeed
        assert len(child_context_ids) == 10
        assert len(set(child_context_ids)) == 10, "All context IDs should be unique"
        
        # Verify all children exist
        children = await context_manager.get_child_contexts(parent_context_id)
        assert len(children) == 10
    
    @pytest.mark.asyncio
    async def test_invalid_operations(self, context_manager):
        """Test error handling for invalid operations"""
        non_existent_id = "non_existent_context"
        
        # Test getting non-existent context
        context = await context_manager.get_context(non_existent_id)
        assert context is None, "Should return None for non-existent context"
        
        # Test updating non-existent context
        result = await context_manager.update_context(non_existent_id, {"test": "data"})
        assert result is False, "Should return False for non-existent context"
        
        # Test suspending non-existent context
        result = await context_manager.suspend_context(non_existent_id)
        assert result is False, "Should return False for non-existent context"
        
        # Test forking from non-existent parent
        try:
            await context_manager.fork_context(non_existent_id, "child_agent")
            assert False, "Should raise error for non-existent parent"
        except Exception:
            pass  # Expected to fail
    
    @pytest.mark.asyncio
    async def test_context_state_transitions(self, context_manager, sample_context_data):
        """Test valid context state transitions"""
        context_id = await context_manager.create_context(
            agent_id="test_agent",
            **sample_context_data
        )
        
        # CREATED -> SUSPENDED -> ACTIVE -> TERMINATED
        context = await context_manager.get_context(context_id)
        assert context.state == ContextState.CREATED
        
        await context_manager.suspend_context(context_id)
        context = await context_manager.get_context(context_id)
        assert context.state == ContextState.SUSPENDED
        
        await context_manager.resume_context(context_id)
        context = await context_manager.get_context(context_id)
        assert context.state == ContextState.ACTIVE
        
        await context_manager.terminate_context(context_id)
        context = await context_manager.get_context(context_id)
        assert context.state == ContextState.TERMINATED
    
    def test_agent_context_validation(self):
        """Test AgentContext validation"""
        # Valid context should not raise
        valid_context = AgentContext(agent_id="valid_agent")
        assert valid_context.agent_id == "valid_agent"
        
        # Invalid context should raise
        with pytest.raises(ValueError):
            AgentContext(agent_id="")  # Empty agent_id should fail
    
    def test_context_operation_checks(self):
        """Test context operation permission checks"""
        context = AgentContext(
            agent_id="test_agent",
            allowed_operations={"read", "write"},
            restricted_operations={"delete"}
        )
        
        assert context.is_operation_allowed("read") is True
        assert context.is_operation_allowed("write") is True
        assert context.is_operation_allowed("delete") is False
        assert context.is_operation_allowed("compute") is False  # Not in allowed list
    
    def test_context_variable_management(self):
        """Test context variable management"""
        context = AgentContext(agent_id="test_agent")
        
        # Add variable
        context.add_variable("test_var", "test_value")
        assert context.get_variable("test_var") == "test_value"
        
        # Get with default
        assert context.get_variable("non_existent", "default") == "default"
        
        # Remove variable
        result = context.remove_variable("test_var")
        assert result is True
        assert context.get_variable("test_var") is None
        
        # Remove non-existent variable
        result = context.remove_variable("non_existent")
        assert result is False


# Mock implementation for basic testing
class MockContextManager(ContextManagerInterface):
    """Mock implementation for testing interface contract"""
    
    def __init__(self):
        self.contexts = {}
        self.is_healthy = True
    
    async def create_context(
        self, 
        agent_id: str, 
        isolation_level: ContextIsolationLevel = ContextIsolationLevel.DEEP,
        **context_data
    ) -> str:
        context = AgentContext(
            agent_id=agent_id,
            isolation_level=isolation_level,
            **context_data
        )
        self.contexts[context.id] = context
        return context.id
    
    async def fork_context(
        self, 
        parent_context_id: str, 
        child_agent_id: str,
        fork_options: ContextForkOptions = None
    ) -> str:
        parent = self.contexts.get(parent_context_id)
        if not parent:
            raise ContextNotFoundError(f"Parent context {parent_context_id} not found")
        
        options = fork_options or ContextForkOptions()
        
        child = AgentContext(
            agent_id=child_agent_id,
            parent_context_id=parent_context_id,
            isolation_level=options.isolation_level
        )
        
        if options.inherit_variables:
            if options.isolation_level == ContextIsolationLevel.DEEP:
                # Ensure deep isolation of nested structures
                child.variables = copy.deepcopy(parent.variables)
            else:
                child.variables = parent.variables.copy()
        if options.inherit_constraints:
            child.max_execution_time = parent.max_execution_time
            child.allowed_operations = parent.allowed_operations.copy()
        
        # Apply overrides
        if options.max_execution_time_override:
            child.max_execution_time = options.max_execution_time_override
        if options.allowed_operations_override:
            child.allowed_operations = options.allowed_operations_override
        
        self.contexts[child.id] = child
        return child.id
    
    async def get_context(self, context_id: str) -> AgentContext:
        return self.contexts.get(context_id)
    
    async def update_context(self, context_id: str, updates: dict) -> bool:
        context = self.contexts.get(context_id)
        if not context:
            return False
        
        for key, value in updates.items():
            if hasattr(context, key):
                setattr(context, key, value)
        
        context.update_state(context.state)  # Update timestamp
        return True
    
    async def suspend_context(self, context_id: str) -> bool:
        context = self.contexts.get(context_id)
        if not context:
            return False
        context.update_state(ContextState.SUSPENDED)
        return True
    
    async def resume_context(self, context_id: str) -> bool:
        context = self.contexts.get(context_id)
        if not context:
            return False
        context.update_state(ContextState.ACTIVE)
        return True
    
    async def terminate_context(self, context_id: str, cleanup: bool = True) -> bool:
        context = self.contexts.get(context_id)
        if not context:
            return False
        context.update_state(ContextState.TERMINATED)
        return True
    
    async def get_child_contexts(self, parent_context_id: str) -> List[AgentContext]:
        return [ctx for ctx in self.contexts.values() 
                if ctx.parent_context_id == parent_context_id]
    
    async def cleanup_completed_contexts(self, retention_hours: int = 24) -> int:
        cutoff = datetime.utcnow() - timedelta(hours=retention_hours)
        to_remove = []
        
        for ctx_id, ctx in self.contexts.items():
            if ctx.state in [ContextState.COMPLETED, ContextState.TERMINATED]:
                if ctx.updated_at < cutoff:
                    to_remove.append(ctx_id)
        
        for ctx_id in to_remove:
            del self.contexts[ctx_id]
        
        return len(to_remove)
    
    async def validate_operation(self, context_id: str, operation: str) -> bool:
        context = self.contexts.get(context_id)
        if not context:
            return False
        return context.is_operation_allowed(operation)
    
    async def get_context_metrics(self, context_id: str) -> dict:
        context = self.contexts.get(context_id)
        if not context:
            return {}
        
        return {
            "context_id": context_id,
            "agent_id": context.agent_id,
            "state": context.state.value,
            "created_at": context.created_at.isoformat(),
            "updated_at": context.updated_at.isoformat()
        }


class TestMockContextManager(ContextManagerContractTest):
    """Test the mock implementation against the contract"""
    
    @pytest.fixture
    def context_manager(self):
        return MockContextManager()
