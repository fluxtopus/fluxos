"""
Primitives System

Deterministic, composable operations that execute without LLM.
Primitives are fast, free, and predictable.

Usage:
    from src.primitives import execute_primitive

    result = await execute_primitive("http.get", {"url": "https://api.example.com"})
"""

from src.primitives.registry import (
    PrimitiveRegistry,
    execute_primitive,
    get_primitive_handler,
)

__all__ = [
    "PrimitiveRegistry",
    "execute_primitive",
    "get_primitive_handler",
]
