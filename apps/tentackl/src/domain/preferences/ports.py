"""Domain ports for preference operations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class PreferenceOperationsPort(Protocol):
    """Port for preference operations."""

    async def list_preferences(self, user_id: str) -> List[Any]:
        ...

    async def get_preference_stats(self, user_id: str) -> Dict[str, Any]:
        ...

    async def get_preference(self, preference_id: str) -> Optional[Any]:
        ...

    async def delete_preference(self, preference_id: str) -> None:
        ...

    async def create_instruction_preference(
        self,
        user_id: str,
        preference_key: str,
        instruction: str,
        scope: str,
        scope_value: Optional[str],
        organization_id: Optional[str],
    ) -> Optional[str]:
        ...
