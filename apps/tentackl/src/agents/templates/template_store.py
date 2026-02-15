"""
Agent Template Store

Provides storage and retrieval of agent templates using the
existing template versioning infrastructure.
"""

import os
from datetime import datetime
from typing import Dict, List, Optional, Any
import structlog

from src.agents.templates.agent_template import (
    AgentTemplate,
    TemplateValidationError,
)
from src.templates.redis_template_versioning import RedisTemplateVersioning
from src.interfaces.template_versioning import TemplateVersion, ApprovalStatus

logger = structlog.get_logger(__name__)


class AgentTemplateStore:
    """
    Store and retrieve agent templates with versioning support.

    Uses the existing RedisTemplateVersioning infrastructure for
    persistence, approval workflows, and version control.

    Templates are keyed by domain:agent_type:name and support:
    - Multiple versions with semantic versioning
    - Approval workflows for production use
    - Usage tracking and statistics
    - YAML/JSON import/export
    """

    def __init__(
        self,
        redis_url: str = None,
        db: int = 4,  # Dedicated DB for agent templates
        key_prefix: str = "tentackl:agent_templates",
    ):
        """
        Initialize the agent template store.

        Args:
            redis_url: Redis connection URL (defaults to REDIS_URL env var)
            db: Redis database number
            key_prefix: Prefix for all Redis keys
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.db = db
        self.key_prefix = key_prefix

        self._versioning = RedisTemplateVersioning(
            redis_url=self.redis_url,
            db=self.db,
            key_prefix=self.key_prefix,
        )
        self._connected = False

    async def connect(self) -> None:
        """Establish connection to Redis."""
        if not self._connected:
            await self._versioning._connect()
            self._connected = True
            logger.info("Agent template store connected")

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._connected:
            await self._versioning._disconnect()
            self._connected = False
            logger.info("Agent template store disconnected")

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()

    def _template_to_content(self, template: AgentTemplate) -> Dict[str, Any]:
        """Convert AgentTemplate to versioning content format."""
        return {
            "name": template.name,
            "type": "agent_template",
            "capabilities": [],  # Not used for agent templates
            "prompt_template": "",  # Stored in prompts list
            **template.to_dict(),
        }

    def _content_to_template(self, content: Dict[str, Any]) -> AgentTemplate:
        """Convert versioning content to AgentTemplate."""
        return AgentTemplate.from_dict(content)

    async def create_template(
        self,
        template: AgentTemplate,
        author_id: str,
        author_type: str = "human",
        rationale: str = "Initial creation",
        auto_approve: bool = False,
    ) -> AgentTemplate:
        """
        Create a new agent template.

        Args:
            template: The agent template to create
            author_id: ID of the author
            author_type: Type of author ("human" or "agent")
            rationale: Reason for creating the template
            auto_approve: If True, automatically approve the template

        Returns:
            The created template

        Raises:
            TemplateValidationError: If template validation fails
            ValueError: If template already exists
        """
        await self.connect()

        # Validate template
        errors = template.validate()
        if errors:
            raise TemplateValidationError(errors)

        content = self._template_to_content(template)

        try:
            version = await self._versioning.create_template(
                template_id=template.template_id,
                content=content,
                author_id=author_id,
                author_type=author_type,
                rationale=rationale,
                metadata={
                    "domain": template.domain,
                    "agent_type": template.agent_type,
                    "template_name": template.name,
                },
            )

            if auto_approve:
                version = await self._versioning.approve_version(
                    version_id=version.id,
                    approver_id=author_id,
                    comments="Auto-approved on creation",
                )

            logger.info(
                "Created agent template",
                template_id=template.template_id,
                version=version.version,
                author=author_id,
            )

            return self._content_to_template(version.content)

        except Exception as e:
            logger.error(
                "Failed to create agent template",
                template_id=template.template_id,
                error=str(e),
            )
            raise

    async def update_template(
        self,
        template: AgentTemplate,
        author_id: str,
        author_type: str = "human",
        rationale: str = "Update",
    ) -> AgentTemplate:
        """
        Create a new version of an existing template.

        Args:
            template: The updated template
            author_id: ID of the author
            author_type: Type of author
            rationale: Reason for the update

        Returns:
            The updated template

        Raises:
            TemplateValidationError: If template validation fails
            ValueError: If template doesn't exist
        """
        await self.connect()

        # Validate template
        errors = template.validate()
        if errors:
            raise TemplateValidationError(errors)

        content = self._template_to_content(template)

        try:
            version = await self._versioning.create_version(
                template_id=template.template_id,
                content=content,
                author_id=author_id,
                author_type=author_type,
                rationale=rationale,
                metadata={
                    "domain": template.domain,
                    "agent_type": template.agent_type,
                    "template_name": template.name,
                },
            )

            logger.info(
                "Updated agent template",
                template_id=template.template_id,
                version=version.version,
                author=author_id,
            )

            return self._content_to_template(version.content)

        except Exception as e:
            logger.error(
                "Failed to update agent template",
                template_id=template.template_id,
                error=str(e),
            )
            raise

    async def get_template(
        self,
        domain: str,
        agent_type: str,
        name: str,
        approved_only: bool = True,
    ) -> Optional[AgentTemplate]:
        """
        Get the latest version of a template.

        Args:
            domain: Template domain (e.g., "content")
            agent_type: Agent type (e.g., "youtube_script")
            name: Template name
            approved_only: Only return approved templates

        Returns:
            The template if found, None otherwise
        """
        await self.connect()

        template_id = f"{domain}:{agent_type}:{name}"

        try:
            version = await self._versioning.get_latest_version(
                template_id=template_id,
                approved_only=approved_only,
            )

            if version:
                return self._content_to_template(version.content)
            return None

        except Exception as e:
            logger.error(
                "Failed to get agent template",
                template_id=template_id,
                error=str(e),
            )
            return None

    async def get_template_by_id(
        self,
        template_id: str,
        approved_only: bool = True,
    ) -> Optional[AgentTemplate]:
        """
        Get a template by its full ID (domain:agent_type:name).

        Args:
            template_id: Full template ID
            approved_only: Only return approved templates

        Returns:
            The template if found, None otherwise
        """
        await self.connect()

        try:
            version = await self._versioning.get_latest_version(
                template_id=template_id,
                approved_only=approved_only,
            )

            if version:
                return self._content_to_template(version.content)
            return None

        except Exception as e:
            logger.error(
                "Failed to get agent template by ID",
                template_id=template_id,
                error=str(e),
            )
            return None

    async def list_templates(
        self,
        domain: Optional[str] = None,
        agent_type: Optional[str] = None,
        approved_only: bool = True,
    ) -> List[AgentTemplate]:
        """
        List templates with optional filtering.

        Args:
            domain: Filter by domain
            agent_type: Filter by agent type
            approved_only: Only return approved templates

        Returns:
            List of matching templates
        """
        await self.connect()

        templates = []

        try:
            # Search for templates matching the criteria
            query = ""
            if domain:
                query += domain
            if agent_type:
                query += f" {agent_type}" if query else agent_type

            if query:
                versions = await self._versioning.search_templates(
                    query=query,
                    approved_only=approved_only,
                )
            else:
                # Get all templates
                versions = await self._versioning.search_templates(
                    query="agent_template",
                    approved_only=approved_only,
                )

            for version in versions:
                template = self._content_to_template(version.content)

                # Apply filters
                if domain and template.domain != domain:
                    continue
                if agent_type and template.agent_type != agent_type:
                    continue

                templates.append(template)

            return templates

        except Exception as e:
            logger.error(
                "Failed to list agent templates",
                domain=domain,
                agent_type=agent_type,
                error=str(e),
            )
            return []

    async def get_templates_for_agent(
        self,
        domain: str,
        agent_type: str,
        approved_only: bool = True,
    ) -> List[AgentTemplate]:
        """
        Get all templates for a specific agent type.

        Args:
            domain: Template domain
            agent_type: Agent type
            approved_only: Only return approved templates

        Returns:
            List of templates for the agent
        """
        return await self.list_templates(
            domain=domain,
            agent_type=agent_type,
            approved_only=approved_only,
        )

    async def approve_template(
        self,
        domain: str,
        agent_type: str,
        name: str,
        approver_id: str,
        comments: Optional[str] = None,
    ) -> AgentTemplate:
        """
        Approve a template for production use.

        Args:
            domain: Template domain
            agent_type: Agent type
            name: Template name
            approver_id: ID of the approver
            comments: Approval comments

        Returns:
            The approved template

        Raises:
            ValueError: If template not found or already approved
        """
        await self.connect()

        template_id = f"{domain}:{agent_type}:{name}"

        try:
            # Get pending version
            version = await self._versioning.get_latest_version(
                template_id=template_id,
                approved_only=False,
            )

            if not version:
                raise ValueError(f"Template {template_id} not found")

            if version.is_approved:
                raise ValueError(f"Template {template_id} is already approved")

            # Approve the version
            approved_version = await self._versioning.approve_version(
                version_id=version.id,
                approver_id=approver_id,
                comments=comments,
            )

            logger.info(
                "Approved agent template",
                template_id=template_id,
                version=approved_version.version,
                approver=approver_id,
            )

            return self._content_to_template(approved_version.content)

        except Exception as e:
            logger.error(
                "Failed to approve agent template",
                template_id=template_id,
                error=str(e),
            )
            raise

    async def get_version_history(
        self,
        domain: str,
        agent_type: str,
        name: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get version history for a template.

        Args:
            domain: Template domain
            agent_type: Agent type
            name: Template name
            limit: Maximum versions to return

        Returns:
            List of version info dictionaries
        """
        await self.connect()

        template_id = f"{domain}:{agent_type}:{name}"

        try:
            versions = await self._versioning.get_version_history(
                template_id=template_id,
                limit=limit,
            )

            return [
                {
                    "version_id": v.id,
                    "version": v.version,
                    "status": v.approval.status.value if v.approval else "draft",
                    "created_at": v.created_at.isoformat(),
                    "author": v.changes[-1].author_id if v.changes else None,
                    "rationale": v.changes[-1].rationale if v.changes else None,
                }
                for v in versions
            ]

        except Exception as e:
            logger.error(
                "Failed to get template version history",
                template_id=template_id,
                error=str(e),
            )
            return []

    async def import_from_yaml(
        self,
        yaml_content: str,
        author_id: str,
        auto_approve: bool = False,
    ) -> AgentTemplate:
        """
        Import a template from YAML.

        Args:
            yaml_content: YAML template content
            author_id: ID of the importer
            auto_approve: If True, auto-approve the template

        Returns:
            The imported template
        """
        template = AgentTemplate.from_yaml(yaml_content)

        # Check if template exists
        existing = await self.get_template(
            domain=template.domain,
            agent_type=template.agent_type,
            name=template.name,
            approved_only=False,
        )

        if existing:
            return await self.update_template(
                template=template,
                author_id=author_id,
                rationale="Imported from YAML",
            )
        else:
            return await self.create_template(
                template=template,
                author_id=author_id,
                rationale="Imported from YAML",
                auto_approve=auto_approve,
            )

    async def import_from_json(
        self,
        json_content: str,
        author_id: str,
        auto_approve: bool = False,
    ) -> AgentTemplate:
        """
        Import a template from JSON.

        Args:
            json_content: JSON template content
            author_id: ID of the importer
            auto_approve: If True, auto-approve the template

        Returns:
            The imported template
        """
        template = AgentTemplate.from_json(json_content)

        # Check if template exists
        existing = await self.get_template(
            domain=template.domain,
            agent_type=template.agent_type,
            name=template.name,
            approved_only=False,
        )

        if existing:
            return await self.update_template(
                template=template,
                author_id=author_id,
                rationale="Imported from JSON",
            )
        else:
            return await self.create_template(
                template=template,
                author_id=author_id,
                rationale="Imported from JSON",
                auto_approve=auto_approve,
            )

    async def export_to_yaml(
        self,
        domain: str,
        agent_type: str,
        name: str,
    ) -> Optional[str]:
        """
        Export a template to YAML.

        Args:
            domain: Template domain
            agent_type: Agent type
            name: Template name

        Returns:
            YAML string or None if not found
        """
        template = await self.get_template(domain, agent_type, name)
        return template.to_yaml() if template else None

    async def export_to_json(
        self,
        domain: str,
        agent_type: str,
        name: str,
    ) -> Optional[str]:
        """
        Export a template to JSON.

        Args:
            domain: Template domain
            agent_type: Agent type
            name: Template name

        Returns:
            JSON string or None if not found
        """
        template = await self.get_template(domain, agent_type, name)
        return template.to_json() if template else None

    async def get_usage_stats(
        self,
        domain: str,
        agent_type: str,
        name: str,
    ) -> Dict[str, Any]:
        """
        Get usage statistics for a template.

        Args:
            domain: Template domain
            agent_type: Agent type
            name: Template name

        Returns:
            Usage statistics dictionary
        """
        await self.connect()

        template_id = f"{domain}:{agent_type}:{name}"

        try:
            return await self._versioning.get_usage_stats(template_id=template_id)
        except Exception as e:
            logger.error(
                "Failed to get template usage stats",
                template_id=template_id,
                error=str(e),
            )
            return {}

    async def health_check(self) -> Dict[str, Any]:
        """
        Check health of the template store.

        Returns:
            Health status dictionary
        """
        try:
            await self.connect()
            return await self._versioning.health_check()
        except Exception as e:
            logger.error("Template store health check failed", error=str(e))
            return {
                "status": "unhealthy",
                "error": str(e),
            }
