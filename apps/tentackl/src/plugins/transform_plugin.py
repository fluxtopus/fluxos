"""
Transform Plugin - Deterministic data format transformations.

This plugin handles data format conversions like JSON parsing,
stringification, and basic restructuring without LLM involvement.
"""

import json
import structlog
from typing import Any, Dict

logger = structlog.get_logger(__name__)


async def transform_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """
    Transform data between formats.

    Inputs:
        content: any (required) - Content/data to transform
        format: string (optional) - Target format: json, string, csv (default: json)
        instructions: string (optional) - Transformation instructions (for future use)

    Returns:
        {
            transformed_data: any - The transformed data,
            result: any - Alias for transformed_data (for compatibility),
            source_type: string - Original data type,
            target_format: string - Format converted to
        }
    """
    # Support both 'content' (standard) and 'data' (legacy) field names
    content = inputs.get("content") or inputs.get("data")
    # Support both 'format' (standard) and 'target_format' (legacy)
    target_format = inputs.get("format") or inputs.get("target_format", "json")

    if content is None:
        return {"error": "Required field 'content' is missing"}

    source_type = type(content).__name__

    try:
        if target_format == "json":
            if isinstance(content, str):
                transformed = json.loads(content)
            else:
                transformed = content

        elif target_format == "string":
            if isinstance(content, (dict, list)):
                transformed = json.dumps(content, indent=2)
            else:
                transformed = str(content)

        elif target_format == "csv":
            # Basic CSV conversion for lists of dicts
            if isinstance(content, list) and len(content) > 0 and isinstance(content[0], dict):
                headers = list(content[0].keys())
                lines = [",".join(headers)]
                for row in content:
                    lines.append(",".join(str(row.get(h, "")) for h in headers))
                transformed = "\n".join(lines)
            else:
                transformed = str(content)

        else:
            # Unknown format, return as-is
            transformed = content

        return {
            "transformed_data": transformed,
            "result": transformed,  # Alias for compatibility
            "source_type": source_type,
            "target_format": target_format,
        }

    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {str(e)}"}
    except Exception as e:
        logger.error("transform_plugin_failed", error=str(e))
        return {"error": f"Transform failed: {str(e)}"}


PLUGIN_DEFINITION = {
    "name": "transform",
    "description": "Transform data between formats (JSON, string, CSV)",
    "handler": transform_handler,
    "inputs_schema": {
        "content": {"type": "any", "required": True, "description": "Content/data to transform"},
        "format": {
            "type": "string",
            "required": False,
            "default": "json",
            "enum": ["json", "string", "csv"],
            "description": "Target format",
        },
        "instructions": {"type": "string", "required": False, "description": "Transformation instructions"},
    },
    "outputs_schema": {
        "transformed_data": {"type": "any", "description": "The transformed data"},
        "result": {"type": "any", "description": "Alias for transformed_data"},
        "source_type": {"type": "string", "description": "Original data type"},
        "target_format": {"type": "string", "description": "Format converted to"},
    },
    "category": "data_processing",
}
