"""Notification settings schemas for organization branding configuration"""

from pydantic import BaseModel, EmailStr
from typing import Optional


class NotificationSettingsUpdate(BaseModel):
    """Request body for updating organization notification settings (partial update)"""
    brand_name: Optional[str] = None
    from_name: Optional[str] = None
    subject_prefix: Optional[str] = None
    support_email: Optional[EmailStr] = None
    footer_text: Optional[str] = None


class NotificationSettingsResponse(BaseModel):
    """Response schema for notification settings (includes defaults)"""
    brand_name: str
    from_name: str
    subject_prefix: str
    support_email: Optional[str]
    footer_text: str
