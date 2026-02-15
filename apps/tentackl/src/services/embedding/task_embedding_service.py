# REVIEW: Similarity search builds SQL with string interpolation (org_id),
# REVIEW: which risks SQL injection and breaks query caching. Use bind parameters
# REVIEW: for safety. Also duplicates embedding logic seen in other services.
"""Task Embedding Service for semantic task similarity.

Enables "do the HN thing again" pattern recognition by:
1. Generating embeddings for task goals when plans are created
2. Finding similar completed tasks based on semantic similarity
3. Providing context for Arrow chat to suggest past successful patterns

Uses OpenAI text-embedding-3-small (1536 dimensions) for efficient similarity search.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime
import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from src.interfaces.database import Database
from src.database.delegation_models import DelegationPlan, DelegationPlanStatus
from src.llm import OpenAIEmbeddingClient, get_embedding_client

logger = structlog.get_logger(__name__)


class TaskEmbeddingService:
    """Service for generating and searching task embeddings.

    Provides:
    - Embedding generation for new task goals
    - Similarity search for past tasks
    - Batch embedding generation for backfill
    """

    def __init__(
        self,
        database: Optional[Database] = None,
        embedding_client: Optional[OpenAIEmbeddingClient] = None,
    ):
        """Initialize task embedding service.

        Args:
            database: Database instance for queries
            embedding_client: OpenAI embedding client (uses singleton if not provided)
        """
        self._db = database
        self._embedding_client = embedding_client or get_embedding_client()

        logger.info(
            "TaskEmbeddingService initialized",
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
            text: Text to embed (typically task goal + constraints)

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
                    "embedding_generated",
                    text_length=len(text),
                    dimensions=len(result.embedding),
                )
                return result.embedding

        except ValueError as e:
            logger.error("embedding_validation_error", error=str(e))
            return None
        except Exception as e:
            logger.error("embedding_generation_failed", error=str(e))
            return None

    def build_task_text(
        self,
        goal: str,
        constraints: Optional[Dict[str, Any]] = None,
        success_criteria: Optional[List[str]] = None,
    ) -> str:
        """Build text representation for task embedding.

        Combines goal, constraints, and success criteria into searchable text.

        Args:
            goal: The task goal
            constraints: Optional constraints dict
            success_criteria: Optional list of success criteria

        Returns:
            Combined text for embedding generation
        """
        parts = [f"Goal: {goal}"]

        if constraints:
            # Extract key constraints that might be semantically relevant
            relevant_keys = [
                "target_audience", "format", "output_type", "domain",
                "platform", "channel", "frequency", "topic",
            ]
            for key in relevant_keys:
                if key in constraints:
                    parts.append(f"{key}: {constraints[key]}")

        if success_criteria:
            parts.append(f"Success criteria: {', '.join(success_criteria[:3])}")

        return " | ".join(parts)

    async def embed_plan(self, plan_id: str) -> bool:
        """Generate and store embedding for a plan.

        Args:
            plan_id: Plan ID to generate embedding for

        Returns:
            True if embedding was generated and stored successfully
        """
        if not self.is_enabled:
            return False

        try:
            db = await self._get_database()
            async with db.get_session() as session:
                result = await session.execute(
                    select(DelegationPlan).where(
                        DelegationPlan.id == uuid.UUID(plan_id)
                    )
                )
                plan = result.scalar_one_or_none()

                if not plan:
                    logger.warning("plan_not_found_for_embedding", plan_id=plan_id)
                    return False

                # Build searchable text
                text = self.build_task_text(
                    goal=plan.goal,
                    constraints=plan.constraints,
                    success_criteria=plan.success_criteria,
                )

                # Generate embedding
                embedding = await self.generate_embedding(text)

                if embedding is None:
                    # Update status to failed
                    plan.embedding_status = "failed"
                    await session.commit()
                    return False

                # Store embedding
                plan.goal_embedding = embedding
                plan.embedding_status = "ready"
                await session.commit()

                logger.info(
                    "plan_embedding_generated",
                    plan_id=plan_id,
                    text_length=len(text),
                )
                return True

        except Exception as e:
            logger.error(
                "embed_plan_failed",
                plan_id=plan_id,
                error=str(e),
            )
            return False

    async def find_similar_tasks(
        self,
        query: str,
        organization_id: Optional[str] = None,
        limit: int = 5,
        min_similarity: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """Find similar completed tasks based on semantic similarity.

        Args:
            query: Natural language query (e.g., "the HN thing")
            organization_id: Optional org filter
            limit: Maximum number of results
            min_similarity: Minimum cosine similarity threshold

        Returns:
            List of similar tasks with similarity scores
        """
        if not self.is_enabled:
            return []

        try:
            # Generate embedding for query
            query_embedding = await self.generate_embedding(query)
            if query_embedding is None:
                return []

            db = await self._get_database()
            async with db.get_session() as session:
                # Build the similarity query
                # Using 1 - cosine distance as similarity
                embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

                # Query using pgvector cosine similarity
                query_sql = text("""
                    SELECT
                        id,
                        goal,
                        constraints,
                        success_criteria,
                        steps,
                        1 - (goal_embedding <=> :embedding::vector) as similarity
                    FROM tasks
                    WHERE status = 'completed'
                        AND embedding_status = 'ready'
                        AND goal_embedding IS NOT NULL
                        AND (:organization_id IS NULL OR organization_id = :organization_id)
                    ORDER BY goal_embedding <=> :embedding::vector
                    LIMIT :limit
                """)

                result = await session.execute(
                    query_sql,
                    {
                        "embedding": embedding_str,
                        "limit": limit,
                        "organization_id": organization_id,
                    }
                )
                rows = result.fetchall()

                # Filter by minimum similarity and format results
                similar_tasks = []
                for row in rows:
                    similarity = float(row.similarity)
                    if similarity >= min_similarity:
                        similar_tasks.append({
                            "plan_id": str(row.id),
                            "goal": row.goal,
                            "constraints": row.constraints or {},
                            "success_criteria": row.success_criteria or [],
                            "steps": row.steps or [],
                            "similarity": similarity,
                        })

                logger.info(
                    "similar_tasks_found",
                    query=query[:50],
                    found=len(similar_tasks),
                    organization_id=organization_id,
                )

                return similar_tasks

        except Exception as e:
            logger.error(
                "find_similar_tasks_failed",
                query=query[:50],
                error=str(e),
            )
            return []

    async def backfill_embeddings(
        self,
        batch_size: int = 50,
        organization_id: Optional[str] = None,
    ) -> Dict[str, int]:
        """Backfill embeddings for completed plans without embeddings.

        Args:
            batch_size: Number of plans to process per batch
            organization_id: Optional org filter

        Returns:
            Statistics dict with processed, succeeded, failed counts
        """
        if not self.is_enabled:
            return {"processed": 0, "succeeded": 0, "failed": 0}

        stats = {"processed": 0, "succeeded": 0, "failed": 0}

        try:
            db = await self._get_database()
            async with db.get_session() as session:
                # Find plans needing embeddings
                query = (
                    select(DelegationPlan)
                    .where(
                        DelegationPlan.status == "completed",
                        DelegationPlan.embedding_status == "pending",
                    )
                    .limit(batch_size)
                )

                if organization_id:
                    query = query.where(
                        DelegationPlan.organization_id == organization_id
                    )

                result = await session.execute(query)
                plans = result.scalars().all()

                for plan in plans:
                    stats["processed"] += 1

                    # Build text and generate embedding
                    text = self.build_task_text(
                        goal=plan.goal,
                        constraints=plan.constraints,
                        success_criteria=plan.success_criteria,
                    )

                    embedding = await self.generate_embedding(text)

                    if embedding:
                        plan.goal_embedding = embedding
                        plan.embedding_status = "ready"
                        stats["succeeded"] += 1
                    else:
                        plan.embedding_status = "failed"
                        stats["failed"] += 1

                await session.commit()

                logger.info(
                    "backfill_embeddings_completed",
                    **stats,
                    organization_id=organization_id,
                )

                return stats

        except Exception as e:
            logger.error(
                "backfill_embeddings_failed",
                error=str(e),
            )
            return stats


# Singleton instance
_service: Optional[TaskEmbeddingService] = None


def get_task_embedding_service() -> TaskEmbeddingService:
    """Get or create the singleton task embedding service.

    Returns:
        TaskEmbeddingService instance
    """
    global _service
    if _service is None:
        _service = TaskEmbeddingService()
    return _service
