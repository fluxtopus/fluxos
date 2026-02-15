# REVIEW: Local cache + Redis + DB caching adds complexity; cache invalidation
# REVIEW: strategy isn't obvious.
# REVIEW: Uses provided db_session directly; no session lifecycle management here.
"""
Brand Settings Service

Manages organization-specific brand settings for communications.
Settings are stored per-organization in the database with caching.

For platform operations (organization_id="aios-platform"),
uses platform defaults from config as fallback.
"""

from typing import Any, Dict, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
import structlog
import json

from src.core.config import settings as app_settings

logger = structlog.get_logger(__name__)


@dataclass
class BrandSettings:
    """
    Brand settings for an organization.

    These settings control how agents compose communications.
    """
    # Identity
    brand_name: str = "aios"
    tagline: str = "AI-powered workflow automation"

    # Support contact
    support_email: str = "support@fluxtopus.com"
    support_url: str = "https://fluxtopus.com/support"

    # Communication guidelines
    include_phone: bool = False  # Whether to include phone numbers
    phone_number: Optional[str] = None  # Phone if include_phone is True

    # Email settings
    footer_text: str = "Sent by aios - AI-powered workflow automation"
    from_name: str = "aios"

    # Metadata
    organization_id: str = ""
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/serialization."""
        return {
            "brand_name": self.brand_name,
            "tagline": self.tagline,
            "support_email": self.support_email,
            "support_url": self.support_url,
            "include_phone": self.include_phone,
            "phone_number": self.phone_number,
            "footer_text": self.footer_text,
            "from_name": self.from_name,
            "organization_id": self.organization_id,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_prompt_context(self) -> Dict[str, Any]:
        """
        Convert to context dict for prompt templates.

        Returns field names matching template variables.
        """
        return {
            "brand_name": self.brand_name,
            "brand_tagline": self.tagline,
            "brand_support_email": self.support_email,
            "brand_support_url": self.support_url,
            "brand_include_phone": self.include_phone,
            "brand_phone_number": self.phone_number or "",
            "brand_footer_text": self.footer_text,
            "brand_from_name": self.from_name,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BrandSettings":
        """Create from dictionary."""
        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif updated_at is None:
            updated_at = datetime.utcnow()

        return cls(
            brand_name=data.get("brand_name", "aios"),
            tagline=data.get("tagline", "AI-powered workflow automation"),
            support_email=data.get("support_email", "support@fluxtopus.com"),
            support_url=data.get("support_url", "https://fluxtopus.com/support"),
            include_phone=data.get("include_phone", False),
            phone_number=data.get("phone_number"),
            footer_text=data.get("footer_text", "Sent by aios - AI-powered workflow automation"),
            from_name=data.get("from_name", "aios"),
            organization_id=data.get("organization_id", ""),
            updated_at=updated_at,
        )

    @classmethod
    def platform_defaults(cls) -> "BrandSettings":
        """
        Get platform default settings from config.

        Used for platform-level operations (aios-platform org).
        """
        return cls(
            brand_name=app_settings.BRAND_NAME,
            tagline=app_settings.BRAND_TAGLINE,
            support_email=app_settings.BRAND_SUPPORT_EMAIL,
            support_url=app_settings.BRAND_SUPPORT_URL,
            include_phone=app_settings.BRAND_INCLUDE_PHONE,
            phone_number=None,
            footer_text=app_settings.BRAND_FOOTER_TEXT,
            from_name=app_settings.BRAND_NAME,
            organization_id="aios-platform",
        )


class BrandSettingsService:
    """
    Service for managing brand settings.

    Stores settings in Redis with PostgreSQL as source of truth.
    Provides caching for performance.
    """

    CACHE_TTL = timedelta(minutes=15)
    REDIS_KEY_PREFIX = "tentackl:brand_settings"

    def __init__(self, redis_client=None, db_session=None):
        """
        Initialize brand settings service.

        Args:
            redis_client: Redis client for caching (optional)
            db_session: Database session for persistence (optional)
        """
        self._redis = redis_client
        self._db = db_session
        self._local_cache: Dict[str, tuple[BrandSettings, datetime]] = {}

    async def get_settings(self, organization_id: str) -> BrandSettings:
        """
        Get brand settings for an organization.

        Priority:
        1. Local cache (fastest)
        2. Redis cache (fast)
        3. Database (source of truth)
        4. Platform defaults (fallback)

        Args:
            organization_id: Organization ID

        Returns:
            BrandSettings for the organization
        """
        # Platform operations use platform defaults
        if organization_id == "aios-platform":
            return BrandSettings.platform_defaults()

        # Check local cache
        if organization_id in self._local_cache:
            settings, cached_at = self._local_cache[organization_id]
            if datetime.utcnow() - cached_at < self.CACHE_TTL:
                return settings

        # Check Redis cache
        if self._redis:
            try:
                cached = await self._get_from_redis(organization_id)
                if cached:
                    self._local_cache[organization_id] = (cached, datetime.utcnow())
                    return cached
            except Exception as e:
                logger.warning("Redis cache read failed", error=str(e))

        # Check database
        if self._db:
            try:
                db_settings = await self._get_from_db(organization_id)
                if db_settings:
                    await self._cache_settings(organization_id, db_settings)
                    return db_settings
            except Exception as e:
                logger.warning("Database read failed", error=str(e))

        # Fallback to platform defaults
        logger.info(
            "Using platform defaults for organization",
            organization_id=organization_id,
        )
        return BrandSettings.platform_defaults()

    async def save_settings(
        self,
        organization_id: str,
        settings: BrandSettings,
    ) -> bool:
        """
        Save brand settings for an organization.

        Args:
            organization_id: Organization ID
            settings: Brand settings to save

        Returns:
            True if saved successfully
        """
        settings.organization_id = organization_id
        settings.updated_at = datetime.utcnow()

        # Save to database
        if self._db:
            try:
                await self._save_to_db(organization_id, settings)
            except Exception as e:
                logger.error("Failed to save to database", error=str(e))
                return False

        # Update caches
        await self._cache_settings(organization_id, settings)

        logger.info(
            "Brand settings saved",
            organization_id=organization_id,
            brand_name=settings.brand_name,
        )
        return True

    async def _get_from_redis(self, organization_id: str) -> Optional[BrandSettings]:
        """Get settings from Redis cache."""
        key = f"{self.REDIS_KEY_PREFIX}:{organization_id}"
        data = await self._redis.get(key)
        if data:
            return BrandSettings.from_dict(json.loads(data))
        return None

    async def _get_from_db(self, organization_id: str) -> Optional[BrandSettings]:
        """Get settings from database."""
        # TODO: Implement database query
        # For now, return None to use fallback
        return None

    async def _save_to_db(self, organization_id: str, settings: BrandSettings) -> None:
        """Save settings to database."""
        # TODO: Implement database save
        pass

    async def _cache_settings(self, organization_id: str, settings: BrandSettings) -> None:
        """Cache settings in Redis and local cache."""
        self._local_cache[organization_id] = (settings, datetime.utcnow())

        if self._redis:
            try:
                key = f"{self.REDIS_KEY_PREFIX}:{organization_id}"
                await self._redis.setex(
                    key,
                    int(self.CACHE_TTL.total_seconds()),
                    json.dumps(settings.to_dict()),
                )
            except Exception as e:
                logger.warning("Redis cache write failed", error=str(e))

    def clear_cache(self, organization_id: Optional[str] = None) -> None:
        """
        Clear cached settings.

        Args:
            organization_id: Specific org to clear, or None for all
        """
        if organization_id:
            self._local_cache.pop(organization_id, None)
        else:
            self._local_cache.clear()


# Singleton instance
_brand_service: Optional[BrandSettingsService] = None


def get_brand_settings_service() -> BrandSettingsService:
    """Get or create the brand settings service singleton."""
    global _brand_service
    if _brand_service is None:
        _brand_service = BrandSettingsService()
    return _brand_service


async def get_brand_settings(organization_id: str) -> BrandSettings:
    """
    Convenience function to get brand settings.

    Args:
        organization_id: Organization ID

    Returns:
        BrandSettings for the organization
    """
    service = get_brand_settings_service()
    return await service.get_settings(organization_id)
