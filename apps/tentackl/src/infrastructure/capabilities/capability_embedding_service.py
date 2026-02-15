# REVIEW: This service largely duplicates AgentEmbeddingService, including raw
# REVIEW: SQL embedding writes. Consider extracting a shared embedding repository
# REVIEW: to reduce duplication and to standardize error handling/metrics.
"""Capability Embedding Service for semantic capability discovery.

Enables dynamic capability discovery by:
1. Generating embeddings for capability descriptions when capabilities are created/updated
2. Finding similar capabilities based on natural language queries
3. Supporting "find a capability that can..." style searches

Uses OpenAI text-embedding-3-small (1536 dimensions) for efficient similarity search.
Uses pgvector HNSW index for fast nearest neighbor lookups.

This service follows the same patterns as AgentEmbeddingService for consistency.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime
from uuid import UUID
import structlog
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.interfaces.database import Database
from src.llm import OpenAIEmbeddingClient, get_embedding_client

logger = structlog.get_logger(__name__)


class CapabilityEmbeddingService:
    """Service for generating and searching capability embeddings.

    Provides:
    - Embedding generation for capability descriptions
    - Semantic search for capabilities by natural language query
    - Batch embedding generation for existing capabilities
    - Embedding status tracking

    Usage:
        service = CapabilityEmbeddingService()

        # Generate embedding for new capability
        await service.generate_and_store_embedding(capability_id)

        # Backfill embeddings for all pending capabilities
        stats = await service.backfill_embeddings(batch_size=50)
    """

    def __init__(
        self,
        database: Optional[Database] = None,
        embedding_client: Optional[OpenAIEmbeddingClient] = None,
    ):
        """Initialize capability embedding service.

        Args:
            database: Database instance for queries
            embedding_client: OpenAI embedding client (uses singleton if not provided)
        """
        self._db = database
        self._embedding_client = embedding_client or get_embedding_client()

        logger.info(
            "CapabilityEmbeddingService initialized",
            enabled=self._embedding_client.is_configured,
            model=self._embedding_client.model,
            dimensions=self._embedding_client.dimensions,
        )

    @property
    def is_enabled(self) -> bool:
        """Check if embedding service is enabled."""
        return self._embedding_client.is_configured

    async def _get_database(self) -> Database:
        """Get or create database instance."""
        if self._db is None:
            self._db = Database()
        return self._db

    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text.

        Args:
            text: Text to embed (capability name + description + keywords)

        Returns:
            1536-dimensional embedding vector or None on failure
        """
        if not self.is_enabled:
            logger.debug("embedding_disabled", reason="api_key_not_configured")
            return None

        if not text or not text.strip():
            logger.warning("embedding_empty_text")
            return None

        try:
            async with self._embedding_client as client:
                result = await client.create_embedding(text)
                logger.debug(
                    "capability_embedding_generated",
                    text_length=len(text),
                    dimensions=len(result.embedding),
                )
                return result.embedding

        except ValueError as e:
            logger.error("capability_embedding_validation_error", error=str(e))
            return None
        except Exception as e:
            logger.error("capability_embedding_generation_failed", error=str(e))
            return None

    def build_capability_text(
        self,
        agent_type: str,
        name: str,
        description: Optional[str] = None,
        domain: Optional[str] = None,
        system_prompt: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        inputs_schema: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build text representation for capability embedding.

        Combines capability metadata into searchable text optimized for
        semantic similarity matching.

        Args:
            agent_type: Capability agent type
            name: Display name
            description: Full description
            domain: Capability domain (content, research, etc.)
            system_prompt: First 500 chars of system prompt (for context)
            keywords: Search keywords
            tags: Categorization tags
            inputs_schema: Input schema (extract input names)

        Returns:
            Combined text for embedding generation
        """
        parts = [f"Capability: {name}"]

        if agent_type != name:
            parts.append(f"Type: {agent_type}")

        if description:
            parts.append(f"Description: {description}")

        if domain:
            parts.append(f"Domain: {domain}")

        # Include a snippet of system prompt for semantic context
        if system_prompt:
            prompt_snippet = system_prompt[:500]
            if len(system_prompt) > 500:
                prompt_snippet += "..."
            parts.append(f"Behavior: {prompt_snippet}")

        if keywords:
            parts.append(f"Keywords: {', '.join(keywords)}")

        if tags:
            parts.append(f"Tags: {', '.join(tags)}")

        # Extract input names for searchability
        if inputs_schema and isinstance(inputs_schema, dict):
            input_names = [
                k for k, v in inputs_schema.items()
                if isinstance(v, dict) and k != "type"
            ]
            if input_names:
                parts.append(f"Inputs: {', '.join(input_names)}")

        return "\n".join(parts)

    async def generate_and_store_embedding(
        self,
        capability_id: str,
        session: Optional[AsyncSession] = None,
    ) -> bool:
        """Generate embedding for a capability and store it.

        Args:
            capability_id: ID of the AgentCapability to process
            session: Optional database session (creates new if not provided)

        Returns:
            True if embedding was generated and stored successfully
        """
        try:
            db = await self._get_database()
            own_session = session is None

            if own_session:
                async with db.get_session() as session:
                    return await self._generate_and_store_impl(capability_id, session)
            else:
                return await self._generate_and_store_impl(capability_id, session)

        except Exception as e:
            logger.error(
                "capability_embedding_store_failed",
                capability_id=capability_id,
                error=str(e),
            )
            return False

    async def _generate_and_store_impl(
        self,
        capability_id: str,
        session: AsyncSession,
    ) -> bool:
        """Implementation of generate_and_store_embedding."""
        from src.database.capability_models import AgentCapability

        # Get capability
        result = await session.execute(
            select(AgentCapability).where(AgentCapability.id == capability_id)
        )
        capability = result.scalar_one_or_none()

        if not capability:
            logger.warning("capability_not_found", capability_id=capability_id)
            return False

        # Build text for embedding
        capability_text = self.build_capability_text(
            agent_type=capability.agent_type,
            name=capability.name,
            description=capability.description,
            domain=capability.domain,
            system_prompt=capability.system_prompt,
            keywords=capability.keywords,
            tags=capability.tags,
            inputs_schema=capability.inputs_schema,
        )

        # Generate embedding
        embedding = await self.generate_embedding(capability_text)

        if embedding is None:
            # Mark as failed
            await session.execute(
                update(AgentCapability)
                .where(AgentCapability.id == capability_id)
                .values(embedding_status="failed")
            )
            await session.commit()
            logger.warning(
                "capability_embedding_failed",
                capability_id=capability_id,
                agent_type=capability.agent_type,
            )
            return False

        # Store embedding using raw SQL for pgvector
        embedding_str = f"[{','.join(str(x) for x in embedding)}]"
        await session.execute(
            text("""
                UPDATE capabilities_agents
                SET description_embedding = CAST(:embedding AS vector),
                    embedding_status = 'generated',
                    updated_at = :now
                WHERE id = :id
            """),
            {
                "embedding": embedding_str,
                "id": capability_id,
                "now": datetime.utcnow(),
            },
        )
        await session.commit()

        logger.info(
            "capability_embedding_stored",
            capability_id=capability_id,
            agent_type=capability.agent_type,
            name=capability.name,
        )
        return True

    async def backfill_embeddings(
        self,
        batch_size: int = 50,
        organization_id: Optional[str] = None,
    ) -> Dict[str, int]:
        """Generate embeddings for capabilities without them.

        Args:
            batch_size: Number of capabilities to process per batch
            organization_id: Optional org ID to limit backfill scope

        Returns:
            Statistics dict with success/failure counts
        """
        if not self.is_enabled:
            return {"error": "embeddings_not_enabled", "processed": 0}

        try:
            from src.database.capability_models import AgentCapability

            db = await self._get_database()
            stats = {"success": 0, "failed": 0, "skipped": 0}

            async with db.get_session() as session:
                # Build query for capabilities needing embeddings
                conditions = [
                    AgentCapability.is_active == True,  # noqa: E712
                    AgentCapability.embedding_status.in_(["pending", None, "failed"]),
                ]

                if organization_id:
                    from sqlalchemy import or_
                    # Include org capabilities and system capabilities
                    conditions.append(
                        or_(
                            AgentCapability.organization_id == organization_id,
                            AgentCapability.is_system == True,  # noqa: E712
                        )
                    )

                result = await session.execute(
                    select(AgentCapability)
                    .where(*conditions)
                    .limit(batch_size)
                )
                capabilities = result.scalars().all()

                for cap in capabilities:
                    success = await self._generate_and_store_impl(str(cap.id), session)
                    if success:
                        stats["success"] += 1
                    else:
                        stats["failed"] += 1

            logger.info("capability_embedding_backfill_complete", stats=stats)
            return stats

        except Exception as e:
            logger.error("capability_embedding_backfill_failed", error=str(e))
            return {"error": str(e), "processed": 0}

    async def get_embedding_status(
        self,
        organization_id: Optional[str] = None,
    ) -> Dict[str, int]:
        """Get counts of capabilities by embedding status.

        Args:
            organization_id: Optional org ID to filter by

        Returns:
            Dict with counts: {pending: N, generated: N, failed: N}
        """
        try:
            from src.database.capability_models import AgentCapability

            db = await self._get_database()

            async with db.get_session() as session:
                # Build the appropriate SQL based on whether org_id is provided
                # We need to handle the case where org_id is None separately
                # because PostgreSQL can't infer the type of NULL parameter
                if organization_id:
                    result = await session.execute(
                        text("""
                            SELECT
                                embedding_status,
                                COUNT(*) as count
                            FROM capabilities_agents
                            WHERE is_active = true
                                AND is_latest = true
                                AND (organization_id = :org_id OR is_system = true)
                            GROUP BY embedding_status
                        """),
                        {"org_id": organization_id},
                    )
                else:
                    result = await session.execute(
                        text("""
                            SELECT
                                embedding_status,
                                COUNT(*) as count
                            FROM capabilities_agents
                            WHERE is_active = true
                                AND is_latest = true
                            GROUP BY embedding_status
                        """),
                    )

                rows = result.fetchall()
                counts = {"pending": 0, "generated": 0, "failed": 0, "null": 0}
                for row in rows:
                    status = row.embedding_status or "null"
                    counts[status] = row.count

                return counts

        except Exception as e:
            logger.error("capability_embedding_status_failed", error=str(e))
            return {"error": str(e)}


# Singleton instance for convenience
_service: Optional[CapabilityEmbeddingService] = None


def get_capability_embedding_service() -> CapabilityEmbeddingService:
    """Get or create singleton capability embedding service."""
    global _service
    if _service is None:
        _service = CapabilityEmbeddingService()
    return _service
