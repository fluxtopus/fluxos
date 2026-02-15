"""Unit tests for the budget controller."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.interfaces.budget_controller import (
    BudgetConfig,
    ResourceLimit,
    ResourceType,
    ResourceUsage,
    BudgetExceededError
)
from src.budget.redis_budget_controller import RedisBudgetController


@pytest.fixture
async def mock_redis_client():
    """Create a mock Redis client."""
    client = AsyncMock()
    client.hset = AsyncMock()
    client.hgetall = AsyncMock()
    client.get = AsyncMock()
    client.set = AsyncMock()
    client.eval = AsyncMock()
    client.sadd = AsyncMock()
    client.smembers = AsyncMock()
    client.delete = AsyncMock()
    client.ping = AsyncMock()
    client.scan_iter = AsyncMock()
    return client


@pytest.fixture
async def budget_controller(mock_redis_client):
    """Create a budget controller with mocked Redis."""
    controller = RedisBudgetController()
    controller._client = mock_redis_client
    return controller


@pytest.fixture
def sample_budget_config():
    """Create a sample budget configuration."""
    return BudgetConfig(
        limits=[
            ResourceLimit(
                resource_type=ResourceType.LLM_CALLS,
                limit=100,
                period="per_workflow",
                hard_limit=True
            ),
            ResourceLimit(
                resource_type=ResourceType.LLM_COST,
                limit=10.0,
                period="per_workflow",
                hard_limit=True
            ),
            ResourceLimit(
                resource_type=ResourceType.GENERATION_DEPTH,
                limit=3,
                hard_limit=True
            )
        ],
        owner="test_user",
        created_at=datetime.now(),
        metadata={"project": "test"}
    )


class TestRedisBudgetController:
    """Test the Redis budget controller implementation."""
    
    async def test_create_budget(self, budget_controller, mock_redis_client, sample_budget_config):
        """Test creating a new budget."""
        await budget_controller.create_budget("test_budget", sample_budget_config)
        
        # Verify config was stored
        assert mock_redis_client.hset.called
        call_args = mock_redis_client.hset.call_args
        assert "budget:test_budget:config" in str(call_args)
        
        # Verify usage counters were initialized
        assert mock_redis_client.set.call_count == 3  # One for each limit
    
    async def test_check_budget_within_limit(self, budget_controller, mock_redis_client, sample_budget_config):
        """Test checking budget when within limits."""
        # Setup mocks
        mock_redis_client.get.return_value = "50"  # Current usage
        mock_redis_client.hgetall.return_value = {
            "owner": "test_user",
            "created_at": datetime.now().isoformat(),
            "metadata": "{}",
            "limits": '[{"resource_type": "llm_calls", "limit": 100, "period": "per_workflow", "hard_limit": true}]'
        }
        
        result = await budget_controller.check_budget(
            "test_budget",
            ResourceType.LLM_CALLS,
            10
        )
        
        assert result is True  # 50 + 10 = 60, which is < 100
    
    async def test_check_budget_exceeds_limit(self, budget_controller, mock_redis_client, sample_budget_config):
        """Test checking budget when it would exceed limits."""
        # Setup mocks
        mock_redis_client.get.return_value = "95"  # Current usage
        mock_redis_client.hgetall.return_value = {
            "owner": "test_user",
            "created_at": datetime.now().isoformat(),
            "metadata": "{}",
            "limits": '[{"resource_type": "llm_calls", "limit": 100, "period": "per_workflow", "hard_limit": true}]'
        }
        
        result = await budget_controller.check_budget(
            "test_budget",
            ResourceType.LLM_CALLS,
            10
        )
        
        assert result is False  # 95 + 10 = 105, which is > 100
    
    async def test_consume_budget_success(self, budget_controller, mock_redis_client, sample_budget_config):
        """Test consuming budget successfully."""
        # Setup mocks
        mock_redis_client.hgetall.return_value = {
            "owner": "test_user",
            "created_at": datetime.now().isoformat(),
            "metadata": "{}",
            "limits": '[{"resource_type": "llm_calls", "limit": 100, "period": "per_workflow", "hard_limit": true}]'
        }
        mock_redis_client.eval.return_value = [60, 1]  # New value, incremented
        
        usage = await budget_controller.consume_budget(
            "test_budget",
            ResourceType.LLM_CALLS,
            10
        )
        
        assert usage.current == 60
        assert usage.limit == 100
        assert usage.percentage == 60.0
        assert not usage.exceeded
    
    async def test_consume_budget_hard_limit_exceeded(self, budget_controller, mock_redis_client, sample_budget_config):
        """Test consuming budget when hard limit would be exceeded."""
        # Setup mocks
        mock_redis_client.hgetall.return_value = {
            "owner": "test_user",
            "created_at": datetime.now().isoformat(),
            "metadata": "{}",
            "limits": '[{"resource_type": "llm_calls", "limit": 100, "period": "per_workflow", "hard_limit": true}]'
        }
        mock_redis_client.eval.return_value = [95, 0]  # Current value, not incremented
        
        with pytest.raises(BudgetExceededError) as exc_info:
            await budget_controller.consume_budget(
                "test_budget",
                ResourceType.LLM_CALLS,
                10
            )
        
        assert exc_info.value.resource_type == ResourceType.LLM_CALLS
        assert exc_info.value.limit == 100
    
    async def test_consume_budget_soft_limit(self, budget_controller, mock_redis_client):
        """Test consuming budget with soft limit (warning only)."""
        # Setup mocks
        mock_redis_client.hgetall.return_value = {
            "owner": "test_user",
            "created_at": datetime.now().isoformat(),
            "metadata": "{}",
            "limits": '[{"resource_type": "llm_calls", "limit": 100, "period": "per_workflow", "hard_limit": false}]'
        }
        mock_redis_client.eval.return_value = [105, 1]  # Over limit but allowed
        
        usage = await budget_controller.consume_budget(
            "test_budget",
            ResourceType.LLM_CALLS,
            10
        )
        
        assert usage.current == 105
        assert usage.exceeded is True
        # Should not raise an exception
    
    async def test_get_usage(self, budget_controller, mock_redis_client, sample_budget_config):
        """Test getting current usage."""
        # Setup mocks
        mock_redis_client.hgetall.return_value = {
            "owner": "test_user",
            "created_at": datetime.now().isoformat(),
            "metadata": "{}",
            "limits": '[{"resource_type": "llm_calls", "limit": 100, "period": "per_workflow", "hard_limit": true}]'
        }
        mock_redis_client.get.return_value = "75"
        
        usage_list = await budget_controller.get_usage("test_budget")
        
        assert len(usage_list) == 1
        assert usage_list[0].resource_type == ResourceType.LLM_CALLS
        assert usage_list[0].current == 75
        assert usage_list[0].percentage == 75.0
    
    async def test_reset_budget(self, budget_controller, mock_redis_client, sample_budget_config):
        """Test resetting budget counters."""
        # Setup mocks
        mock_redis_client.hgetall.return_value = {
            "owner": "test_user",
            "created_at": datetime.now().isoformat(),
            "metadata": "{}",
            "limits": '[{"resource_type": "llm_calls", "limit": 100, "period": "per_workflow", "hard_limit": true}]'
        }
        
        await budget_controller.reset_budget("test_budget")
        
        # Verify counter was reset
        mock_redis_client.set.assert_called_with(
            "budget:test_budget:usage:llm_calls",
            0
        )
    
    async def test_create_child_budget(self, budget_controller, mock_redis_client, sample_budget_config):
        """Test creating a child budget."""
        # Setup parent budget
        mock_redis_client.hgetall.return_value = {
            "owner": "test_user",
            "created_at": datetime.now().isoformat(),
            "metadata": "{}",
            "limits": '[{"resource_type": "llm_calls", "limit": 100, "period": "per_workflow", "hard_limit": true}]'
        }
        
        # Create child with lower limits
        child_config = BudgetConfig(
            limits=[
                ResourceLimit(
                    resource_type=ResourceType.LLM_CALLS,
                    limit=50,  # Less than parent's 100
                    period="per_agent",
                    hard_limit=True
                )
            ],
            owner="test_user",
            created_at=datetime.now(),
            metadata={"agent": "child"}
        )
        
        await budget_controller.create_child_budget(
            "parent_budget",
            "child_budget",
            child_config
        )
        
        # Verify parent-child relationship was stored
        mock_redis_client.sadd.assert_called_with(
            "budget:parent_budget:children",
            "child_budget"
        )
        mock_redis_client.set.assert_any_call(
            "budget:child_budget:parent",
            "parent_budget"
        )
    
    async def test_create_child_budget_exceeds_parent(self, budget_controller, mock_redis_client):
        """Test creating a child budget that exceeds parent limits."""
        # Setup parent budget
        mock_redis_client.hgetall.return_value = {
            "owner": "test_user",
            "created_at": datetime.now().isoformat(),
            "metadata": "{}",
            "limits": '[{"resource_type": "llm_calls", "limit": 100, "period": "per_workflow", "hard_limit": true}]'
        }
        
        # Try to create child with higher limits
        child_config = BudgetConfig(
            limits=[
                ResourceLimit(
                    resource_type=ResourceType.LLM_CALLS,
                    limit=150,  # More than parent's 100
                    period="per_agent",
                    hard_limit=True
                )
            ],
            owner="test_user",
            created_at=datetime.now(),
            metadata={"agent": "child"}
        )
        
        with pytest.raises(ValueError) as exc_info:
            await budget_controller.create_child_budget(
                "parent_budget",
                "child_budget",
                child_config
            )
        
        assert "exceeds parent limit" in str(exc_info.value)
    
    async def test_health_check(self, budget_controller, mock_redis_client):
        """Test health check."""
        mock_redis_client.ping.return_value = True
        
        result = await budget_controller.health_check()
        assert result is True
        mock_redis_client.ping.assert_called_once()