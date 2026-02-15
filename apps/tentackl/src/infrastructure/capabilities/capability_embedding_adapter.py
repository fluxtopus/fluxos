"""Infrastructure adapter for capability embedding operations."""

from __future__ import annotations

from typing import Dict, Optional

from src.domain.tasks.ports import CapabilityEmbeddingPort
from src.infrastructure.capabilities.capability_embedding_service import (
    CapabilityEmbeddingService,
)


class CapabilityEmbeddingAdapter(CapabilityEmbeddingPort):
    """Adapter exposing capability embedding workflows to worker tasks."""

    def __init__(self, service: Optional[CapabilityEmbeddingService] = None) -> None:
        self._service = service or CapabilityEmbeddingService()

    @property
    def is_enabled(self) -> bool:
        return self._service.is_enabled

    async def generate_and_store_embedding(self, capability_id: str) -> bool:
        return await self._service.generate_and_store_embedding(capability_id)

    async def backfill_embeddings(
        self,
        batch_size: int = 50,
        organization_id: Optional[str] = None,
    ) -> Dict[str, int]:
        return await self._service.backfill_embeddings(
            batch_size=batch_size,
            organization_id=organization_id,
        )
