"""
Capability Protocols

Defines the interface contracts for each composable capability.
These protocols use Python's Protocol (structural subtyping) so implementations
don't need to explicitly inherit from them.

Each capability is independent and can be composed as needed.
"""

from typing import Protocol, Optional, Dict, Any, List, Type, runtime_checkable
from dataclasses import dataclass
from datetime import datetime


# ============================================================================
# State Persistence Capability
# ============================================================================

@dataclass
class StateSnapshot:
    """A snapshot of agent state at a point in time."""
    agent_id: str
    data: Dict[str, Any]
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None


@runtime_checkable
class StatePersistenceCapability(Protocol):
    """
    Capability for persisting and retrieving agent state.

    Implementations should handle:
    - Saving state snapshots to persistent storage
    - Loading the latest state for an agent
    - Optional auto-save functionality
    """

    async def save_state(self, agent_id: str, state: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Save current agent state.

        Args:
            agent_id: Unique identifier for the agent
            state: State data to persist
            metadata: Optional metadata about the state

        Returns:
            True if save was successful
        """
        ...

    async def load_state(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Load the latest state for an agent.

        Args:
            agent_id: Unique identifier for the agent

        Returns:
            State data if found, None otherwise
        """
        ...

    async def start_auto_save(self, agent_id: str, interval_seconds: int, get_state_fn) -> None:
        """
        Start automatic state saving at regular intervals.

        Args:
            agent_id: Agent to auto-save for
            interval_seconds: Seconds between saves
            get_state_fn: Async function that returns current state
        """
        ...

    async def stop_auto_save(self) -> None:
        """Stop the auto-save loop if running."""
        ...


# ============================================================================
# Context Isolation Capability
# ============================================================================

@dataclass
class IsolatedContext:
    """Represents an isolated execution context."""
    context_id: str
    agent_id: str
    isolation_level: str  # NONE, SHALLOW, DEEP, SANDBOXED
    parent_context_id: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None


@runtime_checkable
class ContextIsolationCapability(Protocol):
    """
    Capability for managing isolated execution contexts.

    Provides context isolation for agents, especially useful when
    creating sub-agents that should have their own isolated scope.
    """

    async def create_context(
        self,
        agent_id: str,
        isolation_level: str = "DEEP",
        variables: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new isolated context.

        Args:
            agent_id: Agent this context belongs to
            isolation_level: NONE, SHALLOW, DEEP, or SANDBOXED
            variables: Initial context variables

        Returns:
            Context ID
        """
        ...

    async def fork_context(
        self,
        parent_context_id: str,
        child_agent_id: str,
        isolation_level: Optional[str] = None
    ) -> str:
        """
        Fork a context for a child agent.

        Args:
            parent_context_id: Context to fork from
            child_agent_id: Agent that will use the forked context
            isolation_level: Override isolation level (inherits from parent if None)

        Returns:
            New context ID for the child
        """
        ...

    async def get_context(self, context_id: str) -> Optional[IsolatedContext]:
        """Get context by ID."""
        ...

    async def validate_operation(self, context_id: str, operation: str) -> bool:
        """Check if an operation is allowed in this context."""
        ...

    async def terminate_context(self, context_id: str, cleanup: bool = True) -> bool:
        """
        Terminate a context.

        Args:
            context_id: Context to terminate
            cleanup: Whether to clean up associated resources

        Returns:
            True if termination was successful
        """
        ...


# ============================================================================
# Execution Tracking Capability
# ============================================================================

@dataclass
class ExecutionNode:
    """A node in the execution tree."""
    node_id: str
    agent_id: str
    name: str
    node_type: str  # AGENT, SUB_AGENT, TASK, etc.
    status: str  # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
    parent_id: Optional[str] = None
    context_id: Optional[str] = None
    task_data: Optional[Dict[str, Any]] = None
    result_data: Optional[Dict[str, Any]] = None
    error_data: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@runtime_checkable
class ExecutionTrackingCapability(Protocol):
    """
    Capability for tracking execution in a tree structure.

    Useful for visualizing agent execution, debugging, and
    understanding the flow of multi-agent workflows.
    """

    async def create_tree(self, tree_id: Optional[str] = None) -> str:
        """
        Create a new execution tree.

        Args:
            tree_id: Optional specific ID, generates one if not provided

        Returns:
            Tree ID
        """
        ...

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
        """
        Add a node to the execution tree.

        Returns:
            Node ID
        """
        ...

    async def update_status(
        self,
        tree_id: str,
        node_id: str,
        status: str,
        result_data: Optional[Dict[str, Any]] = None,
        error_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update the status of an execution node."""
        ...

    async def get_node(self, tree_id: str, node_id: str) -> Optional[ExecutionNode]:
        """Get a specific node."""
        ...

    async def get_tree(self, tree_id: str) -> List[ExecutionNode]:
        """Get all nodes in a tree."""
        ...


# ============================================================================
# Conversation Tracking Capability
# ============================================================================

@dataclass
class ConversationInfo:
    """Information about a tracked conversation."""
    conversation_id: str
    workflow_id: str
    agent_id: str
    status: str  # ACTIVE, COMPLETED, FAILED
    started_at: datetime
    ended_at: Optional[datetime] = None
    parent_conversation_id: Optional[str] = None
    message_count: int = 0


@runtime_checkable
class ConversationTrackingCapability(Protocol):
    """
    Capability for tracking agent conversations and LLM interactions.

    Captures:
    - LLM prompts and responses
    - State changes
    - Errors
    - Inter-agent messages
    """

    async def initialize(self) -> None:
        """Initialize the conversation tracking system (e.g., connect to database)."""
        ...

    async def shutdown(self) -> None:
        """Shutdown and cleanup resources."""
        ...

    async def start_conversation(
        self,
        workflow_id: str,
        agent_id: str,
        trigger_type: str = "API_CALL",
        trigger_source: str = "direct",
        trigger_details: Optional[Dict[str, Any]] = None,
        parent_conversation_id: Optional[str] = None
    ) -> str:
        """
        Start tracking a new conversation.

        Returns:
            Conversation ID
        """
        ...

    async def end_conversation(self, conversation_id: str, status: str) -> bool:
        """
        End a conversation with the given status.

        Args:
            conversation_id: Conversation to end
            status: Final status (COMPLETED, FAILED, etc.)
        """
        ...

    async def intercept_llm_call(
        self,
        agent_id: str,
        prompt: str,
        model: str,
        **kwargs
    ) -> Any:
        """
        Intercept an outgoing LLM call for logging.

        Returns:
            Interception result with message_id for correlating response
        """
        ...

    async def intercept_llm_response(
        self,
        agent_id: str,
        response: Any,
        latency_ms: int,
        parent_message_id: Optional[str] = None
    ) -> None:
        """Log an LLM response."""
        ...

    async def intercept_state_update(
        self,
        agent_id: str,
        old_state: Dict[str, Any],
        new_state: Dict[str, Any],
        changed_fields: List[str]
    ) -> None:
        """Log a state change."""
        ...

    async def intercept_error(
        self,
        agent_id: str,
        error: Exception,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log an error."""
        ...

    def wrap_llm_client(self, client: Any, agent_id: str, model: str) -> Any:
        """
        Wrap an LLM client to automatically intercept calls.

        Args:
            client: The LLM client to wrap
            agent_id: Agent making the calls
            model: Default model being used

        Returns:
            Wrapped client that intercepts all calls
        """
        ...

    def set_context(self, conversation_id: str, agent_id: str) -> None:
        """Set the current conversation context for this thread/task."""
        ...

    def get_current_conversation_id(self) -> Optional[str]:
        """Get the current conversation ID from context."""
        ...


# ============================================================================
# Subagent Manager Capability
# ============================================================================

@dataclass
class SubagentInfo:
    """Information about a managed sub-agent."""
    agent_id: str
    agent_type: str
    context_id: Optional[str] = None
    node_id: Optional[str] = None
    status: str = "IDLE"
    created_at: Optional[datetime] = None


@runtime_checkable
class SubagentManagerCapability(Protocol):
    """
    Capability for creating and managing sub-agents.

    Handles:
    - Creating sub-agents with isolated contexts
    - Executing tasks on sub-agents
    - Parallel execution across multiple sub-agents
    - Cleanup and shutdown
    """

    async def create_subagent(
        self,
        agent_class: Type,
        config: Any,
        parent_context_id: Optional[str] = None,
        tree_id: Optional[str] = None,
        parent_node_id: Optional[str] = None
    ) -> str:
        """
        Create a new sub-agent.

        Args:
            agent_class: The class of agent to create
            config: Configuration for the agent
            parent_context_id: Parent context to fork from
            tree_id: Execution tree to add node to
            parent_node_id: Parent node in execution tree

        Returns:
            Sub-agent ID
        """
        ...

    async def execute_subagent(self, agent_id: str, task: Dict[str, Any]) -> Any:
        """Execute a task on a specific sub-agent."""
        ...

    async def execute_parallel(
        self,
        tasks: List[Dict[str, Any]],
        agent_class: Type,
        base_config: Any
    ) -> List[Any]:
        """
        Execute multiple tasks in parallel using sub-agents.

        Creates a sub-agent for each task and executes them concurrently.

        Returns:
            List of results (may include exceptions for failed tasks)
        """
        ...

    async def get_subagent(self, agent_id: str) -> Optional[SubagentInfo]:
        """Get information about a sub-agent."""
        ...

    async def list_subagents(self) -> List[SubagentInfo]:
        """List all managed sub-agents."""
        ...

    async def shutdown_subagent(self, agent_id: str) -> bool:
        """Shutdown a specific sub-agent."""
        ...

    async def shutdown_all(self) -> None:
        """Shutdown all managed sub-agents."""
        ...
