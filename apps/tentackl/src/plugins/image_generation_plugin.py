"""
Image Generation Plugin

Generates images using OpenRouter's chat completions API with image-capable models like:
- google/gemini-2.5-flash-image (default, fast & cheap)
- google/gemini-3-pro-image-preview (higher quality)
- openai/gpt-5-image-mini
- openai/gpt-5-image

OpenRouter uses /api/v1/chat/completions with modalities: ["image", "text"] for image generation.

**Auto-Storage**: When org_id/workflow_id/agent_id are provided in inputs, images are
automatically uploaded to Den (InkPass file storage) and the output contains file URLs
instead of base64 data. This prevents plan bloat from accumulating large image data.

Usage:
    # Basic (returns base64 - NOT recommended for delegation plans)
    result = await generate_image_handler({
        "prompt": "A surreal octopus conducting an orchestra of AI agents",
    })

    # With auto-storage (returns file URL - RECOMMENDED)
    result = await generate_image_handler({
        "prompt": "A surreal octopus conducting an orchestra of AI agents",
        "org_id": "...",
        "workflow_id": "...",
        "agent_id": "...",
        "folder_path": "/generated-images",  # optional
        "is_public": True,  # optional
    })
"""

import base64
import re
import httpx
import structlog
import uuid
from typing import Any, Dict, Optional
from src.core.config import settings

logger = structlog.get_logger(__name__)


async def _upload_image_to_den(
    image_base64: str,
    content_type: str,
    org_id: str,
    workflow_id: str,
    agent_id: str,
    folder_path: str = "/generated-images",
    filename: Optional[str] = None,
    is_public: bool = True,
    prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Upload a generated image to Den (InkPass file storage).

    Returns file info (file_id, url, cdn_url) on success, or {"error": "..."} on failure.
    """
    try:
        from .den_file_plugin import upload_file_handler
    except ImportError as e:
        logger.warning("Could not import den_file_plugin", error=str(e))
        return {"error": "Den file plugin not available"}

    # Generate filename if not provided
    if not filename:
        # Use a short hash of the prompt for recognizable filenames
        import hashlib
        prompt_hash = hashlib.md5((prompt or "image").encode()).hexdigest()[:8]
        ext = "png" if "png" in content_type else "jpg"
        filename = f"generated-{prompt_hash}-{uuid.uuid4().hex[:8]}.{ext}"

    try:
        result = await upload_file_handler({
            "org_id": org_id,
            "workflow_id": workflow_id,
            "agent_id": agent_id,
            "content": image_base64,
            "filename": filename,
            "content_type": content_type,
            "folder_path": folder_path,
            "is_public": is_public,
            "is_base64": True,
            "tags": ["generated-image", "ai-generated"],
        })

        if result.get("error"):
            return {"error": result["error"]}

        logger.info(
            "Image uploaded to Den",
            file_id=result.get("file_id"),
            filename=result.get("filename"),
            cdn_url=result.get("cdn_url"),
        )

        return result

    except Exception as e:
        logger.error("Failed to upload image to Den", error=str(e))
        return {"error": f"Upload failed: {str(e)}"}


async def generate_image_handler(inputs: Dict[str, Any], context=None) -> Dict[str, Any]:
    """
    Generate an image using OpenRouter's chat completions API.

    OpenRouter uses /api/v1/chat/completions with modalities: ["image", "text"]
    for image generation, NOT /api/v1/images/generations.

    Inputs:
        prompt (str, required): Text description of the image to generate
        model (str, optional): Model to use, default: google/gemini-2.5-flash-image
        filename (str, optional): Filename for saving (default: auto-generated UUID)

        # For auto-storage to Den (recommended for delegation plans):
        org_id (str, optional): Organization ID for Den storage
        workflow_id (str, optional): Workflow ID for Den storage
        agent_id (str, optional): Agent ID for Den storage
        folder_path (str, optional): Folder path in Den (default: /generated-images)
        is_public (bool, optional): Make image publicly accessible (default: True)

    Returns (with auto-storage):
        file_id (str): UUID of uploaded file in Den
        url (str): Access URL for the image
        cdn_url (str): CDN URL for public images
        model (str): Model used for generation
        prompt (str): The prompt used
        filename (str): Name of the stored file

    Returns (without auto-storage - legacy):
        image_base64 (str): Base64-encoded image data (large!)
        content_type (str): Content type (e.g., image/png)
        model (str): Model used for generation
        prompt (str): The prompt used
    """
    prompt = inputs.get("prompt")
    if not prompt:
        raise ValueError("prompt is required for image generation")

    model = inputs.get("model", "google/gemini-2.5-flash-image")

    # Map old/invalid model names to valid ones
    model_mapping = {
        "black-forest-labs/flux.2-pro": "google/gemini-2.5-flash-image",
        "black-forest-labs/flux-1.1-pro": "google/gemini-2.5-flash-image",
        "black-forest-labs/flux-pro": "google/gemini-2.5-flash-image",
        "black-forest-labs/flux-2-pro": "google/gemini-2.5-flash-image",
        "black-forest-labs/flux.2-flex": "google/gemini-2.5-flash-image",
        "flux-schnell": "google/gemini-2.5-flash-image",
        "flux-pro": "google/gemini-2.5-flash-image",
        "flux": "google/gemini-2.5-flash-image",
    }
    model = model_mapping.get(model, model)

    api_key = settings.OPENROUTER_API_KEY
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not configured")

    # Build request payload using chat completions format
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "modalities": ["image", "text"],
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Add optional site headers
    if settings.SITE_URL:
        headers["HTTP-Referer"] = settings.SITE_URL
    if settings.SITE_NAME:
        headers["X-Title"] = settings.SITE_NAME

    # DEBUG: Log payload size to trace token accumulation
    import json as _json
    payload_json = _json.dumps(payload)
    logger.info(
        "Generating image via OpenRouter chat completions",
        model=model,
        prompt_length=len(prompt),
        payload_size=len(payload_json),
        prompt_preview=prompt[:200],
    )

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
            )

            if response.status_code != 200:
                error_text = response.text
                logger.error(
                    "OpenRouter image generation failed",
                    status=response.status_code,
                    error=error_text,
                )
                raise ValueError(f"Image generation failed: {response.status_code} - {error_text}")

            result = response.json()
            logger.debug("OpenRouter image response received")

            # Extract image data from chat completions response
            if "choices" in result and len(result["choices"]) > 0:
                message = result["choices"][0].get("message", {})

                output = {
                    "model": model,
                    "prompt": prompt,
                }

                # Check for images array in the message
                images = message.get("images", [])
                if images and len(images) > 0:
                    image_data = images[0]
                    if "image_url" in image_data and "url" in image_data["image_url"]:
                        data_url = image_data["image_url"]["url"]
                        # Parse data URL: data:image/png;base64,...
                        if data_url.startswith("data:"):
                            # Extract content type and base64 data
                            match = re.match(r"data:([^;]+);base64,(.+)", data_url)
                            if match:
                                output["content_type"] = match.group(1)
                                output["image_base64"] = match.group(2)

                # Alternative: check for content that might contain the image
                content = message.get("content", "")
                if not output.get("image_base64") and content:
                    # Some models return base64 directly in content
                    if content.startswith("data:image"):
                        match = re.match(r"data:([^;]+);base64,(.+)", content)
                        if match:
                            output["content_type"] = match.group(1)
                            output["image_base64"] = match.group(2)

                if output.get("image_base64"):
                    logger.info(
                        "Image generated successfully",
                        model=model,
                        content_type=output.get("content_type"),
                    )

                    # Auto-upload to Den if org context is provided
                    org_id = inputs.get("org_id")
                    workflow_id = inputs.get("workflow_id")
                    agent_id = inputs.get("agent_id")

                    if org_id and workflow_id and agent_id:
                        # Upload to Den and return URL instead of base64
                        upload_result = await _upload_image_to_den(
                            image_base64=output["image_base64"],
                            content_type=output.get("content_type", "image/png"),
                            org_id=org_id,
                            workflow_id=workflow_id,
                            agent_id=agent_id,
                            folder_path=inputs.get("folder_path", "/generated-images"),
                            filename=inputs.get("filename"),
                            is_public=inputs.get("is_public", True),
                            prompt=prompt,
                        )

                        if upload_result.get("error"):
                            logger.warning(
                                "Failed to upload image to Den, returning base64",
                                error=upload_result["error"],
                            )
                            return output

                        # Return file info instead of base64 (much smaller!)
                        return {
                            "file_id": upload_result.get("file_id"),
                            "url": upload_result.get("url"),
                            "cdn_url": upload_result.get("cdn_url"),
                            "filename": upload_result.get("filename"),
                            "folder_path": upload_result.get("folder_path"),
                            "model": model,
                            "prompt": prompt,
                            "content_type": output.get("content_type"),
                            # DO NOT include image_base64 - that's the whole point!
                        }

                    # No Den context - return base64 (legacy behavior)
                    return output
                else:
                    # Log the response for debugging
                    logger.error("No image found in response", response=result)
                    raise ValueError(f"No image found in response. Message: {message}")
            else:
                raise ValueError(f"Unexpected response format: {result}")

    except httpx.TimeoutException:
        logger.error("Image generation timed out", model=model)
        raise ValueError("Image generation timed out after 180 seconds")
    except Exception as e:
        logger.error("Image generation failed", error=str(e), model=model)
        raise


# Plugin handlers dict for registry
PLUGIN_HANDLERS = {
    "generate_image": generate_image_handler,
}

# Plugin definitions for registry
IMAGE_PLUGIN_DEFINITIONS = [
    {
        "name": "generate_image",
        "description": "Generate an image using AI models (FLUX, Gemini) via OpenRouter",
        "handler": generate_image_handler,
        "inputs_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Text description of the image to generate"
                },
                "model": {
                    "type": "string",
                    "description": "Model to use (default: google/gemini-2.5-flash-image)",
                    "default": "google/gemini-2.5-flash-image"
                },
            },
            "required": ["prompt"]
        },
        "outputs_schema": {
            "type": "object",
            "properties": {
                "image_base64": {"type": "string"},
                "content_type": {"type": "string"},
                "model": {"type": "string"},
                "prompt": {"type": "string"},
            }
        },
        "category": "ai_generation",
    },
]
