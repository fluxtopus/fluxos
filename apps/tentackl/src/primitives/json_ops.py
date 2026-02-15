"""
JSON Primitives

Fast, deterministic JSON operations without LLM.
"""

import json
from typing import Dict, Any


async def json_parse(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse JSON string to object.

    Inputs:
        data: JSON string to parse (required)

    Returns:
        result: Parsed object
    """
    data = inputs.get("data")
    if data is None:
        raise ValueError("data is required")

    if isinstance(data, (dict, list)):
        # Already parsed
        return {"result": data}

    result = json.loads(data)
    return {"result": result}


async def json_stringify(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert object to JSON string.

    Inputs:
        data: Object to stringify (required)
        indent: Indentation level (default: None for compact)
        sort_keys: Sort keys alphabetically (default: False)

    Returns:
        result: JSON string
    """
    data = inputs.get("data")
    if data is None:
        raise ValueError("data is required")

    indent = inputs.get("indent")
    sort_keys = inputs.get("sort_keys", False)

    result = json.dumps(data, indent=indent, sort_keys=sort_keys)
    return {"result": result}
