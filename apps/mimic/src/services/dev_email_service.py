"""Development email service using SMTP (Mailtrap, Mailhog, etc.)"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import structlog
from src.config import settings

logger = structlog.get_logger()


class DevEmailService:
    """Simple SMTP email service for development/testing"""

    def __init__(self):
        self.enabled = settings.DEV_SMTP_ENABLED
        self.host = settings.DEV_SMTP_HOST
        self.port = settings.DEV_SMTP_PORT
        self.user = settings.DEV_SMTP_USER
        self.password = settings.DEV_SMTP_PASSWORD
        self.from_email = settings.DEV_SMTP_FROM

    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: str = None,
        from_name: str = None
    ) -> bool:
        """
        Send an email via SMTP.

        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
            from_name: Optional sender display name (e.g., "Tentacle")

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning(
                "dev_email_disabled",
                message="DEV_SMTP_ENABLED is false, email not sent",
                to_email=to_email
            )
            return False

        if not self.host:
            logger.error(
                "dev_email_not_configured",
                message="DEV_SMTP_HOST not set"
            )
            return False

        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            # Use from_name if provided for display name
            if from_name:
                msg["From"] = f"{from_name} <{self.from_email}>"
            else:
                msg["From"] = self.from_email
            msg["To"] = to_email

            # Attach plain text body
            part1 = MIMEText(body, "plain")
            msg.attach(part1)

            # Attach HTML body if provided
            if html_body:
                part2 = MIMEText(html_body, "html")
                msg.attach(part2)

            # Send via SMTP
            with smtplib.SMTP(self.host, self.port) as server:
                # Only use TLS and auth if credentials are provided and not dummy values
                if self.user and self.password and self.user != "test":
                    server.starttls()
                    server.login(self.user, self.password)
                server.sendmail(self.from_email, to_email, msg.as_string())

            logger.info(
                "dev_email_sent",
                to_email=to_email,
                subject=subject,
                smtp_host=self.host
            )
            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error(
                "dev_email_auth_error",
                error=str(e),
                smtp_host=self.host
            )
            return False
        except Exception as e:
            logger.error(
                "dev_email_failed",
                error=str(e),
                to_email=to_email
            )
            return False


# Singleton instance
dev_email_service = DevEmailService()
