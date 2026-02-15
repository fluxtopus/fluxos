"""
HTTP Primitives

Fast, deterministic HTTP operations without LLM.
"""

import httpx
from typing import Dict, Any


async def http_get(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform HTTP GET request.

    Inputs:
        url: URL to fetch (required)
        headers: Optional headers dict
        timeout: Request timeout in seconds (default: 30)

    Returns:
        status_code: HTTP status code
        content: Response body (JSON if parseable, else text)
        headers: Response headers
    """
    url = inputs.get("url")
    if not url:
        raise ValueError("url is required")

    headers = inputs.get("headers", {})
    timeout = inputs.get("timeout", 30.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url, headers=headers)

        # Try to parse as JSON
        try:
            content = response.json()
        except Exception:
            content = response.text

        return {
            "status_code": response.status_code,
            "content": content,
            "headers": dict(response.headers),
        }


async def http_post(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform HTTP POST request.

    Inputs:
        url: URL to post to (required)
        body: Request body (will be sent as JSON)
        headers: Optional headers dict
        timeout: Request timeout in seconds (default: 30)

    Returns:
        status_code: HTTP status code
        content: Response body (JSON if parseable, else text)
        headers: Response headers
    """
    url = inputs.get("url")
    if not url:
        raise ValueError("url is required")

    body = inputs.get("body")
    headers = inputs.get("headers", {})
    timeout = inputs.get("timeout", 30.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=body, headers=headers)

        # Try to parse as JSON
        try:
            content = response.json()
        except Exception:
            content = response.text

        return {
            "status_code": response.status_code,
            "content": content,
            "headers": dict(response.headers),
        }
