# REVIEW: Straightforward dual-store wrapper, but cache consistency is ad-hoc
# REVIEW: (no TTL/invalidations beyond writes). Error handling is minimal, and
# REVIEW: store interfaces are not abstracted here (hard dependency on Postgres
# REVIEW: vs Redis). Consider a shared cache layer or repository pattern to
# REVIEW: standardize read-through/write-through behavior.
"""
Task Tag Service - Tag management operations.

Handles CRUD operations for task tags with dual-storage support.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
import structlog

from src.domain.tasks.models import TaskTag, TaskTagStoreInterface, TaskTagNotFoundError
from src.infrastructure.tasks.stores.redis_task_store import RedisTaskTagStore
from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskTagStore


logger = structlog.get_logger()


class TaskTagService:
    """
    Task tag management service.

    Uses Redis for fast reads and PostgreSQL for persistence.
    """

    def __init__(
        self,
        postgres_store: PostgresTaskTagStore,
        redis_store: Optional[RedisTaskTagStore] = None,
    ):
        """
        Initialize TaskTagService.

        Args:
            postgres_store: PostgreSQL tag store (source of truth)
            redis_store: Optional Redis tag store (cache layer)
        """
        self.postgres = postgres_store
        self.redis = redis_store

    async def create_tag(
        self,
        organization_id: str,
        name: str,
        color: Optional[str] = None,
        description: Optional[str] = None,
    ) -> TaskTag:
        """
        Create a new tag.

        Args:
            organization_id: Organization this tag belongs to
            name: Tag name (unique within org)
            color: Optional hex color code
            description: Optional description

        Returns:
            Created tag
        """
        tag = TaskTag(
            id=str(uuid.uuid4()),
            organization_id=organization_id,
            name=name,
            color=color,
            description=description,
            created_at=datetime.utcnow(),
        )

        # Save to PostgreSQL
        success = await self.postgres.save_tag(tag)
        if not success:
            raise ValueError("Failed to create tag")

        # Save to Redis cache
        if self.redis:
            await self.redis.save_tag(tag)

        logger.info("Created tag", tag_id=tag.id, name=name, org_id=organization_id)
        return tag

    async def get_tag(self, tag_id: str, organization_id: str) -> Optional[TaskTag]:
        """Get a tag by ID."""
        # Try Redis first
        if self.redis:
            tag = await self.redis.get_tag(tag_id, organization_id)
            if tag:
                return tag

        # Fall back to PostgreSQL
        tag = await self.postgres.get_tag(tag_id, organization_id)

        # Populate cache
        if tag and self.redis:
            await self.redis.save_tag(tag)

        return tag

    async def list_tags(self, organization_id: str) -> List[TaskTag]:
        """List all tags for an organization."""
        tags = await self.postgres.list_tags(organization_id)

        # Populate cache
        if self.redis:
            for tag in tags:
                await self.redis.save_tag(tag)

        return tags

    async def update_tag(
        self,
        tag_id: str,
        organization_id: str,
        **updates
    ) -> Optional[TaskTag]:
        """
        Update a tag.

        Args:
            tag_id: Tag ID to update
            organization_id: Organization ID
            **updates: Fields to update (name, color, description)

        Returns:
            Updated tag or None if not found
        """
        updated = await self.postgres.update_tag(tag_id, organization_id, updates)
        if not updated:
            return None

        # Update cache
        if self.redis:
            await self.redis.save_tag(updated)

        logger.info("Updated tag", tag_id=tag_id, updates=list(updates.keys()))
        return updated

    async def delete_tag(self, tag_id: str, organization_id: str) -> bool:
        """Delete a tag."""
        success = await self.postgres.delete_tag(tag_id, organization_id)

        if success and self.redis:
            await self.redis.delete_tag(tag_id, organization_id)

        if success:
            logger.info("Deleted tag", tag_id=tag_id)

        return success
