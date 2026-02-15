"""Delivery logs routes"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Annotated, Optional, List
from datetime import datetime
from src.database.database import get_db
from src.database.models import DeliveryLog
from src.api.auth import require_permission, AuthContext

router = APIRouter()


class DeliveryLogResponse(BaseModel):
    id: str
    delivery_id: str
    workflow_id: Optional[str]
    provider: str
    recipient: str
    status: str
    sent_at: Optional[str]
    completed_at: Optional[str]
    provider_cost: Optional[float]
    error_message: Optional[str]
    created_at: str


@router.get("/logs", response_model=List[DeliveryLogResponse])
async def get_delivery_logs(
    auth: Annotated[AuthContext, Depends(require_permission("delivery_logs", "view"))],
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    provider: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get delivery logs with filtering and pagination"""
    query = db.query(DeliveryLog).filter(
        DeliveryLog.user_id == auth.user_id
    )
    
    # Apply filters
    if provider:
        query = query.filter(DeliveryLog.provider == provider)
    if status:
        query = query.filter(DeliveryLog.status == status)
    
    # Order by created_at descending
    query = query.order_by(DeliveryLog.created_at.desc())
    
    # Apply pagination
    logs = query.offset(offset).limit(limit).all()
    
    return [
        DeliveryLogResponse(
            id=log.id,
            delivery_id=log.delivery_id,
            workflow_id=log.workflow_id,
            provider=log.provider,
            recipient=log.recipient,
            status=log.status,
            sent_at=log.sent_at.isoformat() if log.sent_at else None,
            completed_at=log.completed_at.isoformat() if log.completed_at else None,
            provider_cost=float(log.provider_cost) if log.provider_cost else None,
            error_message=log.error_message,
            created_at=log.created_at.isoformat()
        )
        for log in logs
    ]


@router.get("/logs/{delivery_id}", response_model=DeliveryLogResponse)
async def get_delivery_log(
    delivery_id: str,
    auth: Annotated[AuthContext, Depends(require_permission("delivery_logs", "view"))],
    db: Session = Depends(get_db)
):
    """Get a specific delivery log"""
    log = db.query(DeliveryLog).filter(
        DeliveryLog.delivery_id == delivery_id,
        DeliveryLog.user_id == auth.user_id
    ).first()
    
    if not log:
        raise HTTPException(
            status_code=404,
            detail="Delivery log not found"
        )
    
    return DeliveryLogResponse(
        id=log.id,
        delivery_id=log.delivery_id,
        workflow_id=log.workflow_id,
        provider=log.provider,
        recipient=log.recipient,
        status=log.status,
        sent_at=log.sent_at.isoformat() if log.sent_at else None,
        completed_at=log.completed_at.isoformat() if log.completed_at else None,
        provider_cost=float(log.provider_cost) if log.provider_cost else None,
        error_message=log.error_message,
        created_at=log.created_at.isoformat()
    )

