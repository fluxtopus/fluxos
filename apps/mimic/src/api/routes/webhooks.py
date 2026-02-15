"""Webhook callback routes"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Annotated, Optional
from src.database.database import get_db
from src.database.models import DeliveryLog
from src.api.auth import require_permission, AuthContext
import httpx
import structlog

router = APIRouter()
logger = structlog.get_logger()


class WebhookConfig(BaseModel):
    webhook_url: str


class WebhookCallback(BaseModel):
    delivery_id: str
    status: str
    provider: str
    recipient: str
    error_message: Optional[str] = None


async def send_webhook_callback(webhook_url: str, payload: dict, max_retries: int = 3):
    """Send webhook callback with retry logic"""
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(webhook_url, json=payload)
                if response.status_code < 400:
                    logger.info("Webhook callback sent successfully", webhook_url=webhook_url, attempt=attempt+1)
                    return
                else:
                    logger.warning(
                        "Webhook callback failed",
                        webhook_url=webhook_url,
                        status_code=response.status_code,
                        attempt=attempt+1
                    )
        except Exception as e:
            logger.error(
                "Webhook callback error",
                webhook_url=webhook_url,
                error=str(e),
                attempt=attempt+1
            )
        
        # Exponential backoff
        if attempt < max_retries - 1:
            import asyncio
            await asyncio.sleep(2 ** attempt)


@router.post("/webhooks/config")
async def configure_webhook(
    config: WebhookConfig,
    auth: Annotated[AuthContext, Depends(require_permission("webhooks", "configure"))],
    db: Session = Depends(get_db)
):
    """Configure webhook URL for delivery status callbacks"""
    # Store webhook URL in user metadata or separate table
    # For now, we'll store it in a simple way
    # TODO: Create webhook_configs table if needed
    return {"message": "Webhook configured", "webhook_url": config.webhook_url}


@router.post("/webhooks/callback")
async def receive_webhook_callback(
    callback: WebhookCallback,
    background_tasks: BackgroundTasks,
    auth: Annotated[AuthContext, Depends(require_permission("webhooks", "configure"))],
    db: Session = Depends(get_db)
):
    """Receive webhook callback from Tentackl (internal use)"""
    # Update delivery log
    delivery_log = db.query(DeliveryLog).filter(
        DeliveryLog.delivery_id == callback.delivery_id,
        DeliveryLog.user_id == auth.user_id
    ).first()
    
    if delivery_log:
        delivery_log.status = callback.status
        if callback.error_message:
            delivery_log.error_message = callback.error_message
        db.commit()
    
    # Forward to user's webhook if configured
    # TODO: Get user's webhook URL from database
    # webhook_url = get_user_webhook_url(current_user.id)
    # if webhook_url:
    #     background_tasks.add_task(send_webhook_callback, webhook_url, callback.model_dump())
    
    return {"message": "Callback received"}

