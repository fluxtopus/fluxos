"""Abstract storage backend interface for file management."""

from abc import ABC, abstractmethod
from typing import BinaryIO, Optional
from dataclasses import dataclass


@dataclass
class StorageResult:
    """Result of a storage operation.

    Attributes:
        storage_key: Unique identifier for the stored file
        url: Direct URL to access the file
        cdn_url: CDN URL if available (optional)
        size_bytes: Size of the stored file in bytes
    """
    storage_key: str
    url: str
    cdn_url: Optional[str] = None
    size_bytes: int = 0


class StorageError(Exception):
    """Base exception for storage operations."""
    pass


class FileNotFoundError(StorageError):
    """Raised when a file is not found in storage."""
    pass


class StorageBackend(ABC):
    """Abstract interface for file storage backends.

    This interface allows swapping between different storage implementations
    (local filesystem, Bunny.net CDN, etc.) without changing business logic.
    """

    @abstractmethod
    async def upload(
        self,
        file_data: BinaryIO,
        storage_key: str,
        content_type: str,
        is_public: bool = False
    ) -> StorageResult:
        """Upload a file to storage.

        Args:
            file_data: Binary file data to upload
            storage_key: Unique key/path for storing the file
            content_type: MIME type of the file (e.g., 'image/png')
            is_public: Whether the file should be publicly accessible

        Returns:
            StorageResult containing storage metadata

        Raises:
            StorageError: If upload fails
        """
        pass

    @abstractmethod
    async def download(self, storage_key: str) -> BinaryIO:
        """Download a file from storage.

        Args:
            storage_key: Unique key/path of the file to download

        Returns:
            Binary file data

        Raises:
            FileNotFoundError: If file doesn't exist
            StorageError: If download fails
        """
        pass

    @abstractmethod
    async def delete(self, storage_key: str) -> bool:
        """Delete a file from storage.

        Args:
            storage_key: Unique key/path of the file to delete

        Returns:
            True if file was deleted, False if file didn't exist

        Raises:
            StorageError: If deletion fails
        """
        pass

    @abstractmethod
    async def copy(self, source_key: str, dest_key: str) -> StorageResult:
        """Copy a file within storage.

        Args:
            source_key: Key of the file to copy
            dest_key: Destination key for the copied file

        Returns:
            StorageResult for the copied file

        Raises:
            FileNotFoundError: If source file doesn't exist
            StorageError: If copy operation fails
        """
        pass

    @abstractmethod
    async def get_download_url(
        self,
        storage_key: str,
        expires_in: int = 3600
    ) -> str:
        """Get a temporary download URL for a file.

        Args:
            storage_key: Unique key/path of the file
            expires_in: URL expiration time in seconds (default: 3600)

        Returns:
            Temporary download URL

        Raises:
            FileNotFoundError: If file doesn't exist
            StorageError: If URL generation fails
        """
        pass

    @abstractmethod
    async def exists(self, storage_key: str) -> bool:
        """Check if a file exists in storage.

        Args:
            storage_key: Unique key/path of the file to check

        Returns:
            True if file exists, False otherwise
        """
        pass
