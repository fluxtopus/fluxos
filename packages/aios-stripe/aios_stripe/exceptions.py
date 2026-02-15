"""
Stripe-related exceptions.

Standalone exception hierarchy for the aios-stripe package.
No dependencies on app-specific code.
"""

from typing import Any


class StripeError(Exception):
    """Base exception for all Stripe-related errors."""

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
        original_error: Exception | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.original_error = original_error

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for serialization."""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.message!r}, details={self.details})"


class StripeCustomerError(StripeError):
    """Customer operation failed (create, get, update, delete)."""

    pass


class StripePaymentError(StripeError):
    """Payment or checkout operation failed."""

    pass


class StripeSubscriptionError(StripeError):
    """Subscription operation failed (create, cancel, update)."""

    pass


class StripeWebhookError(StripeError):
    """Webhook verification or processing failed."""

    pass


class StripeConnectionError(StripeError):
    """Unable to connect to Stripe API."""

    pass


class StripeConfigError(StripeError):
    """Invalid configuration provided."""

    pass
