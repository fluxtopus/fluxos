"""
List Primitives

Fast, deterministic list operations without LLM.
"""

from typing import Dict, Any, List
import operator


async def list_filter(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Filter list items by condition.

    Inputs:
        items: List to filter (required)
        field: Field name to check (for list of dicts)
        operator: Comparison operator (eq, ne, gt, lt, gte, lte, contains, exists)
        value: Value to compare against

    Returns:
        result: Filtered list
        count: Number of items after filtering
    """
    items = inputs.get("items")
    if items is None:
        raise ValueError("items is required")

    if not isinstance(items, list):
        raise ValueError("items must be a list")

    field = inputs.get("field")
    op = inputs.get("operator", "eq")
    value = inputs.get("value")

    # Define operators
    ops = {
        "eq": operator.eq,
        "ne": operator.ne,
        "gt": operator.gt,
        "lt": operator.lt,
        "gte": operator.ge,
        "lte": operator.le,
        "contains": lambda a, b: b in a if a else False,
        "exists": lambda a, _: a is not None,
    }

    compare = ops.get(op)
    if not compare:
        raise ValueError(f"Unknown operator: {op}")

    result = []
    for item in items:
        if field:
            # Filter by field in dict
            if isinstance(item, dict):
                item_value = item.get(field)
            else:
                item_value = getattr(item, field, None)
        else:
            item_value = item

        if compare(item_value, value):
            result.append(item)

    return {
        "result": result,
        "count": len(result),
    }


async def list_map(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform list items by extracting or renaming fields.

    Inputs:
        items: List to transform (required)
        fields: List of field names to extract, or dict for renaming
        template: String template with {field} placeholders

    Returns:
        result: Transformed list
        count: Number of items
    """
    items = inputs.get("items")
    if items is None:
        raise ValueError("items is required")

    if not isinstance(items, list):
        raise ValueError("items must be a list")

    fields = inputs.get("fields")
    template = inputs.get("template")

    result = []
    for item in items:
        if template:
            # Apply string template
            if isinstance(item, dict):
                result.append(template.format(**item))
            else:
                result.append(template.format(item=item))
        elif fields:
            if isinstance(fields, list):
                # Extract specific fields
                if isinstance(item, dict):
                    result.append({f: item.get(f) for f in fields})
                else:
                    result.append(item)
            elif isinstance(fields, dict):
                # Rename fields
                if isinstance(item, dict):
                    result.append({new: item.get(old) for old, new in fields.items()})
                else:
                    result.append(item)
        else:
            result.append(item)

    return {
        "result": result,
        "count": len(result),
    }


async def list_reduce(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reduce list to single value.

    Inputs:
        items: List to reduce (required)
        operation: Reduction operation (sum, count, avg, min, max, join)
        field: Field to reduce (for list of dicts)
        separator: Separator for join operation (default: ", ")

    Returns:
        result: Reduced value
    """
    items = inputs.get("items")
    if items is None:
        raise ValueError("items is required")

    if not isinstance(items, list):
        raise ValueError("items must be a list")

    operation = inputs.get("operation", "count")
    field = inputs.get("field")
    separator = inputs.get("separator", ", ")

    # Extract field values if specified
    if field:
        values = [
            item.get(field) if isinstance(item, dict) else getattr(item, field, item)
            for item in items
        ]
    else:
        values = items

    if operation == "count":
        result = len(values)
    elif operation == "sum":
        result = sum(v for v in values if isinstance(v, (int, float)))
    elif operation == "avg":
        nums = [v for v in values if isinstance(v, (int, float))]
        result = sum(nums) / len(nums) if nums else 0
    elif operation == "min":
        nums = [v for v in values if v is not None]
        result = min(nums) if nums else None
    elif operation == "max":
        nums = [v for v in values if v is not None]
        result = max(nums) if nums else None
    elif operation == "join":
        result = separator.join(str(v) for v in values if v is not None)
    else:
        raise ValueError(f"Unknown operation: {operation}")

    return {"result": result}
