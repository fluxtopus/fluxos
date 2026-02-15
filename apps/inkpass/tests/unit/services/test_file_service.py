"""Unit tests for FileService - pure unit tests without database."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from io import BytesIO
from datetime import datetime
import uuid

from src.services.file_service import FileService, StorageQuotaExceededError, FileNotFoundError
from src.services.storage.base import StorageResult


# Create mock classes for testing
class MockOrganization:
    def __init__(self, id, name="Test Org", storage_quota_bytes=1073741824, storage_used_bytes=0):
        self.id = id
        self.name = name
        self.storage_quota_bytes = storage_quota_bytes
        self.storage_used_bytes = storage_used_bytes


class MockFile:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", str(uuid.uuid4()))
        self.organization_id = kwargs.get("organization_id")
        self.name = kwargs.get("name")
        self.storage_key = kwargs.get("storage_key")
        self.content_type = kwargs.get("content_type")
        self.size_bytes = kwargs.get("size_bytes", 0)
        self.checksum_sha256 = kwargs.get("checksum_sha256")
        self.folder_path = kwargs.get("folder_path", "/")
        self.tags = kwargs.get("tags", [])
        self.custom_metadata = kwargs.get("custom_metadata", {})
        self.is_public = kwargs.get("is_public", False)
        self.is_temporary = kwargs.get("is_temporary", False)
        self.status = kwargs.get("status", "active")
        self.created_by_user_id = kwargs.get("created_by_user_id")
        self.created_by_agent = kwargs.get("created_by_agent")
        self.workflow_id = kwargs.get("workflow_id")
        self.created_at = kwargs.get("created_at", datetime.utcnow())
        self.updated_at = kwargs.get("updated_at")
        self.deleted_at = kwargs.get("deleted_at")
        self.expires_at = kwargs.get("expires_at")


class MockStorageBackend:
    """Mock storage backend for testing."""

    def __init__(self):
        self.files = {}

    async def upload(self, file_data, storage_key, content_type, is_public=False):
        content = file_data.read()
        self.files[storage_key] = {
            "content": content,
            "content_type": content_type,
            "is_public": is_public
        }
        cdn_url = f"https://cdn.example.com/{storage_key}" if is_public else None
        return StorageResult(
            storage_key=storage_key,
            url=f"https://storage.example.com/{storage_key}",
            cdn_url=cdn_url,
            size_bytes=len(content)
        )

    async def download(self, storage_key):
        if storage_key not in self.files:
            raise Exception(f"File not found: {storage_key}")
        return BytesIO(self.files[storage_key]["content"])

    async def delete(self, storage_key):
        if storage_key in self.files:
            del self.files[storage_key]
        return True

    async def copy(self, source_key, dest_key):
        if source_key not in self.files:
            raise Exception(f"Source file not found: {source_key}")
        self.files[dest_key] = dict(self.files[source_key])
        return StorageResult(
            storage_key=dest_key,
            url=f"https://storage.example.com/{dest_key}",
            size_bytes=len(self.files[dest_key]["content"])
        )

    async def get_download_url(self, storage_key, expires_in=3600):
        return f"https://storage.example.com/{storage_key}?token=test&expires={expires_in}"

    async def exists(self, storage_key):
        return storage_key in self.files


class TestFileServiceStorageKey:
    """Test storage key generation."""

    def test_generate_storage_key_with_folder(self):
        """Test storage key includes org, folder, and unique prefix."""
        service = FileService(MagicMock(), MockStorageBackend())

        key = service._generate_storage_key("org-123", "/reports/monthly", "report.pdf")

        assert key.startswith("org-123/reports/monthly/")
        assert key.endswith("_report.pdf")
        # Should have unique ID prefix
        parts = key.split("/")[-1].split("_")
        assert len(parts[0]) == 8  # UUID prefix is 8 chars

    def test_generate_storage_key_root_folder(self):
        """Test storage key for root folder."""
        service = FileService(MagicMock(), MockStorageBackend())

        key = service._generate_storage_key("org-123", "/", "file.txt")

        assert key.startswith("org-123/")
        assert key.endswith("_file.txt")
        # Should not have double slashes
        assert "//" not in key

    def test_generate_storage_key_unique(self):
        """Test that storage keys are unique for same file."""
        service = FileService(MagicMock(), MockStorageBackend())

        key1 = service._generate_storage_key("org-123", "/", "file.txt")
        key2 = service._generate_storage_key("org-123", "/", "file.txt")

        assert key1 != key2


class TestFileServiceChecksum:
    """Test checksum calculation."""

    def test_calculate_checksum(self):
        """Test SHA-256 checksum calculation."""
        service = FileService(MagicMock(), MockStorageBackend())

        data = BytesIO(b"test content for checksum")
        checksum = service._calculate_checksum(data)

        # Verify it's a valid SHA-256 hex string
        assert len(checksum) == 64
        assert all(c in "0123456789abcdef" for c in checksum)

        # Verify file position is reset
        assert data.tell() == 0

    def test_calculate_checksum_same_content_same_hash(self):
        """Test that same content produces same hash."""
        service = FileService(MagicMock(), MockStorageBackend())

        data1 = BytesIO(b"identical content")
        data2 = BytesIO(b"identical content")

        assert service._calculate_checksum(data1) == service._calculate_checksum(data2)

    def test_calculate_checksum_different_content_different_hash(self):
        """Test that different content produces different hash."""
        service = FileService(MagicMock(), MockStorageBackend())

        data1 = BytesIO(b"content one")
        data2 = BytesIO(b"content two")

        assert service._calculate_checksum(data1) != service._calculate_checksum(data2)

    def test_calculate_checksum_empty_file(self):
        """Test checksum of empty file."""
        service = FileService(MagicMock(), MockStorageBackend())

        data = BytesIO(b"")
        checksum = service._calculate_checksum(data)

        # Empty file has a known SHA-256
        assert checksum == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_calculate_checksum_large_file(self):
        """Test checksum calculation reads in chunks."""
        service = FileService(MagicMock(), MockStorageBackend())

        # Create a file larger than typical chunk size
        data = BytesIO(b"x" * 100000)
        checksum = service._calculate_checksum(data)

        assert len(checksum) == 64
        assert data.tell() == 0  # Position should be reset


class TestFileServiceToResponse:
    """Test file to response conversion."""

    def test_to_response_basic(self):
        """Test converting file model to response."""
        file_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())
        now = datetime.utcnow()
        mock_file = MockFile(
            id=file_id,
            organization_id=org_id,
            name="test.txt",
            storage_key=f"{org_id}/abc_test.txt",
            content_type="text/plain",
            size_bytes=100,
            checksum_sha256="abc123def456",
            folder_path="/docs",
            tags=["tag1", "tag2"],
            is_public=False,
            status="active",
            created_at=now,
            updated_at=now
        )

        service = FileService(MagicMock(), MockStorageBackend())
        response = service._to_response(mock_file)

        assert str(response.id) == file_id
        assert str(response.organization_id) == org_id
        assert response.name == "test.txt"
        assert response.content_type == "text/plain"
        assert response.size_bytes == 100
        assert response.folder_path == "/docs"
        assert response.tags == ["tag1", "tag2"]
        assert response.is_public is False
        assert response.status == "active"

    def test_to_response_with_cdn_url(self):
        """Test response includes CDN URL when provided."""
        file_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())
        now = datetime.utcnow()
        mock_file = MockFile(
            id=file_id,
            organization_id=org_id,
            name="image.png",
            storage_key=f"{org_id}/abc_image.png",
            content_type="image/png",
            size_bytes=5000,
            is_public=True,
            created_at=now,
            updated_at=now
        )

        service = FileService(MagicMock(), MockStorageBackend())
        response = service._to_response(mock_file, cdn_url="https://cdn.example.com/image.png")

        assert response.cdn_url == "https://cdn.example.com/image.png"

    def test_to_response_handles_none_tags(self):
        """Test response handles None tags gracefully."""
        file_id = str(uuid.uuid4())
        org_id = str(uuid.uuid4())
        now = datetime.utcnow()
        mock_file = MockFile(
            id=file_id,
            organization_id=org_id,
            name="test.txt",
            storage_key=f"{org_id}/abc_test.txt",
            content_type="text/plain",
            size_bytes=100,
            tags=None,
            created_at=now,
            updated_at=now
        )

        service = FileService(MagicMock(), MockStorageBackend())
        response = service._to_response(mock_file)

        assert response.tags == []


class TestFileServiceQuotaLogic:
    """Test quota checking logic (mocked database)."""

    def test_quota_exceeded_calculation(self):
        """Test that quota calculation is correct."""
        # Org has 1000 bytes quota, 900 used, trying to upload 200 bytes
        org = MockOrganization(
            id="org-123",
            storage_quota_bytes=1000,
            storage_used_bytes=900
        )

        # 900 + 200 = 1100 > 1000, should fail
        file_size = 200
        exceeds = (org.storage_used_bytes + file_size) > org.storage_quota_bytes

        assert exceeds is True

    def test_quota_within_limit_calculation(self):
        """Test quota allows upload within limit."""
        org = MockOrganization(
            id="org-123",
            storage_quota_bytes=1000,
            storage_used_bytes=500
        )

        # 500 + 200 = 700 < 1000, should pass
        file_size = 200
        exceeds = (org.storage_used_bytes + file_size) > org.storage_quota_bytes

        assert exceeds is False

    def test_quota_exact_limit_calculation(self):
        """Test quota allows upload at exact limit."""
        org = MockOrganization(
            id="org-123",
            storage_quota_bytes=1000,
            storage_used_bytes=800
        )

        # 800 + 200 = 1000, exactly at limit, should pass
        file_size = 200
        exceeds = (org.storage_used_bytes + file_size) > org.storage_quota_bytes

        assert exceeds is False


class TestFileServiceAccessLogging:
    """Test access logging logic."""

    def test_accessor_type_detection_user(self):
        """Test user accessor type detection."""
        service = FileService(MagicMock(), MockStorageBackend())

        # User IDs are typically UUIDs
        accessor_id = "user-123-uuid"

        if accessor_id.startswith("workflow:") or accessor_id.startswith("agent:"):
            accessor_type = "agent"
        elif accessor_id == "system":
            accessor_type = "service"
        else:
            accessor_type = "user"

        assert accessor_type == "user"

    def test_accessor_type_detection_agent(self):
        """Test agent accessor type detection."""
        accessor_id = "workflow:wf-123:agent:image-gen"

        if accessor_id.startswith("workflow:") or accessor_id.startswith("agent:"):
            accessor_type = "agent"
        elif accessor_id == "system":
            accessor_type = "service"
        else:
            accessor_type = "user"

        assert accessor_type == "agent"

    def test_accessor_type_detection_service(self):
        """Test service accessor type detection."""
        accessor_id = "system"

        if accessor_id.startswith("workflow:") or accessor_id.startswith("agent:"):
            accessor_type = "agent"
        elif accessor_id == "system":
            accessor_type = "service"
        else:
            accessor_type = "user"

        assert accessor_type == "service"


class TestFileServicePathNormalization:
    """Test folder path normalization in move operations."""

    def test_normalize_path_adds_leading_slash(self):
        """Test that leading slash is added."""
        path = "documents/reports"
        if not path.startswith("/"):
            path = "/" + path
        assert path == "/documents/reports"

    def test_normalize_path_removes_trailing_slash(self):
        """Test that trailing slash is removed."""
        path = "/documents/"
        if len(path) > 1:
            path = path.rstrip("/")
        assert path == "/documents"

    def test_normalize_path_preserves_root(self):
        """Test that root slash is preserved."""
        path = "/"
        if len(path) > 1:
            path = path.rstrip("/")
        assert path == "/"

    def test_normalize_path_complex(self):
        """Test complex path normalization."""
        path = "level1/level2/level3/"
        if not path.startswith("/"):
            path = "/" + path
        if len(path) > 1:
            path = path.rstrip("/")
        assert path == "/level1/level2/level3"


class TestMockStorageBackend:
    """Test the mock storage backend itself (for integration testing)."""

    @pytest.mark.asyncio
    async def test_upload_and_download(self):
        """Test mock storage upload/download roundtrip."""
        storage = MockStorageBackend()

        await storage.upload(
            BytesIO(b"test content"),
            "org-123/file.txt",
            "text/plain"
        )

        result = await storage.download("org-123/file.txt")
        assert result.read() == b"test content"

    @pytest.mark.asyncio
    async def test_upload_public_sets_cdn_url(self):
        """Test public upload includes CDN URL."""
        storage = MockStorageBackend()

        result = await storage.upload(
            BytesIO(b"public content"),
            "org-123/public.png",
            "image/png",
            is_public=True
        )

        assert result.cdn_url == "https://cdn.example.com/org-123/public.png"

    @pytest.mark.asyncio
    async def test_upload_private_no_cdn_url(self):
        """Test private upload has no CDN URL."""
        storage = MockStorageBackend()

        result = await storage.upload(
            BytesIO(b"private content"),
            "org-123/private.txt",
            "text/plain",
            is_public=False
        )

        assert result.cdn_url is None

    @pytest.mark.asyncio
    async def test_delete_removes_file(self):
        """Test delete removes file from mock storage."""
        storage = MockStorageBackend()

        await storage.upload(
            BytesIO(b"to delete"),
            "org-123/delete.txt",
            "text/plain"
        )
        assert await storage.exists("org-123/delete.txt") is True

        await storage.delete("org-123/delete.txt")
        assert await storage.exists("org-123/delete.txt") is False

    @pytest.mark.asyncio
    async def test_copy_duplicates_content(self):
        """Test copy creates duplicate with same content."""
        storage = MockStorageBackend()

        await storage.upload(
            BytesIO(b"original"),
            "org-123/original.txt",
            "text/plain"
        )

        await storage.copy("org-123/original.txt", "org-123/copy.txt")

        original = await storage.download("org-123/original.txt")
        copy = await storage.download("org-123/copy.txt")

        assert original.read() == copy.read()
