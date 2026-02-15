"""
Den File Plugin for Tentackl workflows.

This plugin provides file storage operations via InkPass Den API including:
- File upload/download
- JSON persistence
- Agent context/memory storage
- File listing and deletion
- Temporary file management
"""

from typing import Any, Dict, List, Optional
from uuid import UUID
import json
import base64
import structlog

logger = structlog.get_logger(__name__)


class DenFilePluginError(Exception):
    """Raised when Den file operations fail."""
    pass


async def upload_file_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """Upload a file (or batch of files) to InkPass Den.

    Inputs (single file):
      org_id: string (required) - Organization ID
      workflow_id: string (required) - Workflow ID for grouping
      agent_id: string (required) - Agent ID for tracking
      content: bytes or string (required) - File content
      filename: string (required) - Name of the file
      content_type: string (optional) - MIME type (default: "application/octet-stream")
      folder_path: string (optional) - Virtual folder path (default: "/agent-outputs")
      tags: list[string] (optional) - Tags for categorization
      is_public: bool (optional) - Make file publicly accessible (default: False)
      is_temporary: bool (optional) - Mark as temporary file (default: False)
      expires_in_hours: int (optional) - Hours until expiration (for temporary files)

    Inputs (batch upload):
      org_id: string (required) - Organization ID
      workflow_id: string (required) - Workflow ID for grouping
      agent_id: string (required) - Agent ID for tracking
      files: list[dict] (required) - Array of files to upload, each with:
        - file_data or content: bytes or string (required) - File content
        - filename: string (required) - Name of the file
        - content_type: string (optional) - MIME type
      folder_path: string (optional) - Virtual folder path for all files
      tags: list[string] (optional) - Tags for all files
      is_public: bool (optional) - Make files publicly accessible (default: False)

    Returns (single):
      {
        file_id: string - UUID of uploaded file,
        filename: string - Name of file,
        url: string - Access URL,
        size_bytes: int - File size
      }

    Returns (batch):
      {
        files: list[dict] - Array of upload results,
        count: int - Number of files uploaded,
        errors: list[string] - Any errors encountered
      }
    """
    try:
        # Check for batch upload mode
        files_array = inputs.get("files")
        if files_array and isinstance(files_array, list):
            return await _batch_upload_files(inputs, files_array)
        # Import here to avoid circular dependencies and handle missing SDK gracefully
        try:
            from inkpass_sdk.files import FileClient
            from inkpass_sdk.config import InkPassConfig
        except ImportError:
            return {
                "error": "InkPass SDK files module not available. Please install inkpass-sdk."
            }

        from ..core.config import settings

        org_id = inputs.get("org_id")
        workflow_id = inputs.get("workflow_id")
        agent_id = inputs.get("agent_id")
        content = inputs.get("content")
        filename = inputs.get("filename")

        if not all([org_id, workflow_id, agent_id, content, filename]):
            return {"error": "Missing required fields: org_id, workflow_id, agent_id, content, filename"}

        # Convert content to bytes
        if isinstance(content, str):
            # Check if this is base64 encoded data (common for images and PDFs)
            content_type = inputs.get("content_type", "")
            is_binary_type = (
                content_type.startswith("image/") or
                content_type == "application/pdf" or
                content_type == "application/octet-stream"
            )
            if inputs.get("is_base64") or is_binary_type:
                try:
                    content = base64.b64decode(content)
                    logger.debug("Decoded base64 content", size=len(content))
                except Exception as e:
                    logger.warning("Failed to decode as base64, treating as plain text", error=str(e))
                    content = content.encode("utf-8")
            else:
                content = content.encode("utf-8")

        config = InkPassConfig(
            base_url=settings.INKPASS_URL,
            api_key=settings.INKPASS_SERVICE_API_KEY
        )

        from io import BytesIO
        file_data = BytesIO(content)

        async with FileClient(config) as client:
            result = await client.upload(
                org_id=UUID(org_id),
                workflow_id=workflow_id,
                agent_id=agent_id,
                file_data=file_data,
                filename=filename,
                content_type=inputs.get("content_type", "application/octet-stream"),
                folder_path=inputs.get("folder_path", "/agent-outputs"),
                tags=inputs.get("tags"),
                is_public=inputs.get("is_public", False),
                is_temporary=inputs.get("is_temporary", False),
                expires_in_hours=inputs.get("expires_in_hours"),
            )

        return {
            "file_id": str(result.get("id")),
            "filename": result.get("name"),
            "url": result.get("url"),
            "cdn_url": result.get("cdn_url"),  # Include CDN URL for public files
            "size_bytes": result.get("size_bytes"),
            "folder_path": result.get("folder_path"),
        }

    except Exception as e:
        logger.error("den_upload_failed", error=str(e), filename=inputs.get("filename"))
        return {"error": f"Upload failed: {str(e)}"}


async def _batch_upload_files(inputs: Dict[str, Any], files_array: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Internal helper for batch file uploads.

    Iterates through a files array and uploads each file individually,
    collecting results and errors.
    """
    try:
        from inkpass_sdk.files import FileClient
        from inkpass_sdk.config import InkPassConfig
    except ImportError:
        return {"error": "InkPass SDK files module not available. Please install inkpass-sdk."}

    from ..core.config import settings

    # Validate required shared inputs
    org_id = inputs.get("org_id")
    workflow_id = inputs.get("workflow_id")
    agent_id = inputs.get("agent_id")

    if not all([org_id, workflow_id, agent_id]):
        return {"error": "Missing required fields for batch upload: org_id, workflow_id, agent_id"}

    # Shared settings
    folder_path = inputs.get("folder_path", "/agent-outputs")
    tags = inputs.get("tags")
    is_public = inputs.get("is_public", False)
    is_temporary = inputs.get("is_temporary", False)
    expires_in_hours = inputs.get("expires_in_hours")

    config = InkPassConfig(
        base_url=settings.INKPASS_URL,
        api_key=settings.INKPASS_SERVICE_API_KEY
    )

    results = []
    errors = []

    async with FileClient(config) as client:
        for idx, file_item in enumerate(files_array):
            try:
                # Get content from file_data or content field
                content = file_item.get("file_data") or file_item.get("content")
                filename = file_item.get("filename")
                content_type = file_item.get("content_type", "application/octet-stream")

                if not content or not filename:
                    errors.append(f"File {idx}: Missing file_data/content or filename")
                    continue

                # Convert content to bytes
                if isinstance(content, str):
                    # Check if this is base64 encoded data (images, PDFs, binary)
                    is_binary_type = (
                        content_type.startswith("image/") or
                        content_type == "application/pdf" or
                        content_type == "application/octet-stream"
                    )
                    if file_item.get("is_base64") or is_binary_type:
                        try:
                            content = base64.b64decode(content)
                            logger.debug("Decoded base64 content", size=len(content), filename=filename)
                        except Exception as e:
                            logger.warning("Failed to decode as base64, treating as plain text",
                                         error=str(e), filename=filename)
                            content = content.encode("utf-8")
                    else:
                        content = content.encode("utf-8")

                from io import BytesIO
                file_data = BytesIO(content)

                result = await client.upload(
                    org_id=UUID(org_id),
                    workflow_id=workflow_id,
                    agent_id=agent_id,
                    file_data=file_data,
                    filename=filename,
                    content_type=content_type,
                    folder_path=folder_path,
                    tags=tags,
                    is_public=is_public,
                    is_temporary=is_temporary,
                    expires_in_hours=expires_in_hours,
                )

                results.append({
                    "file_id": str(result.get("id")),
                    "filename": result.get("name"),
                    "url": result.get("url"),
                    "cdn_url": result.get("cdn_url"),
                    "size_bytes": result.get("size_bytes"),
                    "folder_path": result.get("folder_path"),
                })
                logger.info("batch_upload_file_success", filename=filename, file_id=result.get("id"))

            except Exception as e:
                error_msg = f"File {idx} ({file_item.get('filename', 'unknown')}): {str(e)}"
                errors.append(error_msg)
                logger.error("batch_upload_file_failed", error=str(e), filename=file_item.get("filename"))

    # For single file uploads, flatten the output for easier template access
    # This allows {{step_X.outputs.cdn_url}} to work directly
    if len(results) == 1 and not errors:
        single_file = results[0]
        return {
            "file_id": single_file.get("file_id"),
            "filename": single_file.get("filename"),
            "url": single_file.get("url"),
            "cdn_url": single_file.get("cdn_url"),
            "size_bytes": single_file.get("size_bytes"),
            "folder_path": single_file.get("folder_path"),
            # Also include batch format for compatibility
            "files": results,
            "count": 1,
            "errors": None,
        }

    return {
        "files": results,
        "count": len(results),
        "errors": errors if errors else None,
    }


async def download_file_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Download a file from InkPass Den.

    Inputs:
      org_id: string (required) - Organization ID
      file_id: string (required) - File ID to download
      agent_id: string (optional) - Agent ID for agent endpoints

    Returns:
      {
        content: bytes - File content,
        size_bytes: int - File size
      }
    """
    try:
        try:
            from inkpass_sdk.files import FileClient
            from inkpass_sdk.config import InkPassConfig
        except ImportError:
            return {"error": "InkPass SDK files module not available"}

        from ..core.config import settings

        org_id = inputs.get("org_id")
        file_id = inputs.get("file_id")
        agent_id = inputs.get("agent_id")

        if not all([org_id, file_id]):
            return {"error": "Missing required fields: org_id, file_id"}

        config = InkPassConfig(
            base_url=settings.INKPASS_URL,
            api_key=settings.INKPASS_SERVICE_API_KEY
        )

        async with FileClient(config) as client:
            file_data = await client.download(UUID(org_id), UUID(file_id), agent_id=agent_id)
            content = file_data.read()

        return {
            "content": content.decode("utf-8") if inputs.get("decode_utf8", True) else content,
            "size_bytes": len(content),
        }

    except Exception as e:
        logger.error("den_download_failed", error=str(e), file_id=inputs.get("file_id"))
        return {"error": f"Download failed: {str(e)}"}


async def get_download_url_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Get a temporary download URL for a file.

    Inputs:
      org_id: string (required) - Organization ID
      file_id: string (required) - File ID
      expires_in: int (optional) - Seconds until URL expires (default: 3600)

    Returns:
      {
        url: string - Temporary download URL,
        expires_in: int - Seconds until expiration
      }
    """
    try:
        try:
            from inkpass_sdk.files import FileClient
            from inkpass_sdk.config import InkPassConfig
        except ImportError:
            return {"error": "InkPass SDK files module not available"}

        from ..core.config import settings

        org_id = inputs.get("org_id")
        file_id = inputs.get("file_id")
        expires_in = inputs.get("expires_in", 3600)

        if not all([org_id, file_id]):
            return {"error": "Missing required fields: org_id, file_id"}

        config = InkPassConfig(
            base_url=settings.INKPASS_URL,
            api_key=settings.INKPASS_SERVICE_API_KEY
        )

        async with FileClient(config) as client:
            url = await client.get_download_url(UUID(org_id), UUID(file_id), expires_in)

        return {
            "url": url,
            "expires_in": expires_in,
        }

    except Exception as e:
        logger.error("den_get_url_failed", error=str(e), file_id=inputs.get("file_id"))
        return {"error": f"Get URL failed: {str(e)}"}


async def list_files_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """List files in Den.

    Inputs:
      org_id: string (required) - Organization ID
      workflow_id: string (optional) - Filter by workflow
      folder_path: string (optional) - Filter by folder
      tags: list[string] (optional) - Filter by tags

    Returns:
      {
        files: list[dict] - List of file metadata,
        count: int - Number of files
      }
    """
    try:
        try:
            from inkpass_sdk.files import FileClient
            from inkpass_sdk.config import InkPassConfig
        except ImportError:
            return {"error": "InkPass SDK files module not available"}

        from ..core.config import settings

        org_id = inputs.get("org_id")
        if not org_id:
            return {"error": "Missing required field: org_id"}

        config = InkPassConfig(
            base_url=settings.INKPASS_URL,
            api_key=settings.INKPASS_SERVICE_API_KEY
        )

        async with FileClient(config) as client:
            files = await client.list_files(
                org_id=UUID(org_id),
                workflow_id=inputs.get("workflow_id"),
                folder_path=inputs.get("folder_path"),
                tags=inputs.get("tags"),
            )

        return {
            "files": files,
            "count": len(files) if isinstance(files, list) else 0,
        }

    except Exception as e:
        logger.error("den_list_failed", error=str(e), org_id=inputs.get("org_id"))
        return {"error": f"List files failed: {str(e)}"}


async def delete_file_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Delete a file from Den.

    Inputs:
      org_id: string (required) - Organization ID
      file_id: string (required) - File ID to delete
      agent_id: string (required) - Agent performing deletion

    Returns:
      {
        deleted: bool - Whether deletion was successful
      }
    """
    try:
        try:
            from inkpass_sdk.files import FileClient
            from inkpass_sdk.config import InkPassConfig
        except ImportError:
            return {"error": "InkPass SDK files module not available"}

        from ..core.config import settings

        org_id = inputs.get("org_id")
        file_id = inputs.get("file_id")
        agent_id = inputs.get("agent_id")

        if not all([org_id, file_id, agent_id]):
            return {"error": "Missing required fields: org_id, file_id, agent_id"}

        config = InkPassConfig(
            base_url=settings.INKPASS_URL,
            api_key=settings.INKPASS_SERVICE_API_KEY
        )

        async with FileClient(config) as client:
            deleted = await client.delete(UUID(org_id), UUID(file_id), agent_id)

        return {"deleted": deleted}

    except Exception as e:
        logger.error("den_delete_failed", error=str(e), file_id=inputs.get("file_id"))
        return {"error": f"Delete failed: {str(e)}"}


async def get_file_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Get file metadata from Den.

    Inputs:
      org_id: string (required) - Organization ID
      file_id: string (required) - File ID

    Returns:
      {
        file: dict - File metadata including name, size, url, etc.
      }
    """
    try:
        try:
            from inkpass_sdk.files import FileClient
            from inkpass_sdk.config import InkPassConfig
        except ImportError:
            return {"error": "InkPass SDK files module not available"}

        from ..core.config import settings

        org_id = inputs.get("org_id")
        file_id = inputs.get("file_id")

        if not all([org_id, file_id]):
            return {"error": "Missing required fields: org_id, file_id"}

        config = InkPassConfig(
            base_url=settings.INKPASS_URL,
            api_key=settings.INKPASS_SERVICE_API_KEY
        )

        async with FileClient(config) as client:
            file_metadata = await client.get_file(UUID(org_id), UUID(file_id))

        return {"file": file_metadata}

    except Exception as e:
        logger.error("den_get_file_failed", error=str(e), file_id=inputs.get("file_id"))
        return {"error": f"Get file failed: {str(e)}"}


async def duplicate_file_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Duplicate a file in Den.

    Inputs:
      org_id: string (required) - Organization ID
      file_id: string (required) - File ID to duplicate
      agent_id: string (required) - Agent performing duplication
      new_name: string (optional) - Name for the duplicate
      new_folder: string (optional) - Folder for the duplicate

    Returns:
      {
        file_id: string - UUID of the new file,
        filename: string - Name of the new file,
        folder_path: string - Folder path of the new file
      }
    """
    try:
        try:
            from inkpass_sdk.files import FileClient
            from inkpass_sdk.config import InkPassConfig
        except ImportError:
            return {"error": "InkPass SDK files module not available"}

        from ..core.config import settings

        org_id = inputs.get("org_id")
        file_id = inputs.get("file_id")
        agent_id = inputs.get("agent_id")

        if not all([org_id, file_id, agent_id]):
            return {"error": "Missing required fields: org_id, file_id, agent_id"}

        config = InkPassConfig(
            base_url=settings.INKPASS_URL,
            api_key=settings.INKPASS_SERVICE_API_KEY
        )

        async with FileClient(config) as client:
            result = await client.duplicate(
                org_id=UUID(org_id),
                file_id=UUID(file_id),
                agent_id=agent_id,
                new_name=inputs.get("new_name"),
                new_folder=inputs.get("new_folder"),
            )

        return {
            "file_id": str(result.get("id")),
            "filename": result.get("name"),
            "folder_path": result.get("folder_path"),
        }

    except Exception as e:
        logger.error("den_duplicate_failed", error=str(e), file_id=inputs.get("file_id"))
        return {"error": f"Duplicate failed: {str(e)}"}


async def move_file_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Move/rename a file in Den.

    Inputs:
      org_id: string (required) - Organization ID
      file_id: string (required) - File ID to move
      new_folder: string (required) - New folder path
      new_name: string (optional) - New file name

    Returns:
      {
        file_id: string - UUID of the file,
        filename: string - Name of the file,
        folder_path: string - New folder path
      }
    """
    try:
        try:
            from inkpass_sdk.files import FileClient
            from inkpass_sdk.config import InkPassConfig
        except ImportError:
            return {"error": "InkPass SDK files module not available"}

        from ..core.config import settings

        org_id = inputs.get("org_id")
        file_id = inputs.get("file_id")
        new_folder = inputs.get("new_folder")

        if not all([org_id, file_id, new_folder]):
            return {"error": "Missing required fields: org_id, file_id, new_folder"}

        config = InkPassConfig(
            base_url=settings.INKPASS_URL,
            api_key=settings.INKPASS_SERVICE_API_KEY
        )

        async with FileClient(config) as client:
            result = await client.move(
                org_id=UUID(org_id),
                file_id=UUID(file_id),
                new_folder=new_folder,
                new_name=inputs.get("new_name"),
            )

        return {
            "file_id": str(result.get("id")),
            "filename": result.get("name"),
            "folder_path": result.get("folder_path"),
        }

    except Exception as e:
        logger.error("den_move_failed", error=str(e), file_id=inputs.get("file_id"))
        return {"error": f"Move failed: {str(e)}"}


async def save_json_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Save JSON data to a file in Den.

    Inputs:
      org_id: string (required) - Organization ID
      workflow_id: string (required) - Workflow ID
      agent_id: string (required) - Agent ID
      data: any (required) - JSON-serializable data
      filename: string (required) - Name of file
      folder_path: string (optional) - Folder path (default: "/agent-outputs")
      tags: list[string] (optional) - Tags for categorization
      is_public: bool (optional) - Make publicly accessible (default: False)

    Returns:
      {
        file_id: string - UUID of saved file,
        filename: string - Name of file,
        url: string - Access URL
      }
    """
    data = inputs.get("data")
    if data is None:
        return {"error": "Missing required field: data"}

    try:
        filename = inputs.get("filename", "")

        # Determine content type and format based on filename and data type
        if filename.endswith(".md") or filename.endswith(".txt"):
            # For markdown/text files, extract content string if data is a dict
            if isinstance(data, dict) and "content" in data:
                content = data["content"]
            elif isinstance(data, str):
                content = data
            else:
                content = json.dumps(data, indent=2, default=str)
            content_type = "text/markdown" if filename.endswith(".md") else "text/plain"
        else:
            # For other files, save as JSON
            content = json.dumps(data, indent=2, default=str)
            content_type = "application/json"

        # Reuse upload handler
        upload_inputs = {
            **inputs,
            "content": content,
            "content_type": content_type,
        }

        return await upload_file_handler(upload_inputs)

    except Exception as e:
        logger.error("den_save_json_failed", error=str(e), filename=inputs.get("filename"))
        return {"error": f"Save JSON failed: {str(e)}"}


async def load_json_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Load JSON data from a file in Den.

    Inputs:
      org_id: string (required) - Organization ID
      file_id: string (required) - File ID to load

    Returns:
      {
        data: any - Parsed JSON data
      }
    """
    try:
        # Reuse download handler
        download_result = await download_file_handler(inputs)

        if "error" in download_result:
            return download_result

        content = download_result.get("content")
        data = json.loads(content)

        return {"data": data}

    except Exception as e:
        logger.error("den_load_json_failed", error=str(e), file_id=inputs.get("file_id"))
        return {"error": f"Load JSON failed: {str(e)}"}


async def save_context_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Save agent context/memory to persistent storage.

    Inputs:
      org_id: string (required) - Organization ID
      workflow_id: string (required) - Workflow ID
      agent_id: string (required) - Agent ID
      context: dict (required) - Context data to save

    Returns:
      {
        file_id: string - UUID of saved context,
        filename: string - Name of context file
      }
    """
    context = inputs.get("context")
    if not context:
        return {"error": "Missing required field: context"}

    agent_id = inputs.get("agent_id")
    workflow_id = inputs.get("workflow_id")

    if not all([agent_id, workflow_id]):
        return {"error": "Missing required fields: agent_id, workflow_id"}

    # Automatically generate filename and folder
    save_inputs = {
        **inputs,
        "data": context,
        "filename": f"context_{agent_id}.json",
        "folder_path": f"/agent-context/{workflow_id}",
        "tags": ["context", "memory"],
        "is_public": False,
    }

    return await save_json_handler(save_inputs)


async def load_context_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Load agent context/memory from persistent storage.

    Inputs:
      org_id: string (required) - Organization ID
      workflow_id: string (required) - Workflow ID
      agent_id: string (required) - Agent ID

    Returns:
      {
        context: dict - Loaded context data or null if not found
      }
    """
    try:
        org_id = inputs.get("org_id")
        workflow_id = inputs.get("workflow_id")
        agent_id = inputs.get("agent_id")

        if not all([org_id, workflow_id, agent_id]):
            return {"error": "Missing required fields: org_id, workflow_id, agent_id"}

        # List files to find the context file
        list_result = await list_files_handler({
            "org_id": org_id,
            "workflow_id": workflow_id,
            "folder_path": f"/agent-context/{workflow_id}",
            "tags": ["context"],
        })

        if "error" in list_result:
            return list_result

        # Find matching context file
        files = list_result.get("files", [])
        context_filename = f"context_{agent_id}.json"

        for file in files:
            if file.get("name") == context_filename:
                # Load the JSON
                load_result = await load_json_handler({
                    "org_id": org_id,
                    "file_id": file.get("id"),
                })

                if "error" in load_result:
                    return load_result

                return {"context": load_result.get("data")}

        # No context found
        return {"context": None}

    except Exception as e:
        logger.error("den_load_context_failed", error=str(e), agent_id=inputs.get("agent_id"))
        return {"error": f"Load context failed: {str(e)}"}


# Export plugin handlers
PLUGIN_HANDLERS = {
    "den_upload": upload_file_handler,
    "den_download": download_file_handler,
    "den_get_url": get_download_url_handler,
    "den_list": list_files_handler,
    "den_delete": delete_file_handler,
    "den_get_file": get_file_handler,
    "den_duplicate": duplicate_file_handler,
    "den_move": move_file_handler,
    "den_save_json": save_json_handler,
    "den_load_json": load_json_handler,
    "den_save_context": save_context_handler,
    "den_load_context": load_context_handler,
}

# Plugin definitions for registry
DEN_PLUGIN_DEFINITIONS = [
    {
        "name": "den_upload",
        "description": "Upload a file to InkPass Den storage",
        "handler": upload_file_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "workflow_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "content": {"type": ["string", "object"]},
                "filename": {"type": "string"},
                "content_type": {"type": "string"},
                "folder_path": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "is_public": {"type": "boolean"},
                "is_temporary": {"type": "boolean"},
                "expires_in_hours": {"type": "integer"},
            },
            "required": ["org_id", "workflow_id", "agent_id", "content", "filename"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string"},
                "filename": {"type": "string"},
                "url": {"type": "string"},
                "size_bytes": {"type": "integer"},
            },
        },
        "category": "file_io",
    },
    {
        "name": "den_download",
        "description": "Download a file from InkPass Den storage",
        "handler": download_file_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "file_id": {"type": "string"},
                "decode_utf8": {"type": "boolean"},
            },
            "required": ["org_id", "file_id"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "content": {},
                "size_bytes": {"type": "integer"},
            },
        },
        "category": "file_io",
    },
    {
        "name": "den_get_url",
        "description": "Get a temporary download URL for a file in Den",
        "handler": get_download_url_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "file_id": {"type": "string"},
                "expires_in": {"type": "integer"},
            },
            "required": ["org_id", "file_id"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "expires_in": {"type": "integer"},
            },
        },
        "category": "file_io",
    },
    {
        "name": "den_list",
        "description": "List files in InkPass Den with optional filtering",
        "handler": list_files_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "workflow_id": {"type": "string"},
                "folder_path": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["org_id"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "files": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
        "category": "file_io",
    },
    {
        "name": "den_delete",
        "description": "Delete a file from InkPass Den storage",
        "handler": delete_file_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "file_id": {"type": "string"},
                "agent_id": {"type": "string"},
            },
            "required": ["org_id", "file_id", "agent_id"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "deleted": {"type": "boolean"},
            },
        },
        "category": "file_io",
    },
    {
        "name": "den_get_file",
        "description": "Get file metadata from InkPass Den storage",
        "handler": get_file_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "file_id": {"type": "string"},
            },
            "required": ["org_id", "file_id"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "file": {"type": "object"},
            },
        },
        "category": "file_io",
    },
    {
        "name": "den_duplicate",
        "description": "Duplicate a file in InkPass Den storage",
        "handler": duplicate_file_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "file_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "new_name": {"type": "string"},
                "new_folder": {"type": "string"},
            },
            "required": ["org_id", "file_id", "agent_id"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string"},
                "filename": {"type": "string"},
                "folder_path": {"type": "string"},
            },
        },
        "category": "file_io",
    },
    {
        "name": "den_move",
        "description": "Move/rename a file in InkPass Den storage",
        "handler": move_file_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "file_id": {"type": "string"},
                "new_folder": {"type": "string"},
                "new_name": {"type": "string"},
            },
            "required": ["org_id", "file_id", "new_folder"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string"},
                "filename": {"type": "string"},
                "folder_path": {"type": "string"},
            },
        },
        "category": "file_io",
    },
    {
        "name": "den_save_json",
        "description": "Save JSON data to a file in Den",
        "handler": save_json_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "workflow_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "data": {},
                "filename": {"type": "string"},
                "folder_path": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "is_public": {"type": "boolean"},
            },
            "required": ["org_id", "workflow_id", "agent_id", "data", "filename"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string"},
                "filename": {"type": "string"},
                "url": {"type": "string"},
            },
        },
        "category": "file_io",
    },
    {
        "name": "den_load_json",
        "description": "Load JSON data from a file in Den",
        "handler": load_json_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "file_id": {"type": "string"},
            },
            "required": ["org_id", "file_id"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "data": {},
            },
        },
        "category": "file_io",
    },
    {
        "name": "den_save_context",
        "description": "Save agent context/memory to persistent storage in Den",
        "handler": save_context_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "workflow_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "context": {"type": "object"},
            },
            "required": ["org_id", "workflow_id", "agent_id", "context"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string"},
                "filename": {"type": "string"},
            },
        },
        "category": "file_io",
    },
    {
        "name": "den_load_context",
        "description": "Load agent context/memory from persistent storage in Den",
        "handler": load_context_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string"},
                "workflow_id": {"type": "string"},
                "agent_id": {"type": "string"},
            },
            "required": ["org_id", "workflow_id", "agent_id"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "context": {"type": ["object", "null"]},
            },
        },
        "category": "file_io",
    },
]
