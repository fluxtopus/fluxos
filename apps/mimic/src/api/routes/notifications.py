"""Notification routes"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Annotated, Optional
from src.database.database import get_db
from src.database.models import DeliveryLog
from src.api.auth import require_permission, AuthContext
from src.clients.tentackl_client import TentacklClient
from src.services.dev_email_service import dev_email_service
from src.services.postmark_email_service import postmark_email_service
from src.services.resend_email_service import resend_email_service
from src.config import settings
import uuid
from datetime import datetime
import structlog

logger = structlog.get_logger()
router = APIRouter()


class SendNotificationRequest(BaseModel):
    recipient: str
    content: str
    provider: str  # email, sms, slack, discord, telegram, webhook
    template_id: Optional[str] = None
    metadata: Optional[dict] = None


class SendNotificationResponse(BaseModel):
    delivery_id: str
    status: str
    message: str


class DeliveryStatusResponse(BaseModel):
    delivery_id: str
    status: str
    provider: str
    recipient: str
    sent_at: Optional[str]
    completed_at: Optional[str]
    error_message: Optional[str]


@router.post("/send", response_model=SendNotificationResponse)
async def send_notification(
    request: SendNotificationRequest,
    auth: Annotated[AuthContext, Depends(require_permission("notifications", "send"))],
    db: Session = Depends(get_db)
):
    """Send a notification"""
    # Generate delivery ID
    delivery_id = str(uuid.uuid4())

    # Create delivery log (skip for service/jwt auth - external users not in Mimic's users table)
    # Delivery logs only work for Mimic's local users (api_key auth)
    delivery_log = None
    if auth.auth_type == "api_key":
        delivery_log = DeliveryLog(
            id=str(uuid.uuid4()),
            user_id=auth.user_id,
            delivery_id=delivery_id,
            provider=request.provider,
            recipient=request.recipient,
            status="pending",
            sent_at=datetime.utcnow()
        )
        db.add(delivery_log)
        db.commit()

    # Extract common email parameters from metadata
    metadata = request.metadata or {}
    subject = metadata.get("subject", "Notification")
    from_name = metadata.get("from_name")
    from_email = metadata.get("from_email")  # Caller provides their sender address
    html_body = metadata.get("html_body")

    # Route email based on EMAIL_PROVIDER setting
    if request.provider == "email":
        email_provider = settings.EMAIL_PROVIDER.lower()

        # Dev SMTP (for local development/testing)
        if email_provider == "dev" and settings.DEV_SMTP_ENABLED:
            try:
                success = dev_email_service.send_email(
                    to_email=request.recipient,
                    subject=subject,
                    body=request.content,
                    html_body=html_body,
                    from_name=from_name
                )

                if success:
                    if delivery_log:
                        delivery_log.status = "sent"
                        delivery_log.completed_at = datetime.utcnow()
                        db.commit()

                    logger.info(
                        "notification_sent_dev_smtp",
                        delivery_id=delivery_id,
                        recipient=request.recipient,
                        subject=subject
                    )

                    return SendNotificationResponse(
                        delivery_id=delivery_id,
                        status="sent",
                        message="Notification sent via dev SMTP"
                    )
                else:
                    raise Exception("Dev SMTP send failed")
            except Exception as e:
                if delivery_log:
                    delivery_log.status = "failed"
                    delivery_log.error_message = str(e)
                    delivery_log.completed_at = datetime.utcnow()
                    db.commit()

                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to send notification via dev SMTP: {str(e)}"
                )

        # Postmark (production email)
        elif email_provider == "postmark":
            if not from_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="from_email is required in metadata for Postmark"
                )

            try:
                success = await postmark_email_service.send_email(
                    to_email=request.recipient,
                    subject=subject,
                    body=request.content,
                    html_body=html_body,
                    from_email=from_email,
                    from_name=from_name
                )

                if success:
                    if delivery_log:
                        delivery_log.status = "sent"
                        delivery_log.completed_at = datetime.utcnow()
                        db.commit()

                    logger.info(
                        "notification_sent_postmark",
                        delivery_id=delivery_id,
                        recipient=request.recipient,
                        subject=subject,
                        from_email=from_email
                    )

                    return SendNotificationResponse(
                        delivery_id=delivery_id,
                        status="sent",
                        message="Notification sent via Postmark"
                    )
                else:
                    raise Exception("Postmark send failed")
            except HTTPException:
                raise
            except Exception as e:
                if delivery_log:
                    delivery_log.status = "failed"
                    delivery_log.error_message = str(e)
                    delivery_log.completed_at = datetime.utcnow()
                    db.commit()

                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to send notification via Postmark: {str(e)}"
                )

        # Resend (production email)
        elif email_provider == "resend":
            if not from_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="from_email is required in metadata for Resend"
                )

            try:
                success = await resend_email_service.send_email(
                    to_email=request.recipient,
                    subject=subject,
                    body=request.content,
                    html_body=html_body,
                    from_email=from_email,
                    from_name=from_name
                )

                if success:
                    if delivery_log:
                        delivery_log.status = "sent"
                        delivery_log.completed_at = datetime.utcnow()
                        db.commit()

                    logger.info(
                        "notification_sent_resend",
                        delivery_id=delivery_id,
                        recipient=request.recipient,
                        subject=subject,
                        from_email=from_email
                    )

                    return SendNotificationResponse(
                        delivery_id=delivery_id,
                        status="sent",
                        message="Notification sent via Resend"
                    )
                else:
                    raise Exception("Resend send failed")
            except HTTPException:
                raise
            except Exception as e:
                if delivery_log:
                    delivery_log.status = "failed"
                    delivery_log.error_message = str(e)
                    delivery_log.completed_at = datetime.utcnow()
                    db.commit()

                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to send notification via Resend: {str(e)}"
                )

    # Default/Tentackl path: Send via Tentackl workflow (for non-email or EMAIL_PROVIDER=tentackl)
    try:
        tentackl_client = TentacklClient()
        await tentackl_client.send_notification(
            user_id=auth.user_id,
            recipient=request.recipient,
            content=request.content,
            provider=request.provider,
            template_id=request.template_id,
            metadata=request.metadata or {}
        )

        # Update delivery log
        if delivery_log:
            delivery_log.status = "sent"
            delivery_log.completed_at = datetime.utcnow()
            db.commit()

        return SendNotificationResponse(
            delivery_id=delivery_id,
            status="sent",
            message="Notification sent successfully"
        )
    except Exception as e:
        # Update delivery log with error
        if delivery_log:
            delivery_log.status = "failed"
            delivery_log.error_message = str(e)
            delivery_log.completed_at = datetime.utcnow()
            db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send notification: {str(e)}"
        )


@router.get("/status/{delivery_id}", response_model=DeliveryStatusResponse)
async def get_delivery_status(
    delivery_id: str,
    auth: Annotated[AuthContext, Depends(require_permission("notifications", "view"))],
    db: Session = Depends(get_db)
):
    """Get delivery status"""
    delivery_log = db.query(DeliveryLog).filter(
        DeliveryLog.delivery_id == delivery_id,
        DeliveryLog.user_id == auth.user_id
    ).first()
    
    if not delivery_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delivery not found"
        )
    
    return DeliveryStatusResponse(
        delivery_id=delivery_log.delivery_id,
        status=delivery_log.status,
        provider=delivery_log.provider,
        recipient=delivery_log.recipient,
        sent_at=delivery_log.sent_at.isoformat() if delivery_log.sent_at else None,
        completed_at=delivery_log.completed_at.isoformat() if delivery_log.completed_at else None,
        error_message=delivery_log.error_message
    )


class SendTemplateRequest(BaseModel):
    """Request to send notification using a system template."""
    recipient: str
    template_name: str  # e.g., "invitation", "welcome", "password_reset"
    variables: dict  # Template variables for substitution
    metadata: Optional[dict] = None


@router.post("/send-template", response_model=SendNotificationResponse)
async def send_with_template(
    request: SendTemplateRequest,
    auth: Annotated[AuthContext, Depends(require_permission("notifications", "send"))],
    db: Session = Depends(get_db)
):
    """
    Send a notification using a system template.

    Templates are resolved in order:
    1. Organization-specific template
    2. Platform-wide template (fallback)

    Variables in the template ({{variable_name}}) are substituted with
    the provided values.
    """
    from src.services.template_service import TemplateService, TemplateNotFoundError

    # Get template service
    template_service = TemplateService(db)

    # Look up template
    try:
        template = template_service.get_template(
            name=request.template_name,
            organization_id=auth.organization_id,
        )
    except TemplateNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    # Render template with variables
    rendered_subject, rendered_text, rendered_html = template_service.render_template(
        template=template,
        variables=request.variables,
    )

    # Generate delivery ID
    delivery_id = str(uuid.uuid4())

    # Create delivery log (skip for service/jwt auth - external users not in Mimic's users table)
    # Delivery logs only work for Mimic's local users (api_key auth)
    delivery_log = None
    if auth.auth_type == "api_key":
        delivery_log = DeliveryLog(
            id=str(uuid.uuid4()),
            user_id=auth.user_id,
            delivery_id=delivery_id,
            provider="email",
            recipient=request.recipient,
            status="pending",
            sent_at=datetime.utcnow()
        )
        db.add(delivery_log)
        db.commit()

    # Build metadata with template info
    metadata = request.metadata or {}
    metadata["template_name"] = request.template_name
    metadata["template_id"] = template.id
    from_email = metadata.get("from_email", settings.EMAIL_FROM if hasattr(settings, 'EMAIL_FROM') else None)
    from_name = metadata.get("from_name")

    # Route email based on provider
    email_provider = settings.EMAIL_PROVIDER.lower()

    try:
        if email_provider == "dev" and settings.DEV_SMTP_ENABLED:
            success = dev_email_service.send_email(
                to_email=request.recipient,
                subject=rendered_subject,
                body=rendered_text,
                from_name=from_name
            )
        elif email_provider == "postmark":
            if not from_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="from_email is required in metadata for Postmark"
                )
            success = await postmark_email_service.send_email(
                to_email=request.recipient,
                subject=rendered_subject,
                body=rendered_text,
                html_body=rendered_html,
                from_email=from_email,
                from_name=from_name
            )
        elif email_provider == "resend":
            if not from_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="from_email is required in metadata for Resend"
                )
            success = await resend_email_service.send_email(
                to_email=request.recipient,
                subject=rendered_subject,
                body=rendered_text,
                html_body=rendered_html,
                from_email=from_email,
                from_name=from_name
            )
        else:
            # Fallback to dev SMTP or raise error
            if settings.DEV_SMTP_ENABLED:
                success = dev_email_service.send_email(
                    to_email=request.recipient,
                    subject=rendered_subject,
                    body=rendered_text,
                    from_name=from_name
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"No email provider configured: {email_provider}"
                )

        if success:
            if delivery_log:
                delivery_log.status = "sent"
                delivery_log.completed_at = datetime.utcnow()
                db.commit()

            logger.info(
                "template_notification_sent",
                delivery_id=delivery_id,
                recipient=request.recipient,
                template_name=request.template_name,
                provider=email_provider,
            )

            return SendNotificationResponse(
                delivery_id=delivery_id,
                status="sent",
                message=f"Notification sent via template '{request.template_name}'"
            )
        else:
            raise Exception("Email send returned failure")

    except HTTPException:
        raise
    except Exception as e:
        if delivery_log:
            delivery_log.status = "failed"
            delivery_log.error_message = str(e)
            delivery_log.completed_at = datetime.utcnow()
            db.commit()

        logger.error(
            "template_notification_failed",
            delivery_id=delivery_id,
            recipient=request.recipient,
            template_name=request.template_name,
            error=str(e),
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send template notification: {str(e)}"
        )

