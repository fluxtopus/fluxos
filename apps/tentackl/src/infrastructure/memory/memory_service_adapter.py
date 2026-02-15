"""Infrastructure adapter for memory service operations."""

from __future__ import annotations

from typing import Optional, List

from src.domain.memory.ports import MemoryOperationsPort
from src.domain.memory.models import (
    MemoryCreateRequest,
    MemoryUpdateRequest,
    MemoryQuery,
    MemoryResult,
    MemorySearchResponse,
    MemoryServiceInterface,
)


class MemoryServiceAdapter(MemoryOperationsPort):
    """Adapter that exposes MemoryServiceInterface through the domain port."""

    def __init__(self, service: MemoryServiceInterface):
        self._service = service

    async def store(self, request: MemoryCreateRequest) -> MemoryResult:
        return await self._service.store(request)

    async def retrieve(
        self,
        memory_id: str,
        organization_id: str,
        user_id: str,
        agent_id: Optional[str] = None,
    ) -> Optional[MemoryResult]:
        return await self._service.retrieve(
            memory_id=memory_id,
            organization_id=organization_id,
            user_id=user_id,
            agent_id=agent_id,
        )

    async def retrieve_by_key(
        self,
        key: str,
        organization_id: str,
        user_id: str,
        agent_id: Optional[str] = None,
    ) -> Optional[MemoryResult]:
        return await self._service.retrieve_by_key(
            key=key,
            organization_id=organization_id,
            user_id=user_id,
            agent_id=agent_id,
        )

    async def update(
        self,
        memory_id: str,
        organization_id: str,
        request: MemoryUpdateRequest,
        user_id: str,
        agent_id: Optional[str] = None,
    ) -> MemoryResult:
        return await self._service.update(
            memory_id=memory_id,
            organization_id=organization_id,
            request=request,
            user_id=user_id,
            agent_id=agent_id,
        )

    async def delete(
        self,
        memory_id: str,
        organization_id: str,
        user_id: str,
        agent_id: Optional[str] = None,
    ) -> bool:
        return await self._service.delete(
            memory_id=memory_id,
            organization_id=organization_id,
            user_id=user_id,
            agent_id=agent_id,
        )

    async def search(self, query: MemoryQuery) -> MemorySearchResponse:
        return await self._service.search(query)

    async def get_version_history(
        self,
        memory_id: str,
        organization_id: str,
        user_id: str,
        agent_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[MemoryResult]:
        return await self._service.get_version_history(
            memory_id=memory_id,
            organization_id=organization_id,
            user_id=user_id,
            agent_id=agent_id,
            limit=limit,
        )

    async def format_for_injection(self, query: MemoryQuery, max_tokens: int = 2000) -> str:
        return await self._service.format_for_injection(query, max_tokens=max_tokens)

    async def health_check(self) -> bool:
        return await self._service.health_check()
