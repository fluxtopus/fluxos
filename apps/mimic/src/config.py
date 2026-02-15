"""Configuration settings for Mimic Notification Service"""

from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    # Hosting platforms may provide PORT dynamically
    PORT: int = int(os.getenv("PORT", "8000"))

    # Database
    # Runtime may provide DATABASE_URL
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://mimic:mimic_dev_password@localhost:5433/mimic"
    )

    # Redis (added for consistency)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")

    # Tentackl Integration
    TENTACKL_URL: str = os.getenv("TENTACKL_URL", "http://localhost:8005")
    TENTACKL_API_KEY: Optional[str] = None
    TENTACKL_INTERNAL_URL: str = os.getenv("TENTACKL_INTERNAL_URL", "http://tentackl:8000")

    # InkPass Integration (for auth)
    INKPASS_URL: str = os.getenv("INKPASS_URL", "http://localhost:8004")

    # Encryption
    ENCRYPTION_KEY: str = os.getenv(
        "ENCRYPTION_KEY",
        "dev-encryption-key-32-chars-long"
    )

    # Security
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY",
        "dev-secret-key-change-in-production"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # API
    API_V1_PREFIX: str = "/api/v1"
    
    # Billing
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None

    # Webhook Gateway
    RESEND_WEBHOOK_SECRET: Optional[str] = os.getenv("RESEND_WEBHOOK_SECRET", None)

    # Internal Service URLs (for Celery tasks to call)
    INKPASS_INTERNAL_URL: str = os.getenv("INKPASS_INTERNAL_URL", "http://inkpass:8000")

    # Service API Keys (for authenticating with other services)
    MIMIC_SERVICE_API_KEY: Optional[str] = os.getenv("MIMIC_SERVICE_API_KEY", None)

    # Celery
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

    # Subscription
    FREE_TIER_NOTIFICATIONS_LIMIT: int = 100
    ANNUAL_SUBSCRIPTION_PRICE: int = 49900  # $499.00 in cents

    # Email Provider Selection
    # Options: "dev" (SMTP), "postmark", "resend", "tentackl" (via workflow)
    EMAIL_PROVIDER: str = os.getenv("EMAIL_PROVIDER", "dev")

    # Development SMTP (for testing without Tentackl/provider keys)
    # Supports Mailtrap, Mailhog, or any SMTP server
    DEV_SMTP_ENABLED: bool = os.getenv("DEV_SMTP_ENABLED", "false").lower() == "true"
    DEV_SMTP_HOST: str = os.getenv("DEV_SMTP_HOST", "mailpit")
    DEV_SMTP_PORT: int = int(os.getenv("DEV_SMTP_PORT", "1025"))
    DEV_SMTP_USER: str = os.getenv("DEV_SMTP_USER", "")
    DEV_SMTP_PASSWORD: str = os.getenv("DEV_SMTP_PASSWORD", "")
    DEV_SMTP_FROM: str = os.getenv("DEV_SMTP_FROM", "noreply@fluxtopus.com")

    # Postmark (production email)
    POSTMARK_API_KEY: str = os.getenv("POSTMARK_API_KEY", "")

    # Resend (production email)
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
