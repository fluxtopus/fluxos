"""Application use cases for Google OAuth."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from src.domain.oauth import GoogleOAuthPort


@dataclass
class GoogleOAuthUseCases:
    """Application-layer orchestration for Google OAuth."""

    oauth_ops: GoogleOAuthPort

    async def start_oauth(
        self,
        user_id: str,
        scopes: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        return await self.oauth_ops.start_oauth(user_id=user_id, scopes=scopes)

    async def handle_callback(self, code: str, state: str) -> Dict[str, Any]:
        return await self.oauth_ops.handle_callback(code=code, state=state)

    async def get_status(self, user_id: str) -> Dict[str, Any]:
        return await self.oauth_ops.get_status(user_id=user_id)
