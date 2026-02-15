"""File management schemas for Den API request/response validation."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime


class FileBase(BaseModel):
    """Base file schema with common fields."""

    name: str = Field(..., max_length=255, description="Name of the file")
    folder_path: str = Field(default="/", max_length=1024, description="Virtual folder path for organization")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization and search")
    custom_metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom metadata as key-value pairs")
    is_public: bool = Field(default=False, description="Whether file is publicly accessible via CDN")
    is_temporary: bool = Field(default=False, description="Whether file should auto-expire")


class FileCreate(FileBase):
    """Schema for creating a file (metadata only, file content via multipart)."""

    expires_in_hours: Optional[int] = Field(
        None,
        ge=1,
        le=8760,  # Max 1 year
        description="Hours until file expires (for temporary files)"
    )

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Prevent path traversal attacks in file names."""
        if '..' in v or '/' in v or '\\' in v:
            raise ValueError('Invalid file name: cannot contain "..", "/", or "\\"')
        if not v.strip():
            raise ValueError('File name cannot be empty')
        return v.strip()

    @field_validator('folder_path')
    @classmethod
    def validate_folder_path(cls, v: str) -> str:
        """Normalize and validate folder paths."""
        if '..' in v:
            raise ValueError('Invalid folder path: cannot contain ".."')
        # Ensure path starts with /
        if not v.startswith('/'):
            v = '/' + v
        # Remove trailing slash unless it's the root path
        return v.rstrip('/') if len(v) > 1 else v


class FileUpdate(BaseModel):
    """Schema for updating file metadata (partial updates allowed)."""

    name: Optional[str] = Field(None, max_length=255, description="New file name")
    folder_path: Optional[str] = Field(None, max_length=1024, description="New folder path")
    tags: Optional[List[str]] = Field(None, description="Updated tags list")
    custom_metadata: Optional[Dict[str, Any]] = Field(None, description="Updated custom metadata")
    is_public: Optional[bool] = Field(None, description="Update public access status")

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Prevent path traversal attacks in file names."""
        if v is not None:
            if '..' in v or '/' in v or '\\' in v:
                raise ValueError('Invalid file name: cannot contain "..", "/", or "\\"')
            if not v.strip():
                raise ValueError('File name cannot be empty')
            return v.strip()
        return v

    @field_validator('folder_path')
    @classmethod
    def validate_folder_path(cls, v: Optional[str]) -> Optional[str]:
        """Normalize and validate folder paths."""
        if v is not None:
            if '..' in v:
                raise ValueError('Invalid folder path: cannot contain ".."')
            if not v.startswith('/'):
                v = '/' + v
            return v.rstrip('/') if len(v) > 1 else v
        return v


class FileResponse(BaseModel):
    """Schema for file response."""

    id: UUID = Field(..., description="Unique file identifier")
    organization_id: UUID = Field(..., description="Organization that owns this file")
    name: str = Field(..., description="File name")
    storage_key: str = Field(..., description="S3 storage key")
    content_type: str = Field(..., description="MIME type of the file")
    size_bytes: int = Field(..., description="File size in bytes")
    checksum_sha256: Optional[str] = Field(None, description="SHA-256 checksum for integrity verification")
    folder_path: str = Field(..., description="Virtual folder path")
    tags: List[str] = Field(..., description="File tags")
    custom_metadata: Dict[str, Any] = Field(..., description="Custom metadata")
    created_by_user_id: Optional[UUID] = Field(None, description="User who uploaded the file")
    created_by_agent: Optional[str] = Field(None, description="Agent that created the file")
    workflow_id: Optional[str] = Field(None, description="Associated workflow ID")
    status: str = Field(..., description="File status (active, expired, deleted)")
    is_temporary: bool = Field(..., description="Whether file auto-expires")
    is_public: bool = Field(..., description="Whether file is publicly accessible")
    cdn_url: Optional[str] = Field(None, description="Public CDN URL (only for public files)")
    created_at: datetime = Field(..., description="When file was uploaded")
    updated_at: datetime = Field(..., description="When file metadata was last updated")
    expires_at: Optional[datetime] = Field(None, description="When file expires (for temporary files)")

    model_config = {
        "from_attributes": True  # For Pydantic v2 (was orm_mode in v1)
    }


class FileListResponse(BaseModel):
    """Schema for paginated file list response."""

    files: List[FileResponse] = Field(..., description="List of files")
    total: int = Field(..., description="Total number of files matching filters")
    limit: int = Field(..., description="Number of files per page")
    offset: int = Field(..., description="Number of files skipped")


class FileDownloadUrlResponse(BaseModel):
    """Schema for presigned download URL response."""

    url: str = Field(..., description="Presigned S3 URL for downloading the file")
    expires_in: int = Field(..., description="Seconds until URL expires")


class AgentFileCreate(FileBase):
    """Schema for agent file creation (includes workflow context)."""

    workflow_id: str = Field(..., description="Workflow ID for context")
    agent_id: str = Field(..., description="Agent identifier creating the file")
    expires_in_hours: Optional[int] = Field(
        None,
        ge=1,
        le=8760,
        description="Hours until file expires"
    )

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Prevent path traversal attacks in file names."""
        if '..' in v or '/' in v or '\\' in v:
            raise ValueError('Invalid file name: cannot contain "..", "/", or "\\"')
        if not v.strip():
            raise ValueError('File name cannot be empty')
        return v.strip()

    @field_validator('folder_path')
    @classmethod
    def validate_folder_path(cls, v: str) -> str:
        """Normalize and validate folder paths."""
        if '..' in v:
            raise ValueError('Invalid folder path: cannot contain ".."')
        if not v.startswith('/'):
            v = '/' + v
        return v.rstrip('/') if len(v) > 1 else v
