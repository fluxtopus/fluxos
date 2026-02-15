"""Embedding services for Tentackl.

Provides semantic similarity capabilities for:
- Task pattern recognition ("do the HN thing again")
- Similar task retrieval
- Capability semantic discovery
- Embedding backfill
"""

from .task_embedding_service import (
    TaskEmbeddingService,
    get_task_embedding_service,
)
from .capability_embedding_service import (
    CapabilityEmbeddingService,
    get_capability_embedding_service,
)


__all__ = [
    "TaskEmbeddingService",
    "get_task_embedding_service",
    "CapabilityEmbeddingService",
    "get_capability_embedding_service",
]
