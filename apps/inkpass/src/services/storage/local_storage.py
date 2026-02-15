"""Local filesystem storage backend for development."""

import os
import shutil
from typing import BinaryIO
from datetime import datetime, timedelta
from pathlib import Path
import aiofiles
import aiofiles.os

from .base import StorageBackend, StorageResult, StorageError, FileNotFoundError


class LocalStorage(StorageBackend):
    """Local filesystem storage implementation for development.

    Stores files in a local directory with support for:
    - Async file operations using aiofiles
    - Automatic directory creation
    - File:// URLs for development
    - Signed URL simulation (returns file:// URLs with expiration in path)

    This implementation is suitable for development and testing only.
    For production, use BunnyStorage or similar cloud storage backend.
    """

    def __init__(self, storage_path: str = "/tmp/den-storage"):
        """Initialize local storage backend.

        Args:
            storage_path: Root directory for file storage (default: /tmp/den-storage)
        """
        self.storage_path = Path(storage_path)
        self._ensure_storage_directory()

    def _ensure_storage_directory(self) -> None:
        """Create storage directory if it doesn't exist."""
        try:
            self.storage_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise StorageError(f"Failed to create storage directory: {e}")

    def _get_file_path(self, storage_key: str) -> Path:
        """Get absolute file path for a storage key.

        Args:
            storage_key: Storage key (e.g., 'org123/file123.pdf')

        Returns:
            Absolute path to the file
        """
        # Normalize the key to prevent directory traversal
        normalized_key = os.path.normpath(storage_key).lstrip("/")
        return self.storage_path / normalized_key

    async def upload(
        self,
        file_data: BinaryIO,
        storage_key: str,
        content_type: str,
        is_public: bool = False
    ) -> StorageResult:
        """Upload a file to local storage.

        Args:
            file_data: Binary file data to upload
            storage_key: Unique key/path for storing the file
            content_type: MIME type of the file
            is_public: Whether the file should be publicly accessible (ignored in local storage)

        Returns:
            StorageResult with file metadata

        Raises:
            StorageError: If upload fails
        """
        try:
            file_path = self._get_file_path(storage_key)

            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file asynchronously
            async with aiofiles.open(file_path, 'wb') as f:
                # Read all data from BinaryIO
                data = file_data.read()
                if isinstance(data, bytes):
                    await f.write(data)
                else:
                    await f.write(data.encode())

            # Get file size
            file_size = await aiofiles.os.path.getsize(file_path)

            # Generate file:// URL for development
            url = f"file://{file_path.as_posix()}"

            return StorageResult(
                storage_key=storage_key,
                url=url,
                cdn_url=None,  # No CDN in local storage
                size_bytes=file_size
            )

        except Exception as e:
            raise StorageError(f"Failed to upload file '{storage_key}': {e}")

    async def download(self, storage_key: str) -> BinaryIO:
        """Download a file from local storage.

        Args:
            storage_key: Unique key/path of the file to download

        Returns:
            Binary file data

        Raises:
            FileNotFoundError: If file doesn't exist
            StorageError: If download fails
        """
        try:
            file_path = self._get_file_path(storage_key)

            if not await aiofiles.os.path.exists(file_path):
                raise FileNotFoundError(f"File '{storage_key}' not found in storage")

            # Read file asynchronously
            async with aiofiles.open(file_path, 'rb') as f:
                data = await f.read()

            # Return as BytesIO for BinaryIO compatibility
            from io import BytesIO
            return BytesIO(data)

        except FileNotFoundError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to download file '{storage_key}': {e}")

    async def delete(self, storage_key: str) -> bool:
        """Delete a file from local storage.

        Args:
            storage_key: Unique key/path of the file to delete

        Returns:
            True if file was deleted, False if file didn't exist

        Raises:
            StorageError: If deletion fails
        """
        try:
            file_path = self._get_file_path(storage_key)

            if not await aiofiles.os.path.exists(file_path):
                return True  # Idempotent: success even if already deleted

            # Delete file asynchronously
            await aiofiles.os.remove(file_path)

            # Try to clean up empty parent directories
            try:
                parent = file_path.parent
                while parent != self.storage_path and not list(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
            except (OSError, StopIteration):
                # Ignore errors during cleanup
                pass

            return True

        except Exception as e:
            raise StorageError(f"Failed to delete file '{storage_key}': {e}")

    async def copy(self, source_key: str, dest_key: str) -> StorageResult:
        """Copy a file within local storage.

        Args:
            source_key: Key of the file to copy
            dest_key: Destination key for the copied file

        Returns:
            StorageResult for the copied file

        Raises:
            FileNotFoundError: If source file doesn't exist
            StorageError: If copy operation fails
        """
        try:
            source_path = self._get_file_path(source_key)
            dest_path = self._get_file_path(dest_key)

            if not await aiofiles.os.path.exists(source_path):
                raise FileNotFoundError(f"Source file '{source_key}' not found")

            # Create destination parent directories
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy file (shutil.copy2 preserves metadata)
            # Note: shutil operations are synchronous, but fast for local files
            await aiofiles.os.path.exists(source_path)  # Ensure async context
            shutil.copy2(source_path, dest_path)

            # Get file size
            file_size = await aiofiles.os.path.getsize(dest_path)

            # Generate file:// URL
            url = f"file://{dest_path.as_posix()}"

            return StorageResult(
                storage_key=dest_key,
                url=url,
                cdn_url=None,
                size_bytes=file_size
            )

        except FileNotFoundError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to copy file from '{source_key}' to '{dest_key}': {e}")

    async def get_download_url(
        self,
        storage_key: str,
        expires_in: int = 3600
    ) -> str:
        """Get a download URL for a file.

        In local storage, this returns a file:// URL with expiration metadata
        in the fragment for development/testing purposes.

        Args:
            storage_key: Unique key/path of the file
            expires_in: URL expiration time in seconds (simulated, default: 3600)

        Returns:
            file:// URL with expiration info

        Raises:
            FileNotFoundError: If file doesn't exist
            StorageError: If URL generation fails
        """
        try:
            file_path = self._get_file_path(storage_key)

            if not await aiofiles.os.path.exists(file_path):
                raise FileNotFoundError(f"File '{storage_key}' not found")

            # Calculate expiration timestamp
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            expires_timestamp = int(expires_at.timestamp())

            # Return file:// URL with expiration in fragment (for dev/testing)
            url = f"file://{file_path.as_posix()}#expires={expires_timestamp}"

            return url

        except FileNotFoundError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to generate download URL for '{storage_key}': {e}")

    async def exists(self, storage_key: str) -> bool:
        """Check if a file exists in local storage.

        Args:
            storage_key: Unique key/path of the file to check

        Returns:
            True if file exists, False otherwise
        """
        try:
            file_path = self._get_file_path(storage_key)
            return await aiofiles.os.path.exists(file_path)
        except Exception:
            return False
