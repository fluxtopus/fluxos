"""Text processing plugin for deterministic text transformations.

This plugin provides simple, deterministic text processing operations
that don't require LLM inference.
"""

from typing import Any, Dict
import re


async def clean_yaml_fences_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Clean markdown code fences and extra whitespace from YAML content.

    Inputs:
      text: string (required) - The text containing YAML, possibly with markdown fences

    Returns:
      { result: string } - The cleaned YAML content
    """
    text = inputs.get("text", "")

    if not text:
        return {"result": "", "error": "No text provided"}

    # Remove markdown code fences (```yaml, ```yml, or just ```)
    # Pattern matches opening fence with optional language identifier
    text = re.sub(r'^```(?:yaml|yml)?\s*\n', '', text, flags=re.MULTILINE)

    # Remove closing fences
    text = re.sub(r'\n```\s*$', '', text, flags=re.MULTILINE)

    # Also handle case where the entire content is wrapped
    if text.startswith('```'):
        lines = text.split('\n')
        # Remove first line if it's a fence
        if lines[0].startswith('```'):
            lines = lines[1:]
        # Remove last line if it's a fence
        if lines and lines[-1].strip().startswith('```'):
            lines = lines[:-1]
        text = '\n'.join(lines)

    # Strip leading and trailing whitespace
    text = text.strip()

    return {
        "result": text,
        "original_length": len(inputs.get("text", "")),
        "cleaned_length": len(text)
    }


async def extract_code_block_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Extract content from markdown code blocks.

    Inputs:
      text: string (required) - The text containing code blocks
      language: string (optional) - Specific language to extract (e.g., "yaml", "python")

    Returns:
      { result: string } - The extracted code block content
    """
    text = inputs.get("text", "")
    language = inputs.get("language", None)

    if not text:
        return {"result": "", "error": "No text provided"}

    # Build pattern based on language filter
    if language:
        pattern = rf'```{re.escape(language)}\s*\n(.*?)\n```'
    else:
        pattern = r'```(?:\w+)?\s*\n(.*?)\n```'

    # Find first match
    match = re.search(pattern, text, re.DOTALL)

    if match:
        return {
            "result": match.group(1).strip(),
            "found": True
        }
    else:
        return {
            "result": "",
            "found": False,
            "error": f"No code block found{f' for language {language}' if language else ''}"
        }


async def strip_whitespace_handler(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Strip leading and trailing whitespace from text.

    Inputs:
      text: string (required) - The text to strip

    Returns:
      { result: string } - The stripped text
    """
    text = inputs.get("text", "")
    return {"result": text.strip()}


# Export plugin handlers
PLUGIN_HANDLERS = {
    "clean_yaml_fences": clean_yaml_fences_handler,
    "extract_code_block": extract_code_block_handler,
    "strip_whitespace": strip_whitespace_handler,
}
