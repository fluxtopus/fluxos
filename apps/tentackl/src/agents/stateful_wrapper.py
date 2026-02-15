"""
# REVIEW:
# - Wrapper directly creates execution nodes and updates tree; overlaps with orchestration responsibilities.
# - Saves state snapshots on every execution; no batching or throttling.

Stateful wrapper for existing Tentackl agents

This module provides a concrete implementation that wraps existing agents
with state management capabilities.
"""

from typing import Any, Dict, Optional
from datetime import datetime
import structlog

from src.agents.base import Agent, AgentConfig, AgentStatus
from src.agents.stateful_agent import StatefulAgent, StatefulAgentConfig
from src.infrastructure.state.redis_state_store import RedisStateStore
from src.context.redis_context_manager import RedisContextManager
from src.infrastructure.execution_runtime.redis_execution_tree import RedisExecutionTree
from src.core.execution_tree import ExecutionNode, ExecutionStatus, NodeType, ExecutionPriority
from src.interfaces.state_store import StateSnapshot, StateType


logger = structlog.get_logger()


class StatefulAgentWrapper(StatefulAgent):
    """Concrete wrapper that adds state management to existing agents"""
    
    def __init__(
        self,
        wrapped_agent: Agent,
        state_store: RedisStateStore,
        context_manager: RedisContextManager,
        execution_tree: RedisExecutionTree,
        tree_id: Optional[str] = None,
        parent_node_id: Optional[str] = None
    ):
        """
        Initialize stateful wrapper
        
        Args:
            wrapped_agent: The existing agent to wrap
            state_store: Redis state store instance
            context_manager: Redis context manager instance
            execution_tree: Redis execution tree instance
            tree_id: Optional execution tree ID
            parent_node_id: Optional parent node ID in the tree
        """
        # Store reference to wrapped agent first (needed for property access)
        self.wrapped_agent = wrapped_agent
        self.tree_id = tree_id
        self.parent_node_id = parent_node_id
        
        # Create stateful config from wrapped agent
        stateful_config = StatefulAgentConfig(
            name=wrapped_agent.config.name,
            agent_type=wrapped_agent.config.agent_type,
            state_store=state_store,
            context_manager=context_manager,
            execution_tree=execution_tree,
            timeout=wrapped_agent.config.timeout
        )
        
        # Initialize parent class
        super().__init__(config=stateful_config)
        
        # Override ID to match wrapped agent
        self.id = wrapped_agent.id
        
        logger.info(
            "Created stateful wrapper",
            agent_id=self.id,
            agent_name=stateful_config.name,
            agent_type=stateful_config.agent_type
        )
    
    async def _execute_stateful(self, task: Dict[str, Any]) -> Any:
        """
        Execute the wrapped agent's task with state management
        
        This method delegates actual execution to the wrapped agent
        while adding state tracking and tree updates.
        """
        # Extract context and tree info from task
        context_id = task.get("context_id")
        tree_id = task.get("tree_id", self.tree_id)
        
        # Create execution node if tree is available
        execution_node = None
        if tree_id and self.execution_tree:
            execution_node = ExecutionNode(
                name=self.config.name,
                node_type=NodeType.SUB_AGENT,
                status=ExecutionStatus.PENDING,
                priority=ExecutionPriority.NORMAL,
                parent_id=self.parent_node_id,
                context_id=context_id,
                task_data={
                    "agent_id": self.id,
                    "agent_type": self.config.agent_type,
                    "task": task
                }
            )
            
            success = await self.execution_tree.add_node(
                tree_id=tree_id,
                node=execution_node,
                parent_id=self.parent_node_id
            )
            
            if success:
                logger.debug(
                    "Added execution node",
                    node_id=execution_node.id,
                    tree_id=tree_id
                )
                
                # Update node status to running
                await self.execution_tree.update_node_status(
                    tree_id=tree_id,
                    node_id=execution_node.id,
                    status=ExecutionStatus.RUNNING
                )
        
        try:
            # Update wrapped agent's status
            self.wrapped_agent.status = AgentStatus.RUNNING
            
            # Execute the wrapped agent's task
            result = await self.wrapped_agent.execute(task)
            
            # Update wrapped agent's status
            self.wrapped_agent.status = AgentStatus.COMPLETED
            
            # Save execution state
            state_snapshot = StateSnapshot(
                agent_id=self.id,
                state_type=StateType.AGENT_STATE,
                data={
                    "status": "completed",
                    "task": task,
                    "result": result,
                    "completed_at": datetime.utcnow().isoformat()
                },
                metadata={
                    "agent_type": self.config.agent_type,
                    "execution_time": datetime.utcnow().isoformat()
                }
            )
            
            await self.state_store.save_state(state_snapshot)
            
            # Update execution node to completed
            if execution_node and tree_id:
                await self.execution_tree.update_node_status(
                    tree_id=tree_id,
                    node_id=execution_node.id,
                    status=ExecutionStatus.COMPLETED,
                    result_data={"result": result}
                )
            
            logger.info(
                "Stateful execution completed",
                agent_id=self.id,
                agent_name=self.config.name
            )
            
            return result
            
        except Exception as e:
            # Update wrapped agent's status
            self.wrapped_agent.status = AgentStatus.FAILED
            
            # Save error state
            error_snapshot = StateSnapshot(
                agent_id=self.id,
                state_type=StateType.AGENT_STATE,
                data={
                    "status": "failed",
                    "task": task,
                    "error": str(e),
                    "failed_at": datetime.utcnow().isoformat()
                },
                metadata={
                    "agent_type": self.config.agent_type,
                    "error_type": type(e).__name__
                }
            )
            
            await self.state_store.save_state(error_snapshot)
            
            # Update execution node to failed
            if execution_node and tree_id:
                await self.execution_tree.update_node_status(
                    tree_id=tree_id,
                    node_id=execution_node.id,
                    status=ExecutionStatus.FAILED,
                    error_data={"error": str(e), "error_type": type(e).__name__}
                )
            
            logger.error(
                "Stateful execution failed",
                agent_id=self.id,
                agent_name=self.config.name,
                error=str(e)
            )
            
            raise
    
    @property
    def status(self) -> AgentStatus:
        """Get status from wrapped agent"""
        return self.wrapped_agent.status
    
    @status.setter
    def status(self, value: AgentStatus):
        """Set status on wrapped agent"""
        self.wrapped_agent.status = value
    
    def get_state(self) -> Dict[str, Any]:
        """Get state from wrapped agent with additional metadata"""
        base_state = self.wrapped_agent.get_state()
        base_state.update({
            "stateful": True,
            "tree_id": self.tree_id,
            "parent_node_id": self.parent_node_id
        })
        return base_state
