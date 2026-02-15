"""Domain ports for memory operations."""

from __future__ import annotations

from typing import Optional, Protocol, List

from src.domain.memory.models import (
    MemoryCreateRequest,
    MemoryUpdateRequest,
    MemoryQuery,
    MemoryResult,
    MemorySearchResponse,
)


class MemoryOperationsPort(Protocol):
    """Port for memory lifecycle and retrieval operations."""

    async def store(self, request: MemoryCreateRequest) -> MemoryResult:
        ...

    async def retrieve(
        self,
        memory_id: str,
        organization_id: str,
        user_id: str,
        agent_id: Optional[str] = None,
    ) -> Optional[MemoryResult]:
        ...

    async def retrieve_by_key(
        self,
        key: str,
        organization_id: str,
        user_id: str,
        agent_id: Optional[str] = None,
    ) -> Optional[MemoryResult]:
        ...

    async def update(
        self,
        memory_id: str,
        organization_id: str,
        request: MemoryUpdateRequest,
        user_id: str,
        agent_id: Optional[str] = None,
    ) -> MemoryResult:
        ...

    async def delete(
        self,
        memory_id: str,
        organization_id: str,
        user_id: str,
        agent_id: Optional[str] = None,
    ) -> bool:
        ...

    async def search(self, query: MemoryQuery) -> MemorySearchResponse:
        ...

    async def get_version_history(
        self,
        memory_id: str,
        organization_id: str,
        user_id: str,
        agent_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[MemoryResult]:
        ...

    async def format_for_injection(self, query: MemoryQuery, max_tokens: int = 2000) -> str:
        ...

    async def health_check(self) -> bool:
        ...
