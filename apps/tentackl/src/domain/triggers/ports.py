"""Domain ports for triggers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class TriggerRegistryPort(Protocol):
    """Port for trigger registry operations."""

    async def get_triggers_for_user(self, org_id: str, user_id: str) -> List[Dict[str, Any]]:
        ...

    async def get_trigger_config(self, task_id: str) -> Optional[Dict[str, Any]]:
        ...

    async def get_trigger_history(self, task_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        ...

    async def register_trigger(
        self,
        task_id: str,
        organization_id: str,
        trigger_config: Dict[str, Any],
        user_id: str,
    ) -> bool:
        ...

    async def unregister_trigger(self, task_id: str) -> bool:
        ...

    async def update_trigger(self, task_id: str, updates: Dict[str, Any]) -> bool:
        ...

    async def find_matching_tasks(
        self,
        event: Any,
        organization_id: Optional[str] = None,
    ) -> List[str]:
        ...

    async def add_execution_to_history(
        self,
        task_id: str,
        execution: Dict[str, Any],
        max_history: int = 100,
    ) -> bool:
        ...

    async def update_execution_in_history(
        self,
        task_id: str,
        execution_id: str,
        updates: Dict[str, Any],
    ) -> bool:
        ...
