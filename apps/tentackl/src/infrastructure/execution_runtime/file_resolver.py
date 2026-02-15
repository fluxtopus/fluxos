"""File resolution utility for step-level file pre-download.

Downloads referenced files from Den (InkPass file storage) before LLM
step execution, so the planner doesn't need to create separate
``file_storage`` download steps.

Image files are later sent as vision attachments; text files are inlined
into the agent's prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB

IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
TEXT_TYPES = {"text/plain", "text/csv", "text/markdown", "application/json"}
SUPPORTED_TYPES = IMAGE_TYPES | TEXT_TYPES

MAX_IMAGES_PER_STEP = 5


@dataclass
class ResolvedFile:
    """A file that has been downloaded and is ready for injection."""

    file_id: str
    name: str
    content_type: str
    content_bytes: bytes

    @property
    def is_image(self) -> bool:
        return self.content_type in IMAGE_TYPES


@dataclass
class StepFileContext:
    """Runtime-only file context passed alongside a step.

    Not part of the domain model — never stored in DB/Redis.
    """

    resolved_files: List[ResolvedFile] = field(default_factory=list)


async def resolve_file_references(
    file_references: List[Dict[str, Any]],
    organization_id: str,
) -> List[ResolvedFile]:
    """Download files from Den before step execution.

    Only swallows ``ResourceNotFoundError`` (file was deleted — skip it).
    All other download failures (auth, validation, network) propagate so the
    caller can fail the step visibly instead of running the LLM blind.

    Args:
        file_references: list of dicts with at least ``id``, ``name``, ``content_type``.
        organization_id: org UUID string used for the Den API call.

    Returns:
        List of successfully resolved files.

    Raises:
        Exception: on non-recoverable download errors (422, 403, network, etc.)
    """
    from inkpass_sdk.exceptions import ResourceNotFoundError

    if not file_references:
        return []

    resolved: List[ResolvedFile] = []
    image_count = 0

    for ref in file_references:
        file_id = ref.get("id")
        name = ref.get("name", "unknown")
        content_type = ref.get("content_type", "")

        if not file_id:
            logger.warning("file_reference_missing_id", name=name)
            continue

        # Type guard
        if content_type not in SUPPORTED_TYPES:
            logger.warning(
                "file_reference_unsupported_type",
                file_id=file_id,
                name=name,
                content_type=content_type,
            )
            continue

        # Image cap
        if content_type in IMAGE_TYPES:
            if image_count >= MAX_IMAGES_PER_STEP:
                logger.warning(
                    "file_reference_image_cap_reached",
                    file_id=file_id,
                    name=name,
                    max=MAX_IMAGES_PER_STEP,
                )
                continue
            image_count += 1

        try:
            content_bytes = await _download_file(file_id, organization_id)
        except ResourceNotFoundError:
            # File was deleted between planning and execution — skip it
            logger.warning(
                "file_reference_not_found",
                file_id=file_id,
                name=name,
            )
            continue

        # Size guard
        if len(content_bytes) > MAX_FILE_SIZE_BYTES:
            logger.warning(
                "file_reference_too_large",
                file_id=file_id,
                name=name,
                size_bytes=len(content_bytes),
                max_bytes=MAX_FILE_SIZE_BYTES,
            )
            continue

        resolved.append(
            ResolvedFile(
                file_id=file_id,
                name=name,
                content_type=content_type,
                content_bytes=content_bytes,
            )
        )

    logger.info(
        "file_references_resolved",
        requested=len(file_references),
        resolved=len(resolved),
    )
    return resolved


async def _download_file(file_id: str, organization_id: str) -> bytes:
    """Download a single file from Den via the InkPass SDK."""
    from inkpass_sdk.files import FileClient
    from inkpass_sdk.config import InkPassConfig
    from src.core.config import settings

    config = InkPassConfig(
        base_url=settings.INKPASS_URL,
        api_key=settings.INKPASS_SERVICE_API_KEY,
    )

    async with FileClient(config) as client:
        file_data = await client.download(
            UUID(organization_id),
            UUID(file_id),
            agent_id="file-resolver",
        )
        return file_data.read()
