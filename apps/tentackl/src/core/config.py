# REVIEW:
# - Mixes BaseSettings with os.getenv at class definition time; some values bypass pydantic env parsing and are fixed at import.
# - Many alias fields (X_API_KEY_SECRET/X_API_SECRET, etc.) increase config ambiguity.
from pydantic_settings import BaseSettings
from pydantic import ConfigDict, computed_field
from typing import Optional
import os
import logging


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "tentackl"
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    # Hosting platforms may provide PORT dynamically - use it if available
    APP_PORT: int = int(os.getenv("PORT", "8000"))
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False
    
    # API (alternative names for compatibility)
    API_HOST: Optional[str] = None
    API_PORT: Optional[int] = None

    # Public URL Configuration (for webhooks and callbacks)
    # Priority: API_BASE_URL > localhost fallback
    API_BASE_URL: Optional[str] = None  # Explicit override (highest priority)

    # Database
    # Runtime may provide DATABASE_URL - use it if available, otherwise use default
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://tentackl:tentackl_pass@postgres:5432/tentackl_db"
    )
    # Database pool settings - lower defaults for reduced idle CPU
    # Can be increased via env vars for higher load scenarios
    DATABASE_POOL_SIZE: int = int(os.getenv("DATABASE_POOL_SIZE", "5"))
    DATABASE_MAX_OVERFLOW: int = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))

    # Database connection components (for building DATABASE_URL if needed)
    POSTGRES_HOST: Optional[str] = None
    POSTGRES_PORT: Optional[int] = None
    POSTGRES_DB: Optional[str] = None
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None

    # Redis
    # Runtime may provide REDIS_URL - use it if available, otherwise use default
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    REDIS_PASSWORD: Optional[str] = None
    REDIS_MAX_CONNECTIONS: int = 50

    # Redis connection components (for building REDIS_URL if needed)
    REDIS_HOST: Optional[str] = None
    REDIS_PORT: Optional[int] = None
    REDIS_DB: Optional[int] = None

    # Celery
    # Build Celery URLs from REDIS_URL if available
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL") or (
        os.getenv("REDIS_URL", "redis://redis:6379/0").rsplit("/", 1)[0] + "/1"
        if os.getenv("REDIS_URL") else "redis://redis:6379/1"
    )
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND") or (
        os.getenv("REDIS_URL", "redis://redis:6379/0").rsplit("/", 1)[0] + "/2"
        if os.getenv("REDIS_URL") else "redis://redis:6379/2"
    )
    
    # Agent Configuration
    AGENT_DEFAULT_TIMEOUT: int = 300
    AGENT_MAX_RETRIES: int = 3
    AGENT_HEARTBEAT_INTERVAL: int = 30

    # Playground limits (for demo mode)
    PLAYGROUND_MAX_NODES: int = 6          # Max workflow nodes
    PLAYGROUND_MAX_LOOPS: int = 10         # Max for_each iterations
    PLAYGROUND_MAX_LLM_CALLS: int = 3      # Max LLM nodes

    # Security
    SECRET_KEY: Optional[str] = None
    JWT_SECRET: Optional[str] = None
    API_KEY_HEADER: str = "X-API-Key"

    # CORS - comma-separated list of allowed origins
    # Example: "https://fluxtopus.com,https://www.fluxtopus.com"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    
    # External APIs
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None
    
    # OpenRouter Configuration
    SITE_URL: Optional[str] = None
    SITE_NAME: Optional[str] = "Tentackl Multi-Agent System"
    
    # File Operations
    FILE_OPERATIONS_BASE_DIR: str = os.getenv("FILE_OPERATIONS_BASE_DIR", "/app/data")

    # MCP Configuration
    MCP_ENABLED: bool = True
    MCP_REGISTRY_PATH: str = "/app/config/mcp_registry.json"
    
    # Monitoring
    ENABLE_METRICS: bool = True
    PROMETHEUS_ENABLED: Optional[bool] = None  # Alias for ENABLE_METRICS
    METRICS_PORT: int = 9090

    # PostHog Analytics
    POSTHOG_API_KEY: Optional[str] = os.getenv("POSTHOG_API_KEY", None)
    POSTHOG_HOST: str = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com")
    POSTHOG_ENABLED: bool = os.getenv("POSTHOG_ENABLED", "false").lower() == "true"
    
    # Logging
    LOG_FORMAT: Optional[str] = None
    LOG_FILE: Optional[str] = None
    
    # Twitter/X API Configuration
    X_API_KEY: Optional[str] = None
    X_API_KEY_SECRET: Optional[str] = None
    X_API_SECRET: Optional[str] = None  # Alias for X_API_KEY_SECRET
    X_BEARER_TOKEN: Optional[str] = None
    X_ACCESS_TOKEN: Optional[str] = None
    X_ACCESS_TOKEN_SECRET: Optional[str] = None
    X_OAUTH2_CLIENT_ID: Optional[str] = None
    X_OAUTH2_CLIENT_SECRET: Optional[str] = None
    X_OAUTH2_USER_ACCESS_TOKEN: Optional[str] = None
    X_USER_ID: Optional[str] = None
    X_API_USER_ID: Optional[str] = None  # Alias for X_USER_ID
    TWITTER_DAILY_POST_LIMIT: int = 3

    # Google OAuth Configuration
    GOOGLE_OAUTH_CLIENT_ID: Optional[str] = None
    GOOGLE_OAUTH_CLIENT_SECRET: Optional[str] = None
    GOOGLE_OAUTH_REDIRECT_URI: Optional[str] = None

    # InkPass Connection (for Den file operations)
    # Empty default = standalone mode (no InkPass dependency)
    INKPASS_URL: str = os.getenv("INKPASS_URL", "")
    INKPASS_SERVICE_API_KEY: Optional[str] = None

    # Mimic Connection (for notifications)
    MIMIC_URL: str = os.getenv("MIMIC_URL", "")

    @computed_field
    @property
    def INKPASS_ENABLED(self) -> bool:
        """Whether InkPass auth service is configured."""
        return bool(self.INKPASS_URL)

    @computed_field
    @property
    def MIMIC_ENABLED(self) -> bool:
        """Whether Mimic notification service is configured."""
        return bool(self.MIMIC_URL)

    # ==========================================================================
    # BRAND CONFIGURATION
    # Global brand settings that agents must follow when composing communications.
    # ==========================================================================

    # Brand identity - defaults used for agent-generated communications
    BRAND_NAME: str = "aios"
    BRAND_TAGLINE: str = "AI-powered workflow automation"

    # Support contact information
    BRAND_SUPPORT_EMAIL: str = "support@fluxtopus.com"
    BRAND_SUPPORT_URL: str = "https://fluxtopus.com/support"

    # Communication guidelines
    BRAND_INCLUDE_PHONE: bool = False  # Never include phone numbers
    BRAND_FOOTER_TEXT: str = "Sent by aios - AI-powered workflow automation"

    @computed_field
    @property
    def webhook_base_url(self) -> str:
        """
        Get webhook base URL with priority:
        1. API_BASE_URL (explicit override)
        2. localhost fallback (development)
        """
        if self.API_BASE_URL:
            return self.API_BASE_URL.rstrip('/')

        return f"http://localhost:{self.APP_PORT}"

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="allow"  # Allow extra environment variables that aren't defined in the model
    )


settings = Settings()

# Log webhook configuration at startup
_logger = logging.getLogger(__name__)
_webhook_source = (
    "API_BASE_URL" if settings.API_BASE_URL
    else "localhost_fallback"
)
_logger.info(
    f"Webhook base URL configured: {settings.webhook_base_url} (source: {_webhook_source})"
)

# Known insecure default secret patterns
_INSECURE_SECRET_PATTERNS = [
    "your-secret-key-here-change-in-production",
    "your-secret-key-change-this-in-production",
    "change-this-in-production",
    "changeme",
    "secret",
    "password",
    "your-secret-key",
]


def validate_secrets() -> None:
    """Validate that SECRET_KEY is set and not an insecure default.

    In production (APP_ENV != 'development'), raises RuntimeError if
    SECRET_KEY is None or matches a known insecure pattern.

    In development, logs warnings for the same conditions.
    """
    is_production = settings.APP_ENV != "development"
    secret = settings.SECRET_KEY
    jwt_secret = settings.JWT_SECRET

    # Also check the auth_middleware env var (TENTACKL_SECRET_KEY)
    tentackl_secret = os.getenv("TENTACKL_SECRET_KEY")

    issues = []

    # Check settings.SECRET_KEY
    if secret is None:
        issues.append("SECRET_KEY is not set (None)")
    elif secret.lower() in _INSECURE_SECRET_PATTERNS or len(secret) < 16:
        issues.append(f"SECRET_KEY uses an insecure default or is too short (<16 chars)")

    # Check TENTACKL_SECRET_KEY env var used by auth_middleware
    if tentackl_secret is not None:
        if tentackl_secret.lower() in _INSECURE_SECRET_PATTERNS or len(tentackl_secret) < 16:
            issues.append("TENTACKL_SECRET_KEY env var uses an insecure default or is too short (<16 chars)")

    if issues:
        message = (
            "JWT/Secret key validation failed:\n"
            + "\n".join(f"  - {issue}" for issue in issues)
            + "\n\nSet SECRET_KEY and TENTACKL_SECRET_KEY to secure random values "
            "(at least 32 characters). Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )
        if is_production:
            raise RuntimeError(message)
        else:
            _logger.warning(f"⚠️  SECURITY WARNING (development mode): {message}")


def validate_dev_auth_bypass() -> None:
    """Validate and warn about DEV_AUTH_BYPASS configuration at startup.

    SEC-010: Hardens the dev auth bypass mechanism with multiple guards:
    1. In production (APP_ENV != 'development'), DEV_AUTH_BYPASS is forced off.
    2. When enabled, requires DEV_AUTH_BYPASS_TOKEN to be set as a second factor.
    3. Logs a prominent warning when bypass is active.

    Call this from the application lifespan, after validate_secrets().
    """
    app_env = settings.APP_ENV
    bypass_enabled = os.getenv("DEV_AUTH_BYPASS", "false").lower() == "true"

    if not bypass_enabled:
        return

    # Guard 1: Force off in production regardless of env var
    if app_env != "development":
        _logger.warning(
            "SEC-010: DEV_AUTH_BYPASS=true ignored because APP_ENV=%s (not 'development'). "
            "Auth bypass is only allowed in development mode.",
            app_env,
        )
        return

    # Guard 2: Require a non-empty DEV_AUTH_BYPASS_TOKEN as second factor
    bypass_token = os.getenv("DEV_AUTH_BYPASS_TOKEN", "")
    if not bypass_token:
        _logger.warning(
            "SEC-010: DEV_AUTH_BYPASS=true but DEV_AUTH_BYPASS_TOKEN is not set. "
            "Auth bypass will be INACTIVE. Set DEV_AUTH_BYPASS_TOKEN to a non-empty "
            "value to enable bypass in development."
        )
        return

    # Both guards passed — bypass is active, log a prominent warning
    _logger.warning(
        "⚠️  SEC-010: DEV_AUTH_BYPASS is ACTIVE (APP_ENV=development, token present). "
        "All authentication is bypassed. Do NOT use this in any non-local environment."
    )


def is_dev_auth_bypass_allowed() -> bool:
    """Check if DEV_AUTH_BYPASS should be honored at request time.

    Returns True only when ALL conditions are met:
    1. APP_ENV is 'development'
    2. DEV_AUTH_BYPASS env var is 'true'
    3. DEV_AUTH_BYPASS_TOKEN env var is set (non-empty)

    Used by auth_middleware to decide whether to inject a dev user.
    """
    if settings.APP_ENV != "development":
        return False
    if os.getenv("DEV_AUTH_BYPASS", "false").lower() != "true":
        return False
    if not os.getenv("DEV_AUTH_BYPASS_TOKEN", ""):
        return False
    return True
