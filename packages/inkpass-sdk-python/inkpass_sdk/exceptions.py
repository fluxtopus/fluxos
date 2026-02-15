"""Exceptions for inkPass SDK."""


class InkPassError(Exception):
    """Base exception for all inkPass SDK errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """
        Initialize InkPassError.

        Args:
            message: Error message
            status_code: HTTP status code if applicable
        """
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class AuthenticationError(InkPassError):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication failed") -> None:
        """Initialize AuthenticationError."""
        super().__init__(message, status_code=401)


class PermissionDeniedError(InkPassError):
    """Raised when user lacks required permissions."""

    def __init__(self, message: str = "Permission denied") -> None:
        """Initialize PermissionDeniedError."""
        super().__init__(message, status_code=403)


class ResourceNotFoundError(InkPassError):
    """Raised when requested resource is not found."""

    def __init__(self, message: str = "Resource not found") -> None:
        """Initialize ResourceNotFoundError."""
        super().__init__(message, status_code=404)


class ValidationError(InkPassError):
    """Raised when request validation fails."""

    def __init__(self, message: str = "Validation failed") -> None:
        """Initialize ValidationError."""
        super().__init__(message, status_code=422)


class RateLimitError(InkPassError):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded") -> None:
        """Initialize RateLimitError."""
        super().__init__(message, status_code=429)


class ServiceUnavailableError(InkPassError):
    """Raised when inkPass service is unavailable."""

    def __init__(self, message: str = "inkPass service unavailable") -> None:
        """Initialize ServiceUnavailableError."""
        super().__init__(message, status_code=503)
