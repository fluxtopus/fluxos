"""Application use cases for allowed host flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from src.domain.allowed_hosts import AllowedHostOperationsPort


@dataclass
class AllowedHostUseCases:
    """Application-layer orchestration for allowed hosts."""

    host_ops: AllowedHostOperationsPort

    async def list_allowed_hosts(self, environment: Optional[str] = None) -> List[Any]:
        return await self.host_ops.get_allowed_hosts(environment=environment)

    async def create_allowed_host(
        self,
        host: str,
        environment: str,
        created_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Any:
        return await self.host_ops.add_allowed_host(
            host=host,
            environment=environment,
            created_by=created_by,
            notes=notes,
        )

    async def delete_allowed_host(self, host: str, environment: str) -> bool:
        return await self.host_ops.remove_allowed_host(host=host, environment=environment)

    async def check_host_allowed(
        self,
        url: str,
        environment: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        return await self.host_ops.is_host_allowed(url=url, environment=environment)

