"""Unit tests for storage backends."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from io import BytesIO
import tempfile
import os
import shutil

from src.services.storage.base import StorageBackend, StorageResult


class TestStorageResult:
    """Test StorageResult dataclass."""

    def test_storage_result_basic(self):
        """Test basic StorageResult creation."""
        result = StorageResult(
            storage_key="org-123/file.txt",
            url="https://storage.example.com/org-123/file.txt",
            size_bytes=1024
        )

        assert result.storage_key == "org-123/file.txt"
        assert result.url == "https://storage.example.com/org-123/file.txt"
        assert result.size_bytes == 1024
        assert result.cdn_url is None

    def test_storage_result_with_cdn(self):
        """Test StorageResult with CDN URL."""
        result = StorageResult(
            storage_key="org-123/public.png",
            url="https://storage.example.com/org-123/public.png",
            cdn_url="https://cdn.example.com/org-123/public.png",
            size_bytes=2048
        )

        assert result.cdn_url == "https://cdn.example.com/org-123/public.png"

    def test_storage_result_zero_size(self):
        """Test StorageResult with zero size (empty file)."""
        result = StorageResult(
            storage_key="org-123/empty.txt",
            url="https://storage.example.com/org-123/empty.txt",
            size_bytes=0
        )

        assert result.size_bytes == 0


class TestLocalStorage:
    """Test LocalStorage backend."""

    @pytest.fixture
    def temp_storage_dir(self):
        """Create a temporary directory for storage."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def local_storage(self, temp_storage_dir):
        """Create LocalStorage instance with temp directory."""
        from src.services.storage.local_storage import LocalStorage
        return LocalStorage(storage_path=temp_storage_dir)

    @pytest.mark.asyncio
    async def test_upload_creates_file(self, local_storage, temp_storage_dir):
        """Test upload creates file on disk."""
        file_data = BytesIO(b"test content for upload")

        result = await local_storage.upload(
            file_data=file_data,
            storage_key="org-123/test.txt",
            content_type="text/plain"
        )

        assert result.storage_key == "org-123/test.txt"
        assert result.size_bytes == 23  # len(b"test content for upload")

        # Verify file exists on disk
        file_path = os.path.join(temp_storage_dir, "org-123", "test.txt")
        assert os.path.exists(file_path)

        with open(file_path, "rb") as f:
            assert f.read() == b"test content for upload"

    @pytest.mark.asyncio
    async def test_upload_creates_directories(self, local_storage, temp_storage_dir):
        """Test upload creates nested directories."""
        file_data = BytesIO(b"nested content")

        await local_storage.upload(
            file_data=file_data,
            storage_key="org-123/level1/level2/file.txt",
            content_type="text/plain"
        )

        file_path = os.path.join(temp_storage_dir, "org-123", "level1", "level2", "file.txt")
        assert os.path.exists(file_path)

    @pytest.mark.asyncio
    async def test_download_returns_content(self, local_storage, temp_storage_dir):
        """Test download returns file content."""
        # First upload
        await local_storage.upload(
            file_data=BytesIO(b"downloadable content"),
            storage_key="org-123/download.txt",
            content_type="text/plain"
        )

        # Then download
        result = await local_storage.download("org-123/download.txt")

        assert result.read() == b"downloadable content"

    @pytest.mark.asyncio
    async def test_download_nonexistent_raises(self, local_storage):
        """Test download raises for nonexistent file."""
        from src.services.storage.base import FileNotFoundError as StorageFileNotFoundError
        with pytest.raises(StorageFileNotFoundError):
            await local_storage.download("org-123/nonexistent.txt")

    @pytest.mark.asyncio
    async def test_delete_removes_file(self, local_storage, temp_storage_dir):
        """Test delete removes file from disk."""
        await local_storage.upload(
            file_data=BytesIO(b"to delete"),
            storage_key="org-123/delete-me.txt",
            content_type="text/plain"
        )

        file_path = os.path.join(temp_storage_dir, "org-123", "delete-me.txt")
        assert os.path.exists(file_path)

        result = await local_storage.delete("org-123/delete-me.txt")

        assert result is True
        assert not os.path.exists(file_path)

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_true(self, local_storage):
        """Test delete returns True for nonexistent file (idempotent)."""
        result = await local_storage.delete("org-123/never-existed.txt")
        assert result is True

    @pytest.mark.asyncio
    async def test_copy_duplicates_file(self, local_storage, temp_storage_dir):
        """Test copy creates duplicate."""
        await local_storage.upload(
            file_data=BytesIO(b"original content"),
            storage_key="org-123/original.txt",
            content_type="text/plain"
        )

        result = await local_storage.copy(
            "org-123/original.txt",
            "org-123/copy.txt"
        )

        assert result.storage_key == "org-123/copy.txt"

        # Both files should exist
        original_path = os.path.join(temp_storage_dir, "org-123", "original.txt")
        copy_path = os.path.join(temp_storage_dir, "org-123", "copy.txt")
        assert os.path.exists(original_path)
        assert os.path.exists(copy_path)

        # Content should be identical
        with open(copy_path, "rb") as f:
            assert f.read() == b"original content"

    @pytest.mark.asyncio
    async def test_exists_returns_true_for_existing(self, local_storage):
        """Test exists returns True for existing file."""
        await local_storage.upload(
            file_data=BytesIO(b"exists"),
            storage_key="org-123/exists.txt",
            content_type="text/plain"
        )

        result = await local_storage.exists("org-123/exists.txt")
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_for_missing(self, local_storage):
        """Test exists returns False for missing file."""
        result = await local_storage.exists("org-123/missing.txt")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_download_url_returns_file_url(self, local_storage, temp_storage_dir):
        """Test get_download_url returns file:// URL for local storage."""
        await local_storage.upload(
            file_data=BytesIO(b"content"),
            storage_key="org-123/public.txt",
            content_type="text/plain"
        )

        url = await local_storage.get_download_url("org-123/public.txt", expires_in=3600)

        assert url.startswith("file://")
        assert "org-123/public.txt" in url


class TestBunnyStorageMocked:
    """Test BunnyStorage with mocked HTTP calls."""

    @pytest.mark.asyncio
    async def test_upload_calls_bunny_api(self):
        """Test upload makes PUT request to Bunny API."""
        from src.services.storage.bunny_storage import BunnyStorage

        storage = BunnyStorage(
            api_key="test-api-key",
            storage_zone="test-zone",
            storage_hostname="storage.bunnycdn.com",
            cdn_hostname="test.b-cdn.net"
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.raise_for_status = MagicMock()
            mock_client.put.return_value = mock_response

            result = await storage.upload(
                file_data=BytesIO(b"test content"),
                storage_key="org-123/test.txt",
                content_type="text/plain",
                is_public=True
            )

            mock_client.put.assert_called_once()
            call_args = mock_client.put.call_args

            # Verify URL
            assert "storage.bunnycdn.com" in call_args[0][0]
            assert "test-zone" in call_args[0][0]
            assert "org-123/test.txt" in call_args[0][0]

            # Verify headers
            headers = call_args[1]["headers"]
            assert headers["AccessKey"] == "test-api-key"
            assert headers["Content-Type"] == "text/plain"

            # Verify result
            assert result.storage_key == "org-123/test.txt"
            assert result.cdn_url == "https://test.b-cdn.net/org-123/test.txt"

    @pytest.mark.asyncio
    async def test_upload_private_no_cdn(self):
        """Test private upload has no CDN URL."""
        from src.services.storage.bunny_storage import BunnyStorage

        storage = BunnyStorage(
            api_key="test-api-key",
            storage_zone="test-zone",
            storage_hostname="storage.bunnycdn.com",
            cdn_hostname="test.b-cdn.net"
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_response = MagicMock()
            mock_response.status_code = 201
            mock_response.raise_for_status = MagicMock()
            mock_client.put.return_value = mock_response

            result = await storage.upload(
                file_data=BytesIO(b"private"),
                storage_key="org-123/private.txt",
                content_type="text/plain",
                is_public=False
            )

            assert result.cdn_url is None

    @pytest.mark.asyncio
    async def test_download_calls_bunny_api(self):
        """Test download makes GET request to Bunny API."""
        from src.services.storage.bunny_storage import BunnyStorage

        storage = BunnyStorage(
            api_key="test-api-key",
            storage_zone="test-zone",
            storage_hostname="storage.bunnycdn.com"
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_response = MagicMock()
            mock_response.content = b"downloaded content"
            mock_response.raise_for_status = MagicMock()
            mock_client.get.return_value = mock_response

            result = await storage.download("org-123/test.txt")

            mock_client.get.assert_called_once()
            assert result.read() == b"downloaded content"

    @pytest.mark.asyncio
    async def test_delete_calls_bunny_api(self):
        """Test delete makes DELETE request to Bunny API."""
        from src.services.storage.bunny_storage import BunnyStorage

        storage = BunnyStorage(
            api_key="test-api-key",
            storage_zone="test-zone",
            storage_hostname="storage.bunnycdn.com"
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.delete.return_value = mock_response

            result = await storage.delete("org-123/test.txt")

            mock_client.delete.assert_called_once()
            assert result is True

    @pytest.mark.asyncio
    async def test_delete_404_returns_true(self):
        """Test delete returns True for 404 (already deleted)."""
        from src.services.storage.bunny_storage import BunnyStorage

        storage = BunnyStorage(
            api_key="test-api-key",
            storage_zone="test-zone",
            storage_hostname="storage.bunnycdn.com"
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_client.delete.return_value = mock_response

            result = await storage.delete("org-123/nonexistent.txt")

            assert result is True

    @pytest.mark.asyncio
    async def test_get_download_url_generates_token(self):
        """Test get_download_url generates signed token URL."""
        from src.services.storage.bunny_storage import BunnyStorage

        storage = BunnyStorage(
            api_key="test-api-key",
            storage_zone="test-zone",
            storage_hostname="storage.bunnycdn.com",
            cdn_hostname="test.b-cdn.net",
            token_key="test-token-key"
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            # Mock the exists() call within get_download_url
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_response = MagicMock()
            mock_response.status_code = 206  # Range request => file exists
            mock_client.get.return_value = mock_response

            url = await storage.get_download_url("org-123/test.txt", expires_in=3600)

            assert "test.b-cdn.net" in url
            assert "org-123/test.txt" in url
            assert "token=" in url
            assert "expires=" in url

    @pytest.mark.asyncio
    async def test_exists_returns_true(self):
        """Test exists returns True when file exists."""
        from src.services.storage.bunny_storage import BunnyStorage

        storage = BunnyStorage(
            api_key="test-api-key",
            storage_zone="test-zone",
            storage_hostname="storage.bunnycdn.com"
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_response = MagicMock()
            mock_response.status_code = 206  # Range request => file exists
            mock_client.get.return_value = mock_response

            result = await storage.exists("org-123/exists.txt")

            assert result is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_on_404(self):
        """Test exists returns False when file doesn't exist."""
        from src.services.storage.bunny_storage import BunnyStorage

        storage = BunnyStorage(
            api_key="test-api-key",
            storage_zone="test-zone",
            storage_hostname="storage.bunnycdn.com"
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_client.get.return_value = mock_response

            result = await storage.exists("org-123/missing.txt")

            assert result is False
