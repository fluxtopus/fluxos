"""Unit tests for file rename/move with optional new_folder."""

import pytest
from unittest.mock import MagicMock
from datetime import datetime
import uuid

from src.services.file_service import FileService, FileNotFoundError


class MockFile:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", str(uuid.uuid4()))
        self.organization_id = kwargs.get("organization_id", "org-1")
        self.name = kwargs.get("name", "original.png")
        self.storage_key = kwargs.get("storage_key", "org-1/abc_original.png")
        self.content_type = kwargs.get("content_type", "image/png")
        self.size_bytes = kwargs.get("size_bytes", 1024)
        self.checksum_sha256 = kwargs.get("checksum_sha256", "abc123")
        self.folder_path = kwargs.get("folder_path", "/photos")
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
        self.cdn_url = kwargs.get("cdn_url")


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    return db


@pytest.fixture
def mock_storage():
    return MagicMock()


@pytest.fixture
def file_service(mock_db, mock_storage):
    return FileService(mock_db, mock_storage)


FILE_ID = str(uuid.uuid4())
ORG_ID = str(uuid.uuid4())


@pytest.fixture
def sample_file():
    return MockFile(
        id=FILE_ID,
        organization_id=ORG_ID,
        name="original.png",
        folder_path="/photos",
    )


class TestMoveFileRenameOnly:
    """Test renaming a file without changing its folder."""

    def test_rename_only_keeps_folder(self, file_service, mock_db, sample_file):
        mock_db.query.return_value.filter.return_value.first.return_value = sample_file

        result = file_service.move_file(FILE_ID, ORG_ID, new_name="renamed.png")

        assert result.name == "renamed.png"
        assert result.folder_path == "/photos"

    def test_rename_only_updates_timestamp(self, file_service, mock_db, sample_file):
        mock_db.query.return_value.filter.return_value.first.return_value = sample_file

        file_service.move_file(FILE_ID, ORG_ID, new_name="renamed.png")

        assert sample_file.updated_at is not None
        mock_db.commit.assert_called_once()


class TestMoveFileMoveFolderOnly:
    """Test moving a file to a new folder without renaming."""

    def test_move_only_changes_folder(self, file_service, mock_db, sample_file):
        mock_db.query.return_value.filter.return_value.first.return_value = sample_file

        result = file_service.move_file(FILE_ID, ORG_ID, new_folder="/documents")

        assert result.folder_path == "/documents"
        assert result.name == "original.png"

    def test_move_normalizes_folder_path(self, file_service, mock_db, sample_file):
        mock_db.query.return_value.filter.return_value.first.return_value = sample_file

        result = file_service.move_file(FILE_ID, ORG_ID, new_folder="documents/")

        assert result.folder_path == "/documents"

    def test_move_to_root(self, file_service, mock_db, sample_file):
        mock_db.query.return_value.filter.return_value.first.return_value = sample_file

        result = file_service.move_file(FILE_ID, ORG_ID, new_folder="/")

        assert result.folder_path == "/"


class TestMoveFileMovePlusRename:
    """Test moving and renaming a file simultaneously."""

    def test_move_and_rename(self, file_service, mock_db, sample_file):
        mock_db.query.return_value.filter.return_value.first.return_value = sample_file

        result = file_service.move_file(
            FILE_ID, ORG_ID, new_folder="/documents", new_name="report.png"
        )

        assert result.folder_path == "/documents"
        assert result.name == "report.png"


class TestMoveFileValidation:
    """Test validation when neither new_folder nor new_name is provided."""

    def test_neither_provided_raises_value_error(self, file_service):
        with pytest.raises(ValueError, match="At least one of new_folder or new_name"):
            file_service.move_file(FILE_ID, ORG_ID)

    def test_both_none_raises_value_error(self, file_service):
        with pytest.raises(ValueError, match="At least one of new_folder or new_name"):
            file_service.move_file(FILE_ID, ORG_ID, new_folder=None, new_name=None)


class TestMoveFileNotFound:
    """Test file not found scenario."""

    def test_file_not_found_raises(self, file_service, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(FileNotFoundError, match="File not found"):
            file_service.move_file(FILE_ID, ORG_ID, new_name="renamed.png")
