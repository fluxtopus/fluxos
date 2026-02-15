"""Helpers for task planning."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

import structlog

from src.domain.tasks.models import TaskStep


logger = structlog.get_logger(__name__)


def assign_parallel_groups(steps: List[TaskStep]) -> None:
    """
    Auto-assign parallel groups to steps that can run concurrently.

    Steps are grouped together if:
    1. They have the same dependencies (or both have no dependencies)
    2. They don't depend on each other
    3. They are of the same agent type (for balanced resource usage)
    """
    step_by_id = {s.id: s for s in steps}

    groups: Dict[tuple, List[str]] = defaultdict(list)
    for step in steps:
        if step.parallel_group:
            continue
        deps_key = tuple(sorted(step.dependencies or []))
        group_key = (step.agent_type, deps_key)
        groups[group_key].append(step.id)

    group_counter = 1
    for group_key, step_ids in groups.items():
        if len(step_ids) > 1:
            agent_type, _ = group_key
            parallel_group_name = f"parallel_{agent_type}_{group_counter}"
            for step_id in step_ids:
                step_by_id[step_id].parallel_group = parallel_group_name
            logger.debug(
                "Assigned parallel group",
                group=parallel_group_name,
                step_ids=step_ids,
                agent_type=agent_type,
            )
            group_counter += 1

    grouped_count = sum(1 for s in steps if s.parallel_group)
    if grouped_count > 0:
        logger.info(
            "Auto-assigned parallel groups",
            grouped_steps=grouped_count,
            total_steps=len(steps),
            groups=group_counter - 1,
        )
