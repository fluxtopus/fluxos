# REVIEW: This service mixes DB access and prompt formatting in one class,
# REVIEW: with in-method imports and hard-coded scope precedence. Error handling
# REVIEW: swallows failures by returning [] which can hide data issues. Consider
# REVIEW: separating query logic, adding caching, and making precedence/config
# REVIEW: declarative (or stored in DB) to avoid drift.
"""
Preference Injection Service for Tentackl Agent Memory System.

This service loads user preferences and formats them for injection into
agent prompts. Preferences help agents personalize their behavior based
on learned user preferences and explicit instructions.

Preference Scoping Hierarchy (higher priority wins):
1. TASK - Specific task ID
2. TASK_TYPE - Task category (e.g., "meal_planning", "email_digest")
3. AGENT_TYPE - Agent type (e.g., "compose", "notify")
4. GLOBAL - Applies to all agents

Preference Types:
- instruction: Human-readable guidance injected into prompts
- auto_approval: Checkpoint auto-approval rules (handled elsewhere)
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ApplicablePreference:
    """A preference that applies to the current context."""
    preference_id: str
    preference_key: str
    instruction: str
    scope: str
    scope_value: Optional[str]
    confidence: float
    source: str  # learned, manual, imported
    last_used: datetime


class PreferenceInjectionService:
    """
    Service for loading and formatting user preferences for agent prompts.

    Usage:
        service = PreferenceInjectionService(db_session)
        preferences = await service.get_preferences_for_context(
            user_id="user_123",
            agent_type="compose",
            task_type="meal_planning",
            task_id="task_456"
        )
        prompt_section = service.format_preferences_for_prompt(preferences)
    """

    def __init__(self, db_session):
        """Initialize with database session.

        Args:
            db_session: SQLAlchemy async session for database operations
        """
        self.db_session = db_session

    async def get_preferences_for_context(
        self,
        user_id: str,
        agent_type: Optional[str] = None,
        task_type: Optional[str] = None,
        task_id: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> List[ApplicablePreference]:
        """
        Get all applicable preferences for the given context.

        Preferences are returned in priority order (highest first).
        Duplicates by preference_key are deduplicated, keeping the
        highest-priority version.

        Args:
            user_id: User ID
            agent_type: Type of agent (e.g., "compose", "notify")
            task_type: Type of task (e.g., "meal_planning")
            task_id: Specific task ID
            organization_id: Optional organization ID

        Returns:
            List of applicable preferences in priority order
        """
        try:
            from sqlalchemy import select, and_, or_
            from src.database.task_models import UserPreference, PreferenceScope, PreferenceType

            # Build query for instruction-type preferences
            conditions = [
                UserPreference.user_id == user_id,
                UserPreference.preference_type == PreferenceType.INSTRUCTION.value,
            ]

            if organization_id:
                conditions.append(
                    or_(
                        UserPreference.organization_id == organization_id,
                        UserPreference.organization_id.is_(None),
                    )
                )

            # Build scope conditions
            scope_conditions = [
                UserPreference.scope == PreferenceScope.GLOBAL.value,
            ]

            if agent_type:
                scope_conditions.append(
                    and_(
                        UserPreference.scope == PreferenceScope.AGENT_TYPE.value,
                        UserPreference.scope_value == agent_type,
                    )
                )

            if task_type:
                scope_conditions.append(
                    and_(
                        UserPreference.scope == PreferenceScope.TASK_TYPE.value,
                        UserPreference.scope_value == task_type,
                    )
                )

            if task_id:
                scope_conditions.append(
                    and_(
                        UserPreference.scope == PreferenceScope.TASK.value,
                        UserPreference.scope_value == task_id,
                    )
                )

            # Combine conditions
            conditions.append(or_(*scope_conditions))

            # Execute query
            query = select(UserPreference).where(and_(*conditions))
            result = await self.db_session.execute(query)
            preferences = result.scalars().all()

            # Convert to ApplicablePreference and sort by priority
            applicable = []
            for pref in preferences:
                if pref.instruction:  # Only include if has instruction
                    applicable.append(ApplicablePreference(
                        preference_id=str(pref.id),
                        preference_key=pref.preference_key,
                        instruction=pref.instruction,
                        scope=pref.scope,
                        scope_value=pref.scope_value,
                        confidence=pref.confidence,
                        source=pref.source,
                        last_used=pref.last_used,
                    ))

            # Sort by priority (TASK > TASK_TYPE > AGENT_TYPE > GLOBAL)
            scope_priority = {
                PreferenceScope.TASK.value: 4,
                PreferenceScope.TASK_TYPE.value: 3,
                PreferenceScope.AGENT_TYPE.value: 2,
                PreferenceScope.GLOBAL.value: 1,
            }
            applicable.sort(
                key=lambda p: (scope_priority.get(p.scope, 0), p.confidence),
                reverse=True
            )

            # Deduplicate by preference_key (keep highest priority)
            seen_keys = set()
            deduped = []
            for pref in applicable:
                if pref.preference_key not in seen_keys:
                    seen_keys.add(pref.preference_key)
                    deduped.append(pref)

            logger.debug(
                "preferences_loaded",
                user_id=user_id,
                agent_type=agent_type,
                task_type=task_type,
                count=len(deduped),
            )

            return deduped

        except Exception as e:
            logger.error("preference_load_failed", error=str(e), user_id=user_id)
            return []

    def format_preferences_for_prompt(
        self,
        preferences: List[ApplicablePreference],
        include_metadata: bool = False,
    ) -> str:
        """
        Format preferences as a prompt section for injection.

        Args:
            preferences: List of applicable preferences
            include_metadata: Include source/confidence info (for debugging)

        Returns:
            Formatted markdown section for prompt injection
        """
        if not preferences:
            return ""

        lines = ["## User Preferences", ""]
        lines.append("The user has specified the following preferences:")
        lines.append("")

        for pref in preferences:
            # Main instruction
            lines.append(f"- {pref.instruction}")

            # Optional metadata for debugging
            if include_metadata:
                lines.append(f"  (scope: {pref.scope}, confidence: {pref.confidence:.0%})")

        lines.append("")
        lines.append("Please incorporate these preferences into your response where applicable.")
        lines.append("")

        return "\n".join(lines)

    async def record_preference_usage(
        self,
        preference_id: str,
    ) -> None:
        """
        Record that a preference was used (for analytics and confidence updates).

        Args:
            preference_id: ID of the preference that was used
        """
        try:
            from sqlalchemy import update
            from src.database.task_models import UserPreference

            stmt = (
                update(UserPreference)
                .where(UserPreference.id == preference_id)
                .values(
                    usage_count=UserPreference.usage_count + 1,
                    last_used=datetime.utcnow(),
                )
            )
            await self.db_session.execute(stmt)
            await self.db_session.commit()

        except Exception as e:
            logger.error("preference_usage_record_failed", error=str(e), preference_id=preference_id)

    async def create_instruction_preference(
        self,
        user_id: str,
        preference_key: str,
        instruction: str,
        scope: str = "global",
        scope_value: Optional[str] = None,
        organization_id: Optional[str] = None,
        source: str = "manual",
    ) -> Optional[str]:
        """
        Create a new instruction preference.

        Args:
            user_id: User ID
            preference_key: Unique key for this preference
            instruction: Human-readable instruction
            scope: Preference scope (global, agent_type, task_type, task)
            scope_value: Value for scope (e.g., "compose" for agent_type)
            organization_id: Optional organization ID
            source: How preference was created (manual, learned, imported)

        Returns:
            Preference ID if created successfully, None otherwise
        """
        try:
            from src.database.task_models import UserPreference, PreferenceType

            preference = UserPreference(
                user_id=user_id,
                organization_id=organization_id,
                preference_key=preference_key,
                scope=scope,
                scope_value=scope_value,
                preference_type=PreferenceType.INSTRUCTION.value,
                instruction=instruction,
                decision="instruction",  # Required by DB, but not used for instruction-type preferences
                source=source,
                confidence=1.0,  # Manual preferences have full confidence
            )

            self.db_session.add(preference)
            await self.db_session.commit()
            await self.db_session.refresh(preference)

            logger.info(
                "preference_created",
                preference_id=str(preference.id),
                preference_key=preference_key,
                scope=scope,
            )

            return str(preference.id)

        except Exception as e:
            logger.error("preference_create_failed", error=str(e), preference_key=preference_key)
            await self.db_session.rollback()
            return None

    async def update_instruction_preference(
        self,
        preference_id: str,
        instruction: Optional[str] = None,
        scope: Optional[str] = None,
        scope_value: Optional[str] = None,
    ) -> bool:
        """
        Update an existing instruction preference.

        Args:
            preference_id: ID of preference to update
            instruction: New instruction text (if updating)
            scope: New scope (if updating)
            scope_value: New scope value (if updating)

        Returns:
            True if updated successfully
        """
        try:
            from sqlalchemy import update
            from src.database.task_models import UserPreference

            values = {"updated_at": datetime.utcnow()}
            if instruction is not None:
                values["instruction"] = instruction
            if scope is not None:
                values["scope"] = scope
            if scope_value is not None:
                values["scope_value"] = scope_value

            stmt = (
                update(UserPreference)
                .where(UserPreference.id == preference_id)
                .values(**values)
            )
            result = await self.db_session.execute(stmt)
            await self.db_session.commit()

            return result.rowcount > 0

        except Exception as e:
            logger.error("preference_update_failed", error=str(e), preference_id=preference_id)
            await self.db_session.rollback()
            return False

    async def delete_preference(self, preference_id: str) -> bool:
        """
        Delete a preference.

        Args:
            preference_id: ID of preference to delete

        Returns:
            True if deleted successfully
        """
        try:
            from sqlalchemy import delete
            from src.database.task_models import UserPreference

            stmt = delete(UserPreference).where(UserPreference.id == preference_id)
            result = await self.db_session.execute(stmt)
            await self.db_session.commit()

            return result.rowcount > 0

        except Exception as e:
            logger.error("preference_delete_failed", error=str(e), preference_id=preference_id)
            await self.db_session.rollback()
            return False

    async def list_user_preferences(
        self,
        user_id: str,
        organization_id: Optional[str] = None,
        scope: Optional[str] = None,
        preference_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List all preferences for a user.

        Args:
            user_id: User ID
            organization_id: Optional organization filter
            scope: Optional scope filter
            preference_type: Optional type filter (instruction, auto_approval)

        Returns:
            List of preference dictionaries
        """
        try:
            from sqlalchemy import select, and_
            from src.database.task_models import UserPreference

            conditions = [UserPreference.user_id == user_id]

            if organization_id:
                conditions.append(UserPreference.organization_id == organization_id)
            if scope:
                conditions.append(UserPreference.scope == scope)
            if preference_type:
                conditions.append(UserPreference.preference_type == preference_type)

            query = select(UserPreference).where(and_(*conditions))
            result = await self.db_session.execute(query)
            preferences = result.scalars().all()

            return [
                {
                    "id": str(p.id),
                    "preference_key": p.preference_key,
                    "scope": p.scope,
                    "scope_value": p.scope_value,
                    "preference_type": p.preference_type,
                    "instruction": p.instruction,
                    "confidence": p.confidence,
                    "source": p.source,
                    "usage_count": p.usage_count,
                    "last_used": p.last_used.isoformat() if p.last_used else None,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                }
                for p in preferences
            ]

        except Exception as e:
            logger.error("preference_list_failed", error=str(e), user_id=user_id)
            return []
