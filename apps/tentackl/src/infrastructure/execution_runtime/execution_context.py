"""
ExecutionContext - Immutable context for step execution.

Built from trusted sources (plan document loaded from DB), not from
agent-controllable inputs. Provides identity and scoping information
to plugin handlers without relying on step inputs for security-sensitive
fields like organization_id.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ExecutionContext:
    """
    Immutable execution context built from trusted DB sources.

    This context is constructed from the plan document (loaded from PostgreSQL)
    and passed to all plugin handlers. Handlers must use these fields for
    identity and scoping — never from step inputs.

    Attributes:
        organization_id: Required. The organization this execution belongs to.
        task_id: The task/plan ID.
        step_id: The current step ID.
        user_id: The user who initiated the task.
        agent_id: The agent executing the step (if applicable).
        workflow_id: Legacy alias for task_id (kept for backwards-compatible payloads).
        metadata: Additional metadata from the plan.
    """

    organization_id: str
    task_id: Optional[str] = None
    step_id: Optional[str] = None
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    workflow_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.organization_id:
            raise ValueError("ExecutionContext requires a non-empty organization_id")

    @staticmethod
    def from_plan(plan, step_id: str) -> "ExecutionContext":
        """
        Build an ExecutionContext from a Task (plan document) loaded from DB.

        Args:
            plan: Task object with organization_id, id, user_id, metadata
            step_id: The step being executed

        Returns:
            ExecutionContext with all fields populated from the plan
        """
        return ExecutionContext(
            organization_id=plan.organization_id,
            task_id=str(plan.id) if plan.id else None,
            step_id=step_id,
            user_id=str(plan.user_id) if plan.user_id else None,
            workflow_id=str(plan.id) if plan.id else None,
            metadata=plan.metadata or {},
        )
