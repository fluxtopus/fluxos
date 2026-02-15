"""Infrastructure adapter for preference operations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol

from src.domain.preferences.ports import PreferenceOperationsPort
from src.interfaces.database import Database
from src.infrastructure.preferences.preference_injection_service import PreferenceInjectionService


class PreferenceRuntime(Protocol):
    """Runtime contract required by preference operations adapter."""

    async def list_preferences(self, user_id: str) -> List[Any]:
        ...

    async def get_preference_stats(self, user_id: str) -> Dict[str, Any]:
        ...

    async def get_preference(self, preference_id: str) -> Optional[Any]:
        ...

    async def delete_preference(self, preference_id: str) -> None:
        ...


class PreferenceServiceAdapter(PreferenceOperationsPort):
    """Adapter exposing preference operations via runtime and database."""

    def __init__(self, runtime: PreferenceRuntime, database: Database) -> None:
        self._runtime = runtime
        self._database = database

    async def list_preferences(self, user_id: str) -> List[Any]:
        return await self._runtime.list_preferences(user_id)

    async def get_preference_stats(self, user_id: str) -> Dict[str, Any]:
        return await self._runtime.get_preference_stats(user_id)

    async def get_preference(self, preference_id: str) -> Optional[Any]:
        return await self._runtime.get_preference(preference_id)

    async def delete_preference(self, preference_id: str) -> None:
        await self._runtime.delete_preference(preference_id)

    async def create_instruction_preference(
        self,
        user_id: str,
        preference_key: str,
        instruction: str,
        scope: str,
        scope_value: Optional[str],
        organization_id: Optional[str],
    ) -> Optional[str]:
        async with self._database.get_session() as session:
            service = PreferenceInjectionService(session)
            return await service.create_instruction_preference(
                user_id=user_id,
                preference_key=preference_key,
                instruction=instruction,
                scope=scope,
                scope_value=scope_value,
                organization_id=organization_id,
                source="manual",
            )
