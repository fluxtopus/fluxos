"""
# REVIEW:
# - StatefulAgent owns DB connections for conversation tracking; mixing persistence with agent logic increases coupling.
# - Auto-save uses background task but no explicit error reporting if it fails.

StatefulAgent implementation with state persistence and context isolation

This module provides a StatefulAgent base class that extends the existing Agent
with state management, context isolation, and sub-agent generation capabilities.
"""

import asyncio
from typing import Any, Dict, List, Optional, Set, Callable, Type
from datetime import datetime, timedelta
from abc import abstractmethod
import structlog

from src.agents.base import Agent, AgentConfig, AgentStatus
from src.interfaces.state_store import StateStoreInterface, StateSnapshot, StateType, StateQuery
from src.interfaces.context_manager import (
    ContextManagerInterface, AgentContext, ContextForkOptions, 
    ContextIsolationLevel, ContextState
)
from src.core.execution_tree import ExecutionTreeInterface, ExecutionNode, NodeType, ExecutionStatus
from src.infrastructure.state.redis_state_store import RedisStateStore
from src.database.conversation_store import ConversationStore, ConversationTrigger
from src.database.conversation_interceptor import ConversationInterceptor, current_conversation_id, current_agent_id
from src.database.models import ConversationStatus, TriggerType
from src.interfaces.database import Database


logger = structlog.get_logger()


from dataclasses import dataclass

@dataclass
class StatefulAgentConfig:
    """Extended configuration for StatefulAgent"""
    
    name: str
    agent_type: str
    state_store: Optional[StateStoreInterface] = None
    context_manager: Optional[ContextManagerInterface] = None
    execution_tree: Optional[ExecutionTreeInterface] = None
    state_persistence_enabled: bool = True
    context_isolation_level: ContextIsolationLevel = ContextIsolationLevel.DEEP
    auto_save_interval: Optional[int] = None  # seconds
    max_sub_agents: int = 10
    timeout: Optional[int] = None
    enable_conversation_tracking: bool = True  # Enable by default for all agents
    
    def to_agent_config(self) -> AgentConfig:
        """Convert to base AgentConfig for compatibility"""
        return AgentConfig(
            name=self.name,
            agent_type=self.agent_type,
            timeout=self.timeout or 300
        )


class StatefulAgent(Agent):
    """
    Base class for stateful agents with context isolation and state persistence
    Follows SRP - handles agent execution with state management
    """
    
    def __init__(self, config: StatefulAgentConfig):
        super().__init__(config.to_agent_config())
        
        self.config = config
        self.state_store = config.state_store
        self.context_manager = config.context_manager
        self.execution_tree = config.execution_tree
        
        # State management
        self.current_state: Dict[str, Any] = {}
        self.context_id: Optional[str] = None
        self.execution_node_id: Optional[str] = None
        self.tree_id: Optional[str] = None
        
        # Sub-agent management
        self.sub_agents: Dict[str, 'StatefulAgent'] = {}
        self.sub_agent_contexts: Dict[str, str] = {}  # sub_agent_id -> context_id
        
        # Auto-save task
        self._auto_save_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # State change callbacks
        self._state_change_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        
        # Conversation tracking
        self.enable_conversation_tracking = config.enable_conversation_tracking
        self.conversation_store: Optional[ConversationStore] = None
        self.conversation_interceptor: Optional[ConversationInterceptor] = None
        self.current_conversation_id: Optional[str] = None
        self._db: Optional[Database] = None
    
    async def initialize(
        self, 
        context_id: Optional[str] = None,
        tree_id: Optional[str] = None,
        execution_node_id: Optional[str] = None
    ) -> None:
        """
        Initialize the stateful agent with context and execution tracking
        
        Args:
            context_id: Optional existing context ID
            tree_id: Optional execution tree ID
            execution_node_id: Optional execution node ID
        """
        try:
            # Initialize context if not provided
            if not context_id and self.context_manager:
                self.context_id = await self.context_manager.create_context(
                    agent_id=self.id,
                    isolation_level=self.config.context_isolation_level
                )
            else:
                self.context_id = context_id
            
            # Set execution tracking
            self.tree_id = tree_id
            self.execution_node_id = execution_node_id
            
            # Load existing state if available
            if self.state_store and self.config.state_persistence_enabled:
                await self._load_state()
            
            # Start auto-save if configured
            if self.config.auto_save_interval:
                self._auto_save_task = asyncio.create_task(self._auto_save_loop())
            
            # Initialize conversation tracking
            if self.enable_conversation_tracking:
                try:
                    self._db = Database()
                    await self._db.connect()
                    
                    self.conversation_store = ConversationStore(self._db)
                    self.conversation_interceptor = ConversationInterceptor(self.conversation_store)
                    
                    logger.info(f"Conversation tracking enabled for agent {self.id}")
                except Exception as e:
                    logger.error(f"Failed to initialize conversation tracking: {e}")
                    # Don't fail agent initialization if conversation tracking fails
                    self.enable_conversation_tracking = False
            
            logger.info(
                "StatefulAgent initialized",
                agent_id=self.id,
                context_id=self.context_id,
                tree_id=self.tree_id,
                node_id=self.execution_node_id,
                conversation_tracking=self.enable_conversation_tracking
            )
            
        except Exception as e:
            logger.error("Failed to initialize StatefulAgent", agent_id=self.id, error=str(e))
            raise
    
    async def shutdown(self) -> None:
        """Gracefully shutdown the agent and save state"""
        try:
            # Signal shutdown
            self._shutdown_event.set()
            
            # Cancel auto-save task
            if self._auto_save_task and not self._auto_save_task.done():
                self._auto_save_task.cancel()
                try:
                    await self._auto_save_task
                except asyncio.CancelledError:
                    pass
            
            # Shutdown sub-agents
            await self._shutdown_sub_agents()
            
            # Save final state
            if self.state_store and self.config.state_persistence_enabled:
                await self._save_state()
            
            # Terminate context
            if self.context_manager and self.context_id:
                await self.context_manager.terminate_context(self.context_id, cleanup=True)
            
            # Close database connection for conversation tracking
            if self._db:
                try:
                    await self._db.disconnect()
                except Exception as e:
                    logger.error(f"Error disconnecting database: {e}")
            
            logger.info("StatefulAgent shutdown complete", agent_id=self.id)
            
        except Exception as e:
            logger.error("Error during StatefulAgent shutdown", agent_id=self.id, error=str(e))
    
    async def execute(self, task: Dict[str, Any]) -> Any:
        """
        Execute task with state management, context isolation, and conversation tracking
        
        Args:
            task: Task data to execute
            
        Returns:
            Task execution result
        """
        # Start conversation if enabled and not already started
        if self.enable_conversation_tracking and not self.current_conversation_id:
            await self._start_conversation(task)
        
        try:
            # Update execution node status
            if self.execution_tree and self.tree_id and self.execution_node_id:
                await self.execution_tree.update_node_status(
                    self.tree_id, self.execution_node_id, ExecutionStatus.RUNNING
                )
            
            # Validate operation in context
            if self.context_manager and self.context_id:
                operation = task.get("operation", "execute")
                allowed = await self.context_manager.validate_operation(self.context_id, operation)
                if not allowed:
                    raise PermissionError(f"Operation '{operation}' not allowed in current context")
            
            # Update state before execution
            await self.update_state({
                "current_task": task,
                "status": "executing",
                "started_at": datetime.utcnow().isoformat()
            })
            
            # Execute the specific agent logic
            result = await self._execute_stateful(task)
            
            # Update state after execution
            await self.update_state({
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "last_result": result
            })
            
            # Update execution node status
            if self.execution_tree and self.tree_id and self.execution_node_id:
                await self.execution_tree.update_node_status(
                    self.tree_id, self.execution_node_id, ExecutionStatus.COMPLETED,
                    result_data={"result": result}
                )
            
            # End conversation on success
            if self.current_conversation_id:
                await self._end_conversation(ConversationStatus.COMPLETED)
            
            return result
            
        except Exception as e:
            # Log error to conversation
            if self.conversation_interceptor:
                await self.conversation_interceptor.intercept_error(
                    self.agent_id,
                    e,
                    {"task": task}
                )
            
            # Update state on error
            await self.update_state({
                "status": "failed",
                "failed_at": datetime.utcnow().isoformat(),
                "error": str(e)
            })
            
            # Update execution node status
            if self.execution_tree and self.tree_id and self.execution_node_id:
                await self.execution_tree.update_node_status(
                    self.tree_id, self.execution_node_id, ExecutionStatus.FAILED,
                    error_data={"error": str(e), "type": type(e).__name__}
                )
            
            # End conversation as failed
            if self.current_conversation_id:
                await self._end_conversation(ConversationStatus.FAILED)
            
            logger.error("StatefulAgent execution failed", agent_id=self.id, error=str(e))
            raise
    
    @abstractmethod
    async def _execute_stateful(self, task: Dict[str, Any]) -> Any:
        """
        Abstract method for specific agent execution logic
        Subclasses must implement this method
        
        Args:
            task: Task data to execute
            
        Returns:
            Task execution result
        """
        pass
    
    async def update_state(self, state_updates: Dict[str, Any]) -> None:
        """
        Update agent state and persist if enabled
        
        Args:
            state_updates: Dictionary of state updates to apply
        """
        try:
            # Keep old state for comparison
            old_state = self.current_state.copy()
            
            # Update local state
            self.current_state.update(state_updates)
            self.current_state["updated_at"] = datetime.utcnow().isoformat()
            
            # Log state change to conversation if enabled
            if self.enable_conversation_tracking and self.conversation_interceptor:
                # Find changed fields
                changed_fields = []
                for key in set(old_state.keys()) | set(self.current_state.keys()):
                    if old_state.get(key) != self.current_state.get(key):
                        changed_fields.append(key)
                
                if changed_fields:
                    await self.conversation_interceptor.intercept_state_update(
                        self.agent_id,
                        old_state,
                        self.current_state,
                        changed_fields
                    )
            
            # Notify callbacks
            for callback in self._state_change_callbacks:
                try:
                    callback(self.current_state.copy())
                except Exception as e:
                    logger.warning("State change callback failed", error=str(e))
            
            # Persist state if enabled
            if self.state_store and self.config.state_persistence_enabled:
                await self._save_state()
            
        except Exception as e:
            logger.error("Failed to update state", agent_id=self.id, error=str(e))
    
    async def get_state(self) -> Dict[str, Any]:
        """Get current agent state"""
        return self.current_state.copy()
    
    async def add_state_change_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Add callback for state changes"""
        self._state_change_callbacks.append(callback)
    
    async def create_sub_agent(
        self, 
        sub_agent_class: Type['StatefulAgent'],
        sub_agent_config: StatefulAgentConfig,
        fork_options: Optional[ContextForkOptions] = None
    ) -> str:
        """
        Create a sub-agent with isolated context
        
        Args:
            sub_agent_class: Class of sub-agent to create
            sub_agent_config: Configuration for sub-agent
            fork_options: Optional context fork options
            
        Returns:
            Sub-agent ID
        """
        try:
            if len(self.sub_agents) >= self.config.max_sub_agents:
                raise RuntimeError(f"Maximum sub-agents ({self.config.max_sub_agents}) reached")
            
            # Fork context for sub-agent
            sub_context_id = None
            if self.context_manager and self.context_id:
                sub_context_id = await self.context_manager.fork_context(
                    parent_context_id=self.context_id,
                    child_agent_id=sub_agent_config.name,
                    fork_options=fork_options
                )
            
            # Create execution node for sub-agent
            sub_node_id = None
            if self.execution_tree and self.tree_id:
                sub_node = ExecutionNode(
                    name=sub_agent_config.name,
                    node_type=NodeType.SUB_AGENT,
                    agent_id=sub_agent_config.name,
                    context_id=sub_context_id,
                    parent_id=self.execution_node_id
                )
                
                await self.execution_tree.add_node(
                    self.tree_id, sub_node, parent_id=self.execution_node_id
                )
                sub_node_id = sub_node.id
            
            # Create sub-agent instance
            sub_agent = sub_agent_class(sub_agent_config)
            await sub_agent.initialize(
                context_id=sub_context_id,
                tree_id=self.tree_id,
                execution_node_id=sub_node_id
            )
            
            # Track sub-agent
            self.sub_agents[sub_agent.id] = sub_agent
            if sub_context_id:
                self.sub_agent_contexts[sub_agent.id] = sub_context_id
            
            logger.info(
                "Created sub-agent",
                parent_id=self.id,
                sub_agent_id=sub_agent.id,
                sub_context_id=sub_context_id
            )
            
            return sub_agent.id
            
        except Exception as e:
            logger.error("Failed to create sub-agent", parent_id=self.id, error=str(e))
            raise
    
    async def execute_sub_agent(self, sub_agent_id: str, task: Dict[str, Any]) -> Any:
        """
        Execute a task on a specific sub-agent
        
        Args:
            sub_agent_id: ID of sub-agent to execute
            task: Task to execute
            
        Returns:
            Sub-agent execution result
        """
        if sub_agent_id not in self.sub_agents:
            raise ValueError(f"Sub-agent {sub_agent_id} not found")
        
        sub_agent = self.sub_agents[sub_agent_id]
        return await sub_agent.execute(task)
    
    async def execute_sub_agents_parallel(
        self, 
        tasks: List[Dict[str, Any]],
        sub_agent_class: Type['StatefulAgent'],
        base_config: StatefulAgentConfig
    ) -> List[Any]:
        """
        Execute multiple tasks in parallel using sub-agents
        
        Args:
            tasks: List of tasks to execute
            sub_agent_class: Class of sub-agents to create
            base_config: Base configuration for sub-agents
            
        Returns:
            List of execution results
        """
        try:
            # Create sub-agents for each task
            sub_agent_ids = []
            for i, task in enumerate(tasks):
                config = StatefulAgentConfig(
                    name=f"{base_config.name}_{i}",
                    agent_type=base_config.agent_type,
                    state_store=base_config.state_store,
                    context_manager=base_config.context_manager,
                    execution_tree=base_config.execution_tree,
                    context_isolation_level=base_config.context_isolation_level
                )
                
                sub_agent_id = await self.create_sub_agent(sub_agent_class, config)
                sub_agent_ids.append(sub_agent_id)
            
            # Execute tasks in parallel
            execution_tasks = [
                self.execute_sub_agent(sub_agent_id, task)
                for sub_agent_id, task in zip(sub_agent_ids, tasks)
            ]
            
            results = await asyncio.gather(*execution_tasks, return_exceptions=True)
            
            logger.info(
                "Parallel sub-agent execution complete",
                parent_id=self.id,
                sub_agents_count=len(sub_agent_ids),
                success_count=sum(1 for r in results if not isinstance(r, Exception))
            )
            
            return results
            
        except Exception as e:
            logger.error("Parallel sub-agent execution failed", parent_id=self.id, error=str(e))
            raise
    
    async def _load_state(self) -> None:
        """Load agent state from state store"""
        if not self.state_store:
            return
        
        try:
            latest_state = await self.state_store.get_latest_state(
                self.id, StateType.AGENT_STATE
            )
            
            if latest_state:
                self.current_state = latest_state.data.copy()
                logger.debug("Loaded agent state", agent_id=self.id)
            
        except Exception as e:
            logger.warning("Failed to load agent state", agent_id=self.id, error=str(e))
    
    async def _save_state(self) -> None:
        """Save agent state to state store"""
        if not self.state_store:
            return
        
        try:
            snapshot = StateSnapshot(
                agent_id=self.id,
                state_type=StateType.AGENT_STATE,
                data=self.current_state.copy(),
                metadata={
                    "context_id": self.context_id,
                    "tree_id": self.tree_id,
                    "node_id": self.execution_node_id,
                    "sub_agents_count": len(self.sub_agents)
                }
            )
            
            await self.state_store.save_state(snapshot)
            
        except Exception as e:
            logger.error("Failed to save agent state", agent_id=self.id, error=str(e))
    
    async def _auto_save_loop(self) -> None:
        """Auto-save state at regular intervals"""
        try:
            while not self._shutdown_event.is_set():
                await asyncio.sleep(self.config.auto_save_interval)
                
                if not self._shutdown_event.is_set():
                    await self._save_state()
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Auto-save loop error", agent_id=self.id, error=str(e))
    
    async def _shutdown_sub_agents(self) -> None:
        """Shutdown all sub-agents"""
        try:
            shutdown_tasks = [
                sub_agent.shutdown() 
                for sub_agent in self.sub_agents.values()
            ]
            
            if shutdown_tasks:
                await asyncio.gather(*shutdown_tasks, return_exceptions=True)
            
            self.sub_agents.clear()
            self.sub_agent_contexts.clear()
            
        except Exception as e:
            logger.error("Error shutting down sub-agents", parent_id=self.id, error=str(e))
    
    async def _start_conversation(self, task: Dict[str, Any]) -> Optional[str]:
        """Start a new conversation for this agent's execution."""
        if not self.conversation_store:
            return None
        
        try:
            # Determine trigger type based on task
            trigger_type = TriggerType.API_CALL
            if task.get("trigger_type"):
                trigger_type = TriggerType[task["trigger_type"].upper()]
            elif task.get("parent_agent_id"):
                trigger_type = TriggerType.INTER_AGENT
            
            trigger = ConversationTrigger(
                type=trigger_type,
                source=task.get("trigger_source", "direct_execution"),
                details=task
            )
            
            conversation = await self.conversation_store.start_conversation(
                workflow_id=task.get("workflow_id", "unknown"),
                root_agent_id=self.agent_id,
                trigger=trigger,
                parent_conversation_id=task.get("parent_conversation_id")
            )
            
            self.current_conversation_id = str(conversation.id)
            
            # Set context for interceptor
            self.conversation_interceptor.set_context(
                self.current_conversation_id,
                self.agent_id
            )
            
            # Also set the context vars directly
            current_conversation_id.set(self.current_conversation_id)
            current_agent_id.set(self.agent_id)
            
            logger.info(
                "Started conversation",
                conversation_id=self.current_conversation_id,
                agent_id=self.agent_id
            )
            
            return self.current_conversation_id
            
        except Exception as e:
            logger.error(f"Failed to start conversation: {e}")
            return None
    
    async def _end_conversation(self, status: ConversationStatus) -> bool:
        """End the current conversation."""
        if not self.current_conversation_id or not self.conversation_store:
            return False
        
        try:
            success = await self.conversation_store.end_conversation(
                self.current_conversation_id,
                status
            )
            
            if success:
                logger.info(
                    "Ended conversation",
                    conversation_id=self.current_conversation_id,
                    status=status.value
                )
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to end conversation: {e}")
            return False


class WorkerStatefulAgent(StatefulAgent):
    """Example implementation of StatefulAgent for worker tasks"""
    
    async def _execute_stateful(self, task: Dict[str, Any]) -> Any:
        """Execute worker-specific logic with state management"""
        operation = task.get("operation", "unknown")
        
        if operation == "compute":
            # Simulate computation work
            data = task.get("data", [])
            duration = task.get("duration", 1)
            
            await self.update_state({
                "operation": operation,
                "data_size": len(data),
                "progress": 0
            })
            
            # Simulate work with progress updates
            for i in range(10):
                await asyncio.sleep(duration / 10)
                await self.update_state({"progress": (i + 1) * 10})
            
            result = sum(data) if data else 42
            return {"operation": operation, "result": result}
            
        elif operation == "validate":
            # Simulate validation work
            threshold = task.get("threshold", 0.5)
            value = task.get("value", 0.8)
            
            await self.update_state({
                "operation": operation,
                "threshold": threshold,
                "value": value
            })
            
            await asyncio.sleep(0.5)  # Simulate work
            
            is_valid = value >= threshold
            return {"operation": operation, "valid": is_valid, "value": value}
        
        else:
            raise ValueError(f"Unknown operation: {operation}")


class CoordinatorStatefulAgent(StatefulAgent):
    """Example coordinator agent that manages sub-agents"""
    
    async def _execute_stateful(self, task: Dict[str, Any]) -> Any:
        """Execute coordinator logic with sub-agent management"""
        operation = task.get("operation", "unknown")
        
        if operation == "parallel_compute":
            # Distribute work across sub-agents
            tasks = task.get("tasks", [])
            
            await self.update_state({
                "operation": operation,
                "total_tasks": len(tasks),
                "status": "distributing"
            })
            
            # Execute tasks in parallel using sub-agents
            base_config = StatefulAgentConfig(
                name="worker",
                agent_type="worker_stateful",
                state_store=self.state_store,
                context_manager=self.context_manager,
                execution_tree=self.execution_tree
            )
            
            results = await self.execute_sub_agents_parallel(
                tasks, WorkerStatefulAgent, base_config
            )
            
            # Aggregate results
            successful_results = [r for r in results if not isinstance(r, Exception)]
            failed_count = len(results) - len(successful_results)
            
            await self.update_state({
                "status": "completed",
                "successful_tasks": len(successful_results),
                "failed_tasks": failed_count
            })
            
            return {
                "operation": operation,
                "results": successful_results,
                "success_count": len(successful_results),
                "failure_count": failed_count
            }
        
        else:
            raise ValueError(f"Unknown operation: {operation}")
