"""Infrastructure base class and types for OAuth providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class OAuthTokenResult:
    """Result of an OAuth token exchange or refresh."""

    access_token: str
    refresh_token: Optional[str]
    expires_in: Optional[int]
    scope: Optional[str]
    token_type: str = "bearer"


class IntegrationOAuthProvider(ABC):
    """Abstract base class for integration OAuth providers."""

    provider_name: str

    @abstractmethod
    def get_authorization_url(self, state: str, code_challenge: str, redirect_uri: str) -> str:
        ...

    @abstractmethod
    async def exchange_code(
        self,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> OAuthTokenResult:
        ...

    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> OAuthTokenResult:
        ...

    @abstractmethod
    async def revoke_token(self, access_token: str) -> bool:
        ...
