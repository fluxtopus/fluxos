"""Bunny.net CDN storage backend for production."""

import httpx
import hashlib
import time
from typing import BinaryIO, Optional
from io import BytesIO

from .base import StorageBackend, StorageResult, StorageError, FileNotFoundError


class BunnyStorage(StorageBackend):
    """Bunny.net storage implementation.

    Provides cloud storage using Bunny.net Edge Storage with features:
    - Direct file upload/download via Edge Storage API
    - CDN URL generation for public files
    - Signed URL generation for private files (token authentication)
    - HTTP/2 support with async operations using httpx

    Bunny.net API Reference:
    - Storage API: https://docs.bunny.net/reference/storage-api
    - Token Authentication: https://docs.bunny.net/docs/stream-security#url-token-authentication

    Example:
        storage = BunnyStorage(
            api_key="your-storage-api-key",
            storage_zone="my-storage-zone",
            cdn_hostname="cdn.example.com",  # Optional
            token_key="your-token-key"  # Optional, for signed URLs
        )

        # Upload a file
        with open("document.pdf", "rb") as f:
            result = await storage.upload(
                file_data=f,
                storage_key="org123/document.pdf",
                content_type="application/pdf",
                is_public=True
            )
            print(result.cdn_url)  # https://cdn.example.com/org123/document.pdf
    """

    def __init__(
        self,
        api_key: str,
        storage_zone: str,
        storage_hostname: str = "storage.bunnycdn.com",
        cdn_hostname: Optional[str] = None,
        token_key: Optional[str] = None,
    ):
        """Initialize Bunny.net storage backend.

        Args:
            api_key: Bunny.net Edge Storage API key (from storage zone settings)
            storage_zone: Name of the storage zone
            storage_hostname: Edge Storage hostname (default: storage.bunnycdn.com)
            cdn_hostname: CDN hostname for pull zone (optional, for public URLs)
            token_key: Token authentication key (optional, for signed URLs)
        """
        self.api_key = api_key
        self.storage_zone = storage_zone
        self.storage_hostname = storage_hostname
        self.cdn_hostname = cdn_hostname
        self.token_key = token_key
        self.base_url = f"https://{storage_hostname}/{storage_zone}"

    def _sign_cdn_url(self, storage_key: str, expires_in: int = 86400) -> Optional[str]:
        """Generate a signed CDN URL for a file.

        Args:
            storage_key: Unique key/path of the file
            expires_in: URL expiration time in seconds (default: 24 hours)

        Returns:
            Signed CDN URL or None if CDN is not configured
        """
        if not self.cdn_hostname:
            return None

        # If no token key, return unsigned URL
        if not self.token_key:
            return f"https://{self.cdn_hostname}/{storage_key}"

        import base64

        expiry = int(time.time()) + expires_in
        token_path = f"/{storage_key}"

        # Bunny.net URL token format:
        # Hash: sha256(security_key + path + expiry), then base64 encode
        hashable = f"{self.token_key}{token_path}{expiry}"
        hash_bytes = hashlib.sha256(hashable.encode()).digest()
        token = base64.b64encode(hash_bytes).decode()
        # Make URL-safe
        token = token.replace('+', '-').replace('/', '_').rstrip('=')

        return f"https://{self.cdn_hostname}/{storage_key}?token={token}&expires={expiry}"

    async def upload(
        self,
        file_data: BinaryIO,
        storage_key: str,
        content_type: str,
        is_public: bool = False
    ) -> StorageResult:
        """Upload a file to Bunny.net Edge Storage.

        Args:
            file_data: Binary file data to upload
            storage_key: Unique key/path for storing the file (e.g., 'org123/file.pdf')
            content_type: MIME type of the file (e.g., 'application/pdf')
            is_public: Whether the file should be publicly accessible via CDN

        Returns:
            StorageResult with storage metadata and URLs

        Raises:
            StorageError: If upload fails
        """
        try:
            url = f"{self.base_url}/{storage_key}"
            content = file_data.read()

            async with httpx.AsyncClient() as client:
                response = await client.put(
                    url,
                    content=content,
                    headers={
                        "AccessKey": self.api_key,
                        "Content-Type": content_type,
                    },
                    timeout=300.0
                )
                response.raise_for_status()

            # Generate signed CDN URL if public and CDN is configured
            # Using signed URL ensures the file is accessible even with token auth enabled
            cdn_url = None
            if is_public:
                cdn_url = self._sign_cdn_url(storage_key, expires_in=86400)  # 24 hour expiry

            return StorageResult(
                storage_key=storage_key,
                url=url,
                cdn_url=cdn_url,
                size_bytes=len(content)
            )

        except httpx.HTTPStatusError as e:
            raise StorageError(f"Failed to upload file '{storage_key}': {e.response.status_code} {e.response.text}")
        except Exception as e:
            raise StorageError(f"Failed to upload file '{storage_key}': {e}")

    async def download(self, storage_key: str) -> BinaryIO:
        """Download a file from Bunny.net Edge Storage.

        Args:
            storage_key: Unique key/path of the file to download

        Returns:
            Binary file data as BytesIO

        Raises:
            FileNotFoundError: If file doesn't exist
            StorageError: If download fails
        """
        try:
            url = f"{self.base_url}/{storage_key}"

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers={"AccessKey": self.api_key},
                    timeout=300.0
                )
                if response.status_code == 404:
                    raise FileNotFoundError(f"File '{storage_key}' not found in storage")
                response.raise_for_status()

            return BytesIO(response.content)

        except FileNotFoundError:
            raise
        except httpx.HTTPStatusError as e:
            raise StorageError(f"Failed to download file '{storage_key}': {e.response.status_code} {e.response.text}")
        except Exception as e:
            raise StorageError(f"Failed to download file '{storage_key}': {e}")

    async def delete(self, storage_key: str) -> bool:
        """Delete a file from Bunny.net Edge Storage.

        Args:
            storage_key: Unique key/path of the file to delete

        Returns:
            True if file was deleted, False if file didn't exist

        Raises:
            StorageError: If deletion fails (excluding 404 not found)
        """
        try:
            url = f"{self.base_url}/{storage_key}"

            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    url,
                    headers={"AccessKey": self.api_key}
                )
                # 200 = deleted, 404 = didn't exist
                return response.status_code in (200, 404)

        except Exception as e:
            raise StorageError(f"Failed to delete file '{storage_key}': {e}")

    async def copy(self, source_key: str, dest_key: str) -> StorageResult:
        """Copy a file within Bunny.net Edge Storage.

        Note: Bunny.net doesn't have a native copy API, so this downloads
        and re-uploads the file.

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
            # Download source file
            file_data = await self.download(source_key)

            # Re-upload to destination
            # Use generic content type since we don't know the original
            return await self.upload(
                file_data=file_data,
                storage_key=dest_key,
                content_type="application/octet-stream",
                is_public=False
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
        """Get a signed download URL for a file.

        Generates a token-authenticated URL that expires after the specified time.
        Requires `token_key` to be configured during initialization.

        Token format follows Bunny.net URL token authentication:
        https://cdn.example.com/path?token={sha256_hash}&expires={timestamp}

        Args:
            storage_key: Unique key/path of the file
            expires_in: URL expiration time in seconds (default: 3600 = 1 hour)

        Returns:
            Signed download URL

        Raises:
            FileNotFoundError: If file doesn't exist
            StorageError: If token_key is not configured or URL generation fails
        """
        try:
            # Check if file exists first
            if not await self.exists(storage_key):
                raise FileNotFoundError(f"File '{storage_key}' not found in storage")

            if not self.token_key:
                # If no token key, return CDN URL or direct storage URL
                if self.cdn_hostname:
                    return f"https://{self.cdn_hostname}/{storage_key}"
                # Fall back to direct storage URL (requires API key for access)
                # This is useful for development/testing without CDN configured
                return f"{self.base_url}/{storage_key}"

            # Generate Bunny.net token authentication URL
            # Reference: https://docs.bunny.net/docs/stream-security
            expiry = int(time.time()) + expires_in
            token_path = f"/{storage_key}"

            # Bunny.net URL token format:
            # 1. Hash: sha256(security_key + path + expiry)
            # 2. Base64 encode the hash (not hex!)
            # 3. Make URL-safe: replace + with -, / with _, remove trailing =
            import base64
            hashable = f"{self.token_key}{token_path}{expiry}"
            hash_bytes = hashlib.sha256(hashable.encode()).digest()
            token = base64.b64encode(hash_bytes).decode()
            # Make URL-safe
            token = token.replace('+', '-').replace('/', '_').rstrip('=')

            # Use CDN hostname if available, otherwise fall back to storage URL
            if self.cdn_hostname:
                return f"https://{self.cdn_hostname}/{storage_key}?token={token}&expires={expiry}"
            return f"{self.base_url}/{storage_key}?token={token}&expires={expiry}"

        except FileNotFoundError:
            raise
        except Exception as e:
            raise StorageError(f"Failed to generate download URL for '{storage_key}': {e}")

    async def exists(self, storage_key: str) -> bool:
        """Check if a file exists in Bunny.net Edge Storage.

        Note: Uses GET with Range header instead of HEAD because Bunny.net
        returns 401 for HEAD requests even with valid credentials.

        Args:
            storage_key: Unique key/path of the file to check

        Returns:
            True if file exists, False otherwise
        """
        try:
            url = f"{self.base_url}/{storage_key}"

            async with httpx.AsyncClient() as client:
                # Use GET with Range header to fetch minimal data
                # HEAD requests return 401 on Bunny.net even with valid key
                response = await client.get(
                    url,
                    headers={
                        "AccessKey": self.api_key,
                        "Range": "bytes=0-0"  # Fetch only first byte
                    },
                    timeout=10.0
                )
                # 200 = full file, 206 = partial content (range request worked)
                return response.status_code in (200, 206)

        except Exception:
            return False
