"""Capability recommendation engine for intelligent capability discovery.

Uses a hybrid approach:
1. Semantic search via pgvector embeddings (when available)
2. Keyword-based search as fallback

This replaces AgentRecommender to use the unified capabilities_agents table
as part of the capabilities unification (CAP-015).
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import structlog

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


@dataclass
class CapabilityMatch:
    """Represents a matched capability with similarity score."""
    id: str
    agent_type: str
    name: str
    description: str
    domain: str
    tags: List[str]
    similarity: float  # 0.0 to 1.0
    match_type: str  # "semantic" or "keyword"
    is_system: bool
    inputs_schema: Dict[str, Any]
    outputs_schema: Dict[str, Any]
    usage_count: int
    success_rate: float  # Calculated from success_count / usage_count


class CapabilityRecommender:
    """Intelligent capability recommendation using hybrid search.

    Stage 1: Try semantic search via pgvector (accurate, ~50ms)
    Stage 2: Fall back to keyword search if semantic fails (fast, < 10ms)

    This class queries the capabilities_agents table directly, replacing
    the old AgentRecommender that used agent_specs.
    """

    def __init__(self, database):
        """Initialize recommender with database connection.

        Args:
            database: Database instance for async session management
        """
        self.database = database

    async def search_and_rank(
        self,
        query: str,
        domain: Optional[str] = None,
        tags: Optional[List[str]] = None,
        organization_id: Optional[str] = None,
        include_system: bool = True,
        limit: int = 10
    ) -> List[CapabilityMatch]:
        """Search for capabilities and rank them by relevance.

        Args:
            query: Search keywords (e.g., "summarize text")
            domain: Optional domain filter (e.g., "content", "research")
            tags: Optional tag filters
            organization_id: User's organization ID for org-scoped search
            include_system: Include system capabilities (default: True)
            limit: Maximum results to return

        Returns:
            List of CapabilityMatch objects, ranked by similarity
        """
        logger.info(
            "Capability recommendation started",
            query=query,
            domain=domain,
            tags=tags,
            organization_id=organization_id
        )

        async with self.database.get_session() as session:
            # Try semantic search first
            results = await self._semantic_search(
                session=session,
                query=query,
                domain=domain,
                tags=tags,
                organization_id=organization_id,
                include_system=include_system,
                limit=limit
            )

            if results:
                logger.info(
                    f"Found {len(results)} capabilities via semantic search",
                    query=query,
                    top_similarity=results[0].similarity if results else 0
                )
                return results

            # Fall back to keyword search
            results = await self._keyword_search(
                session=session,
                query=query,
                domain=domain,
                tags=tags,
                organization_id=organization_id,
                include_system=include_system,
                limit=limit
            )

            if results:
                logger.info(
                    f"Found {len(results)} capabilities via keyword search",
                    query=query,
                    top_similarity=results[0].similarity if results else 0
                )
            else:
                logger.info("No capabilities found matching criteria", query=query)

            return results

    async def _semantic_search(
        self,
        session: AsyncSession,
        query: str,
        domain: Optional[str],
        tags: Optional[List[str]],
        organization_id: Optional[str],
        include_system: bool,
        limit: int,
        min_similarity: float = 0.5
    ) -> List[CapabilityMatch]:
        """Search using pgvector cosine similarity on embeddings.

        Returns empty list if embeddings are not available.
        """
        try:
            # Generate query embedding
            query_embedding = await self._generate_query_embedding(query)
            if not query_embedding:
                return []

            # Import here to avoid circular imports
            from src.database.capability_models import AgentCapability

            # Build filter conditions
            conditions = [
                AgentCapability.is_latest == True,  # noqa: E712
                AgentCapability.is_active == True,  # noqa: E712
                AgentCapability.description_embedding.isnot(None),  # Must have embedding
            ]

            # Organization scoping
            org_conditions = []
            if organization_id:
                org_conditions.append(AgentCapability.organization_id == organization_id)
            if include_system:
                org_conditions.append(AgentCapability.is_system == True)  # noqa: E712

            if org_conditions:
                conditions.append(or_(*org_conditions))
            elif not include_system:
                return []

            if domain:
                conditions.append(AgentCapability.domain == domain)

            if tags:
                conditions.append(AgentCapability.tags.overlap(tags))

            # Build query with cosine similarity
            # pgvector's <=> operator gives cosine distance, similarity = 1 - distance
            similarity_expr = (1 - AgentCapability.description_embedding.cosine_distance(query_embedding)).label('similarity')

            query_obj = (
                select(AgentCapability, similarity_expr)
                .where(and_(*conditions))
                .order_by(similarity_expr.desc())
                .limit(limit)
            )

            result = await session.execute(query_obj)
            rows = result.all()

            # Filter by minimum similarity and convert to CapabilityMatch
            matches = []
            for cap, similarity in rows:
                if similarity >= min_similarity:
                    matches.append(self._create_match(cap, similarity, "semantic"))

            return matches

        except Exception as e:
            logger.warning(
                "Semantic search failed, will fall back to keyword search",
                error=str(e),
                query=query
            )
            return []

    async def _keyword_search(
        self,
        session: AsyncSession,
        query: str,
        domain: Optional[str],
        tags: Optional[List[str]],
        organization_id: Optional[str],
        include_system: bool,
        limit: int
    ) -> List[CapabilityMatch]:
        """Search using keyword matching as fallback.

        Searches in: name, description, agent_type, tags, keywords
        """
        # Import here to avoid circular imports
        from src.database.capability_models import AgentCapability

        # Prepare search terms
        search_terms = [term.lower().strip() for term in query.split() if term.strip()]
        if not search_terms:
            return []

        # Build filter conditions
        conditions = [
            AgentCapability.is_latest == True,  # noqa: E712
            AgentCapability.is_active == True,  # noqa: E712
        ]

        # Organization scoping
        org_conditions = []
        if organization_id:
            org_conditions.append(AgentCapability.organization_id == organization_id)
        if include_system:
            org_conditions.append(AgentCapability.is_system == True)  # noqa: E712

        if org_conditions:
            conditions.append(or_(*org_conditions))
        elif not include_system:
            return []

        if domain:
            conditions.append(AgentCapability.domain == domain)

        if tags:
            conditions.append(AgentCapability.tags.overlap(tags))

        # Build text search conditions: match any term in any field
        text_conditions = []
        for term in search_terms:
            pattern = f"%{term}%"
            text_conditions.append(
                or_(
                    func.lower(AgentCapability.name).like(pattern),
                    func.lower(AgentCapability.description).like(pattern),
                    func.lower(AgentCapability.agent_type).like(pattern),
                    func.array_to_string(AgentCapability.tags, ' ').ilike(pattern),
                    func.array_to_string(AgentCapability.keywords, ' ').ilike(pattern),
                )
            )

        if text_conditions:
            # Match at least one term
            conditions.append(or_(*text_conditions))

        # Build and execute query
        query_obj = (
            select(AgentCapability)
            .where(and_(*conditions))
            .order_by(
                AgentCapability.usage_count.desc(),
                AgentCapability.name.asc()
            )
            .limit(limit * 2)  # Get more for scoring
        )

        result = await session.execute(query_obj)
        capabilities = result.scalars().all()

        # Calculate relevance score based on matches
        matches = []
        for cap in capabilities:
            similarity = self._calculate_keyword_score(
                search_terms,
                cap.name or "",
                cap.description or "",
                cap.agent_type or "",
                cap.tags or [],
                cap.keywords or []
            )
            matches.append(self._create_match(cap, similarity, "keyword"))

        # Sort by relevance
        matches.sort(key=lambda x: x.similarity, reverse=True)
        return matches[:limit]

    def _calculate_keyword_score(
        self,
        search_terms: List[str],
        name: str,
        description: str,
        agent_type: str,
        tags: List[str],
        keywords: List[str]
    ) -> float:
        """Calculate relevance score based on keyword matching.

        All comparisons are case-insensitive.

        Returns:
            Score between 0 and 1
        """
        if not search_terms:
            return 0.0

        name_lower = name.lower()
        desc_lower = description.lower()
        agent_type_lower = agent_type.lower()
        tags_lower = [t.lower() for t in tags]
        keywords_lower = [k.lower() for k in keywords]

        matches = 0
        total_terms = len(search_terms)

        for term in search_terms:
            term = term.lower()  # Ensure case-insensitive matching
            # Name match (highest weight - 2 points)
            if term in name_lower:
                matches += 2
            # Agent type match (high weight - 1.5 points)
            elif term in agent_type_lower:
                matches += 1.5
            # Description match (medium weight - 1 point)
            elif term in desc_lower:
                matches += 1
            # Tag match (medium weight - 1 point)
            elif any(term in tag for tag in tags_lower):
                matches += 1
            # Keyword match (medium weight - 1 point)
            elif any(term in kw for kw in keywords_lower):
                matches += 1

        # Normalize score to 0-1 range (max would be all terms matching name = 2 * total)
        max_score = 2 * total_terms
        return min(matches / max_score, 1.0) if max_score > 0 else 0.0

    async def _generate_query_embedding(self, query: str) -> Optional[List[float]]:
        """Generate embedding vector for search query.

        Uses OpenAI text-embedding-3-small for compatibility with
        capability embeddings.
        """
        try:
            from src.llm import get_embedding_client

            client = get_embedding_client()
            if not client or not client.is_configured:
                return None

            # Use the client as async context manager
            async with client as c:
                response = await c.embeddings.create(
                    model="text-embedding-3-small",
                    input=query,
                    dimensions=1536
                )
                return response.data[0].embedding

        except Exception as e:
            logger.warning(
                "Failed to generate query embedding",
                error=str(e),
                query=query[:50]
            )
            return None

    def _create_match(self, capability, similarity: float, match_type: str) -> CapabilityMatch:
        """Create a CapabilityMatch from a database capability.

        Args:
            capability: AgentCapability model instance
            similarity: Match similarity score (0-1)
            match_type: "semantic" or "keyword"

        Returns:
            CapabilityMatch object
        """
        # Calculate success rate
        usage_count = capability.usage_count or 0
        success_count = capability.success_count or 0
        success_rate = (success_count / usage_count) if usage_count > 0 else 0.0

        return CapabilityMatch(
            id=str(capability.id),
            agent_type=capability.agent_type,
            name=capability.name or capability.agent_type,
            description=capability.description or "",
            domain=capability.domain or "",
            tags=capability.tags or [],
            similarity=similarity,
            match_type=match_type,
            is_system=capability.is_system,
            inputs_schema=capability.inputs_schema or {},
            outputs_schema=capability.outputs_schema or {},
            usage_count=usage_count,
            success_rate=round(success_rate, 2)
        )
