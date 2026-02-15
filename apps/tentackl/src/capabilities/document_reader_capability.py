"""
Document Reader Capabilities for Tentackl

This module defines a base capability for reading documents and a concrete
implementation that works with local filesystem sources. Future integrations
can layer additional readers (e.g., remote object storage, HTTP sources) on top
of the shared abstractions provided here.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import structlog

from ..interfaces.configurable_agent import AgentCapability
from .capability_registry import ToolDefinition

logger = structlog.get_logger(__name__)


@dataclass
class DocumentReadResult:
    """Normalized document output returned by document reader capabilities."""

    source: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class DocumentReaderCapability:
    """
    Base capability for reading documents.

    Concrete implementations should focus on fetching and validating the
    underlying payload, while delegating shared limits (size, extension
    filtering, etc.) to this base class.
    """

    DEFAULT_MAX_SIZE_MB = 2

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config = config or {}
        max_size_mb = self._config.get("max_size_mb", self.DEFAULT_MAX_SIZE_MB)
        self._max_size_bytes = int(max_size_mb * 1024 * 1024)
        self._allowed_extensions = {
            ext.lower().lstrip(".")
            for ext in self._config.get("allowed_extensions", [])
        }

    async def read(self, **kwargs: Any) -> DocumentReadResult:
        """Read a document. Must be implemented by subclasses."""
        raise NotImplementedError

    # Allow capability instances to be called like a coroutine handler
    async def __call__(self, **kwargs: Any) -> DocumentReadResult:
        return await self.read(**kwargs)

    def _validate_extension(self, path: Path) -> None:
        """Ensure file extension is allowed when a whitelist is provided."""
        if not self._allowed_extensions:
            return

        extension = path.suffix.lower().lstrip(".")
        if extension not in self._allowed_extensions:
            raise ValueError(
                f"Extension '.{extension}' not supported by this reader"
            )

    def _validate_size(self, size_bytes: int, *, source: str) -> None:
        """Ensure the payload fits within configured size constraints."""
        if size_bytes > self._max_size_bytes:
            raise ValueError(
                f"Document '{source}' exceeds max size of {self._max_size_bytes} bytes"
            )


class LocalDocumentReader(DocumentReaderCapability):
    """
    Document reader that loads files from the local filesystem.

    Configuration options (all optional):
        - allowed_directories: List[str] of absolute/relative paths that the
          agent is allowed to read from. Relative paths resolve against the
          current working directory.
        - encoding: Default text encoding (default: utf-8).
        - follow_symlinks: Whether to allow symlinks (default: False).
        - max_size_mb / allowed_extensions inherited from base class.
    """

    def __init__(self, **config: Any) -> None:
        super().__init__(config)
        cwd = Path.cwd()
        directories = config.get("allowed_directories")

        if directories:
            self._allowed_roots: List[Path] = [
                self._resolve_root(Path(directory), cwd)
                for directory in directories
            ]
        else:
            self._allowed_roots = [cwd.resolve()]

        self._encoding = config.get("encoding", "utf-8")
        self._follow_symlinks = config.get("follow_symlinks", False)

    async def read(
        self,
        path: str,
        *,
        encoding: Optional[str] = None,
    ) -> DocumentReadResult:
        """Read a local document and return normalized content + metadata."""
        resolved_path = self._resolve_path(Path(path))
        self._validate_extension(resolved_path)

        try:
            stat = resolved_path.stat()
        except FileNotFoundError as exc:
            logger.warning("Document not found", path=str(resolved_path))
            raise FileNotFoundError(f"Document '{path}' not found") from exc

        if not resolved_path.is_file():
            raise ValueError(f"Path '{path}' is not a file")

        self._validate_size(stat.st_size, source=str(resolved_path))

        document_encoding = encoding or self._encoding
        logger.debug(
            "Reading local document",
            path=str(resolved_path),
            encoding=document_encoding,
            size_bytes=stat.st_size,
        )

        content = await asyncio.to_thread(
            resolved_path.read_text,
            encoding=document_encoding,
        )

        return DocumentReadResult(
            source=str(resolved_path),
            content=content,
            metadata={
                "encoding": document_encoding,
                "size_bytes": stat.st_size,
                "modified_timestamp": stat.st_mtime,
            },
        )

    def _resolve_root(self, directory: Path, base: Path) -> Path:
        """Resolve allowed directories safely."""
        if not directory.is_absolute():
            directory = (base / directory).resolve()
        else:
            directory = directory.resolve()
        return directory

    def _resolve_path(self, raw_path: Path) -> Path:
        """Resolve and validate the target path against allowed directories."""
        path = raw_path.expanduser()
        if not path.is_absolute():
            # If relative, resolve against first allowed root
            primary_root = next(iter(self._allowed_roots))
            path = (primary_root / path).resolve()
        else:
            path = path.resolve()

        if not self._follow_symlinks and path.is_symlink():
            raise ValueError(f"Symlinks are not permitted: {path}")

        if not any(self._is_within_root(path, root) for root in self._allowed_roots):
            raise PermissionError(
                f"Access to '{path}' is not allowed by configured directories"
            )

        return path

    @staticmethod
    def _is_within_root(target: Path, root: Path) -> bool:
        """Check if target path is within an allowed root."""
        try:
            target.relative_to(root)
            return True
        except ValueError:
            return False


# Tool definition exposed to the capability registry
LOCAL_DOCUMENT_READER_CAPABILITY = ToolDefinition(
    name="local_document_reader",
    description="Read text documents from the local filesystem with safety controls",
    handler=LocalDocumentReader,
    config_schema={
        "type": "object",
        "properties": {
            "allowed_directories": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Directories that the reader can access",
            },
            "encoding": {
                "type": "string",
                "default": "utf-8",
                "description": "Default text encoding to use when reading documents",
            },
            "follow_symlinks": {
                "type": "boolean",
                "default": False,
                "description": "Allow following symbolic links when resolving paths",
            },
            "max_size_mb": {
                "type": "number",
                "default": DocumentReaderCapability.DEFAULT_MAX_SIZE_MB,
                "description": "Maximum document size in megabytes",
            },
            "allowed_extensions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional whitelist of allowed file extensions",
            },
        },
    },
    permissions_required=["filesystem:read"],
    sandboxable=True,
    category=AgentCapability.FILE_READ,
)
