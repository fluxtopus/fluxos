"""Unit tests for file_resolver — step-level file pre-download."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from io import BytesIO

from src.infrastructure.execution_runtime.file_resolver import (
    ResolvedFile,
    StepFileContext,
    resolve_file_references,
    MAX_FILE_SIZE_BYTES,
    MAX_IMAGES_PER_STEP,
    IMAGE_TYPES,
    TEXT_TYPES,
)


# ---------------------------------------------------------------------------
# ResolvedFile
# ---------------------------------------------------------------------------


class TestResolvedFile:
    def test_is_image_true_for_png(self):
        f = ResolvedFile(file_id="1", name="photo.png", content_type="image/png", content_bytes=b"data")
        assert f.is_image is True

    def test_is_image_true_for_jpeg(self):
        f = ResolvedFile(file_id="1", name="photo.jpg", content_type="image/jpeg", content_bytes=b"data")
        assert f.is_image is True

    def test_is_image_false_for_text(self):
        f = ResolvedFile(file_id="1", name="notes.txt", content_type="text/plain", content_bytes=b"data")
        assert f.is_image is False

    def test_is_image_false_for_json(self):
        f = ResolvedFile(file_id="1", name="data.json", content_type="application/json", content_bytes=b"{}")
        assert f.is_image is False


# ---------------------------------------------------------------------------
# StepFileContext
# ---------------------------------------------------------------------------


class TestStepFileContext:
    def test_defaults_to_empty_list(self):
        ctx = StepFileContext()
        assert ctx.resolved_files == []

    def test_accepts_resolved_files(self):
        f = ResolvedFile(file_id="1", name="a.txt", content_type="text/plain", content_bytes=b"hi")
        ctx = StepFileContext(resolved_files=[f])
        assert len(ctx.resolved_files) == 1


# ---------------------------------------------------------------------------
# resolve_file_references
# ---------------------------------------------------------------------------


def _mock_download(content: bytes = b"file content"):
    """Create a patched _download_file that returns fixed bytes."""
    return AsyncMock(return_value=content)


class TestResolveFileReferences:
    @pytest.mark.asyncio
    async def test_resolves_text_file(self):
        refs = [{"id": "f1", "name": "notes.txt", "content_type": "text/plain"}]

        with patch(
            "src.infrastructure.execution_runtime.file_resolver._download_file",
            _mock_download(b"hello world"),
        ):
            result = await resolve_file_references(refs, "org-1")

        assert len(result) == 1
        assert result[0].file_id == "f1"
        assert result[0].name == "notes.txt"
        assert result[0].content_bytes == b"hello world"
        assert result[0].is_image is False

    @pytest.mark.asyncio
    async def test_resolves_image_file(self):
        refs = [{"id": "f1", "name": "photo.png", "content_type": "image/png"}]

        with patch(
            "src.infrastructure.execution_runtime.file_resolver._download_file",
            _mock_download(b"\x89PNG"),
        ):
            result = await resolve_file_references(refs, "org-1")

        assert len(result) == 1
        assert result[0].is_image is True

    @pytest.mark.asyncio
    async def test_skips_unsupported_content_type(self):
        refs = [{"id": "f1", "name": "video.mp4", "content_type": "video/mp4"}]

        with patch(
            "src.infrastructure.execution_runtime.file_resolver._download_file",
            _mock_download(),
        ) as mock_dl:
            result = await resolve_file_references(refs, "org-1")

        assert len(result) == 0
        mock_dl.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_file_exceeding_size_limit(self):
        refs = [{"id": "f1", "name": "huge.txt", "content_type": "text/plain"}]
        huge_content = b"x" * (MAX_FILE_SIZE_BYTES + 1)

        with patch(
            "src.infrastructure.execution_runtime.file_resolver._download_file",
            _mock_download(huge_content),
        ):
            result = await resolve_file_references(refs, "org-1")

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_caps_images_at_max(self):
        refs = [
            {"id": f"f{i}", "name": f"img{i}.png", "content_type": "image/png"}
            for i in range(MAX_IMAGES_PER_STEP + 2)
        ]

        with patch(
            "src.infrastructure.execution_runtime.file_resolver._download_file",
            _mock_download(b"\x89PNG"),
        ):
            result = await resolve_file_references(refs, "org-1")

        assert len(result) == MAX_IMAGES_PER_STEP

    @pytest.mark.asyncio
    async def test_not_found_skips_file(self):
        """A deleted file (ResourceNotFoundError) is skipped, not fatal."""
        from inkpass_sdk.exceptions import ResourceNotFoundError

        refs = [{"id": "f1", "name": "notes.txt", "content_type": "text/plain"}]
        failing_download = AsyncMock(side_effect=ResourceNotFoundError("not found"))

        with patch(
            "src.infrastructure.execution_runtime.file_resolver._download_file",
            failing_download,
        ):
            result = await resolve_file_references(refs, "org-1")

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_validation_error_propagates(self):
        """A 422 (ValidationError) must propagate, not be swallowed."""
        from inkpass_sdk.exceptions import ValidationError

        refs = [{"id": "f1", "name": "notes.txt", "content_type": "text/plain"}]
        failing_download = AsyncMock(side_effect=ValidationError("agent_id required"))

        with patch(
            "src.infrastructure.execution_runtime.file_resolver._download_file",
            failing_download,
        ):
            with pytest.raises(ValidationError, match="agent_id required"):
                await resolve_file_references(refs, "org-1")

    @pytest.mark.asyncio
    async def test_permission_error_propagates(self):
        """A 403 (PermissionDeniedError) must propagate, not be swallowed."""
        from inkpass_sdk.exceptions import PermissionDeniedError

        refs = [{"id": "f1", "name": "img.png", "content_type": "image/png"}]
        failing_download = AsyncMock(side_effect=PermissionDeniedError("forbidden"))

        with patch(
            "src.infrastructure.execution_runtime.file_resolver._download_file",
            failing_download,
        ):
            with pytest.raises(PermissionDeniedError):
                await resolve_file_references(refs, "org-1")

    @pytest.mark.asyncio
    async def test_generic_exception_propagates(self):
        """Non-SDK errors (network, unexpected) must also propagate."""
        refs = [{"id": "f1", "name": "notes.txt", "content_type": "text/plain"}]
        failing_download = AsyncMock(side_effect=RuntimeError("connection refused"))

        with patch(
            "src.infrastructure.execution_runtime.file_resolver._download_file",
            failing_download,
        ):
            with pytest.raises(RuntimeError, match="connection refused"):
                await resolve_file_references(refs, "org-1")

    @pytest.mark.asyncio
    async def test_not_found_skips_but_resolves_others(self):
        """A 404 on one file skips it; remaining files still resolve."""
        from inkpass_sdk.exceptions import ResourceNotFoundError

        refs = [
            {"id": "f1", "name": "gone.txt", "content_type": "text/plain"},
            {"id": "f2", "name": "here.txt", "content_type": "text/plain"},
        ]

        call_count = 0

        async def _download(file_id, org_id):
            nonlocal call_count
            call_count += 1
            if file_id == "f1":
                raise ResourceNotFoundError("deleted")
            return b"present"

        with patch(
            "src.infrastructure.execution_runtime.file_resolver._download_file",
            side_effect=_download,
        ):
            result = await resolve_file_references(refs, "org-1")

        assert len(result) == 1
        assert result[0].file_id == "f2"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_empty_references_returns_empty(self):
        result = await resolve_file_references([], "org-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_skips_ref_without_id(self):
        refs = [{"name": "notes.txt", "content_type": "text/plain"}]

        with patch(
            "src.infrastructure.execution_runtime.file_resolver._download_file",
            _mock_download(),
        ) as mock_dl:
            result = await resolve_file_references(refs, "org-1")

        assert len(result) == 0
        mock_dl.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_mixed_files_resolved_correctly(self):
        refs = [
            {"id": "f1", "name": "notes.txt", "content_type": "text/plain"},
            {"id": "f2", "name": "photo.png", "content_type": "image/png"},
            {"id": "f3", "name": "video.mp4", "content_type": "video/mp4"},
        ]

        with patch(
            "src.infrastructure.execution_runtime.file_resolver._download_file",
            _mock_download(b"data"),
        ):
            result = await resolve_file_references(refs, "org-1")

        # video should be skipped
        assert len(result) == 2
        assert result[0].name == "notes.txt"
        assert result[1].name == "photo.png"


# ---------------------------------------------------------------------------
# execute_step — file resolution error propagation
# ---------------------------------------------------------------------------


class TestExecuteStepFileResolutionErrors:
    """Verify that file resolution errors surface as step failures
    instead of being silently swallowed (the LLM would run blind)."""

    def _make_step(self):
        step = MagicMock()
        step.id = "step-1"
        step.name = "Analyze image"
        step.agent_type = "analyze"
        step.inputs = {"content": "describe the image"}
        return step

    @pytest.mark.asyncio
    async def test_validation_error_fails_step(self):
        """A 422 from file download should fail execute_step."""
        from inkpass_sdk.exceptions import ValidationError
        from src.infrastructure.execution_runtime.plugin_executor import execute_step

        step = self._make_step()
        refs = [{"id": "f1", "name": "img.png", "content_type": "image/png"}]

        with patch(
            "src.infrastructure.execution_runtime.file_resolver._download_file",
            AsyncMock(side_effect=ValidationError("agent_id required")),
        ), patch(
            "src.capabilities.unified_registry.get_registry",
            new_callable=AsyncMock,
        ) as mock_get_registry:
            # Set up a mock agent that would succeed if reached
            mock_agent = AsyncMock()
            mock_registry = AsyncMock()
            mock_registry.create_agent = AsyncMock(return_value=mock_agent)
            mock_get_registry.return_value = mock_registry

            result = await execute_step(
                step,
                model="test-model",
                organization_id="org-1",
                file_references=refs,
            )

        assert result.success is False
        assert "agent_id required" in (result.error or "")
        # The LLM agent should NOT have been called
        mock_agent.execute.assert_not_awaited()
        mock_agent.execute_validated.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_network_error_fails_step(self):
        """A network error during file download should fail execute_step."""
        from src.infrastructure.execution_runtime.plugin_executor import execute_step

        step = self._make_step()
        refs = [{"id": "f1", "name": "data.csv", "content_type": "text/csv"}]

        with patch(
            "src.infrastructure.execution_runtime.file_resolver._download_file",
            AsyncMock(side_effect=ConnectionError("ECONNREFUSED")),
        ), patch(
            "src.capabilities.unified_registry.get_registry",
            new_callable=AsyncMock,
        ) as mock_get_registry:
            mock_agent = AsyncMock()
            mock_registry = AsyncMock()
            mock_registry.create_agent = AsyncMock(return_value=mock_agent)
            mock_get_registry.return_value = mock_registry

            result = await execute_step(
                step,
                model="test-model",
                organization_id="org-1",
                file_references=refs,
            )

        assert result.success is False
        assert "ECONNREFUSED" in (result.error or "")

    @pytest.mark.asyncio
    async def test_not_found_does_not_fail_step(self):
        """A 404 (deleted file) should be skipped, not fail the step."""
        from inkpass_sdk.exceptions import ResourceNotFoundError
        from src.infrastructure.execution_runtime.plugin_executor import execute_step, ExecutionResult

        step = self._make_step()
        refs = [{"id": "f1", "name": "gone.png", "content_type": "image/png"}]

        with patch(
            "src.infrastructure.execution_runtime.file_resolver._download_file",
            AsyncMock(side_effect=ResourceNotFoundError("not found")),
        ), patch(
            "src.capabilities.unified_registry.get_registry",
            new_callable=AsyncMock,
        ) as mock_get_registry:
            mock_agent = AsyncMock()
            mock_agent.execute_validated = AsyncMock(return_value=ExecutionResult(
                status="success", output={"analysis": "done"}, execution_time_ms=100,
            ))
            mock_registry = AsyncMock()
            mock_registry.create_agent = AsyncMock(return_value=mock_agent)
            mock_get_registry.return_value = mock_registry

            result = await execute_step(
                step,
                model="test-model",
                organization_id="org-1",
                file_references=refs,
            )

        # Step should still succeed (file was just missing, LLM ran without it)
        assert result.success is True
