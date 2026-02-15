"""Configuration for Mimic SDK."""

from dataclasses import dataclass


@dataclass
class MimicConfig:
    """
    Configuration for Mimic SDK client.

    Attributes:
        base_url: Base URL for Mimic service (e.g., "http://localhost:8006")
        api_key: API key for service-to-service authentication
        timeout: Request timeout in seconds (default: 5.0)
        max_retries: Maximum number of retry attempts (default: 3)
        retry_min_wait: Minimum wait time between retries in seconds (default: 1)
        retry_max_wait: Maximum wait time between retries in seconds (default: 10)
        verify_ssl: Whether to verify SSL certificates (default: True)

    Example:
        ```python
        config = MimicConfig(
            base_url="http://mimic:8000",
            api_key="your-service-api-key",
            timeout=10.0,
            max_retries=5
        )
        ```
    """

    base_url: str = "http://localhost:8006"
    api_key: str | None = None
    timeout: float = 5.0
    max_retries: int = 3
    retry_min_wait: int = 1
    retry_max_wait: int = 10
    verify_ssl: bool = True

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        # Remove trailing slash from base_url
        self.base_url = self.base_url.rstrip("/")

        # Validate timeout
        if self.timeout <= 0:
            raise ValueError("timeout must be greater than 0")

        # Validate retry settings
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")

        if self.retry_min_wait < 0:
            raise ValueError("retry_min_wait must be non-negative")

        if self.retry_max_wait < self.retry_min_wait:
            raise ValueError("retry_max_wait must be >= retry_min_wait")
