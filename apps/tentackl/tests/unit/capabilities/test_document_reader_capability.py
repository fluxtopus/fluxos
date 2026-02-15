"""
Tests for document reader capabilities.
"""

import pytest

from src.capabilities.document_reader_capability import LocalDocumentReader


@pytest.mark.asyncio
async def test_local_document_reader_reads_file(tmp_path):
    """Ensure local reader can load content within allowed directory."""
    cities_file = tmp_path / "cities.txt"
    cities_file.write_text("Paris\nMadrid\nLisbon", encoding="utf-8")

    reader = LocalDocumentReader(
        allowed_directories=[str(tmp_path)],
        allowed_extensions=["txt"],
    )

    result = await reader.read(path=str(cities_file))
    assert "Paris" in result.content
    assert result.metadata["encoding"] == "utf-8"
    assert result.metadata["size_bytes"] == len(cities_file.read_bytes())


@pytest.mark.asyncio
async def test_local_document_reader_blocks_outside_paths(tmp_path):
    """Reader should forbid access to files outside configured roots."""
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("hidden", encoding="utf-8")

    reader = LocalDocumentReader(
        allowed_directories=[str(allowed_dir)],
        allowed_extensions=["txt"],
    )

    with pytest.raises(PermissionError):
        await reader.read(path=str(secret_file))


@pytest.mark.asyncio
async def test_local_document_reader_respects_max_size(tmp_path):
    """Size limits should raise an error when exceeded."""
    large_file = tmp_path / "large.txt"
    # Create ~2 KB file and enforce smaller limit
    large_file.write_text("a" * 2048, encoding="utf-8")

    reader = LocalDocumentReader(
        allowed_directories=[str(tmp_path)],
        allowed_extensions=["txt"],
        max_size_mb=0.001,  # ~1 KB
    )

    with pytest.raises(ValueError):
        await reader.read(path=str(large_file))


@pytest.mark.asyncio
async def test_local_document_reader_allows_relative_paths(tmp_path, monkeypatch):
    """Relative paths should resolve against the first allowed directory."""
    doc_dir = tmp_path / "docs"
    doc_dir.mkdir()
    guide = doc_dir / "guide.txt"
    guide.write_text("Welcome to the city guide.", encoding="utf-8")

    reader = LocalDocumentReader(
        allowed_directories=[str(doc_dir)],
        allowed_extensions=["txt"],
    )

    # Change working directory to ensure relative resolution still works
    monkeypatch.chdir(doc_dir)

    result = await reader.read(path="guide.txt")
    assert "city guide" in result.content
