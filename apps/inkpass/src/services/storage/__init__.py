"""Storage backend for file management.

This module provides an abstract storage interface and implementations
for different storage backends (local, Bunny.net CDN, etc.).
"""

from .base import (
    StorageBackend,
    StorageResult,
    StorageError,
    FileNotFoundError,
)
from .local_storage import LocalStorage
from .bunny_storage import BunnyStorage

__all__ = [
    "StorageBackend",
    "StorageResult",
    "StorageError",
    "FileNotFoundError",
    "LocalStorage",
    "BunnyStorage",
]
