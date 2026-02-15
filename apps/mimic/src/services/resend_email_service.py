"""Resend email service for production email delivery."""

import httpx
import structlog
from src.config import settings

logger = structlog.get_logger()


class ResendEmailService:
    """Email service using Resend API for production email delivery."""

    def __init__(self):
        self.api_key = settings.RESEND_API_KEY
        self.base_url = "https://api.resend.com"

    @property
    def enabled(self) -> bool:
        """Check if Resend is configured."""
        return bool(self.api_key)

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: str = None,
        from_email: str = None,
        from_name: str = None,
    ) -> bool:
        """
        Send an email via Resend API.

        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
            from_email: Sender email address (required)
            from_name: Optional sender display name

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning(
                "resend_not_configured",
                message="RESEND_API_KEY not set, email not sent",
                to_email=to_email,
            )
            return False

        if not from_email:
            logger.error(
                "resend_from_email_required",
                message="from_email is required for Resend",
            )
            return False

        # Build From field with optional display name
        from_field = f"{from_name} <{from_email}>" if from_name else from_email

        payload = {
            "from": from_field,
            "to": [to_email],
            "subject": subject,
            "text": body,
        }

        if html_body:
            payload["html"] = html_body

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/emails",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=10.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info(
                        "resend_email_sent",
                        to_email=to_email,
                        subject=subject,
                        message_id=data.get("id"),
                    )
                    return True
                else:
                    error_data = response.json() if response.content else {}
                    logger.error(
                        "resend_email_failed",
                        status_code=response.status_code,
                        error=error_data.get("message", response.text),
                        to_email=to_email,
                    )
                    return False

        except httpx.TimeoutException:
            logger.error(
                "resend_timeout",
                to_email=to_email,
                message="Request to Resend timed out",
            )
            return False
        except Exception as e:
            logger.error(
                "resend_error",
                error=str(e),
                to_email=to_email,
            )
            return False


# Singleton instance
resend_email_service = ResendEmailService()
