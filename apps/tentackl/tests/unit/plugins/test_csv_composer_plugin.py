"""Unit tests for csv_composer_plugin."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.plugins.csv_composer_plugin import csv_composer_handler, _generate_csv, _csv_to_records


# ---------------------------------------------------------------------------
# Helper: _generate_csv
# ---------------------------------------------------------------------------


class TestGenerateCsv:
    def test_list_of_dicts(self):
        data = [{"name": "Alice", "age": "30"}, {"name": "Bob", "age": "25"}]
        result = _generate_csv(data)
        assert "name,age" in result
        assert "Alice,30" in result
        assert "Bob,25" in result

    def test_list_of_lists_with_headers(self):
        data = [["Alice", 30], ["Bob", 25]]
        result = _generate_csv(data, headers=["name", "age"])
        assert "name,age" in result
        assert "Alice,30" in result

    def test_list_of_lists_without_headers(self):
        data = [["Alice", 30], ["Bob", 25]]
        result = _generate_csv(data)
        # No header row, just data
        assert "Alice,30" in result

    def test_empty_data(self):
        result = _generate_csv([])
        assert result == ""

    def test_custom_delimiter(self):
        data = [{"a": "1", "b": "2"}]
        result = _generate_csv(data, delimiter="\t")
        assert "a\tb" in result
        assert "1\t2" in result


class TestCsvToRecords:
    def test_basic_parsing(self):
        csv_text = "name,age\nAlice,30\nBob,25\n"
        records = _csv_to_records(csv_text)
        assert len(records) == 2
        assert records[0]["name"] == "Alice"
        assert records[1]["age"] == "25"


# ---------------------------------------------------------------------------
# Handler: csv_composer_handler
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_upload():
    """Mock Den upload_file_handler."""
    with patch("src.plugins.den_file_plugin.upload_file_handler", new_callable=AsyncMock) as m:
        m.return_value = {
            "file_id": "file-123",
            "filename": "test.csv",
            "url": "https://den.example.com/files/file-123",
            "cdn_url": "https://cdn.example.com/file-123",
            "size_bytes": 42,
        }
        yield m


@pytest.mark.asyncio
async def test_list_of_dicts_uploads_and_returns_structured_data(mock_upload):
    """List of dicts → correct CSV + Den upload + StructuredDataContent output."""
    data = [{"name": "Alice", "age": "30"}, {"name": "Bob", "age": "25"}]
    result = await csv_composer_handler({"data": data, "org_id": "org-1"})

    assert result["file_id"] == "file-123"
    assert result["content_type"] == "text/csv"
    assert result["object_type"] == "csv_export"
    assert len(result["data"]) == 2
    assert result["data"][0]["name"] == "Alice"
    assert result["total_count"] == 2

    # Verify upload was called with CSV content
    call_args = mock_upload.call_args[0][0]
    assert call_args["content_type"] == "text/csv"
    assert "Alice" in call_args["content"]
    assert call_args["org_id"] == "org-1"


@pytest.mark.asyncio
async def test_list_of_lists_with_explicit_headers(mock_upload):
    """List of lists → explicit headers."""
    data = [["Alice", 30], ["Bob", 25]]
    result = await csv_composer_handler({
        "data": data,
        "headers": ["name", "age"],
        "org_id": "org-1",
    })

    assert result["file_id"] == "file-123"
    assert result["object_type"] == "csv_export"
    # Preview should parse with headers
    assert result["total_count"] == 2


@pytest.mark.asyncio
async def test_raw_csv_text_passthrough(mock_upload):
    """Raw csv_text passthrough."""
    csv_text = "name,age\nAlice,30\nBob,25\n"
    result = await csv_composer_handler({
        "csv_text": csv_text,
        "org_id": "org-1",
    })

    assert result["file_id"] == "file-123"
    assert result["object_type"] == "csv_export"
    call_args = mock_upload.call_args[0][0]
    assert call_args["content"] == csv_text


@pytest.mark.asyncio
async def test_missing_data_and_csv_text_returns_error():
    """Missing data + csv_text → error."""
    result = await csv_composer_handler({"org_id": "org-1"})
    assert "error" in result
    assert "Either 'data' or 'csv_text' is required" in result["error"]


@pytest.mark.asyncio
async def test_missing_org_id_returns_error():
    """Missing org_id → error."""
    result = await csv_composer_handler({"data": [{"a": 1}]})
    assert "error" in result
    assert "org_id is required" in result["error"]


@pytest.mark.asyncio
async def test_preview_limit_truncation(mock_upload):
    """Preview limit truncation."""
    data = [{"i": str(n)} for n in range(200)]
    result = await csv_composer_handler({
        "data": data,
        "org_id": "org-1",
        "preview_limit": 5,
    })

    assert result["total_count"] == 200
    assert len(result["data"]) == 5


@pytest.mark.asyncio
async def test_filename_generation(mock_upload):
    """Filename generation from title."""
    result = await csv_composer_handler({
        "data": [{"a": "1"}],
        "org_id": "org-1",
        "title": "My Report 2024",
    })

    call_args = mock_upload.call_args[0][0]
    assert call_args["filename"] == "my-report-2024.csv"


@pytest.mark.asyncio
async def test_filename_sanitization(mock_upload):
    """Filename with special characters gets sanitized."""
    result = await csv_composer_handler({
        "data": [{"a": "1"}],
        "org_id": "org-1",
        "title": "Report: Q1 (2024) <test>",
    })

    call_args = mock_upload.call_args[0][0]
    # Only alphanumeric, -, _ survive
    assert ".csv" in call_args["filename"]
    assert ":" not in call_args["filename"]
    assert "<" not in call_args["filename"]


@pytest.mark.asyncio
async def test_explicit_filename_used(mock_upload):
    """Explicit filename is used without sanitization."""
    result = await csv_composer_handler({
        "data": [{"a": "1"}],
        "org_id": "org-1",
        "filename": "my-custom-file.csv",
    })

    call_args = mock_upload.call_args[0][0]
    assert call_args["filename"] == "my-custom-file.csv"


@pytest.mark.asyncio
async def test_csv_extension_added(mock_upload):
    """Extension is added if missing."""
    result = await csv_composer_handler({
        "data": [{"a": "1"}],
        "org_id": "org-1",
        "filename": "myfile",
    })

    call_args = mock_upload.call_args[0][0]
    assert call_args["filename"] == "myfile.csv"


@pytest.mark.asyncio
async def test_custom_delimiter(mock_upload):
    """Custom delimiter."""
    data = [{"a": "1", "b": "2"}]
    result = await csv_composer_handler({
        "data": data,
        "org_id": "org-1",
        "delimiter": "\t",
    })

    call_args = mock_upload.call_args[0][0]
    assert "1\t2" in call_args["content"]


@pytest.mark.asyncio
async def test_json_string_data_parsing(mock_upload):
    """JSON string data parsing."""
    import json
    data = json.dumps([{"name": "Alice"}, {"name": "Bob"}])
    result = await csv_composer_handler({
        "data": data,
        "org_id": "org-1",
    })

    assert result["file_id"] == "file-123"
    assert result["total_count"] == 2


@pytest.mark.asyncio
async def test_den_upload_failure_propagation():
    """Den upload failure propagation."""
    with patch("src.plugins.den_file_plugin.upload_file_handler", new_callable=AsyncMock) as m:
        m.return_value = {"error": "Upload failed: connection timeout"}
        result = await csv_composer_handler({
            "data": [{"a": "1"}],
            "org_id": "org-1",
        })

        assert "error" in result
        assert "Upload failed" in result["error"]


@pytest.mark.asyncio
async def test_context_org_id_extraction(mock_upload):
    """org_id extracted from context."""
    ctx = MagicMock()
    ctx.org_id = "org-from-context"
    ctx.workflow_id = "wf-1"
    ctx.agent_id = "agent-1"

    result = await csv_composer_handler({"data": [{"a": "1"}]}, context=ctx)

    call_args = mock_upload.call_args[0][0]
    assert call_args["org_id"] == "org-from-context"


@pytest.mark.asyncio
async def test_no_preview_when_disabled(mock_upload):
    """include_preview=false skips data preview."""
    result = await csv_composer_handler({
        "data": [{"a": "1"}],
        "org_id": "org-1",
        "include_preview": False,
    })

    assert result["data"] == []
    assert result["total_count"] == 0
