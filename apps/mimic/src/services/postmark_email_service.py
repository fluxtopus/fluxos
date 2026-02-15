"""Postmark email service for production email delivery."""

import httpx
import structlog
from src.config import settings

logger = structlog.get_logger()


class PostmarkEmailService:
    """Email service using Postmark API for production email delivery."""

    def __init__(self):
        self.api_key = settings.POSTMARK_API_KEY
        self.base_url = "https://api.postmarkapp.com"

    @property
    def enabled(self) -> bool:
        """Check if Postmark is configured."""
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
        Send an email via Postmark API.

        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
            from_email: Sender email address (required - set by calling service)
            from_name: Optional sender display name

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning(
                "postmark_not_configured",
                message="POSTMARK_API_KEY not set, email not sent",
                to_email=to_email,
            )
            return False

        if not from_email:
            logger.error(
                "postmark_from_email_required",
                message="from_email is required for Postmark",
            )
            return False

        # Build From field with optional display name
        from_field = f"{from_name} <{from_email}>" if from_name else from_email

        payload = {
            "From": from_field,
            "To": to_email,
            "Subject": subject,
            "TextBody": body,
        }

        if html_body:
            payload["HtmlBody"] = html_body

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/email",
                    headers={
                        "X-Postmark-Server-Token": self.api_key,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json=payload,
                    timeout=10.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info(
                        "postmark_email_sent",
                        to_email=to_email,
                        subject=subject,
                        message_id=data.get("MessageID"),
                    )
                    return True
                else:
                    error_data = response.json() if response.content else {}
                    logger.error(
                        "postmark_email_failed",
                        status_code=response.status_code,
                        error=error_data.get("Message", response.text),
                        error_code=error_data.get("ErrorCode"),
                        to_email=to_email,
                    )
                    return False

        except httpx.TimeoutException:
            logger.error(
                "postmark_timeout",
                to_email=to_email,
                message="Request to Postmark timed out",
            )
            return False
        except Exception as e:
            logger.error(
                "postmark_error",
                error=str(e),
                to_email=to_email,
            )
            return False


# Singleton instance
postmark_email_service = PostmarkEmailService()
