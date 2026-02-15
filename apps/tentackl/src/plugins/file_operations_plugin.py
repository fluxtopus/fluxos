"""File operations plugin for writing files, CSVs, and managing file I/O.

This plugin provides file system operations including:
- CSV file generation from data
- JSON file writing
- Text file writing
- File reading
- Directory management

All file operations are restricted to the configured base directory
(FILE_OPERATIONS_BASE_DIR) to prevent path traversal attacks.
"""

from typing import Any, Dict, List, Optional, Tuple
import csv
import json
import logging
import os
from pathlib import Path
import io

logger = logging.getLogger(__name__)


def _get_base_dir() -> Path:
    """Get the base directory for file operations.

    Returns the resolved absolute path of FILE_OPERATIONS_BASE_DIR.
    Defaults to /app/data if not configured.
    """
    from src.core.config import settings
    return Path(settings.FILE_OPERATIONS_BASE_DIR).resolve()


def _validate_path(file_path: str, *, is_directory: bool = False) -> Tuple[Optional[Path], Optional[str]]:
    """Validate that a file path is safe and within the allowed base directory.

    Checks:
    1. Rejects paths containing '..' segments
    2. Resolves the path to an absolute canonical form
    3. Verifies the resolved path starts with BASE_DIR
    4. If the target exists and is a symlink, resolves the symlink and re-checks

    Args:
        file_path: The raw file path string from user input.
        is_directory: If True, validates as a directory path.

    Returns:
        Tuple of (validated_path, error_message). If error_message is not None,
        the path is invalid and should be rejected.
    """
    if not file_path:
        return None, "No file_path provided"

    base_dir = _get_base_dir()

    # Reject explicit '..' segments before any resolution
    raw_path = Path(file_path)
    if '..' in raw_path.parts:
        logger.warning(
            "Path traversal attempt blocked: path contains '..' segments",
            extra={"file_path": file_path}
        )
        return None, "Path traversal not allowed: '..' segments are forbidden"

    # Resolve to absolute path (relative paths are resolved against base_dir)
    if raw_path.is_absolute():
        resolved = raw_path.resolve()
    else:
        resolved = (base_dir / raw_path).resolve()

    # Check that resolved path is within base_dir
    try:
        resolved.relative_to(base_dir)
    except ValueError:
        logger.warning(
            "Path traversal attempt blocked: resolved path outside base directory",
            extra={"file_path": file_path, "resolved": str(resolved), "base_dir": str(base_dir)}
        )
        return None, f"Path not allowed: must be within {base_dir}"

    # If the target exists and is a symlink, resolve the symlink and re-check
    if resolved.exists() and resolved.is_symlink():
        real_path = Path(os.path.realpath(resolved))
        try:
            real_path.relative_to(base_dir)
        except ValueError:
            logger.warning(
                "Symlink traversal attempt blocked: symlink target outside base directory",
                extra={"file_path": file_path, "symlink_target": str(real_path), "base_dir": str(base_dir)}
            )
            return None, f"Path not allowed: symlink target must be within {base_dir}"
        resolved = real_path

    return resolved, None


async def write_csv_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Write data to a CSV file.

    Inputs:
      data: list[dict] or list[list] (required) - Data to write as CSV
      file_path: string (required) - Where to save the CSV file (within base directory)
      headers: list[string] (optional) - Column headers (auto-detected from dict keys if not provided)
      delimiter: string (optional) - CSV delimiter (default: ",")
      append: bool (optional) - Append to existing file (default: False)

    Returns:
      {
        result: string - Path to created file,
        rows_written: int - Number of rows written,
        size_bytes: int - File size in bytes
      }
    """
    data = inputs.get("data", [])
    file_path = inputs.get("file_path", "")
    headers = inputs.get("headers", None)
    delimiter = inputs.get("delimiter", ",")
    append = inputs.get("append", False)

    if not data:
        return {"result": "", "error": "No data provided"}
    if not file_path:
        return {"result": "", "error": "No file_path provided"}

    path, error = _validate_path(file_path)
    if error:
        return {"result": "", "error": error}

    try:
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        mode = 'a' if append else 'w'

        with open(path, mode, newline='', encoding='utf-8') as f:
            # Determine if data is list of dicts or list of lists
            if data and isinstance(data[0], dict):
                # List of dictionaries
                if headers is None:
                    headers = list(data[0].keys())

                writer = csv.DictWriter(f, fieldnames=headers, delimiter=delimiter)
                if not append or path.stat().st_size == 0:
                    writer.writeheader()
                writer.writerows(data)
            else:
                # List of lists
                writer = csv.writer(f, delimiter=delimiter)
                if headers and (not append or path.stat().st_size == 0):
                    writer.writerow(headers)
                writer.writerows(data)

        # Get file stats
        file_size = path.stat().st_size
        rows_written = len(data)

        return {
            "result": str(path.absolute()),
            "rows_written": rows_written,
            "size_bytes": file_size,
            "format": "csv"
        }

    except Exception as e:
        return {
            "result": "",
            "error": f"Failed to write CSV: {str(e)}"
        }


async def csv_from_text_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Parse CSV text content and save to file.

    Useful when an LLM generates CSV content as text and you want to save it.

    Inputs:
      csv_text: string (required) - CSV content as text
      file_path: string (required) - Where to save the CSV file (within base directory)
      skip_validation: bool (optional) - Skip CSV validation (default: False)

    Returns:
      {
        result: string - Path to created file,
        rows_written: int - Number of rows written,
        size_bytes: int - File size in bytes
      }
    """
    csv_text = inputs.get("csv_text", "")
    file_path = inputs.get("file_path", "")
    skip_validation = inputs.get("skip_validation", False)

    if not csv_text:
        return {"result": "", "error": "No csv_text provided"}
    if not file_path:
        return {"result": "", "error": "No file_path provided"}

    path, error = _validate_path(file_path)
    if error:
        return {"result": "", "error": error}

    try:
        # Validate CSV format (unless skipped)
        if not skip_validation:
            # Try to parse it to ensure it's valid CSV
            csv_reader = csv.reader(io.StringIO(csv_text))
            rows = list(csv_reader)
            if not rows:
                return {"result": "", "error": "CSV text contains no rows"}

        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write the CSV text
        with open(path, 'w', encoding='utf-8') as f:
            f.write(csv_text)

        # Get stats
        file_size = path.stat().st_size

        # Count rows
        with open(path, 'r', encoding='utf-8') as f:
            rows_written = sum(1 for _ in csv.reader(f))

        return {
            "result": str(path.absolute()),
            "rows_written": rows_written,
            "size_bytes": file_size,
            "format": "csv"
        }

    except Exception as e:
        return {
            "result": "",
            "error": f"Failed to save CSV from text: {str(e)}"
        }


async def write_json_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Write data to a JSON file.

    Inputs:
      data: dict or list (required) - Data to write as JSON
      file_path: string (required) - Where to save the JSON file (within base directory)
      indent: int (optional) - JSON indentation (default: 2, use 0 for compact)
      append_to_array: bool (optional) - Append to existing JSON array (default: False)

    Returns:
      {
        result: string - Path to created file,
        size_bytes: int - File size in bytes
      }
    """
    data = inputs.get("data")
    file_path = inputs.get("file_path", "")
    indent = inputs.get("indent", 2)
    append_to_array = inputs.get("append_to_array", False)

    if data is None:
        return {"result": "", "error": "No data provided"}
    if not file_path:
        return {"result": "", "error": "No file_path provided"}

    path, error = _validate_path(file_path)
    if error:
        return {"result": "", "error": error}

    try:
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Handle append to array
        if append_to_array and path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
                if not isinstance(existing, list):
                    return {"result": "", "error": "Cannot append to non-array JSON"}
                if isinstance(data, list):
                    existing.extend(data)
                else:
                    existing.append(data)
                data = existing

        # Write JSON
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent if indent > 0 else None, ensure_ascii=False)

        # Get file size
        file_size = path.stat().st_size

        return {
            "result": str(path.absolute()),
            "size_bytes": file_size,
            "format": "json"
        }

    except Exception as e:
        return {
            "result": "",
            "error": f"Failed to write JSON: {str(e)}"
        }


async def write_text_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Write text content to a file.

    Inputs:
      content: string (required) - Text content to write
      file_path: string (required) - Where to save the file (within base directory)
      append: bool (optional) - Append to existing file (default: False)
      encoding: string (optional) - File encoding (default: "utf-8")

    Returns:
      {
        result: string - Path to created file,
        size_bytes: int - File size in bytes,
        lines_written: int - Number of lines written
      }
    """
    content = inputs.get("content", "")
    file_path = inputs.get("file_path", "")
    append = inputs.get("append", False)
    encoding = inputs.get("encoding", "utf-8")

    if not content:
        return {"result": "", "error": "No content provided"}
    if not file_path:
        return {"result": "", "error": "No file_path provided"}

    path, error = _validate_path(file_path)
    if error:
        return {"result": "", "error": error}

    try:
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        mode = 'a' if append else 'w'

        with open(path, mode, encoding=encoding) as f:
            f.write(content)

        # Get stats
        file_size = path.stat().st_size
        lines_written = content.count('\n') + 1

        return {
            "result": str(path.absolute()),
            "size_bytes": file_size,
            "lines_written": lines_written,
            "format": "text"
        }

    except Exception as e:
        return {
            "result": "",
            "error": f"Failed to write text file: {str(e)}"
        }


async def read_file_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Read content from a file.

    Inputs:
      file_path: string (required) - Path to file to read (within base directory)
      encoding: string (optional) - File encoding (default: "utf-8")
      max_bytes: int (optional) - Maximum bytes to read (default: None = read all)

    Returns:
      {
        result: string - File contents,
        size_bytes: int - File size in bytes,
        lines: int - Number of lines (for text files)
      }
    """
    file_path = inputs.get("file_path", "")
    encoding = inputs.get("encoding", "utf-8")
    max_bytes = inputs.get("max_bytes", None)

    if not file_path:
        return {"result": "", "error": "No file_path provided"}

    path, error = _validate_path(file_path)
    if error:
        return {"result": "", "error": error}

    try:
        if not path.exists():
            return {"result": "", "error": f"File not found: {file_path}"}

        file_size = path.stat().st_size

        with open(path, 'r', encoding=encoding) as f:
            if max_bytes:
                content = f.read(max_bytes)
            else:
                content = f.read()

        lines = content.count('\n') + 1

        return {
            "result": content,
            "size_bytes": file_size,
            "lines": lines,
            "truncated": max_bytes is not None and file_size > max_bytes
        }

    except Exception as e:
        return {
            "result": "",
            "error": f"Failed to read file: {str(e)}"
        }


async def list_files_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """List files in a directory.

    Inputs:
      directory: string (required) - Directory path to list (within base directory)
      pattern: string (optional) - Glob pattern (e.g., "*.csv", "**/*.json")
      recursive: bool (optional) - Search recursively (default: False)

    Returns:
      {
        result: list[string] - List of file paths,
        count: int - Number of files found
      }
    """
    directory = inputs.get("directory", "")
    pattern = inputs.get("pattern", "*")
    recursive = inputs.get("recursive", False)

    if not directory:
        return {"result": [], "error": "No directory provided"}

    path, error = _validate_path(directory, is_directory=True)
    if error:
        return {"result": [], "error": error}

    try:
        if not path.exists():
            return {"result": [], "error": f"Directory not found: {directory}"}

        if not path.is_dir():
            return {"result": [], "error": f"Not a directory: {directory}"}

        if recursive:
            files = [str(p.absolute()) for p in path.rglob(pattern) if p.is_file()]
        else:
            files = [str(p.absolute()) for p in path.glob(pattern) if p.is_file()]

        return {
            "result": sorted(files),
            "count": len(files)
        }

    except Exception as e:
        return {
            "result": [],
            "error": f"Failed to list files: {str(e)}"
        }


# Export plugin handlers
PLUGIN_HANDLERS = {
    "write_csv": write_csv_handler,
    "csv_from_text": csv_from_text_handler,
    "write_json": write_json_handler,
    "write_text": write_text_handler,
    "read_file": read_file_handler,
    "list_files": list_files_handler,
}
