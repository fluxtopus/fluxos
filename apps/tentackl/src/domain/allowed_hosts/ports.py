"""Domain ports for allowed host operations."""

from __future__ import annotations

from typing import Any, List, Optional, Protocol, Tuple


class AllowedHostOperationsPort(Protocol):
    """Port for host allowlist administration and checks."""

    async def get_allowed_hosts(self, environment: Optional[str] = None) -> List[Any]:
        ...

    async def add_allowed_host(
        self,
        host: str,
        environment: str,
        created_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Any:
        ...

    async def remove_allowed_host(self, host: str, environment: str) -> bool:
        ...

    async def is_host_allowed(
        self,
        url: str,
        environment: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        ...

