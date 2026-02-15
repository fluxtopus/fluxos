"""
Template Versioning Interface

This module defines the abstract interface for template version control,
providing contracts for storing, retrieving, and managing template versions
with full traceability and approval workflows.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import uuid


class ApprovalStatus(Enum):
    """Template approval status"""
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


class ChangeType(Enum):
    """Type of template change"""
    CREATED = "created"
    MODIFIED = "modified"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


@dataclass
class TemplateDiff:
    """Represents a diff between template versions"""
    field: str
    old_value: Any
    new_value: Any
    change_type: str  # added, modified, removed


@dataclass
class TemplateChange:
    """Represents a change to a template"""
    timestamp: datetime
    author_id: str
    author_type: str  # "agent" or "human"
    change_type: ChangeType
    diff: List[TemplateDiff]
    rationale: str
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class TemplateApproval:
    """Represents an approval action on a template"""
    status: ApprovalStatus
    approver_id: str
    timestamp: datetime
    comments: Optional[str] = None
    conditions: Optional[Dict[str, Any]] = None


@dataclass
class TemplateVersion:
    """Represents a versioned template"""
    id: str
    template_id: str
    version: str  # Semantic version string
    parent_version_id: Optional[str]
    content: Dict[str, Any]
    changes: List[TemplateChange]
    approval: Optional[TemplateApproval]
    created_at: datetime
    updated_at: datetime
    metadata: Optional[Dict[str, Any]] = None
    
    @property
    def is_approved(self) -> bool:
        """Check if template is approved"""
        return self.approval and self.approval.status == ApprovalStatus.APPROVED


class TemplateVersioningInterface(ABC):
    """
    Abstract interface for template version control
    
    This interface provides methods for managing template versions,
    tracking changes, and handling approval workflows.
    """
    
    @abstractmethod
    async def create_template(
        self,
        template_id: str,
        content: Dict[str, Any],
        author_id: str,
        author_type: str = "human",
        rationale: str = "Initial creation",
        metadata: Optional[Dict[str, Any]] = None
    ) -> TemplateVersion:
        """
        Create a new template with initial version
        
        Args:
            template_id: Unique identifier for the template
            content: Template content as dictionary
            author_id: ID of the author (human or agent)
            author_type: Type of author ("human" or "agent")
            rationale: Reason for creating the template
            metadata: Optional metadata
            
        Returns:
            Created template version
        """
        pass
    
    @abstractmethod
    async def create_version(
        self,
        template_id: str,
        content: Dict[str, Any],
        author_id: str,
        author_type: str = "human",
        rationale: str = "",
        parent_version_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> TemplateVersion:
        """
        Create a new version of an existing template
        
        Args:
            template_id: Template identifier
            content: New template content
            author_id: ID of the author
            author_type: Type of author
            rationale: Reason for the change
            parent_version_id: Parent version ID (uses latest if None)
            metadata: Optional metadata
            
        Returns:
            New template version
        """
        pass
    
    @abstractmethod
    async def get_version(
        self,
        version_id: str
    ) -> Optional[TemplateVersion]:
        """
        Get a specific template version
        
        Args:
            version_id: Version identifier
            
        Returns:
            Template version if found
        """
        pass
    
    @abstractmethod
    async def get_latest_version(
        self,
        template_id: str,
        approved_only: bool = True
    ) -> Optional[TemplateVersion]:
        """
        Get the latest version of a template
        
        Args:
            template_id: Template identifier
            approved_only: Only return approved versions
            
        Returns:
            Latest template version if found
        """
        pass
    
    @abstractmethod
    async def get_version_history(
        self,
        template_id: str,
        limit: Optional[int] = None
    ) -> List[TemplateVersion]:
        """
        Get version history for a template
        
        Args:
            template_id: Template identifier
            limit: Maximum number of versions to return
            
        Returns:
            List of template versions in reverse chronological order
        """
        pass
    
    @abstractmethod
    async def approve_version(
        self,
        version_id: str,
        approver_id: str,
        comments: Optional[str] = None,
        conditions: Optional[Dict[str, Any]] = None
    ) -> TemplateVersion:
        """
        Approve a template version
        
        Args:
            version_id: Version identifier
            approver_id: ID of the approver
            comments: Optional approval comments
            conditions: Optional approval conditions
            
        Returns:
            Updated template version
        """
        pass
    
    @abstractmethod
    async def reject_version(
        self,
        version_id: str,
        approver_id: str,
        comments: str
    ) -> TemplateVersion:
        """
        Reject a template version
        
        Args:
            version_id: Version identifier
            approver_id: ID of the approver
            comments: Rejection reason
            
        Returns:
            Updated template version
        """
        pass
    
    @abstractmethod
    async def deprecate_version(
        self,
        version_id: str,
        deprecator_id: str,
        reason: str
    ) -> TemplateVersion:
        """
        Deprecate a template version
        
        Args:
            version_id: Version identifier
            deprecator_id: ID of the person deprecating
            reason: Deprecation reason
            
        Returns:
            Updated template version
        """
        pass
    
    @abstractmethod
    async def get_pending_approvals(
        self,
        approver_id: Optional[str] = None
    ) -> List[TemplateVersion]:
        """
        Get templates pending approval
        
        Args:
            approver_id: Filter by specific approver
            
        Returns:
            List of template versions pending approval
        """
        pass
    
    @abstractmethod
    async def rollback_to_version(
        self,
        template_id: str,
        target_version_id: str,
        author_id: str,
        rationale: str
    ) -> TemplateVersion:
        """
        Rollback a template to a previous version
        
        Args:
            template_id: Template identifier
            target_version_id: Version to rollback to
            author_id: ID of person performing rollback
            rationale: Reason for rollback
            
        Returns:
            New template version with rolled back content
        """
        pass
    
    @abstractmethod
    async def get_templates_by_capability(
        self,
        capability: str,
        approved_only: bool = True
    ) -> List[TemplateVersion]:
        """
        Get templates that use a specific capability
        
        Args:
            capability: Capability name
            approved_only: Only return approved versions
            
        Returns:
            List of template versions using the capability
        """
        pass
    
    @abstractmethod
    async def validate_template(
        self,
        content: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate template content
        
        Args:
            content: Template content to validate
            
        Returns:
            Validation result with any errors/warnings
        """
        pass
    
    @abstractmethod
    async def calculate_diff(
        self,
        old_content: Dict[str, Any],
        new_content: Dict[str, Any]
    ) -> List[TemplateDiff]:
        """
        Calculate differences between two template versions
        
        Args:
            old_content: Previous template content
            new_content: New template content
            
        Returns:
            List of differences
        """
        pass
    
    @abstractmethod
    async def search_templates(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        approved_only: bool = True
    ) -> List[TemplateVersion]:
        """
        Search templates by content or metadata
        
        Args:
            query: Search query
            filters: Additional filters
            approved_only: Only return approved versions
            
        Returns:
            List of matching template versions
        """
        pass
    
    @abstractmethod
    async def export_template(
        self,
        version_id: str,
        format: str = "yaml"
    ) -> str:
        """
        Export a template version in specified format
        
        Args:
            version_id: Version identifier
            format: Export format (yaml, json, etc.)
            
        Returns:
            Exported template content
        """
        pass
    
    @abstractmethod
    async def import_template(
        self,
        content: str,
        format: str,
        author_id: str,
        validate: bool = True
    ) -> TemplateVersion:
        """
        Import a template from external format
        
        Args:
            content: Template content to import
            format: Content format
            author_id: ID of the importer
            validate: Whether to validate before importing
            
        Returns:
            Created template version
        """
        pass
    
    @abstractmethod
    async def get_usage_stats(
        self,
        template_id: str,
        version_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get usage statistics for a template
        
        Args:
            template_id: Template identifier
            version_id: Specific version (latest if None)
            
        Returns:
            Usage statistics including execution count, success rate, etc.
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        Check health of the versioning system
        
        Returns:
            Health status information
        """
        pass