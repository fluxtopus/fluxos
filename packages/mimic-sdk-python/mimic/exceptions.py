"""Exceptions for Mimic SDK."""


class MimicError(Exception):
    """Base exception for all Mimic SDK errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """
        Initialize MimicError.

        Args:
            message: Error message
            status_code: HTTP status code if applicable
        """
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class AuthenticationError(MimicError):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication failed") -> None:
        """Initialize AuthenticationError."""
        super().__init__(message, status_code=401)


class PermissionDeniedError(MimicError):
    """Raised when user lacks required permissions."""

    def __init__(self, message: str = "Permission denied") -> None:
        """Initialize PermissionDeniedError."""
        super().__init__(message, status_code=403)


class ResourceNotFoundError(MimicError):
    """Raised when requested resource is not found."""

    def __init__(self, message: str = "Resource not found") -> None:
        """Initialize ResourceNotFoundError."""
        super().__init__(message, status_code=404)


class ValidationError(MimicError):
    """Raised when request validation fails."""

    def __init__(self, message: str = "Validation failed") -> None:
        """Initialize ValidationError."""
        super().__init__(message, status_code=422)


class RateLimitError(MimicError):
    """Raised when rate limit is exceeded."""

    def __init__(
        self, message: str = "Rate limit exceeded", retry_after_seconds: int = 0
    ) -> None:
        """Initialize RateLimitError."""
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message, status_code=429)


class ServiceUnavailableError(MimicError):
    """Raised when Mimic service is unavailable."""

    def __init__(self, message: str = "Mimic service unavailable") -> None:
        """Initialize ServiceUnavailableError."""
        super().__init__(message, status_code=503)
