"""Agent Worker - Processes workflow agent tasks from a queue.

Task plan steps are now executed via Celery (see core/tasks.py:execute_task_step).
This worker handles only workflow agent tasks.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional
import redis.asyncio as redis

from src.agents.factory import AgentFactory
from src.agents.base import AgentConfig
from src.agents.registry import register_default_agents
from src.interfaces.execution_tree import ExecutionTreeInterface

from src.infrastructure.execution_runtime.redis_execution_tree import RedisExecutionTree
from src.core.execution_tree import ExecutionStatus
from src.event_bus import RedisEventBus
from src.interfaces.event_bus import Event, EventSourceType
from src.infrastructure.tasks.event_publisher import TaskEventPublisher
from src.interfaces.database import Database
from src.domain.memory import MemoryOperationsPort
from src.infrastructure.memory import build_memory_use_cases

logger = logging.getLogger(__name__)


class AgentWorker:
    """Worker that processes agent tasks from Redis queue."""

    def __init__(
        self,
        worker_id: str = "worker-1",
        redis_url: str = "redis://redis:6379",
        database: Optional[Database] = None,
    ):
        self.worker_id = worker_id
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self.execution_tree: Optional[ExecutionTreeInterface] = None
        self.event_bus: Optional[RedisEventBus] = None
        self.delegation_publisher: Optional[TaskEventPublisher] = None
        self.database: Optional[Database] = database
        self._owns_database = database is None
        self._connected_database = False
        self._pg_task_store: Optional["PostgresTaskStore"] = None  # For dual-write consistency
        self._memory_service: Optional[MemoryOperationsPort] = None  # For prompt injection
        self._running = False
        self.queue_key = "tentackl:agent:task:queue"
        
    async def start(self):
        """Start the worker."""
        logger.info(f"Starting agent worker {self.worker_id}")

        # Initialize connections
        self.redis_client = await redis.from_url(self.redis_url, decode_responses=True)
        self.execution_tree = RedisExecutionTree()
        self.event_bus = RedisEventBus()
        await self.event_bus.start()

        # Initialize database for checkpoint storage and task updates
        if self.database is None:
            raise RuntimeError("AgentWorker requires an injected Database dependency")
        if getattr(self.database, "session_maker", None) is None:
            await self.database.connect()
            self._connected_database = True

        # Initialize workspace plugin with database
        from src.plugins.workspace_plugin import set_database as set_workspace_database
        set_workspace_database(self.database)
        logger.info("Workspace plugin initialized with database in worker")

        # Initialize workspace CSV plugin with database
        from src.plugins.workspace_csv_plugin import set_database as set_workspace_csv_db
        set_workspace_csv_db(self.database)

        # Initialize PostgreSQL task store for dual-write consistency
        from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskStore
        self._pg_task_store = PostgresTaskStore(self.database)

        # Initialize MemoryUseCases for prompt injection (MEM-021)
        try:
            self._memory_service = build_memory_use_cases(self.database)
            logger.info("MemoryUseCases initialized for prompt injection in worker")
        except Exception as e:
            logger.warning(f"Failed to initialize MemoryUseCases: {e}")
            self._memory_service = None

        # Initialize memory plugin with database (for agent tool calls)
        try:
            from src.plugins.memory_plugin import set_database as set_memory_database
            set_memory_database(self.database)
            logger.info("Memory plugin initialized with database in worker")
        except Exception as e:
            logger.warning(f"Failed to initialize memory plugin: {e}")

        # Initialize task output retrieval plugin with database
        try:
            from src.plugins.task_output_retrieval_plugin import set_database as set_task_retrieval_db
            set_task_retrieval_db(self.database)
            logger.info("Task output retrieval plugin initialized with database in worker")
        except Exception as e:
            logger.warning(f"Failed to initialize task output retrieval plugin: {e}")

        # Initialize delegation event publisher
        self.delegation_publisher = TaskEventPublisher(redis_url=self.redis_url)

        # Register agent types
        register_default_agents()

        self._running = True

        # Start processing tasks
        await self._process_tasks()
    
    async def stop(self):
        """Stop the worker."""
        logger.info(f"Stopping agent worker {self.worker_id}")
        self._running = False

        if self.delegation_publisher:
            await self.delegation_publisher.close()
        if self.event_bus:
            await self.event_bus.stop()
        if self.database and self._connected_database and self._owns_database:
            await self.database.disconnect()
        if self.redis_client:
            await self.redis_client.close()
    
    async def _process_tasks(self):
        """Main task processing loop."""
        logger.info(f"Worker {self.worker_id} listening for tasks on {self.queue_key}")
        
        while self._running:
            try:
                # Block waiting for task (timeout after 5 seconds to check if still running)
                result = await self.redis_client.blpop(self.queue_key, timeout=5)
                
                if result:
                    _, task_json = result
                    task = json.loads(task_json)
                    await self._handle_task(task)
                    
            except Exception as e:
                logger.error(f"Error processing task: {e}", exc_info=True)
                await asyncio.sleep(1)  # Prevent tight error loop
    
    async def _handle_task(self, task: Dict[str, Any]):
        """Handle a single task."""
        await self._handle_agent_task(task)

    async def _handle_agent_task(self, task: Dict[str, Any]):
        """Handle a workflow agent task."""
        task_id = task.get("task_id", "unknown")
        agent_config_dict = task.get("agent_config", {})
        workflow_id = task.get("workflow_id")
        node_id = task.get("node_id")

        logger.info(f"Processing task {task_id} for workflow {workflow_id}")

        try:
            # Update node status to running
            if workflow_id and node_id:
                await self.execution_tree.update_node_status(
                    workflow_id, node_id, ExecutionStatus.RUNNING
                )

            # Convert dict to AgentConfig object
            agent_config = AgentConfig.model_validate(agent_config_dict)

            # Create and run the agent
            agent = AgentFactory.create(agent_config)
            result = await agent.execute(task.get("task_data", {}))
            
            # Update node status to completed
            if workflow_id and node_id:
                await self.execution_tree.update_node_status(
                    workflow_id, node_id, ExecutionStatus.COMPLETED,
                    result_data=result
                )
            
            # Publish completion event
            if workflow_id:
                event = Event(
                    source=self.worker_id,
                    source_type=EventSourceType.INTERNAL,
                    event_type="agent.task.completed",
                    data={
                        "task_id": task_id,
                        "agent_id": agent.id,
                        "result": result
                    },
                    workflow_id=workflow_id
                )
                await self.event_bus.publish(event)
            
            logger.info(f"Task {task_id} completed successfully")
            
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)
            
            # Update node status to failed
            if workflow_id and node_id:
                await self.execution_tree.update_node_status(
                    workflow_id, node_id, ExecutionStatus.FAILED,
                    error_data={"error": str(e)}
                )
            
            # Publish failure event
            if workflow_id:
                event = Event(
                    source=self.worker_id,
                    source_type=EventSourceType.INTERNAL,
                    event_type="agent.task.failed",
                    data={
                        "task_id": task_id,
                        "error": str(e)
                    },
                    workflow_id=workflow_id
                )
                await self.event_bus.publish(event)


async def run_worker(worker_id: str = "worker-1"):
    """Run an agent worker."""
    worker = AgentWorker(worker_id, database=Database())
    
    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Worker interrupted")
    finally:
        await worker.stop()


if __name__ == "__main__":
    import sys
    
    # Get worker ID from command line or use default
    worker_id = sys.argv[1] if len(sys.argv) > 1 else "worker-1"
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run worker
    asyncio.run(run_worker(worker_id))
