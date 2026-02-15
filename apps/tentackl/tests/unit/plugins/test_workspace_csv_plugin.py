"""Unit tests for workspace_csv_plugin."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from contextlib import asynccontextmanager

from src.plugins.workspace_csv_plugin import (
    workspace_export_csv_handler,
    workspace_import_csv_handler,
    set_database,
    _flatten_object,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _mock_session_ctx():
    """Async context manager that yields a mock session."""
    yield MagicMock()


@pytest.fixture
def mock_workspace_service():
    """Mock WorkspaceService with a fake database."""
    service = AsyncMock()
    mock_db = MagicMock()
    mock_db.get_session.return_value = _mock_session_ctx()

    set_database(mock_db)

    with patch("src.plugins.workspace_csv_plugin.WorkspaceService", return_value=service):
        yield service


@pytest.fixture
def mock_upload():
    """Mock Den upload_file_handler."""
    with patch("src.plugins.den_file_plugin.upload_file_handler", new_callable=AsyncMock) as m:
        m.return_value = {
            "file_id": "file-456",
            "filename": "export.csv",
            "url": "https://den.example.com/files/file-456",
            "cdn_url": "https://cdn.example.com/file-456",
            "size_bytes": 100,
        }
        yield m


@pytest.fixture
def sample_objects():
    """Sample workspace objects."""
    return [
        {
            "id": "obj-1",
            "type": "contact",
            "created_at": "2024-01-01T00:00:00",
            "tags": ["vip"],
            "data": {"name": "Alice", "email": "alice@example.com", "age": 30},
        },
        {
            "id": "obj-2",
            "type": "contact",
            "created_at": "2024-01-02T00:00:00",
            "tags": [],
            "data": {"name": "Bob", "email": "bob@example.com", "age": 25},
        },
    ]


# ---------------------------------------------------------------------------
# Helper: _flatten_object
# ---------------------------------------------------------------------------


class TestFlattenObject:
    def test_flattens_data_fields(self):
        obj = {
            "id": "obj-1",
            "type": "contact",
            "created_at": "2024-01-01",
            "tags": ["a"],
            "data": {"name": "Alice", "age": 30},
        }
        flat = _flatten_object(obj)
        assert flat["id"] == "obj-1"
        assert flat["name"] == "Alice"
        assert flat["age"] == 30

    def test_without_metadata(self):
        obj = {
            "id": "obj-1",
            "type": "contact",
            "created_at": "2024-01-01",
            "data": {"name": "Alice"},
        }
        flat = _flatten_object(obj, include_metadata=False)
        assert "id" not in flat
        assert "created_at" not in flat
        assert flat["name"] == "Alice"

    def test_nested_dict_serialized(self):
        obj = {
            "id": "1",
            "type": "t",
            "created_at": "",
            "data": {"name": "A", "address": {"city": "NY"}},
        }
        flat = _flatten_object(obj)
        assert '"city"' in flat["address"]


# ---------------------------------------------------------------------------
# Handler: workspace_export_csv_handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_query_flatten_csv_upload(mock_workspace_service, mock_upload, sample_objects):
    """Export: query → flatten → CSV → Den upload."""
    mock_workspace_service.query.return_value = sample_objects

    result = await workspace_export_csv_handler({
        "org_id": "org-1",
        "type": "contact",
    })

    assert result["rows_exported"] == 2
    assert result["object_type"] == "csv_export"
    assert result["file_id"] == "file-456"
    assert len(result["data"]) == 2

    # Verify workspace service was queried
    mock_workspace_service.query.assert_called_once()

    # Verify CSV was uploaded
    call_args = mock_upload.call_args[0][0]
    assert call_args["content_type"] == "text/csv"
    assert "Alice" in call_args["content"]
    assert "Bob" in call_args["content"]


@pytest.mark.asyncio
async def test_export_with_column_selection(mock_workspace_service, mock_upload, sample_objects):
    """Export with specific column selection."""
    mock_workspace_service.query.return_value = sample_objects

    result = await workspace_export_csv_handler({
        "org_id": "org-1",
        "type": "contact",
        "columns": ["name", "email"],
    })

    call_args = mock_upload.call_args[0][0]
    csv_content = call_args["content"]
    # Should have id,type,created_at,tags,name,email (metadata + selected columns)
    assert "name" in csv_content
    assert "email" in csv_content


@pytest.mark.asyncio
async def test_export_with_metadata_disabled(mock_workspace_service, mock_upload, sample_objects):
    """Export without metadata columns."""
    mock_workspace_service.query.return_value = sample_objects

    result = await workspace_export_csv_handler({
        "org_id": "org-1",
        "type": "contact",
        "include_metadata": False,
    })

    call_args = mock_upload.call_args[0][0]
    csv_content = call_args["content"]
    lines = csv_content.strip().split("\n")
    header = lines[0]
    # Metadata columns should not be present
    assert "id" not in header.split(",")
    assert "created_at" not in header.split(",")


@pytest.mark.asyncio
async def test_export_empty_results(mock_workspace_service):
    """Export with no matching objects."""
    mock_workspace_service.query.return_value = []

    result = await workspace_export_csv_handler({
        "org_id": "org-1",
        "type": "nonexistent",
    })

    assert result["rows_exported"] == 0
    assert result["object_type"] == "csv_export"
    assert result["data"] == []


@pytest.mark.asyncio
async def test_export_missing_org_id():
    """Export missing org_id → error."""
    result = await workspace_export_csv_handler({"type": "contact"})
    assert "error" in result
    assert "org_id" in result["error"]


# ---------------------------------------------------------------------------
# Handler: workspace_import_csv_handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_from_csv_text(mock_workspace_service):
    """Import from csv_text creates workspace objects."""
    mock_workspace_service.create.return_value = {"id": "new-1", "type": "contact", "data": {"name": "Alice"}}

    csv_text = "name,email\nAlice,alice@test.com\nBob,bob@test.com\n"

    result = await workspace_import_csv_handler({
        "org_id": "org-1",
        "type": "contact",
        "csv_text": csv_text,
    })

    assert result["objects_created"] == 2
    assert result["objects_skipped"] == 0
    assert result["object_type"] == "csv_import"
    assert mock_workspace_service.create.call_count == 2


@pytest.mark.asyncio
async def test_import_from_den_file(mock_workspace_service):
    """Import from Den file_id."""
    mock_workspace_service.create.return_value = {"id": "new-1", "type": "contact", "data": {"name": "Alice"}}

    with patch("src.plugins.den_file_plugin.download_file_handler", new_callable=AsyncMock) as mock_download:
        mock_download.return_value = {
            "content": "name,email\nAlice,alice@test.com\n",
            "size_bytes": 30,
        }

        result = await workspace_import_csv_handler({
            "org_id": "org-1",
            "type": "contact",
            "file_id": "file-789",
        })

        assert result["objects_created"] == 1
        mock_download.assert_called_once()


@pytest.mark.asyncio
async def test_import_with_column_mapping(mock_workspace_service):
    """Import with column mapping renames."""
    mock_workspace_service.create.return_value = {"id": "new-1", "type": "contact", "data": {}}

    csv_text = "First Name,Email Address\nAlice,alice@test.com\n"

    result = await workspace_import_csv_handler({
        "org_id": "org-1",
        "type": "contact",
        "csv_text": csv_text,
        "column_mapping": {"First Name": "name", "Email Address": "email"},
    })

    assert result["objects_created"] == 1
    # Verify the mapped columns were passed to create
    create_call = mock_workspace_service.create.call_args
    assert create_call.kwargs["data"]["name"] == "Alice"
    assert create_call.kwargs["data"]["email"] == "alice@test.com"


@pytest.mark.asyncio
async def test_import_dry_run(mock_workspace_service):
    """Import dry run parses but doesn't create."""
    csv_text = "name,age\nAlice,30\nBob,25\n"

    result = await workspace_import_csv_handler({
        "org_id": "org-1",
        "type": "contact",
        "csv_text": csv_text,
        "dry_run": True,
    })

    assert result["dry_run"] is True
    assert result["rows_parsed"] == 2
    assert result["objects_created"] == 0
    assert result["columns"] == ["name", "age"]
    # Service.create should NOT be called
    mock_workspace_service.create.assert_not_called()


@pytest.mark.asyncio
async def test_import_missing_org_id():
    """Import missing org_id → error."""
    result = await workspace_import_csv_handler({
        "type": "contact",
        "csv_text": "a,b\n1,2\n",
    })
    assert "error" in result
    assert "org_id" in result["error"]


@pytest.mark.asyncio
async def test_import_missing_type():
    """Import missing type → error."""
    result = await workspace_import_csv_handler({
        "org_id": "org-1",
        "csv_text": "a,b\n1,2\n",
    })
    assert "error" in result
    assert "type" in result["error"]


@pytest.mark.asyncio
async def test_import_missing_csv_source():
    """Import with neither csv_text nor file_id → error."""
    result = await workspace_import_csv_handler({
        "org_id": "org-1",
        "type": "contact",
    })
    assert "error" in result
    assert "csv_text" in result["error"] or "file_id" in result["error"]


@pytest.mark.asyncio
async def test_import_skips_empty_rows(mock_workspace_service):
    """Import skips empty rows by default."""
    mock_workspace_service.create.return_value = {"id": "new-1", "type": "t", "data": {}}

    csv_text = "name,email\nAlice,alice@test.com\n,,\nBob,bob@test.com\n"

    result = await workspace_import_csv_handler({
        "org_id": "org-1",
        "type": "contact",
        "csv_text": csv_text,
    })

    # 2 real rows, 1 empty row skipped
    assert result["objects_created"] == 2
    assert mock_workspace_service.create.call_count == 2
