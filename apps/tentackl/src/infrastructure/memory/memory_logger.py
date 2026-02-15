"""
Structured logging for memory service operations.

Provides consistent, structured logging for memory retrieval paths,
injections, stores, and errors using structlog.
"""

import structlog
from typing import Optional

from src.domain.memory.models import MemoryQuery, MemorySearchResponse


logger = structlog.get_logger()


class MemoryLogger:
    """
    Structured logger for memory service operations.

    Provides consistent logging formats for:
    - Memory retrieval operations with path tracking
    - Memory injection into agent prompts
    - Memory store operations
    - Error conditions

    This class contains no business logic - pure structured logging.
    """

    def __init__(self):
        """Initialize the memory logger."""
        self._logger = structlog.get_logger("memory_service")

    def log_retrieval(
        self,
        query: MemoryQuery,
        response: MemorySearchResponse,
    ) -> None:
        """
        Log a memory retrieval operation.

        Args:
            query: The memory query that was executed
            response: The search response with results and path
        """
        # Truncate query text to 100 chars for logging
        query_text = None
        if query.text:
            query_text = query.text[:100] if len(query.text) > 100 else query.text

        # Build list of applied filters
        filters: list[str] = []
        if query.key:
            filters.append("key")
        if query.keys:
            filters.append("keys")
        if query.scope:
            filters.append("scope")
        if query.scope_value:
            filters.append("scope_value")
        if query.topic:
            filters.append("topic")
        if query.topics:
            filters.append("topics")
        if query.tags:
            filters.append("tags")
        if query.created_by_user_id:
            filters.append("created_by_user_id")
        if query.created_by_agent_id:
            filters.append("created_by_agent_id")
        if query.text:
            filters.append("text")

        self._logger.info(
            "memory_retrieval",
            org_id=query.organization_id,
            query_text=query_text,
            filters=filters,
            results_count=response.total_count,
            retrieval_path=response.retrieval_path,
            query_time_ms=response.query_time_ms,
        )

    def log_injection(
        self,
        memory_count: int,
        injected_tokens: int,
        max_tokens: int,
        truncated: bool,
    ) -> None:
        """
        Log a memory injection into an agent prompt.

        Args:
            memory_count: Number of memories injected
            injected_tokens: Approximate token count of injected content
            max_tokens: Maximum token budget allowed
            truncated: Whether memories were truncated to fit budget
        """
        self._logger.info(
            "memory_injection",
            memory_count=memory_count,
            injected_tokens=injected_tokens,
            max_tokens=max_tokens,
            truncated=truncated,
        )

    def log_store(
        self,
        organization_id: str,
        key: str,
        scope: str,
        created_by_agent: bool,
    ) -> None:
        """
        Log a memory store operation.

        Args:
            organization_id: Organization identifier
            key: Memory key
            scope: Memory scope (organization, user, agent, topic)
            created_by_agent: Whether the memory was created by an agent
        """
        self._logger.info(
            "memory_stored",
            org_id=organization_id,
            key=key,
            scope=scope,
            created_by_agent=created_by_agent,
        )

    def log_error(
        self,
        operation: str,
        error: str,
        org_id: Optional[str] = None,
    ) -> None:
        """
        Log a memory service error.

        Args:
            operation: The operation that failed
            error: Error message
            org_id: Organization identifier (optional)
        """
        self._logger.error(
            "memory_error",
            operation=operation,
            error=error,
            org_id=org_id,
        )
