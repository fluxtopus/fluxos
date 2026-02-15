"""Infrastructure adapter for Google OAuth operations."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from src.domain.oauth import GoogleOAuthPort
from src.plugins.registry import registry


class GoogleOAuthAdapter(GoogleOAuthPort):
    """Adapter exposing Google OAuth plugin handlers via the domain port."""

    async def start_oauth(
        self,
        user_id: str,
        scopes: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        inputs: Dict[str, Any] = {"user_id": user_id}
        if scopes is not None:
            inputs["scopes"] = list(scopes)
        return await registry.execute("google_oauth_start", inputs)

    async def handle_callback(self, code: str, state: str) -> Dict[str, Any]:
        return await registry.execute(
            "google_oauth_callback",
            {"code": code, "state": state},
        )

    async def get_status(self, user_id: str) -> Dict[str, Any]:
        return await registry.execute("google_oauth_status", {"user_id": user_id})
