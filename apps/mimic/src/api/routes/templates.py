"""Template routes"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Annotated, Optional, List
from src.database.database import get_db
from src.database.models import Template
from src.api.auth import require_permission, AuthContext
import uuid
import re

router = APIRouter()


class TemplateCreate(BaseModel):
    name: str
    content: str
    variables: Optional[List[str]] = None


class TemplateResponse(BaseModel):
    id: str
    name: str
    content: str
    variables: List[str]
    version: int
    created_at: str
    updated_at: str


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    variables: Optional[List[str]] = None


def extract_variables(content: str) -> List[str]:
    """Extract variable names from template content ({{variable}} format)"""
    pattern = r'\{\{(\w+)\}\}'
    variables = re.findall(pattern, content)
    return list(set(variables))  # Remove duplicates


@router.post("/templates", response_model=TemplateResponse)
async def create_template(
    template_data: TemplateCreate,
    auth: Annotated[AuthContext, Depends(require_permission("templates", "create"))],
    db: Session = Depends(get_db)
):
    """Create a template"""
    # Extract variables if not provided
    variables = template_data.variables or extract_variables(template_data.content)

    template = Template(
        id=str(uuid.uuid4()),
        user_id=auth.user_id,
        name=template_data.name,
        content=template_data.content,
        variables=variables,
        version=1
    )
    
    db.add(template)
    db.commit()
    db.refresh(template)
    
    return TemplateResponse(
        id=template.id,
        name=template.name,
        content=template.content,
        variables=template.variables or [],
        version=template.version,
        created_at=template.created_at.isoformat(),
        updated_at=template.updated_at.isoformat()
    )


@router.get("/templates", response_model=List[TemplateResponse])
async def list_templates(
    auth: Annotated[AuthContext, Depends(require_permission("templates", "view"))],
    db: Session = Depends(get_db)
):
    """List all templates for current user"""
    templates = db.query(Template).filter(
        Template.user_id == auth.user_id
    ).all()
    
    return [
        TemplateResponse(
            id=t.id,
            name=t.name,
            content=t.content,
            variables=t.variables or [],
            version=t.version,
            created_at=t.created_at.isoformat(),
            updated_at=t.updated_at.isoformat()
        )
        for t in templates
    ]


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str,
    auth: Annotated[AuthContext, Depends(require_permission("templates", "view"))],
    db: Session = Depends(get_db)
):
    """Get a template by ID"""
    template = db.query(Template).filter(
        Template.id == template_id,
        Template.user_id == auth.user_id
    ).first()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    return TemplateResponse(
        id=template.id,
        name=template.name,
        content=template.content,
        variables=template.variables or [],
        version=template.version,
        created_at=template.created_at.isoformat(),
        updated_at=template.updated_at.isoformat()
    )


@router.put("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: str,
    template_data: TemplateUpdate,
    auth: Annotated[AuthContext, Depends(require_permission("templates", "update"))],
    db: Session = Depends(get_db)
):
    """Update a template (creates new version)"""
    template = db.query(Template).filter(
        Template.id == template_id,
        Template.user_id == auth.user_id
    ).first()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    # Update fields
    if template_data.name:
        template.name = template_data.name
    if template_data.content:
        template.content = template_data.content
        # Re-extract variables if content changed
        template.variables = extract_variables(template.content)
    if template_data.variables:
        template.variables = template_data.variables
    
    # Increment version
    template.version += 1
    
    db.commit()
    db.refresh(template)
    
    return TemplateResponse(
        id=template.id,
        name=template.name,
        content=template.content,
        variables=template.variables or [],
        version=template.version,
        created_at=template.created_at.isoformat(),
        updated_at=template.updated_at.isoformat()
    )


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    auth: Annotated[AuthContext, Depends(require_permission("templates", "delete"))],
    db: Session = Depends(get_db)
):
    """Delete a template"""
    template = db.query(Template).filter(
        Template.id == template_id,
        Template.user_id == auth.user_id
    ).first()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    db.delete(template)
    db.commit()
    
    return {"message": "Template deleted successfully"}

