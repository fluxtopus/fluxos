"""Application use cases for Google calendar assistant automation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.domain.oauth import GoogleCalendarAssistantPort


@dataclass
class GoogleCalendarAssistantUseCases:
    """Application-layer orchestration for calendar assistant automation."""

    assistant_ops: GoogleCalendarAssistantPort

    async def enable_assistant(
        self,
        user_id: str,
        organization_id: Optional[str],
        cron: str,
    ) -> Dict[str, Any]:
        return await self.assistant_ops.enable(
            user_id=user_id,
            organization_id=organization_id,
            cron=cron,
        )

    async def disable_assistant(self, user_id: str) -> Dict[str, Any]:
        return await self.assistant_ops.disable(user_id=user_id)
