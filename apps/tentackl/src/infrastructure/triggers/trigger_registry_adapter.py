"""Infrastructure adapter for trigger registry operations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.domain.triggers.ports import TriggerRegistryPort
from src.infrastructure.triggers.task_trigger_registry import TaskTriggerRegistry


class TriggerRegistryAdapter(TriggerRegistryPort):
    """Adapter exposing TaskTriggerRegistry through the TriggerRegistryPort."""

    def __init__(self, registry: TaskTriggerRegistry) -> None:
        self._registry = registry

    async def get_triggers_for_user(self, org_id: str, user_id: str) -> List[Dict[str, Any]]:
        return await self._registry.get_triggers_for_user(org_id, user_id)

    async def get_trigger_config(self, task_id: str) -> Optional[Dict[str, Any]]:
        return await self._registry.get_trigger_config(task_id)

    async def get_trigger_history(self, task_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        return await self._registry.get_trigger_history(task_id, limit=limit)

    async def register_trigger(
        self,
        task_id: str,
        organization_id: str,
        trigger_config: Dict[str, Any],
        user_id: str,
    ) -> bool:
        return await self._registry.register_trigger(
            task_id=task_id,
            organization_id=organization_id,
            trigger_config=trigger_config,
            user_id=user_id,
        )

    async def unregister_trigger(self, task_id: str) -> bool:
        return await self._registry.unregister_trigger(task_id)

    async def update_trigger(self, task_id: str, updates: Dict[str, Any]) -> bool:
        return await self._registry.update_trigger(task_id, updates)

    async def find_matching_tasks(
        self,
        event: Any,
        organization_id: Optional[str] = None,
    ) -> List[str]:
        return await self._registry.find_matching_tasks(
            event=event,
            organization_id=organization_id,
        )

    async def add_execution_to_history(
        self,
        task_id: str,
        execution: Dict[str, Any],
        max_history: int = 100,
    ) -> bool:
        return await self._registry.add_execution_to_history(
            task_id=task_id,
            execution=execution,
            max_history=max_history,
        )

    async def update_execution_in_history(
        self,
        task_id: str,
        execution_id: str,
        updates: Dict[str, Any],
    ) -> bool:
        return await self._registry.update_execution_in_history(
            task_id=task_id,
            execution_id=execution_id,
            updates=updates,
        )
