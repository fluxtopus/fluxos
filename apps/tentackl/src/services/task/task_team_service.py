# REVIEW: This mirrors TaskTagService almost exactly (dual-store CRUD with
# REVIEW: read-through caching). The duplication suggests a missing generic
# REVIEW: repository/cache layer. As written, cache consistency and error
# REVIEW: handling are ad-hoc and repeated per service.
"""
Task Team Service - Team management operations.

Handles CRUD operations for task teams with dual-storage support.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
import structlog

from src.domain.tasks.models import TaskTeam, TaskTeamStoreInterface, TaskTeamNotFoundError
from src.infrastructure.tasks.stores.redis_task_store import RedisTaskTeamStore
from src.infrastructure.tasks.stores.postgres_task_store import PostgresTaskTeamStore


logger = structlog.get_logger()


class TaskTeamService:
    """
    Task team management service.

    Uses Redis for fast reads and PostgreSQL for persistence.
    """

    def __init__(
        self,
        postgres_store: PostgresTaskTeamStore,
        redis_store: Optional[RedisTaskTeamStore] = None,
    ):
        """
        Initialize TaskTeamService.

        Args:
            postgres_store: PostgreSQL team store (source of truth)
            redis_store: Optional Redis team store (cache layer)
        """
        self.postgres = postgres_store
        self.redis = redis_store

    async def create_team(
        self,
        organization_id: str,
        name: str,
        description: Optional[str] = None,
        lead_user_id: Optional[str] = None,
        member_ids: Optional[List[str]] = None,
    ) -> TaskTeam:
        """
        Create a new team.

        Args:
            organization_id: Organization this team belongs to
            name: Team name (unique within org)
            description: Optional description
            lead_user_id: Optional team lead user ID
            member_ids: Optional list of member user IDs

        Returns:
            Created team
        """
        team = TaskTeam(
            id=str(uuid.uuid4()),
            organization_id=organization_id,
            name=name,
            description=description,
            lead_user_id=lead_user_id,
            member_ids=member_ids or [],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        # Save to PostgreSQL
        success = await self.postgres.save_team(team)
        if not success:
            raise ValueError("Failed to create team")

        # Save to Redis cache
        if self.redis:
            await self.redis.save_team(team)

        logger.info("Created team", team_id=team.id, name=name, org_id=organization_id)
        return team

    async def get_team(self, team_id: str, organization_id: str) -> Optional[TaskTeam]:
        """Get a team by ID."""
        # Try Redis first
        if self.redis:
            team = await self.redis.get_team(team_id, organization_id)
            if team:
                return team

        # Fall back to PostgreSQL
        team = await self.postgres.get_team(team_id, organization_id)

        # Populate cache
        if team and self.redis:
            await self.redis.save_team(team)

        return team

    async def list_teams(self, organization_id: str) -> List[TaskTeam]:
        """List all teams for an organization."""
        teams = await self.postgres.list_teams(organization_id)

        # Populate cache
        if self.redis:
            for team in teams:
                await self.redis.save_team(team)

        return teams

    async def update_team(
        self,
        team_id: str,
        organization_id: str,
        **updates
    ) -> Optional[TaskTeam]:
        """
        Update a team.

        Args:
            team_id: Team ID to update
            organization_id: Organization ID
            **updates: Fields to update

        Returns:
            Updated team or None if not found
        """
        updated = await self.postgres.update_team(team_id, organization_id, updates)
        if not updated:
            return None

        # Update cache
        if self.redis:
            await self.redis.save_team(updated)

        logger.info("Updated team", team_id=team_id, updates=list(updates.keys()))
        return updated

    async def delete_team(self, team_id: str, organization_id: str) -> bool:
        """Delete a team."""
        success = await self.postgres.delete_team(team_id, organization_id)

        if success and self.redis:
            await self.redis.delete_team(team_id, organization_id)

        if success:
            logger.info("Deleted team", team_id=team_id)

        return success

    async def add_member(
        self,
        team_id: str,
        user_id: str,
        organization_id: str,
    ) -> Optional[TaskTeam]:
        """
        Add a member to a team.

        Args:
            team_id: Team ID
            user_id: User ID to add
            organization_id: Organization ID

        Returns:
            Updated team or None if not found
        """
        success = await self.postgres.add_member(team_id, user_id, organization_id)
        if not success:
            return None

        # Get updated team
        team = await self.postgres.get_team(team_id, organization_id)

        # Update cache
        if team and self.redis:
            await self.redis.save_team(team)

        logger.info("Added member to team", team_id=team_id, user_id=user_id)
        return team

    async def remove_member(
        self,
        team_id: str,
        user_id: str,
        organization_id: str,
    ) -> Optional[TaskTeam]:
        """
        Remove a member from a team.

        Args:
            team_id: Team ID
            user_id: User ID to remove
            organization_id: Organization ID

        Returns:
            Updated team or None if not found
        """
        success = await self.postgres.remove_member(team_id, user_id, organization_id)
        if not success:
            return None

        # Get updated team
        team = await self.postgres.get_team(team_id, organization_id)

        # Update cache
        if team and self.redis:
            await self.redis.save_team(team)

        logger.info("Removed member from team", team_id=team_id, user_id=user_id)
        return team

    async def get_user_teams(
        self,
        user_id: str,
        organization_id: str,
    ) -> List[TaskTeam]:
        """
        Get all teams a user belongs to.

        Args:
            user_id: User ID to find teams for
            organization_id: Organization ID

        Returns:
            List of teams the user is a member of
        """
        all_teams = await self.list_teams(organization_id)
        return [team for team in all_teams if user_id in team.member_ids or team.lead_user_id == user_id]
