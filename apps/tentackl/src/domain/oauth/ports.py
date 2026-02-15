"""Domain ports for OAuth operations."""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, Sequence


class GoogleOAuthPort(Protocol):
    """Port for Google OAuth operations."""

    async def start_oauth(
        self,
        user_id: str,
        scopes: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        ...

    async def handle_callback(self, code: str, state: str) -> Dict[str, Any]:
        ...

    async def get_status(self, user_id: str) -> Dict[str, Any]:
        ...


class GoogleCalendarAssistantPort(Protocol):
    """Port for calendar assistant automation management."""

    async def enable(
        self,
        user_id: str,
        organization_id: Optional[str],
        cron: str,
    ) -> Dict[str, Any]:
        ...

    async def disable(self, user_id: str) -> Dict[str, Any]:
        ...
