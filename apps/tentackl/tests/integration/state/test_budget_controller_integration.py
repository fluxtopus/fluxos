"""Integration tests for the budget controller with real Redis."""

import pytest
import asyncio
from datetime import datetime

from src.interfaces.budget_controller import (
    BudgetConfig,
    ResourceLimit,
    ResourceType,
    BudgetExceededError
)
from src.budget.redis_budget_controller import RedisBudgetController


@pytest.fixture
async def budget_controller():
    """Create a real budget controller connected to Redis."""
    controller = RedisBudgetController(db=13)  # Use test DB
    yield controller
    # Cleanup
    await controller.close()


@pytest.fixture
async def test_budget_config():
    """Create a test budget configuration."""
    return BudgetConfig(
        limits=[
            ResourceLimit(
                resource_type=ResourceType.LLM_CALLS,
                limit=10,
                period="per_test",
                hard_limit=True
            ),
            ResourceLimit(
                resource_type=ResourceType.LLM_COST,
                limit=1.0,
                period="per_test",
                hard_limit=False  # Soft limit for testing
            ),
            ResourceLimit(
                resource_type=ResourceType.GENERATION_DEPTH,
                limit=2,
                hard_limit=True
            )
        ],
        owner="integration_test",
        created_at=datetime.now(),
        metadata={"test": "integration"}
    )


@pytest.mark.asyncio
class TestBudgetControllerIntegration:
    """Integration tests for budget controller."""
    
    async def test_full_budget_lifecycle(self, budget_controller, test_budget_config):
        """Test complete budget lifecycle: create, use, check, reset, delete."""
        budget_id = "test_budget_lifecycle"
        
        # Cleanup any existing budget
        await budget_controller.delete_budget(budget_id)
        
        # Create budget
        await budget_controller.create_budget(budget_id, test_budget_config)
        
        # Verify config
        config = await budget_controller.get_budget_config(budget_id)
        assert config is not None
        assert config.owner == "integration_test"
        assert len(config.limits) == 3
        
        # Check initial usage
        usage = await budget_controller.get_usage(budget_id)
        assert all(u.current == 0 for u in usage)
        
        # Consume some budget
        usage1 = await budget_controller.consume_budget(
            budget_id,
            ResourceType.LLM_CALLS,
            5
        )
        assert usage1.current == 5
        assert usage1.percentage == 50.0
        
        # Check budget availability
        can_use = await budget_controller.check_budget(
            budget_id,
            ResourceType.LLM_CALLS,
            3
        )
        assert can_use is True
        
        can_exceed = await budget_controller.check_budget(
            budget_id,
            ResourceType.LLM_CALLS,
            8  # 5 + 8 = 13 > 10
        )
        assert can_exceed is False
        
        # Consume more budget
        usage2 = await budget_controller.consume_budget(
            budget_id,
            ResourceType.LLM_CALLS,
            3
        )
        assert usage2.current == 8
        
        # Try to exceed hard limit
        with pytest.raises(BudgetExceededError) as exc_info:
            await budget_controller.consume_budget(
                budget_id,
                ResourceType.LLM_CALLS,
                5  # 8 + 5 = 13 > 10
            )
        assert exc_info.value.resource_type == ResourceType.LLM_CALLS
        
        # Test soft limit (should not raise, just warn)
        usage_soft = await budget_controller.consume_budget(
            budget_id,
            ResourceType.LLM_COST,
            1.5  # Exceeds soft limit of 1.0
        )
        assert usage_soft.current == 1.5
        assert usage_soft.exceeded is True
        
        # Reset specific resource
        await budget_controller.reset_budget(budget_id, ResourceType.LLM_CALLS)
        usage_after_reset = await budget_controller.get_usage(
            budget_id,
            ResourceType.LLM_CALLS
        )
        assert usage_after_reset[0].current == 0
        
        # Cost should still be 1.5
        cost_usage = await budget_controller.get_usage(
            budget_id,
            ResourceType.LLM_COST
        )
        assert cost_usage[0].current == 1.5
        
        # Reset all
        await budget_controller.reset_budget(budget_id)
        all_usage = await budget_controller.get_usage(budget_id)
        assert all(u.current == 0 for u in all_usage)
        
        # Delete budget
        await budget_controller.delete_budget(budget_id)
        config_after_delete = await budget_controller.get_budget_config(budget_id)
        assert config_after_delete is None
    
    async def test_parent_child_budgets(self, budget_controller):
        """Test parent-child budget relationships."""
        parent_id = "test_parent_budget"
        child1_id = "test_child_budget_1"
        child2_id = "test_child_budget_2"
        
        # Cleanup
        for budget_id in [parent_id, child1_id, child2_id]:
            await budget_controller.delete_budget(budget_id)
        
        # Create parent budget
        parent_config = BudgetConfig(
            limits=[
                ResourceLimit(
                    resource_type=ResourceType.LLM_CALLS,
                    limit=100,
                    hard_limit=True
                ),
                ResourceLimit(
                    resource_type=ResourceType.LLM_COST,
                    limit=10.0,
                    hard_limit=True
                )
            ],
            owner="parent_test",
            created_at=datetime.now(),
            metadata={"level": "parent"}
        )
        await budget_controller.create_budget(parent_id, parent_config)
        
        # Create child budgets with lower limits
        child1_config = BudgetConfig(
            limits=[
                ResourceLimit(
                    resource_type=ResourceType.LLM_CALLS,
                    limit=30,  # 30% of parent
                    hard_limit=True
                )
            ],
            owner="child1_test",
            created_at=datetime.now(),
            metadata={"level": "child", "index": 1}
        )
        await budget_controller.create_child_budget(parent_id, child1_id, child1_config)
        
        child2_config = BudgetConfig(
            limits=[
                ResourceLimit(
                    resource_type=ResourceType.LLM_CALLS,
                    limit=50,  # 50% of parent
                    hard_limit=True
                )
            ],
            owner="child2_test",
            created_at=datetime.now(),
            metadata={"level": "child", "index": 2}
        )
        await budget_controller.create_child_budget(parent_id, child2_id, child2_config)
        
        # Get hierarchy
        hierarchy = await budget_controller.get_budget_hierarchy(parent_id)
        assert hierarchy["id"] == parent_id
        assert hierarchy["parent"] is None
        assert len(hierarchy["children"]) == 2
        
        # Verify children
        child_ids = [child["id"] for child in hierarchy["children"]]
        assert child1_id in child_ids
        assert child2_id in child_ids
        
        # Try to create child with excessive limits
        excessive_config = BudgetConfig(
            limits=[
                ResourceLimit(
                    resource_type=ResourceType.LLM_COST,
                    limit=20.0,  # More than parent's 10.0
                    hard_limit=True
                )
            ],
            owner="excessive_test",
            created_at=datetime.now(),
            metadata={"level": "child"}
        )
        
        with pytest.raises(ValueError) as exc_info:
            await budget_controller.create_child_budget(
                parent_id,
                "excessive_child",
                excessive_config
            )
        assert "exceeds parent limit" in str(exc_info.value)
        
        # Cleanup
        for budget_id in [parent_id, child1_id, child2_id]:
            await budget_controller.delete_budget(budget_id)
    
    async def test_concurrent_budget_operations(self, budget_controller):
        """Test concurrent budget operations for thread safety."""
        budget_id = "test_concurrent_budget"
        
        # Cleanup
        await budget_controller.delete_budget(budget_id)
        
        # Create budget with low limit for testing
        config = BudgetConfig(
            limits=[
                ResourceLimit(
                    resource_type=ResourceType.LLM_CALLS,
                    limit=20,
                    hard_limit=True
                )
            ],
            owner="concurrent_test",
            created_at=datetime.now(),
            metadata={"test": "concurrent"}
        )
        await budget_controller.create_budget(budget_id, config)
        
        # Concurrent consume operations
        async def consume_budget(amount: float, delay: float = 0):
            if delay:
                await asyncio.sleep(delay)
            try:
                return await budget_controller.consume_budget(
                    budget_id,
                    ResourceType.LLM_CALLS,
                    amount
                )
            except BudgetExceededError:
                return None
        
        # Launch multiple concurrent operations
        tasks = [
            consume_budget(5),
            consume_budget(5, 0.01),
            consume_budget(5, 0.02),
            consume_budget(5, 0.03),
            consume_budget(5, 0.04),  # This should fail (total would be 25)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successful operations
        successful = [r for r in results if r and not isinstance(r, Exception)]
        failed = [r for r in results if r is None or isinstance(r, Exception)]
        
        # Exactly 4 should succeed (4 * 5 = 20)
        assert len(successful) == 4
        assert len(failed) == 1
        
        # Final usage should be exactly at limit
        final_usage = await budget_controller.get_usage(budget_id, ResourceType.LLM_CALLS)
        assert final_usage[0].current == 20
        
        # Cleanup
        await budget_controller.delete_budget(budget_id)
    
    async def test_health_check(self, budget_controller):
        """Test health check functionality."""
        is_healthy = await budget_controller.health_check()
        assert is_healthy is True