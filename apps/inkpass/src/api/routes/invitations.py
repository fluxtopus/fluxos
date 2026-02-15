"""Invitation routes for user onboarding"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from typing import Optional, List

from src.database.database import get_db
from src.database.models import Organization
from src.services.invitation_service import InvitationService
from src.services.notification_service import notification_service
from src.middleware.auth_middleware import get_auth_context, AuthContext, require_permission
from src.middleware.rate_limiting import rate_limit

router = APIRouter()

# Rate limits
RATE_LIMIT_CREATE = rate_limit("invitations:create", limit=10, window=60)
RATE_LIMIT_ACCEPT = rate_limit("invitations:accept", limit=5, window=60)
RATE_LIMIT_VALIDATE = rate_limit("invitations:validate", limit=20, window=60)


class CreateInvitationRequest(BaseModel):
    email: EmailStr
    role: str = "member"  # viewer, member, developer, admin


class AcceptInvitationRequest(BaseModel):
    token: str
    password: str


class InvitationResponse(BaseModel):
    id: str
    email: str
    role: str
    status: str
    invited_by_email: Optional[str] = None
    expires_at: str
    created_at: str

    class Config:
        from_attributes = True


class AcceptInvitationResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    user_id: str
    email: str
    organization_id: str
    role: str
    is_new_user: bool


class ValidateTokenResponse(BaseModel):
    valid: bool
    email: Optional[str] = None
    role: Optional[str] = None
    organization_name: Optional[str] = None
    error: Optional[str] = None


@router.post("", status_code=status.HTTP_201_CREATED, response_model=InvitationResponse)
async def create_invitation(
    request: CreateInvitationRequest,
    background_tasks: BackgroundTasks,
    _perm: None = Depends(require_permission("users", "create")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(RATE_LIMIT_CREATE)
):
    """
    Create an invitation to invite a user to the organization.
    Requires users:create permission.
    """
    try:
        invitation, raw_token = InvitationService.create_invitation(
            db=db,
            organization_id=auth_context.user.organization_id,
            email=request.email,
            role=request.role,
            invited_by_user_id=auth_context.user.id
        )

        # Get organization for email
        org = db.query(Organization).filter(
            Organization.id == auth_context.user.organization_id
        ).first()

        # Send invitation email in background
        background_tasks.add_task(
            notification_service.send_invitation_email,
            email=request.email,
            organization_name=org.name if org else "Organization",
            inviter_email=auth_context.user.email,
            token=raw_token,
            role=request.role,
            organization=org
        )

        return InvitationResponse(
            id=invitation.id,
            email=invitation.email,
            role=invitation.role,
            status=invitation.status,
            invited_by_email=auth_context.user.email,
            expires_at=invitation.expires_at.isoformat(),
            created_at=invitation.created_at.isoformat()
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("", response_model=List[InvitationResponse])
async def list_invitations(
    status_filter: Optional[str] = None,
    _perm: None = Depends(require_permission("users", "view")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """
    List invitations for the organization.
    Requires users:view permission.
    """
    invitations = InvitationService.list_organization_invitations(
        db=db,
        organization_id=auth_context.user.organization_id,
        status=status_filter
    )

    return [
        InvitationResponse(
            id=inv.id,
            email=inv.email,
            role=inv.role,
            status=inv.status,
            invited_by_email=inv.invited_by.email if inv.invited_by else None,
            expires_at=inv.expires_at.isoformat(),
            created_at=inv.created_at.isoformat()
        )
        for inv in invitations
    ]


@router.delete("/{invitation_id}")
async def revoke_invitation(
    invitation_id: str,
    _perm: None = Depends(require_permission("users", "manage")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
):
    """
    Revoke a pending invitation.
    Requires users:manage permission.
    """
    try:
        invitation = InvitationService.revoke_invitation(
            db=db,
            invitation_id=invitation_id,
            organization_id=auth_context.user.organization_id
        )

        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitation not found"
            )

        return {"message": "Invitation revoked successfully"}

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{invitation_id}/resend")
async def resend_invitation(
    invitation_id: str,
    background_tasks: BackgroundTasks,
    _perm: None = Depends(require_permission("users", "create")),
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(RATE_LIMIT_CREATE)
):
    """
    Resend an invitation with a new token.
    Requires users:create permission.
    """
    try:
        invitation, raw_token = InvitationService.resend_invitation(
            db=db,
            invitation_id=invitation_id,
            organization_id=auth_context.user.organization_id
        )

        # Get organization for email
        org = db.query(Organization).filter(
            Organization.id == auth_context.user.organization_id
        ).first()

        # Send invitation email in background
        background_tasks.add_task(
            notification_service.send_invitation_email,
            email=invitation.email,
            organization_name=org.name if org else "Organization",
            inviter_email=auth_context.user.email,
            token=raw_token,
            role=invitation.role,
            organization=org
        )

        return {"message": "Invitation resent successfully"}

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# Public endpoints (no auth required)

@router.get("/validate/{token}", response_model=ValidateTokenResponse)
async def validate_invitation_token(
    token: str,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(RATE_LIMIT_VALIDATE)
):
    """
    Validate an invitation token and get invitation details.
    This is a public endpoint - no authentication required.
    """
    invitation = InvitationService.get_invitation_by_token(db, token)

    if not invitation:
        return ValidateTokenResponse(
            valid=False,
            error="Invalid invitation token"
        )

    is_valid, error_msg = InvitationService.validate_invitation(invitation)

    if not is_valid:
        return ValidateTokenResponse(
            valid=False,
            error=error_msg
        )

    # Get organization name
    org = db.query(Organization).filter(
        Organization.id == invitation.organization_id
    ).first()

    return ValidateTokenResponse(
        valid=True,
        email=invitation.email,
        role=invitation.role,
        organization_name=org.name if org else "Organization"
    )


@router.post("/accept", response_model=AcceptInvitationResponse)
async def accept_invitation(
    request: AcceptInvitationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(RATE_LIMIT_ACCEPT)
):
    """
    Accept an invitation and create account.
    This is a public endpoint - no authentication required.
    """
    # Get invitation by token
    invitation = InvitationService.get_invitation_by_token(db, request.token)

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid invitation token"
        )

    try:
        result = InvitationService.accept_invitation(
            db=db,
            invitation=invitation,
            password=request.password
        )

        # Get organization for welcome email
        org = db.query(Organization).filter(
            Organization.id == invitation.organization_id
        ).first()

        # Send welcome email to new user
        if result.get("is_new_user"):
            background_tasks.add_task(
                notification_service.send_welcome_email,
                email=result["email"],
                organization_name=org.name if org else "Organization",
                organization=org
            )

        return AcceptInvitationResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
