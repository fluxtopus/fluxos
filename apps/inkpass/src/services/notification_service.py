"""Notification service for sending emails via Mimic SDK with organization branding"""

import structlog
from typing import Optional, Dict, Any

from src.config import settings

logger = structlog.get_logger()

# Default notification settings when organization has no custom configuration
DEFAULT_NOTIFICATION_SETTINGS = {
    "brand_name": "aios",
    "from_name": "aios",
    "from_email": None,  # Falls back to settings.EMAIL_FROM if not set
    "subject_prefix": "",
    "support_email": None,
    "footer_text": "Powered by aios"
}


class NotificationService:
    """Service for sending notifications via Mimic SDK with organization branding"""

    def __init__(self):
        self.base_url = settings.MIMIC_URL.rstrip('/')
        self.api_key = settings.MIMIC_API_KEY
        self.enabled = bool(self.api_key)
        self._client = None

    def _get_client(self):
        """Lazy initialization of Mimic client"""
        if self._client is None and self.enabled:
            from mimic import MimicClient
            self._client = MimicClient(
                api_key=self.api_key,
                base_url=self.base_url
            )
        return self._client

    @staticmethod
    def get_notification_settings(organization: Optional[Any]) -> Dict[str, Any]:
        """
        Extract notification settings from organization with defaults.

        Args:
            organization: Organization model instance or None

        Returns:
            Notification settings dict with defaults applied
        """
        if not organization or not organization.settings:
            return DEFAULT_NOTIFICATION_SETTINGS.copy()

        org_notification = organization.settings.get("notification", {})

        # Merge with defaults - org settings override defaults
        return {
            key: org_notification.get(key, default)
            for key, default in DEFAULT_NOTIFICATION_SETTINGS.items()
        }

    async def _send_template(
        self,
        recipient: str,
        template_name: str,
        variables: Dict[str, Any],
        email_type: str,
        notification_settings: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Send notification using Mimic's template system.

        Args:
            recipient: Email address of the recipient
            template_name: System template name (e.g., "invitation", "welcome")
            variables: Template variables for substitution
            email_type: Email type for logging
            notification_settings: Org notification settings (includes from_email, from_name)

        Returns:
            Delivery response with delivery_id and status, or None if disabled
        """
        if not self.enabled:
            logger.warning(
                "notification_skipped",
                reason="mimic_not_configured",
                recipient=recipient,
                template=template_name
            )
            return None

        client = self._get_client()
        if not client:
            return None

        # Use org's from_email if configured, otherwise fall back to global setting
        ns = notification_settings or {}
        from_email = ns.get("from_email") or settings.EMAIL_FROM
        from_name = ns.get("from_name")

        try:
            result = await client.send_template(
                recipient=recipient,
                template_name=template_name,
                variables=variables,
                metadata={
                    "from_email": from_email,
                    "from_name": from_name,
                    "type": email_type,
                }
            )

            logger.info(
                "notification_sent",
                delivery_id=result.get("delivery_id"),
                recipient=recipient,
                template=template_name,
                from_email=from_email,
                status=result.get("status")
            )

            return result

        except Exception as e:
            logger.error(
                "notification_failed",
                recipient=recipient,
                template=template_name,
                error=str(e)
            )
            return None

    async def send_email(
        self,
        recipient: str,
        content: str,
        subject: str,
        from_name: str,
        template_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Send a raw email notification via Mimic SDK (non-template).

        For transactional emails, prefer using the specialized methods
        (send_welcome_email, send_invitation_email, etc.) which use templates.

        Args:
            recipient: Email address of the recipient
            content: Email content
            subject: Email subject line
            from_name: Sender display name
            template_id: Optional Mimic template ID
            metadata: Optional additional metadata for tracking

        Returns:
            Delivery response with delivery_id and status, or None if disabled
        """
        if not self.enabled:
            logger.warning(
                "notification_skipped",
                reason="mimic_not_configured",
                recipient=recipient
            )
            return None

        client = self._get_client()
        if not client:
            return None

        # Include from_email in metadata for email providers
        email_metadata = metadata.copy() if metadata else {}
        email_metadata["from_email"] = settings.EMAIL_FROM

        try:
            result = await client.send_notification(
                recipient=recipient,
                content=content,
                provider="email",
                template_id=template_id,
                subject=subject,
                from_name=from_name,
                metadata=email_metadata
            )

            logger.info(
                "notification_sent",
                delivery_id=result.get("delivery_id"),
                recipient=recipient,
                subject=subject,
                status=result.get("status")
            )

            return result

        except Exception as e:
            logger.error(
                "notification_failed",
                recipient=recipient,
                error=str(e)
            )
            return None

    async def send_welcome_email(
        self,
        email: str,
        organization_name: str,
        organization: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """Send welcome email to newly registered user"""
        ns = self.get_notification_settings(organization)

        return await self._send_template(
            recipient=email,
            template_name="welcome",
            variables={
                "organization_name": organization_name,
                "email": email,
                "brand_name": ns["brand_name"],
                "footer_text": ns["footer_text"],
            },
            email_type="welcome",
            notification_settings=ns,
        )

    async def send_password_reset_email(
        self,
        email: str,
        otp_code: str,
        expires_minutes: int = 10,
        organization: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """Send password reset OTP email"""
        ns = self.get_notification_settings(organization)

        return await self._send_template(
            recipient=email,
            template_name="password_reset",
            variables={
                "otp_code": otp_code,
                "expires_minutes": str(expires_minutes),
                "brand_name": ns["brand_name"],
                "footer_text": ns["footer_text"],
            },
            email_type="password_reset",
            notification_settings=ns,
        )

    async def send_password_changed_email(
        self,
        email: str,
        organization: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """Send confirmation email when password is changed"""
        ns = self.get_notification_settings(organization)

        return await self._send_template(
            recipient=email,
            template_name="password_changed",
            variables={
                "brand_name": ns["brand_name"],
                "footer_text": ns["footer_text"],
            },
            email_type="password_changed",
            notification_settings=ns,
        )

    async def send_2fa_enabled_email(
        self,
        email: str,
        organization: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """Send confirmation email when 2FA is enabled"""
        ns = self.get_notification_settings(organization)

        return await self._send_template(
            recipient=email,
            template_name="2fa_enabled",
            variables={
                "brand_name": ns["brand_name"],
                "footer_text": ns["footer_text"],
            },
            email_type="2fa_enabled",
            notification_settings=ns,
        )

    async def send_2fa_disabled_email(
        self,
        email: str,
        organization: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """Send confirmation email when 2FA is disabled"""
        ns = self.get_notification_settings(organization)

        return await self._send_template(
            recipient=email,
            template_name="2fa_disabled",
            variables={
                "brand_name": ns["brand_name"],
                "footer_text": ns["footer_text"],
            },
            email_type="2fa_disabled",
            notification_settings=ns,
        )

    async def send_login_alert_email(
        self,
        email: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        organization: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """Send alert email for new login"""
        ns = self.get_notification_settings(organization)

        return await self._send_template(
            recipient=email,
            template_name="login_alert",
            variables={
                "ip_address": ip_address or "Unknown",
                "user_agent": user_agent or "Unknown",
                "brand_name": ns["brand_name"],
                "footer_text": ns["footer_text"],
            },
            email_type="login_alert",
            notification_settings=ns,
        )

    async def send_email_verification(
        self,
        email: str,
        otp_code: str,
        expires_minutes: int = 30,
        organization: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """Send email verification code to newly registered user"""
        ns = self.get_notification_settings(organization)

        return await self._send_template(
            recipient=email,
            template_name="email_verification",
            variables={
                "otp_code": otp_code,
                "expires_minutes": str(expires_minutes),
                "brand_name": ns["brand_name"],
                "footer_text": ns["footer_text"],
            },
            email_type="email_verification",
            notification_settings=ns,
        )

    async def send_email_change_verification(
        self,
        new_email: str,
        otp_code: str,
        expires_minutes: int = 30,
        organization: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """Send email change verification code to new email address"""
        ns = self.get_notification_settings(organization)

        return await self._send_template(
            recipient=new_email,
            template_name="email_verification",
            variables={
                "otp_code": otp_code,
                "expires_minutes": str(expires_minutes),
                "brand_name": ns["brand_name"],
                "footer_text": ns["footer_text"],
            },
            email_type="email_change_verification",
            notification_settings=ns,
        )

    async def send_invitation_email(
        self,
        email: str,
        organization_name: str,
        inviter_email: str,
        token: str,
        role: str,
        organization: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """Send invitation email to join organization"""
        ns = self.get_notification_settings(organization)

        # Build invitation URL from config
        invite_url = f"{settings.FRONTEND_URL}/invite/accept?token={token}"

        return await self._send_template(
            recipient=email,
            template_name="invitation",
            variables={
                "inviter_email": inviter_email,
                "organization_name": organization_name,
                "invite_url": invite_url,
                "role": role,
                "brand_name": ns["brand_name"],
                "footer_text": ns["footer_text"],
            },
            email_type="invitation",
            notification_settings=ns,
        )


# Singleton instance for easy import
notification_service = NotificationService()
