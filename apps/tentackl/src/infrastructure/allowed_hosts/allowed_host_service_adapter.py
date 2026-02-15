"""Infrastructure adapter for allowed host operations."""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from src.domain.allowed_hosts import AllowedHostOperationsPort
from src.infrastructure.allowed_hosts.allowed_host_service import AllowedHostService
from src.interfaces.database import Database


class AllowedHostServiceAdapter(AllowedHostOperationsPort):
    """Adapter exposing AllowedHostService through AllowedHostOperationsPort."""

    def __init__(self, db: Database) -> None:
        self._service = AllowedHostService(database=db)

    async def get_allowed_hosts(self, environment: Optional[str] = None) -> List[Any]:
        return await self._service.get_allowed_hosts(environment=environment)

    async def add_allowed_host(
        self,
        host: str,
        environment: str,
        created_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Any:
        return await self._service.add_allowed_host(
            host=host,
            environment=environment,
            created_by=created_by,
            notes=notes,
        )

    async def remove_allowed_host(self, host: str, environment: str) -> bool:
        return await self._service.remove_allowed_host(host=host, environment=environment)

    async def is_host_allowed(
        self,
        url: str,
        environment: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        return await self._service.is_host_allowed(url=url, environment=environment)
