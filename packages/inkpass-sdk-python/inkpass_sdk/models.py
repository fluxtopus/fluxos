"""Data models for inkPass SDK."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    """Response from login endpoint containing access and refresh tokens."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")


class UserResponse(BaseModel):
    """User information response."""

    id: str = Field(..., description="User ID")
    email: str = Field(..., description="User email")
    first_name: str | None = Field(None, description="User first name")
    last_name: str | None = Field(None, description="User last name")
    organization_id: str = Field(..., description="Organization ID")
    status: str = Field(default="active", description="User status")
    two_fa_enabled: bool = Field(default=False, description="Whether 2FA is enabled")
    created_at: datetime | None = Field(None, description="Creation timestamp")
    updated_at: datetime | None = Field(None, description="Last update timestamp")


class RegistrationResponse(BaseModel):
    """Response from user registration."""

    user_id: str = Field(..., description="Created user ID")
    email: str = Field(..., description="User email")
    organization_id: str = Field(..., description="Created organization ID")


class PermissionCheckResponse(BaseModel):
    """Response from permission check endpoint."""

    has_permission: bool = Field(..., description="Whether user has the permission")
    resource: str | None = Field(None, description="Resource being checked")
    action: str | None = Field(None, description="Action being checked")
    user_id: str | None = Field(None, description="User ID if authenticated")
    organization_id: str | None = Field(None, description="Organization ID if authenticated")


class APIKeyResponse(BaseModel):
    """Response from API key creation."""

    id: str = Field(..., description="API key ID")
    key: str = Field(..., description="The actual API key (only shown once)")
    name: str = Field(..., description="API key name")
    scopes: list[str] = Field(default_factory=list, description="API key scopes")
    created_at: datetime | None = Field(None, description="Creation timestamp")


class APIKeyInfoResponse(BaseModel):
    """Response from /api/v1/auth/me when authenticated with an API key."""

    id: str = Field(..., description="API key ID")
    name: str = Field(..., description="API key name")
    organization_id: str = Field(..., description="Organization ID")
    user_id: str | None = Field(None, description="User ID who created the key")
    scopes: list[str] = Field(default_factory=list, description="API key scopes")
    auth_type: str = Field(default="api_key", description="Authentication type")


class OrganizationResponse(BaseModel):
    """Organization information."""

    id: str = Field(..., description="Organization ID")
    name: str = Field(..., description="Organization name")
    slug: str = Field(..., description="Organization slug")
    settings: dict[str, Any] = Field(default_factory=dict, description="Organization settings")
    created_at: datetime | None = Field(None, description="Creation timestamp")


class GroupResponse(BaseModel):
    """Group information."""

    id: str = Field(..., description="Group ID")
    name: str = Field(..., description="Group name")
    organization_id: str = Field(..., description="Organization ID")
    description: str | None = Field(None, description="Group description")
    created_at: datetime | None = Field(None, description="Creation timestamp")


class PermissionResponse(BaseModel):
    """Permission information."""

    id: str = Field(..., description="Permission ID")
    organization_id: str = Field(..., description="Organization ID")
    resource: str = Field(..., description="Resource name")
    action: str = Field(..., description="Action name")
    conditions: dict[str, Any] = Field(default_factory=dict, description="ABAC conditions")
    created_at: datetime | None = Field(None, description="Creation timestamp")


# === Billing Models ===


class BillingConfigResponse(BaseModel):
    """Response from configuring billing."""

    configured: bool = Field(..., description="Whether configuration was successful")
    organization_id: str = Field(..., description="Organization ID")
    has_webhook_secret: bool = Field(..., description="Whether webhook secret was provided")
    price_ids: list[str] = Field(default_factory=list, description="Configured price keys")


class CheckoutResponse(BaseModel):
    """Response from creating a checkout session."""

    session_id: str = Field(..., description="Stripe checkout session ID")
    url: str = Field(..., description="URL to redirect user for checkout")


class SubscriptionResponse(BaseModel):
    """Subscription status information."""

    status: str = Field(..., description="Subscription status: none, active, past_due, canceled")
    tier: str = Field(..., description="Subscription tier: free, pro, enterprise")
    subscription_id: str | None = Field(None, description="Stripe subscription ID")
    stripe_customer_id: str | None = Field(None, description="Stripe customer ID")
    ends_at: datetime | None = Field(None, description="Subscription end date")
