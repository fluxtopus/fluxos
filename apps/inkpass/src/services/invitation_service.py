"""Invitation service for user onboarding via email invitations"""

from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import secrets
import hashlib

from src.database.models import Invitation, User, UserOrganization, Organization, RoleTemplate, OrganizationTemplate
from src.security.password import hash_password, validate_password
from sqlalchemy import and_
from src.security.jwt import create_access_token, create_refresh_token
from src.config import settings


# Default invitation expiry in days
INVITATION_EXPIRY_DAYS = 7


def generate_invitation_token() -> str:
    """Generate a secure invitation token"""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Hash a token for storage"""
    return hashlib.sha256(token.encode()).hexdigest()


class InvitationService:
    """Service for managing user invitations"""

    @staticmethod
    def _get_role_template_id(db: Session, organization_id: str, role_name: str) -> Optional[str]:
        """
        Look up the role_template_id for a given role name in an organization.

        Args:
            db: Database session
            organization_id: Organization ID
            role_name: Role name (e.g., "developer", "viewer")

        Returns:
            role_template_id if found, None otherwise
        """
        # Get the organization's permission template
        org_template = db.query(OrganizationTemplate).filter(
            OrganizationTemplate.organization_id == organization_id
        ).first()

        if not org_template:
            return None

        # Find the role template for this role name
        role = db.query(RoleTemplate).filter(
            and_(
                RoleTemplate.template_id == org_template.template_id,
                RoleTemplate.role_name == role_name,
            )
        ).first()

        return role.id if role else None

    @staticmethod
    def create_invitation(
        db: Session,
        organization_id: str,
        email: str,
        role: str,
        invited_by_user_id: str,
        expiry_days: int = INVITATION_EXPIRY_DAYS
    ) -> Tuple[Invitation, str]:
        """
        Create an invitation for a user to join an organization.

        Args:
            db: Database session
            organization_id: Organization to invite user to
            email: Email address to send invitation to
            role: Role to assign when user accepts (viewer, member, developer, admin)
            invited_by_user_id: User ID of person sending invitation
            expiry_days: Days until invitation expires

        Returns:
            Tuple of (Invitation object, raw_token) - raw token is for email link

        Raises:
            ValueError: If email already has pending invitation or is existing user
        """
        # Normalize email
        email = email.lower().strip()

        # Check if user already exists in this organization
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            # Check if user is already in this organization
            user_org = db.query(UserOrganization).filter(
                UserOrganization.user_id == existing_user.id,
                UserOrganization.organization_id == organization_id
            ).first()
            if user_org:
                raise ValueError("User is already a member of this organization")

        # Check for existing pending invitation
        existing_invitation = db.query(Invitation).filter(
            Invitation.organization_id == organization_id,
            Invitation.email == email,
            Invitation.status == "pending"
        ).first()
        if existing_invitation:
            # Check if it's still valid (not expired)
            if existing_invitation.expires_at > datetime.utcnow():
                raise ValueError("An invitation has already been sent to this email")
            # Mark expired invitation
            existing_invitation.status = "expired"
            db.flush()

        # Verify organization exists
        organization = db.query(Organization).filter(
            Organization.id == organization_id
        ).first()
        if not organization:
            raise ValueError("Organization not found")

        # Verify inviter exists and is in the organization
        inviter = db.query(User).filter(User.id == invited_by_user_id).first()
        if not inviter:
            raise ValueError("Inviter user not found")

        # Generate token
        raw_token = generate_invitation_token()
        token_hash = hash_token(raw_token)

        # Create invitation
        invitation = Invitation(
            organization_id=organization_id,
            email=email,
            role=role,
            token_hash=token_hash,
            invited_by_user_id=invited_by_user_id,
            status="pending",
            expires_at=datetime.utcnow() + timedelta(days=expiry_days)
        )
        db.add(invitation)
        db.commit()
        db.refresh(invitation)

        return invitation, raw_token

    @staticmethod
    def get_invitation_by_token(db: Session, token: str) -> Optional[Invitation]:
        """
        Get an invitation by its token.

        Args:
            db: Database session
            token: Raw invitation token

        Returns:
            Invitation if found and valid, None otherwise
        """
        token_hash = hash_token(token)
        invitation = db.query(Invitation).filter(
            Invitation.token_hash == token_hash
        ).first()
        return invitation

    @staticmethod
    def validate_invitation(invitation: Invitation) -> Tuple[bool, str]:
        """
        Validate an invitation is usable.

        Args:
            invitation: Invitation to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if invitation.status == "accepted":
            return False, "Invitation has already been used"
        if invitation.status == "revoked":
            return False, "Invitation has been revoked"
        if invitation.status == "expired" or datetime.utcnow() > invitation.expires_at:
            return False, "Invitation has expired"
        if invitation.status != "pending":
            return False, f"Invalid invitation status: {invitation.status}"
        return True, ""

    @staticmethod
    def accept_invitation(
        db: Session,
        invitation: Invitation,
        password: str
    ) -> Dict[str, Any]:
        """
        Accept an invitation and create user account.

        Args:
            db: Database session
            invitation: Invitation to accept
            password: Password for new account

        Returns:
            Dict with access_token, refresh_token, and user info

        Raises:
            ValueError: If invitation invalid or password requirements not met
        """
        # Validate invitation
        is_valid, error_msg = InvitationService.validate_invitation(invitation)
        if not is_valid:
            raise ValueError(error_msg)

        # Validate password
        validate_password(password)

        # Check if user already exists (edge case: registered after invitation sent)
        existing_user = db.query(User).filter(
            User.email == invitation.email
        ).first()

        if existing_user:
            # User exists - just add them to organization
            existing_org_membership = db.query(UserOrganization).filter(
                UserOrganization.user_id == existing_user.id,
                UserOrganization.organization_id == invitation.organization_id
            ).first()

            if existing_org_membership:
                raise ValueError("User is already a member of this organization")

            # Look up the role_template_id for the invited role
            role_template_id = InvitationService._get_role_template_id(
                db, invitation.organization_id, invitation.role
            )

            # Add to organization
            user_org = UserOrganization(
                user_id=existing_user.id,
                organization_id=invitation.organization_id,
                role=invitation.role,
                role_template_id=role_template_id,
                is_primary=False
            )
            db.add(user_org)

            # Mark invitation as accepted
            invitation.status = "accepted"
            invitation.accepted_at = datetime.utcnow()
            db.commit()

            # Create tokens
            token_data = {
                "sub": existing_user.id,
                "email": existing_user.email,
                "organization_id": invitation.organization_id
            }
            access_token = create_access_token(token_data)
            refresh_token = create_refresh_token(token_data)

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                "user_id": existing_user.id,
                "email": existing_user.email,
                "organization_id": invitation.organization_id,
                "role": invitation.role,
                "is_new_user": False
            }

        # Create new user
        user = User(
            email=invitation.email,
            password_hash=hash_password(password),
            organization_id=invitation.organization_id,
            status="active"  # Skip email verification for invited users
        )
        db.add(user)
        db.flush()

        # Look up the role_template_id for the invited role
        role_template_id = InvitationService._get_role_template_id(
            db, invitation.organization_id, invitation.role
        )

        # Create user-organization relationship
        user_org = UserOrganization(
            user_id=user.id,
            organization_id=invitation.organization_id,
            role=invitation.role,
            role_template_id=role_template_id,
            is_primary=True
        )
        db.add(user_org)

        # Mark invitation as accepted
        invitation.status = "accepted"
        invitation.accepted_at = datetime.utcnow()

        db.commit()
        db.refresh(user)

        # Create tokens
        token_data = {
            "sub": user.id,
            "email": user.email,
            "organization_id": invitation.organization_id
        }
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user_id": user.id,
            "email": user.email,
            "organization_id": invitation.organization_id,
            "role": invitation.role,
            "is_new_user": True
        }

    @staticmethod
    def list_organization_invitations(
        db: Session,
        organization_id: str,
        status: Optional[str] = None
    ) -> List[Invitation]:
        """
        List invitations for an organization.

        Args:
            db: Database session
            organization_id: Organization to list invitations for
            status: Optional status filter (pending, accepted, revoked, expired)

        Returns:
            List of Invitation objects
        """
        query = db.query(Invitation).filter(
            Invitation.organization_id == organization_id
        )
        if status:
            query = query.filter(Invitation.status == status)

        return query.order_by(Invitation.created_at.desc()).all()

    @staticmethod
    def get_invitation_by_id(
        db: Session,
        invitation_id: str
    ) -> Optional[Invitation]:
        """
        Get an invitation by ID.

        Args:
            db: Database session
            invitation_id: Invitation ID

        Returns:
            Invitation if found
        """
        return db.query(Invitation).filter(
            Invitation.id == invitation_id
        ).first()

    @staticmethod
    def revoke_invitation(
        db: Session,
        invitation_id: str,
        organization_id: str
    ) -> Optional[Invitation]:
        """
        Revoke a pending invitation.

        Args:
            db: Database session
            invitation_id: Invitation to revoke
            organization_id: Organization ID (for authorization check)

        Returns:
            Revoked invitation, or None if not found

        Raises:
            ValueError: If invitation cannot be revoked
        """
        invitation = db.query(Invitation).filter(
            Invitation.id == invitation_id,
            Invitation.organization_id == organization_id
        ).first()

        if not invitation:
            return None

        if invitation.status != "pending":
            raise ValueError(f"Cannot revoke invitation with status: {invitation.status}")

        invitation.status = "revoked"
        db.commit()
        db.refresh(invitation)
        return invitation

    @staticmethod
    def resend_invitation(
        db: Session,
        invitation_id: str,
        organization_id: str,
        expiry_days: int = INVITATION_EXPIRY_DAYS
    ) -> Tuple[Invitation, str]:
        """
        Resend an invitation with a new token.

        Args:
            db: Database session
            invitation_id: Invitation to resend
            organization_id: Organization ID (for authorization)
            expiry_days: Days until new invitation expires

        Returns:
            Tuple of (Invitation, new_raw_token)

        Raises:
            ValueError: If invitation not found or cannot be resent
        """
        invitation = db.query(Invitation).filter(
            Invitation.id == invitation_id,
            Invitation.organization_id == organization_id
        ).first()

        if not invitation:
            raise ValueError("Invitation not found")

        if invitation.status == "accepted":
            raise ValueError("Cannot resend accepted invitation")

        # Generate new token
        raw_token = generate_invitation_token()
        token_hash = hash_token(raw_token)

        # Update invitation
        invitation.token_hash = token_hash
        invitation.status = "pending"
        invitation.expires_at = datetime.utcnow() + timedelta(days=expiry_days)

        db.commit()
        db.refresh(invitation)

        return invitation, raw_token

    @staticmethod
    def cleanup_expired_invitations(db: Session) -> int:
        """
        Mark all expired invitations.

        Args:
            db: Database session

        Returns:
            Number of invitations marked as expired
        """
        result = db.query(Invitation).filter(
            Invitation.status == "pending",
            Invitation.expires_at < datetime.utcnow()
        ).update({"status": "expired"})
        db.commit()
        return result
