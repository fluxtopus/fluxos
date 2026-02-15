"""Application use cases for trigger operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.domain.triggers.ports import TriggerRegistryPort


class TriggerNotFound(Exception):
    """Raised when a trigger is not found or not accessible."""


class TriggerUpdateError(Exception):
    """Raised when updating a trigger fails."""


@dataclass
class TriggerUseCases:
    """Application-layer orchestration for trigger operations."""

    registry: TriggerRegistryPort

    async def list_triggers(
        self,
        org_id: str,
        user_id: str,
        scope: Optional[str],
    ) -> List[Dict[str, Any]]:
        triggers = await self.registry.get_triggers_for_user(org_id, user_id)

        if scope == "org":
            triggers = [t for t in triggers if not t.get("user_id")]
        elif scope == "user":
            triggers = [t for t in triggers if t.get("user_id") == user_id]

        return triggers

    async def get_trigger(self, task_id: str, org_id: str, user_id: str) -> Dict[str, Any]:
        config = await self.registry.get_trigger_config(task_id)
        self._ensure_access(config, org_id, user_id)
        return config

    async def get_trigger_config(self, task_id: str) -> Optional[Dict[str, Any]]:
        return await self.registry.get_trigger_config(task_id)

    async def get_trigger_history(self, task_id: str, org_id: str, user_id: str, limit: int) -> List[Dict]:
        config = await self.registry.get_trigger_config(task_id)
        self._ensure_access(config, org_id, user_id)
        return await self.registry.get_trigger_history(task_id, limit=limit)

    async def register_trigger(
        self,
        task_id: str,
        org_id: str,
        user_id: str,
        trigger_config: Dict[str, Any],
    ) -> bool:
        if not org_id:
            raise TriggerUpdateError("Organization ID is required to register triggers")
        return await self.registry.register_trigger(
            task_id=task_id,
            organization_id=org_id,
            trigger_config=trigger_config,
            user_id=user_id,
        )

    async def delete_trigger(self, task_id: str, org_id: str, user_id: str) -> None:
        config = await self.registry.get_trigger_config(task_id)
        self._ensure_access(config, org_id, user_id)

        success = await self.registry.unregister_trigger(task_id)
        if not success:
            raise TriggerUpdateError("Failed to delete trigger")

    async def update_trigger(
        self,
        task_id: str,
        org_id: str,
        user_id: str,
        enabled: Optional[bool],
    ) -> Dict[str, Any]:
        config = await self.registry.get_trigger_config(task_id)
        self._ensure_access(config, org_id, user_id)

        updates = {}
        if enabled is not None:
            updates["enabled"] = enabled

        if updates:
            success = await self.registry.update_trigger(task_id, updates)
            if not success:
                raise TriggerUpdateError("Failed to update trigger")

        updated_config = await self.registry.get_trigger_config(task_id)
        self._ensure_access(updated_config, org_id, user_id)
        return updated_config

    async def find_matching_tasks(
        self,
        event: Any,
        org_id: Optional[str] = None,
    ) -> List[str]:
        return await self.registry.find_matching_tasks(
            event=event,
            organization_id=org_id,
        )

    async def add_execution_to_history(
        self,
        task_id: str,
        execution: Dict[str, Any],
        max_history: int = 100,
    ) -> bool:
        return await self.registry.add_execution_to_history(
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
        return await self.registry.update_execution_in_history(
            task_id=task_id,
            execution_id=execution_id,
            updates=updates,
        )

    def _ensure_access(self, config: Optional[Dict], org_id: str, user_id: str) -> None:
        if not config:
            raise TriggerNotFound()

        if config.get("organization_id") != org_id:
            raise TriggerNotFound()

        trigger_user_id = config.get("user_id")
        if trigger_user_id and trigger_user_id != user_id:
            raise TriggerNotFound()
