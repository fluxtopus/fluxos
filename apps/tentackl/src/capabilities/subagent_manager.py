"""
Subagent Manager Capability Implementation

Provides sub-agent creation and management for agents.
Extracted from StatefulAgent.create_sub_agent, execute_sub_agent, etc.

Enhanced with:
- Resource limits via semaphore for concurrent execution
- Cancellation support for running tasks
- Failure policy support for parallel execution groups
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional, Type, Set
from datetime import datetime
from enum import Enum
import uuid
import structlog

from src.capabilities.protocols import SubagentManagerCapability, SubagentInfo
from src.capabilities.context_isolation import ContextIsolationImpl
from src.capabilities.execution_tracking import ExecutionTrackingImpl

logger = structlog.get_logger(__name__)


class ParallelFailurePolicy(Enum):
    """Policy for handling failures in parallel execution."""
    ALL_OR_NOTHING = "all_or_nothing"  # Fail entire group if any fails
    BEST_EFFORT = "best_effort"        # Continue with partial results
    FAIL_FAST = "fail_fast"            # Cancel remaining on first failure


class SubagentManagerImpl:
    """
    Implementation of sub-agent management capability.

    Handles creation, execution, and lifecycle management of sub-agents.
    Optionally integrates with context isolation and execution tracking.

    Features:
    - Concurrent execution limits via semaphore
    - Task cancellation support
    - Failure policy handling for parallel groups
    """

    def __init__(
        self,
        context_isolation: Optional[ContextIsolationImpl] = None,
        execution_tracking: Optional[ExecutionTrackingImpl] = None,
        max_subagents: int = 10,
        max_concurrent: int = 5
    ):
        """
        Initialize sub-agent manager.

        Args:
            context_isolation: Optional context isolation capability
            execution_tracking: Optional execution tracking capability
            max_subagents: Maximum number of sub-agents allowed
            max_concurrent: Maximum concurrent executions (resource limit)
        """
        self._context = context_isolation
        self._tracking = execution_tracking
        self._max_subagents = max_subagents
        self._max_concurrent = max_concurrent

        # Semaphore for resource limiting
        self._execution_semaphore = asyncio.Semaphore(max_concurrent)

        # Track sub-agents
        self._subagents: Dict[str, Any] = {}  # agent_id -> agent instance
        self._subagent_contexts: Dict[str, str] = {}  # agent_id -> context_id
        self._subagent_info: Dict[str, SubagentInfo] = {}  # agent_id -> info

        # Track running tasks for cancellation
        self._running_tasks: Dict[str, asyncio.Task] = {}  # task_id -> Task
        self._cancelled: bool = False

    async def create_subagent(
        self,
        agent_class: Type,
        config: Any,
        parent_context_id: Optional[str] = None,
        tree_id: Optional[str] = None,
        parent_node_id: Optional[str] = None
    ) -> str:
        """Create a new sub-agent."""
        if len(self._subagents) >= self._max_subagents:
            raise RuntimeError(f"Maximum sub-agents ({self._max_subagents}) reached")

        try:
            # Generate agent ID
            agent_id = f"{config.name}_{uuid.uuid4().hex[:8]}"

            # Fork context if context isolation is available and parent context exists
            context_id = None
            if self._context and parent_context_id:
                context_id = await self._context.fork_context(
                    parent_context_id=parent_context_id,
                    child_agent_id=agent_id
                )

            # Add execution node if tracking is available
            node_id = None
            if self._tracking and tree_id:
                node_id = await self._tracking.add_node(
                    tree_id=tree_id,
                    agent_id=agent_id,
                    name=config.name,
                    node_type="SUB_AGENT",
                    parent_id=parent_node_id,
                    context_id=context_id
                )

            # Create the agent instance
            agent = agent_class(config)

            # Initialize the agent
            if hasattr(agent, 'initialize'):
                await agent.initialize(
                    context_id=context_id,
                    tree_id=tree_id,
                    execution_node_id=node_id
                )

            # Track the sub-agent
            self._subagents[agent_id] = agent
            if context_id:
                self._subagent_contexts[agent_id] = context_id

            self._subagent_info[agent_id] = SubagentInfo(
                agent_id=agent_id,
                agent_type=config.agent_type if hasattr(config, 'agent_type') else "unknown",
                context_id=context_id,
                node_id=node_id,
                status="IDLE",
                created_at=datetime.utcnow()
            )

            logger.info(
                "Sub-agent created",
                agent_id=agent_id,
                agent_type=type(agent).__name__,
                context_id=context_id,
                node_id=node_id
            )

            return agent_id

        except Exception as e:
            logger.error("Failed to create sub-agent", error=str(e))
            raise

    async def execute_subagent(self, agent_id: str, task: Dict[str, Any]) -> Any:
        """Execute a task on a specific sub-agent with resource limiting."""
        if self._cancelled:
            raise asyncio.CancelledError("Subagent manager has been cancelled")

        if agent_id not in self._subagents:
            raise ValueError(f"Sub-agent {agent_id} not found")

        agent = self._subagents[agent_id]

        # Update status
        if agent_id in self._subagent_info:
            self._subagent_info[agent_id].status = "RUNNING"

        # Use semaphore to limit concurrent executions
        async with self._execution_semaphore:
            try:
                result = await agent.execute(task)

                # Update status on success
                if agent_id in self._subagent_info:
                    self._subagent_info[agent_id].status = "COMPLETED"

                return result

            except asyncio.CancelledError:
                if agent_id in self._subagent_info:
                    self._subagent_info[agent_id].status = "CANCELLED"
                raise

            except Exception as e:
                # Update status on failure
                if agent_id in self._subagent_info:
                    self._subagent_info[agent_id].status = "FAILED"
                raise

    async def execute_parallel(
        self,
        tasks: List[Dict[str, Any]],
        agent_class: Type,
        base_config: Any
    ) -> List[Any]:
        """Execute multiple tasks in parallel using sub-agents."""
        return await self.execute_parallel_with_policy(
            tasks=tasks,
            agent_class=agent_class,
            base_config=base_config,
            failure_policy=ParallelFailurePolicy.BEST_EFFORT
        )

    async def execute_parallel_with_policy(
        self,
        tasks: List[Dict[str, Any]],
        agent_class: Type,
        base_config: Any,
        failure_policy: ParallelFailurePolicy = ParallelFailurePolicy.ALL_OR_NOTHING,
        timeout_seconds: Optional[float] = None
    ) -> List[Any]:
        """
        Execute multiple tasks in parallel with failure policy handling.

        Args:
            tasks: List of task dictionaries to execute
            agent_class: Agent class to instantiate for each task
            base_config: Base configuration for agents
            failure_policy: How to handle failures in the group
            timeout_seconds: Optional timeout for the entire group

        Returns:
            List of results (may include exceptions based on policy)

        Raises:
            Exception: If policy is ALL_OR_NOTHING and any task fails
            asyncio.CancelledError: If cancelled or FAIL_FAST triggered
        """
        if not tasks:
            return []

        execution_id = uuid.uuid4().hex[:8]

        try:
            # Create a sub-agent for each task
            agent_ids = []
            for i, task in enumerate(tasks):
                config = type(base_config)(
                    name=f"{base_config.name}_{i}",
                    agent_type=base_config.agent_type if hasattr(base_config, 'agent_type') else "worker"
                )
                agent_id = await self.create_subagent(agent_class, config)
                agent_ids.append(agent_id)

            # Create tasks for execution
            async_tasks: List[asyncio.Task] = []
            for agent_id, task in zip(agent_ids, tasks):
                t = asyncio.create_task(
                    self.execute_subagent(agent_id, task),
                    name=f"subagent_{agent_id}"
                )
                async_tasks.append(t)
                self._running_tasks[f"{execution_id}_{agent_id}"] = t

            results: List[Any] = [None] * len(tasks)
            first_exception: Optional[Exception] = None

            if failure_policy == ParallelFailurePolicy.FAIL_FAST:
                # Cancel all on first failure
                done, pending = await asyncio.wait(
                    async_tasks,
                    timeout=timeout_seconds,
                    return_when=asyncio.FIRST_EXCEPTION
                )

                # Check for exceptions in done tasks
                for i, task in enumerate(async_tasks):
                    if task in done:
                        try:
                            results[i] = task.result()
                        except Exception as e:
                            results[i] = e
                            if first_exception is None:
                                first_exception = e

                # Cancel pending tasks if we got an exception
                if first_exception:
                    for task in pending:
                        task.cancel()
                    # Wait for cancellation to complete
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)
                    raise first_exception

                # Otherwise wait for remaining
                if pending:
                    done2, _ = await asyncio.wait(pending)
                    for i, task in enumerate(async_tasks):
                        if task in done2:
                            try:
                                results[i] = task.result()
                            except Exception as e:
                                results[i] = e

            else:
                # BEST_EFFORT or ALL_OR_NOTHING: gather all results
                try:
                    if timeout_seconds:
                        gather_results = await asyncio.wait_for(
                            asyncio.gather(*async_tasks, return_exceptions=True),
                            timeout=timeout_seconds
                        )
                    else:
                        gather_results = await asyncio.gather(*async_tasks, return_exceptions=True)

                    results = list(gather_results)

                except asyncio.TimeoutError:
                    # Cancel remaining tasks
                    for task in async_tasks:
                        if not task.done():
                            task.cancel()
                    raise

            # Check policy
            failures = [r for r in results if isinstance(r, Exception)]

            if failure_policy == ParallelFailurePolicy.ALL_OR_NOTHING and failures:
                raise failures[0]

            logger.info(
                "Parallel execution complete",
                execution_id=execution_id,
                total_tasks=len(tasks),
                success_count=len(tasks) - len(failures),
                failure_count=len(failures),
                policy=failure_policy.value
            )

            return results

        except Exception as e:
            logger.error("Parallel execution failed", execution_id=execution_id, error=str(e))
            raise

        finally:
            # Clean up running task references
            if 'agent_ids' in locals():
                for agent_id in agent_ids:
                    self._running_tasks.pop(f"{execution_id}_{agent_id}", None)

    async def cancel_all_running(self) -> int:
        """
        Cancel all running tasks.

        Returns:
            Number of tasks cancelled
        """
        self._cancelled = True
        cancelled_count = 0

        for task_id, task in list(self._running_tasks.items()):
            if not task.done():
                task.cancel()
                cancelled_count += 1
                logger.debug("Cancelled task", task_id=task_id)

        # Wait for cancellations to complete
        if self._running_tasks:
            await asyncio.gather(*self._running_tasks.values(), return_exceptions=True)

        self._running_tasks.clear()

        logger.info("Cancelled all running tasks", count=cancelled_count)
        return cancelled_count

    def reset_cancellation(self) -> None:
        """Reset the cancelled flag to allow new executions."""
        self._cancelled = False

    @property
    def running_count(self) -> int:
        """Get the number of currently running tasks."""
        return sum(1 for t in self._running_tasks.values() if not t.done())

    async def get_subagent(self, agent_id: str) -> Optional[SubagentInfo]:
        """Get information about a sub-agent."""
        return self._subagent_info.get(agent_id)

    async def list_subagents(self) -> List[SubagentInfo]:
        """List all managed sub-agents."""
        return list(self._subagent_info.values())

    async def shutdown_subagent(self, agent_id: str) -> bool:
        """Shutdown a specific sub-agent."""
        if agent_id not in self._subagents:
            return False

        try:
            agent = self._subagents[agent_id]

            # Shutdown the agent
            if hasattr(agent, 'shutdown'):
                await agent.shutdown()

            # Terminate context if available
            if agent_id in self._subagent_contexts and self._context:
                context_id = self._subagent_contexts[agent_id]
                await self._context.terminate_context(context_id)

            # Remove from tracking
            del self._subagents[agent_id]
            self._subagent_contexts.pop(agent_id, None)
            self._subagent_info.pop(agent_id, None)

            logger.debug("Sub-agent shutdown", agent_id=agent_id)
            return True

        except Exception as e:
            logger.error("Failed to shutdown sub-agent", agent_id=agent_id, error=str(e))
            return False

    async def shutdown_all(self) -> None:
        """Shutdown all managed sub-agents."""
        agent_ids = list(self._subagents.keys())

        shutdown_tasks = [
            self.shutdown_subagent(agent_id)
            for agent_id in agent_ids
        ]

        if shutdown_tasks:
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)

        self._subagents.clear()
        self._subagent_contexts.clear()
        self._subagent_info.clear()

        logger.info("All sub-agents shutdown")

    @property
    def count(self) -> int:
        """Get the number of managed sub-agents."""
        return len(self._subagents)
