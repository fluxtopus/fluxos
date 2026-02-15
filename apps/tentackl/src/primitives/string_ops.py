"""
String Primitives

Fast, deterministic string operations without LLM.
"""

import re
from typing import Dict, Any


async def string_template(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply template substitution.

    Inputs:
        template: Template string with {var} placeholders (required)
        variables: Dict of variable values (required)

    Returns:
        result: Formatted string
    """
    template = inputs.get("template")
    if not template:
        raise ValueError("template is required")

    variables = inputs.get("variables", {})

    result = template.format(**variables)
    return {"result": result}


async def string_split(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Split string into list.

    Inputs:
        text: String to split (required)
        separator: Separator (default: " ")
        max_splits: Maximum number of splits (default: unlimited)

    Returns:
        result: List of parts
        count: Number of parts
    """
    text = inputs.get("text")
    if text is None:
        raise ValueError("text is required")

    separator = inputs.get("separator", " ")
    max_splits = inputs.get("max_splits", -1)

    result = text.split(separator, max_splits)
    return {
        "result": result,
        "count": len(result),
    }


async def string_replace(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Replace text in string.

    Inputs:
        text: String to modify (required)
        pattern: Pattern to find (string or regex)
        replacement: Replacement text
        regex: Whether to treat pattern as regex (default: False)
        count: Max replacements (default: all)

    Returns:
        result: Modified string
        replacements: Number of replacements made
    """
    text = inputs.get("text")
    if text is None:
        raise ValueError("text is required")

    pattern = inputs.get("pattern")
    if not pattern:
        raise ValueError("pattern is required")

    replacement = inputs.get("replacement", "")
    use_regex = inputs.get("regex", False)
    count = inputs.get("count", 0)  # 0 means all

    if use_regex:
        result, num_replacements = re.subn(pattern, replacement, text, count=count)
    else:
        if count:
            result = text.replace(pattern, replacement, count)
            num_replacements = min(text.count(pattern), count)
        else:
            num_replacements = text.count(pattern)
            result = text.replace(pattern, replacement)

    return {
        "result": result,
        "replacements": num_replacements,
    }


async def string_match(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Match pattern in string.

    Inputs:
        text: String to search (required)
        pattern: Pattern to find (regex)
        find_all: Return all matches (default: False)

    Returns:
        matched: Whether pattern was found
        match: First match or list of all matches
        groups: Capture groups from first match
    """
    text = inputs.get("text")
    if text is None:
        raise ValueError("text is required")

    pattern = inputs.get("pattern")
    if not pattern:
        raise ValueError("pattern is required")

    find_all = inputs.get("find_all", False)

    if find_all:
        matches = re.findall(pattern, text)
        return {
            "matched": len(matches) > 0,
            "match": matches,
            "count": len(matches),
        }
    else:
        match = re.search(pattern, text)
        if match:
            return {
                "matched": True,
                "match": match.group(0),
                "groups": match.groups() if match.groups() else None,
            }
        return {
            "matched": False,
            "match": None,
            "groups": None,
        }
