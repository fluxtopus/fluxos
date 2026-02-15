"""
Agent Capabilities Container

Provides a dataclass for composing agent capabilities.
Agents can opt into specific capabilities instead of inheriting everything.
"""

from dataclasses import dataclass, field
from typing import Optional, List

from src.capabilities.protocols import (
    StatePersistenceCapability,
    ContextIsolationCapability,
    ExecutionTrackingCapability,
    ConversationTrackingCapability,
    SubagentManagerCapability,
)


@dataclass
class AgentCapabilities:
    """
    Container for composable agent capabilities.

    Instead of inheriting from StatefulAgent (which bundles all capabilities),
    agents can now specify exactly which capabilities they need.

    Example:
        # Agent that only needs conversation tracking
        caps = AgentCapabilities(
            conversations=ConversationTrackingImpl(db)
        )

        # Full-featured orchestrator
        caps = AgentCapabilities(
            state=StatePersistenceImpl(redis),
            context=ContextIsolationImpl(ctx_manager),
            tracking=ExecutionTrackingImpl(tree),
            conversations=ConversationTrackingImpl(db),
            subagents=SubagentManagerImpl()
        )
    """

    # State persistence (save/load agent state to Redis)
    state: Optional[StatePersistenceCapability] = None

    # Context isolation (isolated execution scopes for sub-agents)
    context: Optional[ContextIsolationCapability] = None

    # Execution tracking (tree structure for visualization/debugging)
    tracking: Optional[ExecutionTrackingCapability] = None

    # Conversation tracking (LLM call logging, state changes, errors)
    conversations: Optional[ConversationTrackingCapability] = None

    # Sub-agent management (create/execute/manage child agents)
    subagents: Optional[SubagentManagerCapability] = None

    def has_state_persistence(self) -> bool:
        """Check if state persistence is enabled."""
        return self.state is not None

    def has_context_isolation(self) -> bool:
        """Check if context isolation is enabled."""
        return self.context is not None

    def has_execution_tracking(self) -> bool:
        """Check if execution tracking is enabled."""
        return self.tracking is not None

    def has_conversation_tracking(self) -> bool:
        """Check if conversation tracking is enabled."""
        return self.conversations is not None

    def has_subagent_management(self) -> bool:
        """Check if sub-agent management is enabled."""
        return self.subagents is not None

    def enabled_capabilities(self) -> List[str]:
        """Get list of enabled capability names."""
        enabled = []
        if self.state:
            enabled.append("state_persistence")
        if self.context:
            enabled.append("context_isolation")
        if self.tracking:
            enabled.append("execution_tracking")
        if self.conversations:
            enabled.append("conversation_tracking")
        if self.subagents:
            enabled.append("subagent_management")
        return enabled

    def is_empty(self) -> bool:
        """Check if no capabilities are configured."""
        return not any([
            self.state,
            self.context,
            self.tracking,
            self.conversations,
            self.subagents
        ])

    def __repr__(self) -> str:
        enabled = self.enabled_capabilities()
        if not enabled:
            return "AgentCapabilities(none)"
        return f"AgentCapabilities({', '.join(enabled)})"
