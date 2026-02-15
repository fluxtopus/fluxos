"""
Embedding Service for generating OpenAI text embeddings.

Uses text-embedding-3-small model (1536 dimensions) for file semantic search.
"""

import httpx
import structlog
from typing import Optional, List

from src.config import settings

logger = structlog.get_logger(__name__)


class EmbeddingService:
    """Generate embeddings using OpenAI API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = settings.EMBEDDING_MODEL
        self.dimensions = settings.EMBEDDING_DIMENSIONS
        self.base_url = "https://api.openai.com/v1"
        self.enabled = settings.EMBEDDING_ENABLED and bool(self.api_key)

    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed (typically filename + folder path + tags)

        Returns:
            1536-dimensional embedding vector or None on failure
        """
        if not self.enabled:
            logger.debug("embedding_disabled", reason="api_key_not_configured" if not self.api_key else "disabled")
            return None

        if not text or not text.strip():
            logger.warning("embedding_empty_text")
            return None

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "input": text.strip(),
                        "dimensions": self.dimensions
                    }
                )
                response.raise_for_status()
                data = response.json()
                embedding = data["data"][0]["embedding"]
                logger.debug("embedding_generated", text_length=len(text), dimensions=len(embedding))
                return embedding

        except httpx.HTTPStatusError as e:
            logger.error(
                "embedding_api_error",
                status=e.response.status_code,
                detail=e.response.text[:200] if e.response.text else None
            )
            return None
        except httpx.TimeoutException:
            logger.error("embedding_timeout")
            return None
        except Exception as e:
            logger.error("embedding_generation_failed", error=str(e))
            return None

    def build_searchable_text(
        self,
        filename: str,
        folder_path: str = "/",
        tags: Optional[List[str]] = None,
        content_type: Optional[str] = None
    ) -> str:
        """
        Build text representation for embedding.

        Combines filename, path, tags, and type into searchable text.
        This creates a rich semantic representation for similarity matching.

        Args:
            filename: The file name
            folder_path: Virtual folder path
            tags: List of tags
            content_type: MIME type

        Returns:
            Combined text for embedding generation
        """
        parts = [f"filename: {filename}"]

        # Add folder path (cleaned up)
        if folder_path and folder_path != "/":
            # Convert path to readable format: /marketing/reports -> marketing reports
            path_words = folder_path.strip("/").replace("/", " ").replace("-", " ").replace("_", " ")
            parts.append(f"folder: {path_words}")

        # Add content type in readable format
        if content_type:
            # Convert MIME type to readable: application/pdf -> pdf document
            type_parts = content_type.split("/")
            if len(type_parts) == 2:
                main_type, sub_type = type_parts
                if main_type == "application":
                    parts.append(f"type: {sub_type} document")
                elif main_type in ("image", "video", "audio"):
                    parts.append(f"type: {main_type} file")
                else:
                    parts.append(f"type: {content_type}")

        # Add tags
        if tags:
            parts.append(f"tags: {', '.join(tags)}")

        return " | ".join(parts)

    def is_enabled(self) -> bool:
        """Check if embedding service is enabled and configured."""
        return self.enabled


# Singleton instance for convenience
embedding_service = EmbeddingService()
