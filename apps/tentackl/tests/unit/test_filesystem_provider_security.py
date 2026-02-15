"""Security tests for MCP filesystem provider path handling."""

import pytest

from src.mcp.filesystem_provider import FileSystemProvider


@pytest.mark.asyncio
async def test_read_file_rejects_path_traversal(tmp_path):
    provider = FileSystemProvider({"base_path": str(tmp_path)})
    await provider.initialize()

    result = await provider.execute_tool("read_file", {"path": "../outside.txt"})
    assert result["success"] is False
    assert "escapes" in result["error"].lower()


@pytest.mark.asyncio
async def test_write_file_rejects_path_traversal(tmp_path):
    provider = FileSystemProvider({"base_path": str(tmp_path)})
    await provider.initialize()

    result = await provider.execute_tool("write_file", {"path": "../../etc/passwd", "content": "x"})
    assert result["success"] is False
    assert "escapes" in result["error"].lower()
