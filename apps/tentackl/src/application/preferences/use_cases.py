"""Application use cases for preference management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.domain.preferences.ports import PreferenceOperationsPort


class PreferenceNotFound(Exception):
    """Raised when a preference does not exist."""


class PreferenceForbidden(Exception):
    """Raised when a user cannot access a preference."""


class PreferenceValidationError(Exception):
    """Raised when a preference request is invalid."""


@dataclass
class PreferenceUseCases:
    """Application-layer orchestration for preference operations."""

    preference_ops: PreferenceOperationsPort

    async def list_preferences(self, user_id: str) -> List[Dict[str, Any]]:
        preferences = await self.preference_ops.list_preferences(user_id)
        return [
            {
                "id": p.id,
                "preference_key": p.preference_key,
                "decision": p.decision,
                "confidence": p.confidence,
                "usage_count": p.usage_count,
                "last_used": p.last_used,
                "created_at": p.created_at,
            }
            for p in preferences
        ]

    async def get_preference_stats(self, user_id: str) -> Dict[str, Any]:
        stats = await self.preference_ops.get_preference_stats(user_id)
        return {
            "total_preferences": stats.get("total_preferences", 0),
            "high_confidence": stats.get("high_confidence", 0),
            "approvals": stats.get("approvals", 0),
            "rejections": stats.get("rejections", 0),
            "avg_confidence": stats.get("avg_confidence", 0.0),
            "total_usage": stats.get("total_usage", 0),
        }

    async def delete_preference(self, user_id: str, preference_id: str) -> None:
        pref = await self.preference_ops.get_preference(preference_id)

        if not pref:
            raise PreferenceNotFound()

        if pref.user_id != user_id:
            raise PreferenceForbidden()

        await self.preference_ops.delete_preference(preference_id)

    async def create_preference(
        self,
        user_id: str,
        organization_id: Optional[str],
        preference_key: str,
        instruction: str,
        scope: str,
        scope_value: Optional[str],
        created_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        valid_scopes = ["global", "agent_type", "task_type", "task"]
        if scope not in valid_scopes:
            raise PreferenceValidationError(
                f"Invalid scope: {scope}. Must be one of: {valid_scopes}"
            )

        if scope != "global" and not scope_value:
            raise PreferenceValidationError(
                f"scope_value is required for scope '{scope}'"
            )

        preference_id = await self.preference_ops.create_instruction_preference(
            user_id=user_id,
            preference_key=preference_key,
            instruction=instruction,
            scope=scope,
            scope_value=scope_value,
            organization_id=organization_id,
        )

        if not preference_id:
            raise PreferenceValidationError("Failed to create preference")

        return {
            "id": preference_id,
            "preference_key": preference_key,
            "instruction": instruction,
            "scope": scope,
            "scope_value": scope_value,
            "created_at": created_at or datetime.utcnow(),
        }
