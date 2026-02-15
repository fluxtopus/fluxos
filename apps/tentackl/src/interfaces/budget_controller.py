"""Budget Controller Interface for managing resource limits and costs."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Any, List
from datetime import datetime


class ResourceType(Enum):
    """Types of resources that can be budgeted."""
    LLM_CALLS = "llm_calls"
    LLM_TOKENS = "llm_tokens"
    LLM_COST = "llm_cost"
    MEMORY = "memory_mb"
    CPU_TIME = "cpu_seconds"
    CONCURRENT_AGENTS = "concurrent_agents"
    GENERATION_DEPTH = "generation_depth"
    AGENT_HIERARCHY = "agent_hierarchy"
    TEMPLATE_COMPOSITION = "template_composition"


@dataclass
class ResourceLimit:
    """Resource limit configuration."""
    resource_type: ResourceType
    limit: float
    period: Optional[str] = None  # e.g., "per_agent", "per_workflow", "per_hour"
    hard_limit: bool = True  # If True, exceeding stops execution; if False, just warns


@dataclass
class ResourceUsage:
    """Current resource usage."""
    resource_type: ResourceType
    current: float
    limit: float
    percentage: float
    exceeded: bool


@dataclass
class BudgetConfig:
    """Budget configuration for a workflow or agent."""
    limits: List[ResourceLimit]
    owner: str
    created_at: datetime
    metadata: Dict[str, Any]


class BudgetExceededError(Exception):
    """Raised when a budget limit is exceeded."""
    def __init__(self, resource_type: ResourceType, current: float, limit: float):
        self.resource_type = resource_type
        self.current = current
        self.limit = limit
        super().__init__(
            f"Budget exceeded for {resource_type.value}: {current} > {limit}"
        )


class BudgetControllerInterface(ABC):
    """Interface for budget control and resource management."""
    
    @abstractmethod
    async def create_budget(
        self,
        budget_id: str,
        config: BudgetConfig
    ) -> None:
        """Create a new budget configuration."""
        pass
    
    @abstractmethod
    async def check_budget(
        self,
        budget_id: str,
        resource_type: ResourceType,
        amount: float
    ) -> bool:
        """Check if a resource usage would exceed budget. Returns True if within budget."""
        pass
    
    @abstractmethod
    async def consume_budget(
        self,
        budget_id: str,
        resource_type: ResourceType,
        amount: float
    ) -> ResourceUsage:
        """Consume budget for a resource. Raises BudgetExceededError if limit exceeded."""
        pass
    
    @abstractmethod
    async def get_usage(
        self,
        budget_id: str,
        resource_type: Optional[ResourceType] = None
    ) -> List[ResourceUsage]:
        """Get current usage for a budget."""
        pass
    
    @abstractmethod
    async def reset_budget(
        self,
        budget_id: str,
        resource_type: Optional[ResourceType] = None
    ) -> None:
        """Reset usage counters for a budget."""
        pass
    
    @abstractmethod
    async def set_limit(
        self,
        budget_id: str,
        limit: ResourceLimit
    ) -> None:
        """Update a resource limit for a budget."""
        pass
    
    @abstractmethod
    async def get_budget_config(
        self,
        budget_id: str
    ) -> Optional[BudgetConfig]:
        """Get budget configuration."""
        pass
    
    @abstractmethod
    async def delete_budget(
        self,
        budget_id: str
    ) -> None:
        """Delete a budget configuration."""
        pass
    
    @abstractmethod
    async def create_child_budget(
        self,
        parent_budget_id: str,
        child_budget_id: str,
        config: BudgetConfig
    ) -> None:
        """Create a child budget that inherits and is constrained by parent limits."""
        pass
    
    @abstractmethod
    async def get_budget_hierarchy(
        self,
        budget_id: str
    ) -> Dict[str, Any]:
        """Get the budget hierarchy tree."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the budget controller is healthy."""
        pass