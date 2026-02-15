"""
CSV Composer Plugin - Generate CSV documents and upload to Den.

This plugin takes structured data (list of dicts, list of lists, or raw CSV text)
and uploads it to Den file storage. It also returns StructuredDataContent fields
so the frontend's DataTable component renders the data automatically.

Usage:
    result = await csv_composer_handler({
        "data": [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}],
        "title": "Users Export",
        "org_id": "org-123"
    }, context)
"""

import csv
import io
import json
import structlog
from typing import Any, Dict, List

logger = structlog.get_logger(__name__)


def _parse_data(data) -> Any:
    """Parse data from JSON string if needed."""
    if isinstance(data, str):
        data = data.strip()
        if data.startswith("[") or data.startswith("{"):
            try:
                data = json.loads(data)
                logger.debug("Parsed JSON string data", parsed_type=type(data).__name__)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in data field: {str(e)}")
        else:
            raise ValueError("data must be a list, or valid JSON string")
    return data


def _generate_csv(data: List, headers: List[str] = None, delimiter: str = ",") -> str:
    """Generate CSV string from list of dicts or list of lists."""
    output = io.StringIO()

    if not data:
        return ""

    # List of dicts
    if isinstance(data[0], dict):
        fieldnames = headers or list(data[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        for row in data:
            writer.writerow(row)
    else:
        # List of lists
        writer = csv.writer(output, delimiter=delimiter)
        if headers:
            writer.writerow(headers)
        for row in data:
            writer.writerow(row)

    return output.getvalue()


def _csv_to_records(csv_text: str, delimiter: str = ",") -> List[Dict[str, Any]]:
    """Parse CSV text into list of dicts for StructuredDataContent."""
    reader = csv.DictReader(io.StringIO(csv_text), delimiter=delimiter)
    return [dict(row) for row in reader]


async def csv_composer_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """
    Generate a CSV file and upload to Den.

    Inputs:
        data: list[dict] or list[list] (optional) - Structured data to convert to CSV
        csv_text: string (optional) - Raw CSV text to use as-is
        headers: list[string] (optional) - Column headers (required for list of lists)
        delimiter: string (optional) - CSV delimiter (default: ",")
        title: string (optional) - Document title (default: "CSV Export")
        filename: string (optional) - Output filename (default: "{title}.csv")
        org_id: string (optional) - Organization ID (from context or inputs)
        folder_path: string (optional) - Den folder path
        tags: list[string] (optional) - Tags for the file
        is_public: bool (optional) - Make file publicly accessible
        include_preview: bool (optional) - Include data preview in output (default: true)
        preview_limit: int (optional) - Max rows in preview (default: 100)

    Returns:
        {
            file_id, filename, url, cdn_url, size_bytes, content_type,
            object_type: "csv_export", data: [...], total_count
        }
    """
    data = inputs.get("data")
    csv_text = inputs.get("csv_text")
    headers = inputs.get("headers", [])
    delimiter = inputs.get("delimiter", ",")
    title = inputs.get("title", "CSV Export")
    filename = inputs.get("filename", "")
    include_preview = inputs.get("include_preview", True)
    preview_limit = inputs.get("preview_limit", 100)

    if data is None and not csv_text:
        return {
            "error": "Either 'data' or 'csv_text' is required",
            "file_id": "",
            "filename": "",
            "size_bytes": 0,
        }

    try:
        # Generate or validate CSV content
        if data is not None:
            data = _parse_data(data)
            if not isinstance(data, list):
                return {
                    "error": "data must be a list of dicts or list of lists",
                    "file_id": "",
                    "filename": "",
                    "size_bytes": 0,
                }
            csv_content = _generate_csv(data, headers, delimiter)
        else:
            # Validate csv_text by parsing it
            try:
                reader = csv.reader(io.StringIO(csv_text), delimiter=delimiter)
                rows = list(reader)
                if not rows:
                    return {
                        "error": "csv_text is empty",
                        "file_id": "",
                        "filename": "",
                        "size_bytes": 0,
                    }
            except csv.Error as e:
                return {
                    "error": f"Invalid CSV text: {str(e)}",
                    "file_id": "",
                    "filename": "",
                    "size_bytes": 0,
                }
            csv_content = csv_text

        # Generate filename from title if not provided
        if not filename:
            safe_title = title.lower().replace(" ", "-")
            safe_title = "".join(c for c in safe_title if c.isalnum() or c in "-_")
            filename = f"{safe_title}.csv"

        # Ensure .csv extension
        if not filename.endswith(".csv"):
            filename += ".csv"

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
            workflow_id = inputs.get("workflow_id", "csv-composer")
        if not agent_id:
            agent_id = inputs.get("agent_id", "csv-composer")

        if not org_id:
            return {
                "error": "org_id is required (via context or inputs)",
                "file_id": "",
                "filename": "",
                "size_bytes": 0,
            }

        # Upload to Den
        from .den_file_plugin import upload_file_handler

        upload_inputs = {
            "org_id": org_id,
            "workflow_id": workflow_id,
            "agent_id": agent_id,
            "content": csv_content,
            "filename": filename,
            "content_type": "text/csv",
            "folder_path": inputs.get("folder_path", "/agent-outputs"),
            "tags": inputs.get("tags", ["document", "csv"]),
            "is_public": inputs.get("is_public", False),
        }

        result = await upload_file_handler(upload_inputs, context)

        if "error" in result and result["error"]:
            logger.error("csv_composer_upload_failed", error=result["error"])
            return result

        logger.info(
            "csv_composer_success",
            filename=filename,
            size_bytes=result.get("size_bytes"),
            file_id=result.get("file_id"),
        )

        # Build preview data for StructuredDataContent
        preview_data = []
        total_count = 0

        if include_preview:
            try:
                records = _csv_to_records(csv_content, delimiter)
                total_count = len(records)
                preview_data = records[:preview_limit]
            except Exception:
                # If parsing fails, just skip preview
                pass

        return {
            "file_id": result.get("file_id", ""),
            "filename": result.get("filename", filename),
            "url": result.get("url", ""),
            "cdn_url": result.get("cdn_url", ""),
            "size_bytes": result.get("size_bytes", len(csv_content.encode("utf-8"))),
            "content_type": "text/csv",
            "title": title,
            # StructuredDataContent fields for frontend DataTable rendering
            "object_type": "csv_export",
            "data": preview_data,
            "total_count": total_count,
        }

    except ValueError as e:
        return {
            "error": str(e),
            "file_id": "",
            "filename": "",
            "size_bytes": 0,
        }
    except Exception as e:
        logger.error("csv_composer_failed", error=str(e))
        return {
            "error": f"CSV generation failed: {str(e)}",
            "file_id": "",
            "filename": "",
            "size_bytes": 0,
        }


# Plugin definition for registration
PLUGIN_DEFINITION = {
    "name": "csv_composer",
    "description": "Generate CSV documents and upload to Den workspace storage with DataTable preview",
    "handler": csv_composer_handler,
    "inputs_schema": {
        "data": {"type": "array", "required": False, "description": "List of dicts or list of lists"},
        "csv_text": {"type": "string", "required": False, "description": "Raw CSV text"},
        "headers": {"type": "array", "required": False, "description": "Column headers"},
        "delimiter": {"type": "string", "required": False, "default": ",", "description": "CSV delimiter"},
        "title": {"type": "string", "required": False, "default": "CSV Export", "description": "Document title"},
        "filename": {"type": "string", "required": False, "description": "Output filename"},
    },
    "outputs_schema": {
        "file_id": {"type": "string", "description": "UUID of uploaded file"},
        "filename": {"type": "string", "description": "Name of the file"},
        "url": {"type": "string", "description": "Access URL"},
        "cdn_url": {"type": "string", "description": "CDN URL for public files"},
        "size_bytes": {"type": "integer", "description": "Size of the file in bytes"},
        "content_type": {"type": "string", "description": "MIME type (text/csv)"},
        "object_type": {"type": "string", "description": "Structured data type for frontend rendering"},
        "data": {"type": "array", "description": "Preview data rows"},
        "total_count": {"type": "integer", "description": "Total row count"},
    },
    "category": "document",
}
