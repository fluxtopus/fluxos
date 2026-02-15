"""
OpenAI API client for embeddings.

This client handles embedding generation via OpenAI's API.
For LLM completions, use OpenRouterClient instead.

Supported models:
- text-embedding-3-small (1536 dimensions, recommended)
- text-embedding-3-large (3072 dimensions)
- text-embedding-ada-002 (1536 dimensions, legacy)
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import httpx
import structlog

from src.interfaces.external_api import HTTPClient
from src.core.config import settings

logger = structlog.get_logger(__name__)


@dataclass
class EmbeddingResult:
    """Result from embedding generation."""
    embedding: List[float]
    model: str
    usage: Dict[str, int]  # prompt_tokens, total_tokens


@dataclass
class BatchEmbeddingResult:
    """Result from batch embedding generation."""
    embeddings: List[List[float]]
    model: str
    usage: Dict[str, int]


class OpenAIEmbeddingClient(HTTPClient):
    """
    OpenAI client specialized for embedding generation.

    Single responsibility: Generate text embeddings via OpenAI API.

    Usage:
        async with OpenAIEmbeddingClient() as client:
            result = await client.create_embedding("Hello world")
            vector = result.embedding  # 1536-dimensional vector
    """

    # Default embedding model
    DEFAULT_MODEL = "text-embedding-3-small"
    DEFAULT_DIMENSIONS = 1536

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        dimensions: int = DEFAULT_DIMENSIONS,
    ):
        """
        Initialize OpenAI embedding client.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY from settings)
            model: Embedding model to use
            dimensions: Vector dimensions (1536 for small, 3072 for large)
        """
        super().__init__(
            base_url="https://api.openai.com/v1",
            timeout=30
        )
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model
        self.dimensions = dimensions

    @property
    def is_configured(self) -> bool:
        """Check if the client has a valid API key."""
        return bool(self.api_key)

    async def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict] = None,
        data: Optional[Any] = None,
        params: Optional[Dict] = None
    ) -> httpx.Response:
        """Make OpenAI API request with authentication."""
        if not self.api_key:
            raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY in environment.")

        headers = headers or {}
        headers["Authorization"] = f"Bearer {self.api_key}"
        headers["Content-Type"] = "application/json"

        return await super().request(method, url, headers, data, params)

    async def create_embedding(
        self,
        text: str,
        model: Optional[str] = None,
        dimensions: Optional[int] = None,
    ) -> EmbeddingResult:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed
            model: Override default model
            dimensions: Override default dimensions

        Returns:
            EmbeddingResult with vector and metadata

        Raises:
            ValueError: If text is empty or API key not configured
            httpx.HTTPStatusError: If API request fails
        """
        if not text or not text.strip():
            raise ValueError("Cannot create embedding for empty text")

        model = model or self.model
        dimensions = dimensions or self.dimensions

        try:
            response = await self.request(
                "POST",
                "/embeddings",
                data={
                    "model": model,
                    "input": text.strip(),
                    "dimensions": dimensions,
                }
            )
            response.raise_for_status()
            data = response.json()

            embedding = data["data"][0]["embedding"]

            logger.debug(
                "embedding_created",
                model=model,
                dimensions=len(embedding),
                text_length=len(text),
                tokens=data.get("usage", {}).get("total_tokens"),
            )

            return EmbeddingResult(
                embedding=embedding,
                model=data["model"],
                usage=data.get("usage", {}),
            )

        except httpx.HTTPStatusError as e:
            logger.error(
                "embedding_api_error",
                status=e.response.status_code,
                detail=e.response.text[:200] if e.response.text else None,
            )
            raise
        except httpx.TimeoutException:
            logger.error("embedding_timeout", model=model, text_length=len(text))
            raise

    async def create_embeddings(
        self,
        texts: List[str],
        model: Optional[str] = None,
        dimensions: Optional[int] = None,
    ) -> BatchEmbeddingResult:
        """
        Generate embeddings for multiple texts in a single API call.

        Args:
            texts: List of texts to embed
            model: Override default model
            dimensions: Override default dimensions

        Returns:
            BatchEmbeddingResult with vectors and metadata
        """
        if not texts:
            raise ValueError("Cannot create embeddings for empty list")

        # Filter empty texts
        cleaned_texts = [t.strip() for t in texts if t and t.strip()]
        if not cleaned_texts:
            raise ValueError("All texts are empty")

        model = model or self.model
        dimensions = dimensions or self.dimensions

        try:
            response = await self.request(
                "POST",
                "/embeddings",
                data={
                    "model": model,
                    "input": cleaned_texts,
                    "dimensions": dimensions,
                }
            )
            response.raise_for_status()
            data = response.json()

            # Extract embeddings in order
            embeddings = [item["embedding"] for item in data["data"]]

            logger.debug(
                "batch_embeddings_created",
                model=model,
                count=len(embeddings),
                dimensions=len(embeddings[0]) if embeddings else 0,
                tokens=data.get("usage", {}).get("total_tokens"),
            )

            return BatchEmbeddingResult(
                embeddings=embeddings,
                model=data["model"],
                usage=data.get("usage", {}),
            )

        except httpx.HTTPStatusError as e:
            logger.error(
                "batch_embedding_api_error",
                status=e.response.status_code,
                count=len(texts),
            )
            raise
        except httpx.TimeoutException:
            logger.error("batch_embedding_timeout", model=model, count=len(texts))
            raise


# Singleton instance for convenience
_client: Optional[OpenAIEmbeddingClient] = None


def get_embedding_client() -> OpenAIEmbeddingClient:
    """Get or create singleton embedding client."""
    global _client
    if _client is None:
        _client = OpenAIEmbeddingClient()
    return _client
