"""Application use cases for memory operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List

from src.domain.memory.ports import MemoryOperationsPort
from src.domain.memory.models import (
    MemoryCreateRequest,
    MemoryUpdateRequest,
    MemoryQuery,
    MemoryResult,
    MemorySearchResponse,
)


@dataclass
class MemoryUseCases:
    """Application-layer orchestration for memory operations.

    This layer delegates to the memory port to preserve existing behavior
    while enabling incremental migration.
    """

    memory_ops: MemoryOperationsPort

    async def store(self, request: MemoryCreateRequest) -> MemoryResult:
        return await self.memory_ops.store(request)

    async def retrieve(
        self,
        memory_id: str,
        organization_id: str,
        user_id: str,
        agent_id: Optional[str] = None,
    ) -> Optional[MemoryResult]:
        return await self.memory_ops.retrieve(
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
        return await self.memory_ops.retrieve_by_key(
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
        return await self.memory_ops.update(
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
        return await self.memory_ops.delete(
            memory_id=memory_id,
            organization_id=organization_id,
            user_id=user_id,
            agent_id=agent_id,
        )

    async def search(self, query: MemoryQuery) -> MemorySearchResponse:
        return await self.memory_ops.search(query)

    async def get_version_history(
        self,
        memory_id: str,
        organization_id: str,
        user_id: str,
        agent_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[MemoryResult]:
        return await self.memory_ops.get_version_history(
            memory_id=memory_id,
            organization_id=organization_id,
            user_id=user_id,
            agent_id=agent_id,
            limit=limit,
        )

    async def format_for_injection(self, query: MemoryQuery, max_tokens: int = 2000) -> str:
        return await self.memory_ops.format_for_injection(query, max_tokens=max_tokens)

    async def health_check(self) -> bool:
        return await self.memory_ops.health_check()
