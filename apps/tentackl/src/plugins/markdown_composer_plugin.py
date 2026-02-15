"""
Markdown Composer Plugin - Upload markdown documents to Den.

This plugin takes markdown content and uploads it directly to Den file storage,
making it available in the user's workspace. Unlike PDF composer, no conversion
is needed — markdown is stored as-is.

Usage:
    result = await markdown_composer_handler({
        "content": "# My Report\n\nThis is the content...",
        "title": "Strategy Report",
        "filename": "strategy-report.md"
    }, context)
"""

import structlog
from typing import Any, Dict

logger = structlog.get_logger(__name__)


async def markdown_composer_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """
    Upload markdown content as a .md file to Den.

    Inputs:
        content: string (required) - Markdown content
        title: string (optional) - Document title (default: "Document")
        filename: string (optional) - Output filename (default: "{title}.md")

    Returns:
        {
            file_id: string - UUID of uploaded file,
            filename: string - Name of file,
            url: string - Access URL,
            cdn_url: string - CDN URL for public files,
            size_bytes: int - File size,
            content_type: string - "text/markdown"
        }
    """
    content = inputs.get("content", "")
    title = inputs.get("title", "Document")
    filename = inputs.get("filename", "")

    if not content:
        return {
            "error": "Required field 'content' is missing",
            "file_id": "",
            "filename": "",
            "size_bytes": 0,
        }

    # Generate filename from title if not provided
    if not filename:
        # Sanitize title for filename
        safe_title = title.lower().replace(" ", "-")
        safe_title = "".join(c for c in safe_title if c.isalnum() or c in "-_")
        filename = f"{safe_title}.md"

    # Ensure .md extension
    if not filename.endswith(".md"):
        filename += ".md"

    # Extract context fields for Den upload
    org_id = None
    workflow_id = None
    agent_id = None

    if context:
        org_id = getattr(context, "org_id", None) or getattr(context, "organization_id", None)
        workflow_id = getattr(context, "workflow_id", None)
        agent_id = getattr(context, "agent_id", None)

    if not org_id:
        org_id = inputs.get("org_id")
    if not workflow_id:
        workflow_id = inputs.get("workflow_id", "markdown-composer")
    if not agent_id:
        agent_id = inputs.get("agent_id", "markdown-composer")

    if not org_id:
        return {
            "error": "org_id is required (via context or inputs)",
            "file_id": "",
            "filename": "",
            "size_bytes": 0,
        }

    try:
        from .den_file_plugin import upload_file_handler

        upload_inputs = {
            "org_id": org_id,
            "workflow_id": workflow_id,
            "agent_id": agent_id,
            "content": content,
            "filename": filename,
            "content_type": "text/markdown",
            "folder_path": inputs.get("folder_path", "/agent-outputs"),
            "tags": inputs.get("tags", ["document", "markdown"]),
            "is_public": inputs.get("is_public", False),
        }

        result = await upload_file_handler(upload_inputs, context)

        if "error" in result and result["error"]:
            logger.error("markdown_composer_upload_failed", error=result["error"])
            return result

        logger.info(
            "markdown_composer_success",
            filename=filename,
            size_bytes=result.get("size_bytes"),
            file_id=result.get("file_id"),
        )

        return {
            "file_id": result.get("file_id", ""),
            "filename": result.get("filename", filename),
            "url": result.get("url", ""),
            "cdn_url": result.get("cdn_url", ""),
            "size_bytes": result.get("size_bytes", len(content.encode("utf-8"))),
            "content_type": "text/markdown",
            "title": title,
        }

    except Exception as e:
        logger.error("markdown_composer_failed", error=str(e))
        return {
            "error": f"Markdown upload failed: {str(e)}",
            "file_id": "",
            "filename": "",
            "size_bytes": 0,
        }


# Plugin definition for registration
PLUGIN_DEFINITION = {
    "name": "markdown_composer",
    "description": "Create and upload markdown documents to Den workspace storage",
    "handler": markdown_composer_handler,
    "inputs_schema": {
        "content": {"type": "string", "required": True, "description": "Markdown content"},
        "title": {"type": "string", "required": False, "default": "Document", "description": "Document title"},
        "filename": {"type": "string", "required": False, "description": "Output filename (default: {title}.md)"},
    },
    "outputs_schema": {
        "file_id": {"type": "string", "description": "UUID of uploaded file"},
        "filename": {"type": "string", "description": "Name of the file"},
        "url": {"type": "string", "description": "Access URL"},
        "cdn_url": {"type": "string", "description": "CDN URL for public files"},
        "size_bytes": {"type": "integer", "description": "Size of the file in bytes"},
        "content_type": {"type": "string", "description": "MIME type (text/markdown)"},
    },
    "category": "document",
}
