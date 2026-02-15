"""
Memory retrieval with query routing and relevance scoring.

Routes queries to the smallest relevant subset first for efficiency,
builds evidence for each match, and filters by permission.

Supports semantic search via pgvector cosine similarity when query.text
is provided and embeddings are available.
"""

import time
from typing import Dict, List, Optional, Tuple

import structlog

from src.domain.memory.models import (
    MemoryQuery,
    MemoryResult,
    MemorySearchResponse,
    RetrievalEvidence,
)
from src.infrastructure.memory.memory_store import MemoryStore
from src.infrastructure.memory.memory_logger import MemoryLogger
from src.database.memory_models import Memory, MemoryVersion
from src.llm import OpenAIEmbeddingClient, get_embedding_client


logger = structlog.get_logger()


class MemoryRetriever:
    """
    Routes queries to the smallest relevant subset and scores results.

    Routing priority (smallest subset first):
    1. Exact key lookup → single result
    2. Topic filter → narrows to specific domain
    3. Scope + scope_value filter → permission-based narrowing
    4. Tags intersection → narrows by classification
    5. Semantic search via pgvector → relevance ranking by cosine similarity
    6. Full org scan → fallback with limit

    Each routing step appends to retrieval_path for debugging.
    Permission filtering excludes denied memories.
    """

    # Relevance scores by match type
    SCORE_EXACT_KEY = 1.0
    SCORE_TOPIC_MATCH = 0.8
    SCORE_TAG_MATCH = 0.6
    SCORE_ORG_SCAN = 0.5

    def __init__(
        self,
        store: MemoryStore,
        memory_logger: MemoryLogger,
        embedding_client: Optional[OpenAIEmbeddingClient] = None,
    ):
        """
        Initialize the retriever.

        Args:
            store: MemoryStore instance for database access
            memory_logger: MemoryLogger for structured logging
            embedding_client: OpenAI embedding client (uses singleton if not provided)
        """
        self._store = store
        self._logger = memory_logger
        self._embedding_client = embedding_client or get_embedding_client()

    async def search(self, query: MemoryQuery) -> MemorySearchResponse:
        """
        Search memories using query routing.

        Routes to the smallest relevant subset first, then applies
        additional filters. When query.text is provided, performs
        semantic search using pgvector cosine similarity.

        Args:
            query: The memory query with all filter parameters

        Returns:
            MemorySearchResponse with memories, evidence, and path
        """
        start_time = time.perf_counter()
        retrieval_path: List[str] = []
        memories: List[Memory] = []
        versions_map: dict[str, MemoryVersion] = {}
        match_type = "org_scan"
        relevance_score = self.SCORE_ORG_SCAN
        total_count = 0

        # Track which filters were applied
        filters_applied: List[str] = []

        # Track per-memory semantic scores (memory_id -> similarity)
        semantic_scores: Dict[str, float] = {}
        used_semantic_search = False

        # Route 1: Exact key lookup (smallest subset)
        if query.key:
            retrieval_path.append(f"route:exact_key={query.key}")
            memory = await self._store.get_by_key(query.key, query.organization_id)
            if memory:
                memories = [memory]
                version = await self._store.get_current_version(str(memory.id))
                if version:
                    versions_map[str(memory.id)] = version
                total_count = 1
            else:
                total_count = 0
            match_type = "exact_key"
            relevance_score = self.SCORE_EXACT_KEY
            filters_applied.append("key")

        else:
            # Build filter parameters for list_filtered
            scope = query.scope.value if query.scope else None
            scope_value = query.scope_value
            topic = query.topic
            topics = query.topics
            tags = query.tags

            # Route 2: Topic filter (narrows set)
            if topic:
                retrieval_path.append(f"filter:topic={topic}")
                filters_applied.append("topic")
                match_type = "topic_match"
                relevance_score = self.SCORE_TOPIC_MATCH

            if topics:
                retrieval_path.append(f"filter:topics={topics}")
                filters_applied.append("topics")
                if match_type != "topic_match":
                    match_type = "topic_match"
                    relevance_score = self.SCORE_TOPIC_MATCH

            # Route 3: Scope + scope_value filter
            if scope:
                retrieval_path.append(f"filter:scope={scope}")
                filters_applied.append("scope")
            if scope_value:
                retrieval_path.append(f"filter:scope_value={scope_value}")
                filters_applied.append("scope_value")

            # Route 4: Tags intersection
            if tags:
                retrieval_path.append(f"filter:tags={tags}")
                filters_applied.append("tags")
                if match_type not in ("topic_match", "exact_key"):
                    match_type = "tag_match"
                    relevance_score = self.SCORE_TAG_MATCH

            # Route 5: Semantic search via pgvector
            if query.text:
                filters_applied.append("text")

                # First get pre-filtered IDs if other filters are set
                pre_filtered_ids: Optional[List[str]] = None
                if filters_applied and len([f for f in filters_applied if f != "text"]) > 0:
                    # Get filtered memories first to narrow semantic search
                    pre_memories, _ = await self._store.list_filtered(
                        organization_id=query.organization_id,
                        scope=scope,
                        scope_value=scope_value,
                        topic=topic,
                        topics=topics,
                        tags=tags,
                        keys=query.keys,
                        created_by_user_id=query.created_by_user_id,
                        created_by_agent_id=query.created_by_agent_id,
                        status=query.status,
                        limit=100,  # Get more for semantic filtering
                        offset=0,
                    )
                    pre_filtered_ids = [str(m.id) for m in pre_memories]

                # Perform semantic search
                semantic_results = await self._semantic_search(
                    organization_id=query.organization_id,
                    text=query.text,
                    pre_filtered_ids=pre_filtered_ids,
                    threshold=query.similarity_threshold,
                    limit=query.limit,
                )

                if semantic_results:
                    used_semantic_search = True
                    match_type = "semantic"
                    # Store scores for per-memory evidence
                    semantic_scores = {mid: score for mid, score in semantic_results}
                    retrieval_path.append(
                        f"semantic:threshold={query.similarity_threshold},matches={len(semantic_results)}"
                    )

                    # Load memories by their IDs in a single batch query
                    memory_ids_ordered = [mid for mid, _ in semantic_results]
                    memories_by_id = await self._store.get_by_ids(
                        memory_ids_ordered, query.organization_id
                    )
                    # Batch load current versions
                    found_ids = list(memories_by_id.keys())
                    if found_ids:
                        versions_map = await self._store.batch_get_current_versions(found_ids)

                    # Preserve semantic order
                    memories = [memories_by_id[mid] for mid in memory_ids_ordered if mid in memories_by_id]
                    total_count = len(memories)
                else:
                    # Semantic search returned no results or failed, fall back to filter-based
                    retrieval_path.append(f"filter:text={query.text[:50]}...")

            # Route 6: Org scan (fallback)
            if not filters_applied:
                retrieval_path.append(f"route:org_scan={query.organization_id}")
                match_type = "org_scan"
                relevance_score = self.SCORE_ORG_SCAN

            # Execute the filtered query if semantic search wasn't used or didn't find results
            if not used_semantic_search:
                memories, total_count = await self._store.list_filtered(
                    organization_id=query.organization_id,
                    scope=scope,
                    scope_value=scope_value,
                    topic=topic,
                    topics=topics,
                    tags=tags,
                    keys=query.keys,
                    created_by_user_id=query.created_by_user_id,
                    created_by_agent_id=query.created_by_agent_id,
                    status=query.status,
                    limit=query.limit,
                    offset=query.offset,
                )

                # Batch load current versions for all memories
                if memories:
                    mem_ids = [str(m.id) for m in memories]
                    versions_map = await self._store.batch_get_current_versions(mem_ids)

        # Permission filtering (batch)
        permitted_ids = await self._store.batch_check_permissions(
            memories=memories,
            user_id=query.requesting_user_id,
            agent_id=query.requesting_agent_id,
            required_level="read",
        )
        permitted_memories: List[Memory] = []
        for memory in memories:
            if str(memory.id) in permitted_ids:
                permitted_memories.append(memory)
            else:
                retrieval_path.append(f"denied:memory_id={memory.id}")

        # Calculate query time
        query_time_ms = int((time.perf_counter() - start_time) * 1000)

        # Convert to MemoryResult with evidence
        results: List[MemoryResult] = []
        for memory in permitted_memories:
            version = versions_map.get(str(memory.id))
            body = version.body if version else ""
            extended_data = version.extended_data if version else {}

            # Use semantic score if available, otherwise use match_type score
            memory_id_str = str(memory.id)
            if memory_id_str in semantic_scores:
                mem_score = semantic_scores[memory_id_str]
                mem_match_type = "semantic"
            else:
                mem_score = relevance_score
                mem_match_type = match_type

            evidence = self._build_evidence(
                match_type=mem_match_type,
                score=mem_score,
                filters=filters_applied,
                time_ms=query_time_ms,
            )

            result = MemoryResult(
                id=str(memory.id),
                key=memory.key,
                title=memory.title,
                body=body,
                scope=memory.scope,
                topic=memory.topic,
                tags=memory.tags or [],
                version=memory.current_version,
                extended_data=extended_data,
                metadata=memory.extra_metadata or {},
                evidence=evidence,
                created_at=memory.created_at,
                updated_at=memory.updated_at,
            )
            results.append(result)

        # Build response
        response = MemorySearchResponse(
            memories=results,
            total_count=len(results),
            retrieval_path=retrieval_path,
            query_time_ms=query_time_ms,
        )

        # Log the retrieval
        self._logger.log_retrieval(query, response)

        return response

    def _build_evidence(
        self,
        match_type: str,
        score: float,
        filters: List[str],
        time_ms: int,
    ) -> RetrievalEvidence:
        """
        Build retrieval evidence for a memory result.

        Args:
            match_type: How the memory was matched (exact_key, topic_match, etc.)
            score: Relevance score (1.0 = perfect match)
            filters: List of filters that were applied
            time_ms: Query execution time in milliseconds

        Returns:
            RetrievalEvidence with all fields populated
        """
        return RetrievalEvidence(
            match_type=match_type,
            relevance_score=score,
            filters_applied=filters,
            retrieval_time_ms=time_ms,
        )

    async def _semantic_search(
        self,
        organization_id: str,
        text: str,
        pre_filtered_ids: Optional[List[str]],
        threshold: float,
        limit: int,
    ) -> List[Tuple[str, float]]:
        """
        Perform semantic search using pgvector cosine similarity.

        Generates a query embedding using OpenAI text-embedding-3-small,
        then searches for similar memories using pgvector's HNSW index.

        Args:
            organization_id: Organization to search within
            text: Query text to embed and search
            pre_filtered_ids: Optional list of memory IDs to search within
                            (from previous filter stages)
            threshold: Minimum cosine similarity threshold (0.0 to 1.0)
            limit: Maximum number of results to return

        Returns:
            List of (memory_id, similarity_score) tuples, sorted by score DESC
        """
        # Check if embedding client is configured
        if not self._embedding_client.is_configured:
            logger.debug(
                "semantic_search_disabled",
                reason="embedding_client_not_configured",
            )
            return []

        # Generate query embedding
        try:
            async with self._embedding_client as client:
                result = await client.create_embedding(text)
                query_embedding = result.embedding
        except Exception as e:
            logger.warning(
                "semantic_search_embedding_failed",
                error=str(e),
                text_length=len(text),
            )
            return []

        # Execute pgvector similarity search
        try:
            from sqlalchemy import text as sql_text

            async with self._store.db.get_session() as session:
                # Build the embedding string for pgvector
                embedding_str = f"[{','.join(str(x) for x in query_embedding)}]"

                # Build query with optional pre-filter
                if pre_filtered_ids and len(pre_filtered_ids) > 0:
                    # Search only within pre-filtered IDs
                    sql = sql_text("""
                        SELECT
                            id::text as memory_id,
                            1 - (content_embedding <=> CAST(:query_embedding AS vector)) as similarity
                        FROM memories
                        WHERE organization_id = :org_id
                          AND status = 'active'
                          AND embedding_status = 'completed'
                          AND content_embedding IS NOT NULL
                          AND id = ANY(:pre_filtered_ids::uuid[])
                          AND 1 - (content_embedding <=> CAST(:query_embedding AS vector)) >= :threshold
                        ORDER BY content_embedding <=> CAST(:query_embedding AS vector)
                        LIMIT :limit
                    """)
                    result = await session.execute(
                        sql,
                        {
                            "org_id": organization_id,
                            "query_embedding": embedding_str,
                            "pre_filtered_ids": pre_filtered_ids,
                            "threshold": threshold,
                            "limit": limit,
                        },
                    )
                else:
                    # Search all memories in org
                    sql = sql_text("""
                        SELECT
                            id::text as memory_id,
                            1 - (content_embedding <=> CAST(:query_embedding AS vector)) as similarity
                        FROM memories
                        WHERE organization_id = :org_id
                          AND status = 'active'
                          AND embedding_status = 'completed'
                          AND content_embedding IS NOT NULL
                          AND 1 - (content_embedding <=> CAST(:query_embedding AS vector)) >= :threshold
                        ORDER BY content_embedding <=> CAST(:query_embedding AS vector)
                        LIMIT :limit
                    """)
                    result = await session.execute(
                        sql,
                        {
                            "org_id": organization_id,
                            "query_embedding": embedding_str,
                            "threshold": threshold,
                            "limit": limit,
                        },
                    )

                rows = result.fetchall()
                semantic_results = [(row.memory_id, float(row.similarity)) for row in rows]

                logger.debug(
                    "semantic_search_completed",
                    organization_id=organization_id,
                    query_length=len(text),
                    threshold=threshold,
                    matches=len(semantic_results),
                )

                return semantic_results

        except Exception as e:
            logger.warning(
                "semantic_search_query_failed",
                error=str(e),
                organization_id=organization_id,
            )
            return []
