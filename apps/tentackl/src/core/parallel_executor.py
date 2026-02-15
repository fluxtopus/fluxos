"""Parallel execution planning and lightweight task execution helper."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import asyncio
import structlog

from src.agents.supervisor import AgentSupervisor
from src.interfaces.sub_agent_generator import AgentSpecification

logger = structlog.get_logger(__name__)


class ExecutionMode(str, Enum):
    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"
    BATCH = "batch"
    PIPELINE = "pipeline"
    ADAPTIVE = "adaptive"


@dataclass
class ExecutionPlan:
    execution_mode: ExecutionMode
    agent_groups: List[List[str]]
    dependency_graph: Dict[str, List[str]]
    total_memory_mb: int
    total_cpu_percent: int
    agent_count: int
    max_parallel_agents: int

    def get_execution_order(self) -> List[List[str]]:
        return self.agent_groups


@dataclass
class ExecutionResult:
    success: bool
    results: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class ParallelExecutor:
    """Lightweight helper for building execution plans and running agent tasks in parallel."""

    def __init__(
        self,
        sub_agent_generator: Optional[Any] = None,
        state_store: Optional[Any] = None,
        context_manager: Optional[Any] = None,
        execution_tree: Optional[Any] = None,
        max_concurrent_executions: int = 5,
    ) -> None:
        self.sub_agent_generator = sub_agent_generator
        self.state_store = state_store
        self.context_manager = context_manager
        self.execution_tree = execution_tree
        self.max_concurrent_executions = max_concurrent_executions

    async def create_execution_plan(
        self,
        specifications: List[AgentSpecification],
        execution_mode: ExecutionMode = ExecutionMode.PARALLEL,
        max_parallel: Optional[int] = None,
    ) -> ExecutionPlan:
        dependency_graph = {spec.name: list(spec.dependencies) for spec in specifications}

        if self.sub_agent_generator and hasattr(self.sub_agent_generator, "estimate_resource_usage"):
            resource_estimates = await self.sub_agent_generator.estimate_resource_usage(specifications)
            total_memory_mb = int(resource_estimates.get("total_memory_mb", 0))
            total_cpu_percent = int(resource_estimates.get("total_cpu_percent", 0))
        else:
            total_memory_mb = sum(int(spec.max_memory_mb or 0) for spec in specifications)
            total_cpu_percent = sum(int(spec.max_cpu_percent or 0) for spec in specifications)

        effective_mode = self._resolve_execution_mode(
            execution_mode,
            specifications,
            total_memory_mb,
            total_cpu_percent,
            dependency_graph,
        )

        max_parallel_agents = min(
            max_parallel or len(specifications) or 1,
            self.max_concurrent_executions,
        )

        agent_groups = self._build_agent_groups(
            specifications,
            effective_mode,
            dependency_graph,
            max_parallel_agents,
            total_memory_mb,
            total_cpu_percent,
        )

        return ExecutionPlan(
            execution_mode=effective_mode,
            agent_groups=agent_groups,
            dependency_graph=dependency_graph,
            total_memory_mb=total_memory_mb,
            total_cpu_percent=total_cpu_percent,
            agent_count=len(specifications),
            max_parallel_agents=max_parallel_agents,
        )

    async def execute_parallel(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        async def run_task(task_payload: Dict[str, Any]) -> Dict[str, Any]:
            agent_id = task_payload.get("agent_id")
            agent_task = task_payload.get("task", {})
            agent = AgentSupervisor.get_global_agent(agent_id)
            if not agent:
                return {"status": "error", "error": f"Agent not found: {agent_id}"}

            try:
                if hasattr(agent, "process_task"):
                    result = await agent.process_task(agent_task)
                else:
                    result = await agent.execute(agent_task)
            except Exception as exc:
                return {"status": "error", "error": str(exc)}

            if isinstance(result, dict) and isinstance(result.get("result"), dict):
                merged = {"status": result.get("status", "success")}
                merged.update(result.get("result", {}))
                if "metadata" in result:
                    merged["metadata"] = result["metadata"]
                return merged

            if isinstance(result, dict):
                return result

            return {"status": "success", "result": result}

        return await asyncio.gather(*(run_task(task) for task in tasks))

    def _resolve_execution_mode(
        self,
        requested: ExecutionMode,
        specs: List[AgentSpecification],
        total_memory_mb: int,
        total_cpu_percent: int,
        dependency_graph: Dict[str, List[str]],
    ) -> ExecutionMode:
        if requested != ExecutionMode.ADAPTIVE:
            return requested

        has_dependencies = any(deps for deps in dependency_graph.values())
        if has_dependencies:
            return ExecutionMode.PIPELINE

        heavy_specs = any(
            (spec.max_memory_mb or 0) >= 2048 or (spec.max_cpu_percent or 0) >= 80
            for spec in specs
        )
        if heavy_specs or total_memory_mb > 4096 or total_cpu_percent > 100:
            return ExecutionMode.BATCH

        return ExecutionMode.PARALLEL

    def _build_agent_groups(
        self,
        specs: List[AgentSpecification],
        execution_mode: ExecutionMode,
        dependency_graph: Dict[str, List[str]],
        max_parallel_agents: int,
        total_memory_mb: int,
        total_cpu_percent: int,
    ) -> List[List[str]]:
        names = [spec.name for spec in specs]

        if not names:
            return []

        if execution_mode == ExecutionMode.PARALLEL:
            return [names]

        if execution_mode == ExecutionMode.SEQUENTIAL:
            return [[name] for name in names]

        if execution_mode == ExecutionMode.PIPELINE:
            return self._build_dependency_levels(names, dependency_graph)

        if execution_mode == ExecutionMode.BATCH:
            heavy = total_memory_mb > 4096 or total_cpu_percent > 100 or any(
                (spec.max_memory_mb or 0) >= 2048 for spec in specs
            )
            batch_size = 1 if heavy else max_parallel_agents
            return [names[i:i + batch_size] for i in range(0, len(names), batch_size)]

        return [names]

    def _build_dependency_levels(
        self,
        names: List[str],
        dependency_graph: Dict[str, List[str]],
    ) -> List[List[str]]:
        remaining = set(names)
        completed: set[str] = set()
        levels: List[List[str]] = []

        while remaining:
            ready = [
                name for name in remaining
                if all(dep in completed for dep in dependency_graph.get(name, []))
            ]

            if not ready:
                # Cycle or missing deps; dump remaining to a final level
                levels.append(sorted(remaining))
                break

            levels.append(ready)
            completed.update(ready)
            remaining.difference_update(ready)

        return levels
