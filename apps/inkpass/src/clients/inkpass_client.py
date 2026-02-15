"""
inkPass Client Library

A client library for integrating with the inkPass authentication and authorization service.
Follows Tentackl architecture patterns with async/await, retry logic, and error handling.
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import httpx
import structlog
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = structlog.get_logger()


@dataclass
class InkPassConfig:
    """Configuration for inkPass client"""

    base_url: str = "http://localhost:8002"
    api_key: Optional[str] = None
    timeout: float = 5.0
    max_retries: int = 3
    retry_min_wait: int = 1
    retry_max_wait: int = 10


class InkPassError(Exception):
    """Base exception for inkPass client errors"""

    pass


class AuthenticationError(InkPassError):
    """Raised when authentication fails"""

    pass


class PermissionError(InkPassError):
    """Raised when permission check fails"""

    pass


class InkPassClient:
    """
    Async client for inkPass authentication and authorization service.

    This client follows Tentackl architecture patterns:
    - Async/await for all I/O operations
    - Retry logic with exponential backoff
    - Comprehensive error handling
    - Type hints and docstrings
    - Structured logging

    Example:
        ```python
        client = InkPassClient(InkPassConfig(base_url="http://inkpass:8000"))

        # Validate token
        user = await client.validate_token(token)

        # Check permission
        has_perm = await client.check_permission(token, "workflows", "create")

        # Get user info
        user_info = await client.get_user_info(token)
        ```
    """

    def __init__(self, config: Optional[InkPassConfig] = None):
        """
        Initialize inkPass client.

        Args:
            config: Client configuration. If None, uses default config.
        """
        self.config = config or InkPassConfig()
        self._client: Optional[httpx.AsyncClient] = None
        logger.info("InkPassClient initialized", base_url=self.config.base_url)

    async def __aenter__(self):
        """Async context manager entry"""
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self._client:
            await self._client.aclose()

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=self.config.timeout,
            )
        return self._client

    def _get_headers(self, token: Optional[str] = None) -> Dict[str, str]:
        """
        Get request headers.

        Args:
            token: Optional JWT token for authentication

        Returns:
            Headers dictionary
        """
        headers = {"Content-Type": "application/json"}

        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif self.config.api_key:
            headers["X-API-Key"] = self.config.api_key

        return headers

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Validate a JWT token and return user information.

        Args:
            token: JWT access token

        Returns:
            User information dict or None if invalid

        Raises:
            AuthenticationError: If token validation fails
            InkPassError: If service is unavailable
        """
        try:
            client = self._get_client()
            response = await client.get(
                "/api/v1/auth/me",
                headers=self._get_headers(token),
            )

            if response.status_code == 200:
                user_data = response.json()
                logger.info("Token validated successfully", user_id=user_data.get("id"))
                return user_data
            elif response.status_code == 401:
                logger.warning("Token validation failed - invalid token")
                return None
            else:
                logger.error(
                    "Token validation failed",
                    status_code=response.status_code,
                    response=response.text,
                )
                raise AuthenticationError(f"Token validation failed: {response.text}")

        except httpx.RequestError as e:
            logger.error("inkPass service unavailable", error=str(e))
            raise InkPassError(f"inkPass service unavailable: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def check_permission(
        self, token: str, resource: str, action: str, context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Check if user has permission for a resource and action.

        Args:
            token: JWT access token
            resource: Resource name (e.g., "workflows", "notifications")
            action: Action name (e.g., "create", "read", "update", "delete")
            context: Optional context for ABAC evaluation

        Returns:
            True if user has permission, False otherwise

        Raises:
            InkPassError: If service is unavailable
        """
        try:
            client = self._get_client()
            params = {"resource": resource, "action": action}

            response = await client.post(
                "/api/v1/auth/check",
                headers=self._get_headers(token),
                params=params,
                json=context or {},
            )

            if response.status_code == 200:
                result = response.json()
                has_permission = result.get("has_permission", False)
                logger.info(
                    "Permission checked",
                    resource=resource,
                    action=action,
                    has_permission=has_permission,
                )
                return has_permission
            elif response.status_code == 401:
                logger.warning("Permission check failed - invalid token")
                return False
            else:
                logger.error(
                    "Permission check failed",
                    status_code=response.status_code,
                    response=response.text,
                )
                # Default to deny access on error
                return False

        except httpx.RequestError as e:
            logger.error("inkPass service unavailable during permission check", error=str(e))
            # Default to deny access if service unavailable
            return False

    async def get_user_info(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Get user information from token.

        This is an alias for validate_token for clarity.

        Args:
            token: JWT access token

        Returns:
            User information dict or None if invalid
        """
        return await self.validate_token(token)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def register_user(
        self, email: str, password: str, organization_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Register a new user.

        Args:
            email: User email
            password: User password
            organization_name: Optional organization name

        Returns:
            Registration result with user_id, email, organization_id

        Raises:
            InkPassError: If registration fails
        """
        try:
            client = self._get_client()
            data = {
                "email": email,
                "password": password,
            }
            if organization_name:
                data["organization_name"] = organization_name

            response = await client.post(
                "/api/v1/auth/register",
                headers=self._get_headers(),
                json=data,
            )

            if response.status_code == 201:
                result = response.json()
                logger.info("User registered successfully", email=email)
                return result
            else:
                logger.error(
                    "User registration failed",
                    status_code=response.status_code,
                    response=response.text,
                )
                raise InkPassError(f"User registration failed: {response.text}")

        except httpx.RequestError as e:
            logger.error("inkPass service unavailable during registration", error=str(e))
            raise InkPassError(f"inkPass service unavailable: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def login(self, email: str, password: str) -> Dict[str, Any]:
        """
        Login user and get tokens.

        Args:
            email: User email
            password: User password

        Returns:
            Login result with access_token, refresh_token, token_type, expires_in

        Raises:
            AuthenticationError: If login fails
            InkPassError: If service is unavailable
        """
        try:
            client = self._get_client()
            response = await client.post(
                "/api/v1/auth/login",
                headers=self._get_headers(),
                json={"email": email, "password": password},
            )

            if response.status_code == 200:
                result = response.json()
                logger.info("User logged in successfully", email=email)
                return result
            elif response.status_code == 401:
                logger.warning("Login failed - invalid credentials", email=email)
                raise AuthenticationError("Invalid email or password")
            else:
                logger.error(
                    "Login failed",
                    status_code=response.status_code,
                    response=response.text,
                )
                raise InkPassError(f"Login failed: {response.text}")

        except httpx.RequestError as e:
            logger.error("inkPass service unavailable during login", error=str(e))
            raise InkPassError(f"inkPass service unavailable: {e}")

    async def close(self):
        """Close the HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("InkPassClient closed")
