"""Configuration settings for inkPass"""

from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    # Hosting platforms may provide PORT dynamically
    PORT: int = int(os.getenv("PORT", "8000"))
    SECRET_KEY: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database
    # Runtime may provide DATABASE_URL
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # Redis
    # Runtime may provide REDIS_URL
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    
    # Encryption
    ENCRYPTION_KEY: str
    
    # Email
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "noreply@inkpass.com")  # Sender email for notifications
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@inkpass.com"  # Deprecated: use EMAIL_FROM
    
    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001,http://localhost:3002,https://fluxtopus.com,https://www.fluxtopus.com"
    
    # Integration
    MIMIC_URL: str = "http://mimic:8001"
    MIMIC_API_KEY: str = ""  # Service API key for Mimic notifications
    TENTACKL_URL: str = "http://tentackl:8000"
    FRONTEND_URL: str = "http://localhost:3000"  # Frontend URL for invitation links

    # OAuth Configuration
    OAUTH_REDIRECT_URI: str = "http://localhost:8002/api/v1/auth/oauth/callback"
    OAUTH_STATE_COOKIE_NAME: str = "oauth_state"
    OAUTH_STATE_COOKIE_MAX_AGE: int = 600  # 10 minutes

    # OAuth Providers (optional - can also be configured via database)
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # Bunny.net Storage Configuration
    BUNNY_API_KEY: str = ""
    BUNNY_STORAGE_ZONE: str = ""
    BUNNY_STORAGE_HOSTNAME: str = "storage.bunnycdn.com"
    BUNNY_CDN_HOSTNAME: str = ""
    BUNNY_TOKEN_KEY: str = ""  # For signed URLs

    # Storage Backend Selection
    STORAGE_BACKEND: str = "local"  # "local" or "bunny"

    # File Storage Limits
    MAX_FILE_SIZE_BYTES: int = 104857600  # 100MB
    DEFAULT_STORAGE_QUOTA_BYTES: int = 5368709120  # 5GB

    # Local Storage (for development)
    LOCAL_STORAGE_PATH: str = "/tmp/den-storage"

    # Service Account Authentication
    # Format: "service1:key1,service2:key2"
    SERVICE_API_KEYS: str = ""

    # OpenAI Configuration (for semantic search embeddings)
    OPENAI_API_KEY: str = ""
    EMBEDDING_ENABLED: bool = True
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536

    # Development Permission Presets
    # Set to a preset name (admin, developer, viewer, etc.) to auto-assign permissions on startup
    DEV_PERMISSIONS: str = ""  # e.g., "admin", "developer", "viewer"
    DEV_USER_EMAIL: str = "admin@fluxtopus.com"  # User to assign dev permissions to

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
