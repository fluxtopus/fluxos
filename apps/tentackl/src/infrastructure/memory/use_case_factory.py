"""Factory helpers for memory use-case composition."""

from __future__ import annotations

from typing import Optional

from src.application.memory import MemoryUseCases
from src.infrastructure.memory.memory_service_adapter import MemoryServiceAdapter
from src.interfaces.database import Database


def build_memory_use_cases(database: Optional[Database] = None) -> MemoryUseCases:
    """Build memory use cases backed by the current memory service implementation."""
    from src.infrastructure.memory.memory_service import MemoryService

    db = database or Database()
    service = MemoryService(db)
    return MemoryUseCases(memory_ops=MemoryServiceAdapter(service))
