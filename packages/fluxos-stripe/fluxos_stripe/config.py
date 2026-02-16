"""
Stripe client configuration.

Standalone configuration with no app-specific dependencies.
"""

from dataclasses import dataclass, field

from .exceptions import StripeConfigError


@dataclass
class StripeConfig:
    """Configuration for Stripe client.

    Args:
        api_key: Stripe secret key (sk_live_* or sk_test_*)
        webhook_secret: Webhook signing secret for signature verification
        timeout: API request timeout in seconds
        max_retries: Maximum number of retries for failed requests
    """

    api_key: str
    webhook_secret: str | None = None
    timeout: float = 30.0
    max_retries: int = 3

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if not self.api_key:
            raise StripeConfigError("api_key is required")

        if not self.api_key.startswith(("sk_live_", "sk_test_", "rk_live_", "rk_test_")):
            raise StripeConfigError(
                "api_key must be a valid Stripe secret key (sk_*) or restricted key (rk_*)"
            )

        if self.timeout <= 0:
            raise StripeConfigError("timeout must be positive")

        if self.max_retries < 0:
            raise StripeConfigError("max_retries must be non-negative")

    @property
    def is_test_mode(self) -> bool:
        """Check if using test mode API key."""
        return "_test_" in self.api_key

    @property
    def is_live_mode(self) -> bool:
        """Check if using live mode API key."""
        return "_live_" in self.api_key
