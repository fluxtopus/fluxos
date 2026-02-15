"""Domain ports for capability persistence and search."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Tuple
from uuid import UUID

from src.database.capability_models import AgentCapability


class CapabilityRepositoryPort(Protocol):
    """Port for capability persistence and search."""

    async def list_capabilities(
        self,
        org_id: Optional[str],
        include_system: bool,
        active_only: bool,
        domain: Optional[str],
        tags: Optional[List[str]],
        limit: int,
        offset: int,
    ) -> Tuple[List[AgentCapability], int]:
        ...

    async def get_capability(self, capability_id: UUID) -> Optional[AgentCapability]:
        ...

    async def find_conflicting_agent_type(
        self,
        org_id: str,
        agent_type: str,
        exclude_id: Optional[UUID] = None,
    ) -> Optional[AgentCapability]:
        ...

    async def create_capability(self, capability: AgentCapability) -> AgentCapability:
        ...

    async def update_capability(self, capability: AgentCapability) -> AgentCapability:
        ...

    async def create_new_version(
        self,
        old_capability_id: UUID,
        new_capability: AgentCapability,
    ) -> AgentCapability:
        ...

    async def search_semantic(
        self,
        query_embedding: List[float],
        org_id: Optional[str],
        include_system: bool,
        active_only: bool,
        domain: Optional[str],
        tags: Optional[List[str]],
        limit: int,
        min_similarity: float,
    ) -> List[Dict[str, Any]]:
        ...

    async def search_keyword(
        self,
        query: str,
        org_id: Optional[str],
        include_system: bool,
        active_only: bool,
        domain: Optional[str],
        tags: Optional[List[str]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        ...
