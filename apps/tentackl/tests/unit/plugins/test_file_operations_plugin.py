"""Unit tests for file_operations_plugin path traversal protection (SEC-007).

Tests the _validate_path() function and all 6 handlers to verify:
- '..' segments are rejected
- Absolute paths outside BASE_DIR are rejected
- Symlinks pointing outside BASE_DIR are rejected
- Relative paths are resolved against BASE_DIR
- Valid paths within BASE_DIR are accepted
- All handlers enforce path validation
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.plugins.file_operations_plugin import (
    _validate_path,
    _get_base_dir,
    write_csv_handler,
    csv_from_text_handler,
    write_json_handler,
    write_text_handler,
    read_file_handler,
    list_files_handler,
)


@pytest.fixture
def base_dir(tmp_path):
    """Create a temporary base directory for file operations."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    with patch("src.plugins.file_operations_plugin._get_base_dir", return_value=data_dir):
        yield data_dir


@pytest.fixture
def base_dir_with_files(base_dir):
    """Create base directory with some test files."""
    # Create a subdirectory with files
    sub = base_dir / "subdir"
    sub.mkdir()
    (base_dir / "test.txt").write_text("hello")
    (sub / "nested.txt").write_text("nested content")
    (base_dir / "data.json").write_text('{"key": "value"}')
    (base_dir / "data.csv").write_text("a,b\n1,2\n3,4\n")
    return base_dir


# ===========================================================================
# _validate_path tests
# ===========================================================================


class TestValidatePath:
    """Tests for the _validate_path() function."""

    def test_rejects_empty_path(self, base_dir):
        """Empty paths should return an error."""
        path, error = _validate_path("")
        assert path is None
        assert error == "No file_path provided"

    def test_rejects_dotdot_in_path(self, base_dir):
        """Paths with '..' segments should be rejected."""
        path, error = _validate_path("../../../etc/passwd")
        assert path is None
        assert "'..' segments are forbidden" in error

    def test_rejects_dotdot_in_middle(self, base_dir):
        """'..' in the middle of a path should be rejected."""
        path, error = _validate_path("subdir/../../etc/passwd")
        assert path is None
        assert "'..' segments are forbidden" in error

    def test_rejects_absolute_path_outside_base(self, base_dir):
        """Absolute paths outside BASE_DIR should be rejected."""
        path, error = _validate_path("/etc/passwd")
        assert path is None
        assert "Path not allowed" in error

    def test_rejects_absolute_path_to_parent(self, base_dir):
        """Absolute path to parent of BASE_DIR should be rejected."""
        parent = str(base_dir.parent / "other_file.txt")
        path, error = _validate_path(parent)
        assert path is None
        assert "Path not allowed" in error

    def test_accepts_relative_path(self, base_dir):
        """Relative paths should resolve against BASE_DIR."""
        path, error = _validate_path("output.csv")
        assert error is None
        assert path == base_dir / "output.csv"

    def test_accepts_relative_path_with_subdir(self, base_dir):
        """Relative paths with subdirectories should work."""
        path, error = _validate_path("reports/2024/output.csv")
        assert error is None
        assert path == base_dir / "reports" / "2024" / "output.csv"

    def test_accepts_absolute_path_within_base(self, base_dir):
        """Absolute paths within BASE_DIR should be accepted."""
        file_path = str(base_dir / "output.csv")
        path, error = _validate_path(file_path)
        assert error is None
        assert path == base_dir / "output.csv"

    def test_rejects_symlink_outside_base(self, base_dir, tmp_path):
        """Symlinks pointing outside BASE_DIR should be rejected."""
        # Create a file outside base_dir
        outside_file = tmp_path / "secret.txt"
        outside_file.write_text("secret data")

        # Create a symlink inside base_dir pointing to it
        link_path = base_dir / "sneaky_link.txt"
        link_path.symlink_to(outside_file)

        path, error = _validate_path(str(link_path))
        assert path is None
        # Path.resolve() follows symlinks, so this is caught either as
        # "resolved path outside base" or "symlink target outside base"
        assert "Path not allowed" in error or "symlink target must be within" in error

    def test_accepts_symlink_within_base(self, base_dir):
        """Symlinks pointing within BASE_DIR should be accepted."""
        # Create a real file and a symlink both within base_dir
        real_file = base_dir / "real.txt"
        real_file.write_text("real content")
        link_path = base_dir / "link.txt"
        link_path.symlink_to(real_file)

        path, error = _validate_path(str(link_path))
        assert error is None
        # Should resolve to the real file
        assert path == real_file.resolve()

    def test_rejects_encoded_traversal(self, base_dir):
        """Path with encoded traversal (e.g. ..%2f) won't bypass because
        Path() doesn't decode URL encoding — but we check the resolved path anyway."""
        # This tests that absolute resolution catches crafted paths
        path, error = _validate_path("/tmp/evil")
        assert path is None
        assert "Path not allowed" in error

    def test_directory_validation(self, base_dir):
        """is_directory flag should work for directory paths."""
        path, error = _validate_path("reports", is_directory=True)
        assert error is None
        assert path == base_dir / "reports"

    def test_rejects_directory_outside_base(self, base_dir):
        """Directory paths outside base should be rejected."""
        path, error = _validate_path("/tmp", is_directory=True)
        assert path is None
        assert "Path not allowed" in error


# ===========================================================================
# Source code verification
# ===========================================================================


class TestSourceCodeVerification:
    """Verify the source code contains path traversal protection."""

    def test_no_raw_path_without_validation(self):
        """All handlers should call _validate_path before using file_path."""
        import inspect
        from src.plugins import file_operations_plugin

        source = inspect.getsource(file_operations_plugin)

        # Every handler that takes file_path should call _validate_path
        for handler_name in ["write_csv_handler", "csv_from_text_handler",
                             "write_json_handler", "write_text_handler",
                             "read_file_handler", "list_files_handler"]:
            handler_source = inspect.getsource(getattr(file_operations_plugin, handler_name))
            assert "_validate_path" in handler_source, \
                f"{handler_name} does not call _validate_path"

    def test_validate_path_checks_dotdot(self):
        """_validate_path should explicitly check for '..' segments."""
        import inspect
        from src.plugins.file_operations_plugin import _validate_path

        source = inspect.getsource(_validate_path)
        assert "'..' in" in source or "'..'" in source, \
            "_validate_path does not check for '..' segments"

    def test_validate_path_checks_symlinks(self):
        """_validate_path should resolve and check symlinks."""
        import inspect
        from src.plugins.file_operations_plugin import _validate_path

        source = inspect.getsource(_validate_path)
        assert "is_symlink" in source, \
            "_validate_path does not check for symlinks"
        assert "realpath" in source or "resolve" in source, \
            "_validate_path does not resolve symlinks"

    def test_base_dir_is_configurable(self):
        """FILE_OPERATIONS_BASE_DIR should be in settings."""
        import inspect
        from src.plugins.file_operations_plugin import _get_base_dir

        source = inspect.getsource(_get_base_dir)
        assert "FILE_OPERATIONS_BASE_DIR" in source, \
            "_get_base_dir does not reference FILE_OPERATIONS_BASE_DIR setting"


# ===========================================================================
# Handler integration tests — path traversal blocked
# ===========================================================================


class TestWriteCsvPathTraversal:
    """Tests for write_csv_handler path validation."""

    @pytest.mark.asyncio
    async def test_rejects_traversal(self, base_dir):
        result = await write_csv_handler({
            "data": [{"a": 1}],
            "file_path": "../../../etc/evil.csv"
        })
        assert "error" in result
        assert "'..' segments are forbidden" in result["error"]

    @pytest.mark.asyncio
    async def test_rejects_absolute_outside(self, base_dir):
        result = await write_csv_handler({
            "data": [{"a": 1}],
            "file_path": "/etc/evil.csv"
        })
        assert "error" in result
        assert "Path not allowed" in result["error"]

    @pytest.mark.asyncio
    async def test_accepts_valid_path(self, base_dir):
        result = await write_csv_handler({
            "data": [{"name": "Alice", "age": 30}],
            "file_path": "output.csv"
        })
        assert "error" not in result
        assert result["rows_written"] == 1
        assert (base_dir / "output.csv").exists()


class TestCsvFromTextPathTraversal:
    """Tests for csv_from_text_handler path validation."""

    @pytest.mark.asyncio
    async def test_rejects_traversal(self, base_dir):
        result = await csv_from_text_handler({
            "csv_text": "a,b\n1,2",
            "file_path": "../../etc/evil.csv"
        })
        assert "error" in result
        assert "'..' segments are forbidden" in result["error"]

    @pytest.mark.asyncio
    async def test_rejects_absolute_outside(self, base_dir):
        result = await csv_from_text_handler({
            "csv_text": "a,b\n1,2",
            "file_path": "/tmp/evil.csv"
        })
        assert "error" in result
        assert "Path not allowed" in result["error"]

    @pytest.mark.asyncio
    async def test_accepts_valid_path(self, base_dir):
        result = await csv_from_text_handler({
            "csv_text": "a,b\n1,2",
            "file_path": "parsed.csv"
        })
        assert "error" not in result
        assert result["rows_written"] == 2  # header + data row
        assert (base_dir / "parsed.csv").exists()


class TestWriteJsonPathTraversal:
    """Tests for write_json_handler path validation."""

    @pytest.mark.asyncio
    async def test_rejects_traversal(self, base_dir):
        result = await write_json_handler({
            "data": {"key": "value"},
            "file_path": "../../../etc/evil.json"
        })
        assert "error" in result
        assert "'..' segments are forbidden" in result["error"]

    @pytest.mark.asyncio
    async def test_rejects_absolute_outside(self, base_dir):
        result = await write_json_handler({
            "data": {"key": "value"},
            "file_path": "/etc/evil.json"
        })
        assert "error" in result
        assert "Path not allowed" in result["error"]

    @pytest.mark.asyncio
    async def test_accepts_valid_path(self, base_dir):
        result = await write_json_handler({
            "data": {"key": "value"},
            "file_path": "output.json"
        })
        assert "error" not in result
        assert result["format"] == "json"
        assert (base_dir / "output.json").exists()


class TestWriteTextPathTraversal:
    """Tests for write_text_handler path validation."""

    @pytest.mark.asyncio
    async def test_rejects_traversal(self, base_dir):
        result = await write_text_handler({
            "content": "evil content",
            "file_path": "../../../etc/evil.txt"
        })
        assert "error" in result
        assert "'..' segments are forbidden" in result["error"]

    @pytest.mark.asyncio
    async def test_rejects_absolute_outside(self, base_dir):
        result = await write_text_handler({
            "content": "evil content",
            "file_path": "/etc/evil.txt"
        })
        assert "error" in result
        assert "Path not allowed" in result["error"]

    @pytest.mark.asyncio
    async def test_accepts_valid_path(self, base_dir):
        result = await write_text_handler({
            "content": "hello world",
            "file_path": "output.txt"
        })
        assert "error" not in result
        assert result["lines_written"] == 1
        assert (base_dir / "output.txt").exists()


class TestReadFilePathTraversal:
    """Tests for read_file_handler path validation."""

    @pytest.mark.asyncio
    async def test_rejects_traversal(self, base_dir):
        result = await read_file_handler({
            "file_path": "../../../etc/passwd"
        })
        assert "error" in result
        assert "'..' segments are forbidden" in result["error"]

    @pytest.mark.asyncio
    async def test_rejects_absolute_outside(self, base_dir):
        result = await read_file_handler({
            "file_path": "/etc/passwd"
        })
        assert "error" in result
        assert "Path not allowed" in result["error"]

    @pytest.mark.asyncio
    async def test_accepts_valid_path(self, base_dir_with_files):
        result = await read_file_handler({
            "file_path": "test.txt"
        })
        assert "error" not in result
        assert result["result"] == "hello"

    @pytest.mark.asyncio
    async def test_reads_nested_file(self, base_dir_with_files):
        result = await read_file_handler({
            "file_path": "subdir/nested.txt"
        })
        assert "error" not in result
        assert result["result"] == "nested content"


class TestListFilesPathTraversal:
    """Tests for list_files_handler path validation."""

    @pytest.mark.asyncio
    async def test_rejects_traversal(self, base_dir):
        result = await list_files_handler({
            "directory": "../../../etc"
        })
        assert "error" in result
        assert "'..' segments are forbidden" in result["error"]

    @pytest.mark.asyncio
    async def test_rejects_absolute_outside(self, base_dir):
        result = await list_files_handler({
            "directory": "/etc"
        })
        assert "error" in result
        assert "Path not allowed" in result["error"]

    @pytest.mark.asyncio
    async def test_accepts_valid_directory(self, base_dir_with_files):
        # list_files_handler uses absolute path internally via _validate_path
        result = await list_files_handler({
            "directory": str(base_dir_with_files)
        })
        assert "error" not in result
        assert result["count"] >= 3  # test.txt, data.json, data.csv

    @pytest.mark.asyncio
    async def test_rejects_symlink_dir_outside(self, base_dir, tmp_path):
        """Symlink directory pointing outside base should be rejected."""
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        (outside_dir / "secret.txt").write_text("secret")

        link_dir = base_dir / "sneaky_dir"
        link_dir.symlink_to(outside_dir)

        result = await list_files_handler({
            "directory": str(link_dir)
        })
        assert "error" in result
        # Path.resolve() follows symlinks, so caught by either check
        assert "Path not allowed" in result["error"] or "symlink target must be within" in result["error"]


# ===========================================================================
# Symlink tests across handlers
# ===========================================================================


class TestSymlinkProtection:
    """Test symlink resolution across all write handlers."""

    @pytest.mark.asyncio
    async def test_write_via_symlink_outside_blocked(self, base_dir, tmp_path):
        """Writing via a symlink that points outside base_dir should be blocked."""
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()

        link_path = base_dir / "evil_link"
        link_path.symlink_to(outside_dir)

        # Try to write text via the symlink target
        result = await write_text_handler({
            "content": "evil content",
            "file_path": str(link_path / "file.txt")
        })
        # The parent dir (the symlink) resolves outside base, so path check fails
        # The resolved path of link_path/file.txt = outside_dir/file.txt which is outside base_dir
        assert "error" in result

    @pytest.mark.asyncio
    async def test_read_via_symlink_outside_blocked(self, base_dir, tmp_path):
        """Reading via a symlink that points outside base_dir should be blocked."""
        outside_file = tmp_path / "secret.txt"
        outside_file.write_text("top secret")

        link_path = base_dir / "sneaky.txt"
        link_path.symlink_to(outside_file)

        result = await read_file_handler({
            "file_path": str(link_path)
        })
        assert "error" in result
        # Path.resolve() follows symlinks, so caught by either check
        assert "Path not allowed" in result["error"] or "symlink target must be within" in result["error"]
