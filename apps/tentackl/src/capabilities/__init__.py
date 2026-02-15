"""
Composable Agent Capabilities

This module provides composable capabilities for agents, replacing the monolithic
StatefulAgent inheritance pattern with a composition-based approach.

Usage:
    from src.capabilities import AgentCapabilities
    from src.capabilities.conversation_tracking import ConversationTrackingImpl
    from src.runtime import AgentRuntime

    # Create runtime with specific capabilities
    runtime = AgentRuntime(
        capabilities=AgentCapabilities(
            conversations=ConversationTrackingImpl(db)
        )
    )

    # Use with any agent
    agent = LLMAgent(config, runtime=runtime)
"""

# Protocols (interfaces)
from src.capabilities.protocols import (
    StatePersistenceCapability,
    ContextIsolationCapability,
    ExecutionTrackingCapability,
    ConversationTrackingCapability,
    SubagentManagerCapability,
    StateSnapshot,
    IsolatedContext,
    ExecutionNode,
    ConversationInfo,
    SubagentInfo,
)

# Container
from src.capabilities.container import AgentCapabilities

# Implementations
from src.capabilities.state_persistence import StatePersistenceImpl
from src.capabilities.context_isolation import ContextIsolationImpl
from src.capabilities.execution_tracking import ExecutionTrackingImpl
from src.capabilities.conversation_tracking import ConversationTrackingImpl
from src.capabilities.subagent_manager import SubagentManagerImpl

__all__ = [
    # Protocols
    "StatePersistenceCapability",
    "ContextIsolationCapability",
    "ExecutionTrackingCapability",
    "ConversationTrackingCapability",
    "SubagentManagerCapability",
    # Data classes
    "StateSnapshot",
    "IsolatedContext",
    "ExecutionNode",
    "ConversationInfo",
    "SubagentInfo",
    # Container
    "AgentCapabilities",
    # Implementations
    "StatePersistenceImpl",
    "ContextIsolationImpl",
    "ExecutionTrackingImpl",
    "ConversationTrackingImpl",
    "SubagentManagerImpl",
]
