"""
Workspace CSV Plugin - Export workspace objects to CSV and import CSV into workspace.

Two handlers:
- workspace_export_csv_handler: Query workspace objects → flatten → CSV → Den upload
- workspace_import_csv_handler: CSV (text or Den file) → parse → create workspace objects
"""

import csv
import io
import json
import structlog
from typing import Any, Dict, List

from src.application.workspace import WorkspaceUseCases
from src.infrastructure.workspace import WorkspaceServiceAdapter
from src.interfaces.database import Database

logger = structlog.get_logger(__name__)

# Database instance - will be set by the lifespan or caller
_database: Database = None


def set_database(db: Database) -> None:
    """Set the database instance for workspace CSV plugins."""
    global _database
    _database = db


class WorkspaceService:
    """Workspace helper that delegates to workspace use cases."""

    def __init__(self, db: Database):
        self._use_cases = WorkspaceUseCases(workspace_ops=WorkspaceServiceAdapter(db))

    async def query(
        self,
        org_id: str,
        type: str | None = None,
        where: Dict[str, Any] | None = None,
        tags: List[str] | None = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        return await self._use_cases.query_objects(
            org_id=org_id,
            type=type,
            where=where,
            tags=tags,
            limit=limit,
        )

    async def create(
        self,
        org_id: str,
        type: str,
        data: Dict[str, Any],
        tags: List[str] | None = None,
        created_by_type: str | None = None,
        created_by_id: str | None = None,
    ) -> Dict[str, Any]:
        return await self._use_cases.create_object(
            org_id=org_id,
            type=type,
            data=data,
            tags=tags,
            created_by_type=created_by_type,
            created_by_id=created_by_id,
        )


async def _get_service() -> WorkspaceService:
    """Get workspace service helper."""
    if not _database:
        raise ValueError("Database not initialized for workspace CSV plugin")
    return WorkspaceService(_database)


def _flatten_object(obj: Dict[str, Any], include_metadata: bool = True) -> Dict[str, Any]:
    """Flatten a workspace object for CSV export.

    Promotes nested data fields to top-level columns.
    Nested dicts/lists within data are JSON-serialized.
    """
    flat = {}

    if include_metadata:
        flat["id"] = obj.get("id", "")
        flat["type"] = obj.get("type", "")
        created_at = obj.get("created_at", "")
        if hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()
        flat["created_at"] = str(created_at)
        tags = obj.get("tags", [])
        flat["tags"] = json.dumps(tags) if tags else ""

    data = obj.get("data", {})
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                flat[key] = json.dumps(value, default=str)
            else:
                flat[key] = value if value is not None else ""
    else:
        flat["data"] = json.dumps(data, default=str) if data else ""

    return flat


async def workspace_export_csv_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """
    Export workspace objects to CSV and upload to Den.

    Inputs:
        org_id: string (required) - Organization ID
        type: string (optional) - Filter by object type
        where: object (optional) - MongoDB-style query operators
        tags: list[string] (optional) - Filter by tags
        limit: int (optional) - Max objects to export (default: 1000)
        columns: list[string] (optional) - Specific data columns to include
        flatten_data: bool (optional) - Flatten nested data (default: true)
        include_metadata: bool (optional) - Include id, created_at, tags (default: true)
        delimiter: string (optional) - CSV delimiter (default: ",")
        title: string (optional) - Document title
        filename: string (optional) - Output filename

    Returns:
        {
            file_id, filename, url, cdn_url, size_bytes, content_type,
            object_type: "csv_export", data: [...], total_count,
            rows_exported
        }
    """
    org_id = inputs.get("org_id")
    if not org_id:
        # Try context
        if context:
            org_id = getattr(context, "org_id", None) or getattr(context, "organization_id", None)
        if not org_id:
            return {"error": "org_id is required"}

    obj_type = inputs.get("type")
    delimiter = inputs.get("delimiter", ",")
    columns = inputs.get("columns")
    include_metadata = inputs.get("include_metadata", True)
    title = inputs.get("title", f"Workspace Export - {obj_type or 'all'}")
    filename = inputs.get("filename", "")
    limit = inputs.get("limit", 1000)

    try:
        service = await _get_service()
        objects = await service.query(
            org_id=org_id,
            type=obj_type,
            where=inputs.get("where"),
            tags=inputs.get("tags"),
            limit=limit,
        )

        if not objects:
            return {
                "rows_exported": 0,
                "message": "No objects found matching the query",
                "object_type": "csv_export",
                "data": [],
                "total_count": 0,
            }

        # Flatten objects
        flat_objects = [_flatten_object(obj, include_metadata) for obj in objects]

        # Determine columns
        if columns:
            # Only include specified columns (plus metadata if requested)
            meta_cols = ["id", "type", "created_at", "tags"] if include_metadata else []
            all_cols = meta_cols + [c for c in columns if c not in meta_cols]
            # Filter flat objects to only include specified columns
            flat_objects = [
                {k: row.get(k, "") for k in all_cols}
                for row in flat_objects
            ]
            fieldnames = all_cols
        else:
            # Collect all unique keys preserving order
            fieldnames = []
            seen = set()
            for obj in flat_objects:
                for key in obj.keys():
                    if key not in seen:
                        fieldnames.append(key)
                        seen.add(key)

        # Generate CSV
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter=delimiter, extrasaction="ignore")
        writer.writeheader()
        for row in flat_objects:
            writer.writerow(row)
        csv_content = output.getvalue()

        # Generate filename
        if not filename:
            safe_title = title.lower().replace(" ", "-")
            safe_title = "".join(c for c in safe_title if c.isalnum() or c in "-_")
            filename = f"{safe_title}.csv"
        if not filename.endswith(".csv"):
            filename += ".csv"

        # Upload to Den
        from .den_file_plugin import upload_file_handler

        workflow_id = inputs.get("workflow_id", "workspace-csv-export")
        agent_id = inputs.get("agent_id", "workspace-csv-export")

        if context:
            workflow_id = getattr(context, "workflow_id", None) or workflow_id
            agent_id = getattr(context, "agent_id", None) or agent_id

        upload_inputs = {
            "org_id": org_id,
            "workflow_id": workflow_id,
            "agent_id": agent_id,
            "content": csv_content,
            "filename": filename,
            "content_type": "text/csv",
            "folder_path": inputs.get("folder_path", "/agent-outputs"),
            "tags": inputs.get("file_tags", ["document", "csv", "workspace-export"]),
            "is_public": inputs.get("is_public", False),
        }

        result = await upload_file_handler(upload_inputs, context)

        if "error" in result and result["error"]:
            logger.error("workspace_export_csv_upload_failed", error=result["error"])
            return result

        logger.info(
            "workspace_export_csv_success",
            filename=filename,
            rows_exported=len(flat_objects),
            file_id=result.get("file_id"),
        )

        # Build preview data (first 100 rows)
        preview_data = flat_objects[:100]

        return {
            "file_id": result.get("file_id", ""),
            "filename": result.get("filename", filename),
            "url": result.get("url", ""),
            "cdn_url": result.get("cdn_url", ""),
            "size_bytes": result.get("size_bytes", len(csv_content.encode("utf-8"))),
            "content_type": "text/csv",
            "title": title,
            "rows_exported": len(flat_objects),
            # StructuredDataContent fields
            "object_type": "csv_export",
            "data": preview_data,
            "total_count": len(flat_objects),
        }

    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.error("workspace_export_csv_failed", error=str(e))
        return {"error": f"Failed to export workspace to CSV: {str(e)}"}


async def workspace_import_csv_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """
    Import CSV data into workspace objects.

    Inputs:
        org_id: string (required) - Organization ID
        type: string (required) - Object type to create
        csv_text: string (optional) - Raw CSV text to import
        file_id: string (optional) - Den file ID to download and import
        column_mapping: dict (optional) - Rename columns {csv_col: workspace_col}
        skip_empty_rows: bool (optional) - Skip rows where all values are empty (default: true)
        tags: list[string] (optional) - Tags for created objects
        dry_run: bool (optional) - Parse only, don't create objects (default: false)

    Returns:
        {
            objects_created, objects_skipped, errors,
            object_type: "csv_import", data: [...]
        }
    """
    org_id = inputs.get("org_id")
    if not org_id:
        if context:
            org_id = getattr(context, "org_id", None) or getattr(context, "organization_id", None)
        if not org_id:
            return {"error": "org_id is required"}

    obj_type = inputs.get("type")
    if not obj_type:
        return {"error": "type is required"}

    csv_text = inputs.get("csv_text")
    file_id = inputs.get("file_id")
    column_mapping = inputs.get("column_mapping", {})
    skip_empty_rows = inputs.get("skip_empty_rows", True)
    tags = inputs.get("tags")
    dry_run = inputs.get("dry_run", False)

    if not csv_text and not file_id:
        return {"error": "Either 'csv_text' or 'file_id' is required"}

    try:
        # Download from Den if file_id provided
        if file_id and not csv_text:
            from .den_file_plugin import download_file_handler

            download_result = await download_file_handler({
                "org_id": org_id,
                "file_id": file_id,
                "decode_utf8": True,
            })

            if "error" in download_result and download_result["error"]:
                return {"error": f"Failed to download CSV: {download_result['error']}"}

            csv_text = download_result.get("content", "")

        if not csv_text:
            return {"error": "No CSV content to import"}

        # Parse CSV
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = []
        for row in reader:
            # Apply column mapping
            if column_mapping:
                mapped = {}
                for csv_col, value in row.items():
                    new_col = column_mapping.get(csv_col, csv_col)
                    mapped[new_col] = value
                row = mapped

            # Remove None key (DictReader overflow from extra delimiters)
            row = {k: v for k, v in row.items() if k is not None}

            # Skip empty rows
            if skip_empty_rows and all(
                not v or (isinstance(v, str) and v.strip() == "") for v in row.values()
            ):
                continue

            rows.append(dict(row))

        if dry_run:
            return {
                "objects_created": 0,
                "objects_skipped": 0,
                "dry_run": True,
                "rows_parsed": len(rows),
                "columns": list(rows[0].keys()) if rows else [],
                "object_type": "csv_import",
                "data": rows[:100],
                "total_count": len(rows),
            }

        # Create workspace objects
        objects_created = 0
        objects_skipped = 0
        errors = []
        created_objects = []

        service = await _get_service()
        for i, row_data in enumerate(rows):
            try:
                result = await service.create(
                    org_id=org_id,
                    type=obj_type,
                    data=row_data,
                    tags=tags,
                    created_by_type="agent",
                    created_by_id=inputs.get("created_by_id", "workspace-csv-import"),
                )
                created_objects.append(result)
                objects_created += 1
            except Exception as e:
                objects_skipped += 1
                errors.append(f"Row {i}: {str(e)}")

        logger.info(
            "workspace_import_csv_success",
            objects_created=objects_created,
            objects_skipped=objects_skipped,
            error_count=len(errors),
        )

        return {
            "objects_created": objects_created,
            "objects_skipped": objects_skipped,
            "errors": errors if errors else None,
            "object_type": "csv_import",
            "data": created_objects[:100],
            "total_count": objects_created,
        }

    except Exception as e:
        logger.error("workspace_import_csv_failed", error=str(e))
        return {"error": f"Failed to import CSV: {str(e)}"}


# Plugin definitions for registration
WORKSPACE_CSV_PLUGIN_DEFINITIONS = [
    {
        "name": "workspace_export_csv",
        "description": "Export workspace objects to CSV file and upload to Den",
        "handler": workspace_export_csv_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string", "description": "Organization ID"},
                "type": {"type": "string", "description": "Object type to export"},
                "where": {"type": "object", "description": "MongoDB-style query operators"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "default": 1000},
                "columns": {"type": "array", "items": {"type": "string"}, "description": "Specific columns to include"},
                "include_metadata": {"type": "boolean", "default": True},
                "delimiter": {"type": "string", "default": ","},
                "title": {"type": "string"},
                "filename": {"type": "string"},
            },
            "required": ["org_id"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string"},
                "filename": {"type": "string"},
                "url": {"type": "string"},
                "rows_exported": {"type": "integer"},
                "object_type": {"type": "string"},
                "data": {"type": "array"},
                "total_count": {"type": "integer"},
            },
        },
        "category": "workspace",
    },
    {
        "name": "workspace_import_csv",
        "description": "Import CSV data into workspace objects",
        "handler": workspace_import_csv_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "org_id": {"type": "string", "description": "Organization ID"},
                "type": {"type": "string", "description": "Object type to create"},
                "csv_text": {"type": "string", "description": "Raw CSV text to import"},
                "file_id": {"type": "string", "description": "Den file ID to download"},
                "column_mapping": {"type": "object", "description": "Column rename mapping"},
                "skip_empty_rows": {"type": "boolean", "default": True},
                "tags": {"type": "array", "items": {"type": "string"}},
                "dry_run": {"type": "boolean", "default": False},
            },
            "required": ["org_id", "type"],
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "objects_created": {"type": "integer"},
                "objects_skipped": {"type": "integer"},
                "errors": {"type": "array"},
                "object_type": {"type": "string"},
                "data": {"type": "array"},
                "total_count": {"type": "integer"},
            },
        },
        "category": "workspace",
    },
]
