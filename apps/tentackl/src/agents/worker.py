# REVIEW:
# - Demo worker with sleep-based behavior; not production-grade.
from typing import Any, Dict
from src.agents.base import Agent, AgentConfig
import asyncio
import structlog

logger = structlog.get_logger()


class WorkerAgent(Agent):
    """Example worker agent implementation"""
    
    async def execute(self, task: Dict[str, Any]) -> Any:
        """Execute a worker task"""
        logger.info(
            f"Worker {self.id} executing task",
            task_type=task.get("type"),
            agent_name=self.config.name
        )
        
        # Simulate work based on task type
        task_type = task.get("type", "default")
        
        if task_type == "compute":
            result = await self._compute_task(task)
        elif task_type == "fetch":
            result = await self._fetch_task(task)
        else:
            result = await self._default_task(task)
        
        logger.info(f"Worker {self.id} completed task", result=result)
        return result
    
    async def _compute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate computational task"""
        duration = task.get("duration", 2)
        await asyncio.sleep(duration)
        
        return {
            "status": "completed",
            "result": f"Computed for {duration} seconds",
            "agent_id": self.id
        }
    
    async def _fetch_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate data fetching task"""
        await asyncio.sleep(1)
        
        return {
            "status": "completed",
            "data": {"sample": "data"},
            "agent_id": self.id
        }
    
    async def _default_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Default task handler"""
        await asyncio.sleep(0.5)
        
        return {
            "status": "completed",
            "message": "Task processed",
            "agent_id": self.id
        }
