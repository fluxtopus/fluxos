"""Workflow routes"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Annotated, Optional, Dict, Any
from src.database.database import get_db
from src.database.models import Workflow, User
from src.api.auth import require_permission, AuthContext
from src.services.workflow_compiler import WorkflowCompiler
from src.clients.tentackl_client import TentacklClient
from src.middleware.subscription_check import check_subscription
from fastapi import HTTPException, status
import uuid

router = APIRouter()
workflow_compiler = WorkflowCompiler()
tentackl_client = TentacklClient()


class WorkflowCreate(BaseModel):
    name: str
    definition_json: Dict[str, Any]


class WorkflowResponse(BaseModel):
    id: str
    name: str
    definition_json: Dict[str, Any]
    version: int
    is_active: bool
    created_at: str
    updated_at: str


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    definition_json: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class WorkflowTriggerRequest(BaseModel):
    parameters: Optional[Dict[str, Any]] = None


class WorkflowTriggerResponse(BaseModel):
    workflow_id: str
    run_id: str
    status: str


@router.post("/workflows", response_model=WorkflowResponse)
async def create_workflow(
    workflow_data: WorkflowCreate,
    auth: Annotated[AuthContext, Depends(require_permission("workflows", "create"))],
    db: Session = Depends(get_db)
):
    """Create a workflow - requires annual subscription for advanced features"""
    # Get user for subscription check (business logic)
    user = db.query(User).filter(User.id == auth.user_id).first()

    # Check subscription for workflow designer (free tier has limited workflows)
    if user and user.subscription_tier != "annual":
        # Count existing workflows for free tier limit
        existing_count = db.query(Workflow).filter(
            Workflow.user_id == auth.user_id
        ).count()

        if existing_count >= 3:  # Free tier limit: 3 workflows
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Free tier limited to 3 workflows. Upgrade to annual subscription for unlimited workflows."
            )
    workflow = Workflow(
        id=str(uuid.uuid4()),
        user_id=auth.user_id,
        name=workflow_data.name,
        definition_json=workflow_data.definition_json,
        version=1,
        is_active=True
    )
    
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    
    return WorkflowResponse(
        id=workflow.id,
        name=workflow.name,
        definition_json=workflow.definition_json,
        version=workflow.version,
        is_active=workflow.is_active,
        created_at=workflow.created_at.isoformat(),
        updated_at=workflow.updated_at.isoformat()
    )


@router.get("/workflows", response_model=list[WorkflowResponse])
async def list_workflows(
    auth: Annotated[AuthContext, Depends(require_permission("workflows", "view"))],
    db: Session = Depends(get_db)
):
    """List all workflows for current user"""
    workflows = db.query(Workflow).filter(
        Workflow.user_id == auth.user_id
    ).all()
    
    return [
        WorkflowResponse(
            id=w.id,
            name=w.name,
            definition_json=w.definition_json,
            version=w.version,
            is_active=w.is_active,
            created_at=w.created_at.isoformat(),
            updated_at=w.updated_at.isoformat()
        )
        for w in workflows
    ]


@router.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: str,
    auth: Annotated[AuthContext, Depends(require_permission("workflows", "view"))],
    db: Session = Depends(get_db)
):
    """Get a workflow by ID"""
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.user_id == auth.user_id
    ).first()
    
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )
    
    return WorkflowResponse(
        id=workflow.id,
        name=workflow.name,
        definition_json=workflow.definition_json,
        version=workflow.version,
        is_active=workflow.is_active,
        created_at=workflow.created_at.isoformat(),
        updated_at=workflow.updated_at.isoformat()
    )


@router.put("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: str,
    workflow_data: WorkflowUpdate,
    auth: Annotated[AuthContext, Depends(require_permission("workflows", "update"))],
    db: Session = Depends(get_db)
):
    """Update a workflow"""
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.user_id == auth.user_id
    ).first()
    
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )
    
    # Update fields
    if workflow_data.name:
        workflow.name = workflow_data.name
    if workflow_data.definition_json:
        workflow.definition_json = workflow_data.definition_json
        workflow.version += 1
    if workflow_data.is_active is not None:
        workflow.is_active = workflow_data.is_active
    
    db.commit()
    db.refresh(workflow)
    
    return WorkflowResponse(
        id=workflow.id,
        name=workflow.name,
        definition_json=workflow.definition_json,
        version=workflow.version,
        is_active=workflow.is_active,
        created_at=workflow.created_at.isoformat(),
        updated_at=workflow.updated_at.isoformat()
    )


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    auth: Annotated[AuthContext, Depends(require_permission("workflows", "delete"))],
    db: Session = Depends(get_db)
):
    """Delete a workflow"""
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.user_id == auth.user_id
    ).first()
    
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )
    
    db.delete(workflow)
    db.commit()
    
    return {"message": "Workflow deleted successfully"}


@router.post("/workflows/{workflow_id}/trigger", response_model=WorkflowTriggerResponse)
async def trigger_workflow(
    workflow_id: str,
    trigger_data: WorkflowTriggerRequest,
    auth: Annotated[AuthContext, Depends(require_permission("workflows", "trigger"))],
    db: Session = Depends(get_db)
):
    """Trigger a workflow execution"""
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.user_id == auth.user_id
    ).first()
    
    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )
    
    if not workflow.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workflow is not active"
        )
    
    # Compile workflow to Tentackl spec
    tentackl_spec = workflow_compiler.compile(workflow.definition_json)
    
    # Trigger workflow in Tentackl
    try:
        run_id = await tentackl_client.trigger_workflow(
            user_id=auth.user_id,
            workflow_spec=tentackl_spec,
            parameters=trigger_data.parameters or {}
        )
        
        return WorkflowTriggerResponse(
            workflow_id=workflow_id,
            run_id=run_id,
            status="triggered"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger workflow: {str(e)}"
        )

