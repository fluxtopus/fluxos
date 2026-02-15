"""Delivery monitoring routes"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Annotated, Optional, Dict, Any
from src.database.database import get_db
from src.database.models import DeliveryLog, Workflow
from src.api.auth import require_permission, AuthContext
from src.clients.tentackl_client import TentacklClient

router = APIRouter()
tentackl_client = TentacklClient()


class DeliveryStatusResponse(BaseModel):
    workflow_id: str
    run_id: Optional[str]
    status: str
    execution_tree: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


@router.get("/delivery/{workflow_id}")
async def get_delivery_status(
    workflow_id: str,
    auth: Annotated[AuthContext, Depends(require_permission("delivery_logs", "view"))],
    db: Session = Depends(get_db)
):
    """Get delivery status for a workflow execution"""
    # Verify workflow belongs to user
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.user_id == auth.user_id
    ).first()
    
    if not workflow:
        raise HTTPException(
            status_code=404,
            detail="Workflow not found"
        )
    
    # Get latest delivery log for this workflow
    delivery_log = db.query(DeliveryLog).filter(
        DeliveryLog.workflow_id == workflow_id
    ).order_by(DeliveryLog.created_at.desc()).first()
    
    if not delivery_log:
        return DeliveryStatusResponse(
            workflow_id=workflow_id,
            run_id=None,
            status="not_started",
            execution_tree=None,
            error_message=None
        )
    
    # Try to get execution status from Tentackl
    execution_tree = None
    try:
        if delivery_log.delivery_id:
            # Query Tentackl for execution status
            execution_tree = await tentackl_client.get_workflow_status(delivery_log.delivery_id)
    except Exception as e:
        # If Tentackl query fails, return database status
        pass
    
    return DeliveryStatusResponse(
        workflow_id=workflow_id,
        run_id=delivery_log.delivery_id,
        status=delivery_log.status,
        execution_tree=execution_tree,
        error_message=delivery_log.error_message
    )

