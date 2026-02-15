"""Template service for rendering system templates."""

import re
from typing import Dict, Any, Optional, Tuple
import structlog
from sqlalchemy.orm import Session
from sqlalchemy import or_

from src.database.models import SystemTemplate

logger = structlog.get_logger()


class TemplateNotFoundError(Exception):
    """Raised when a template cannot be found."""
    pass


class TemplateService:
    """
    Service for managing and rendering system templates.

    Templates are resolved in order of specificity:
    1. Organization-specific template (organization_id matches)
    2. Platform-wide template (organization_id is null)
    """

    def __init__(self, db: Session):
        self.db = db

    def get_template(
        self,
        name: str,
        organization_id: Optional[str] = None,
    ) -> SystemTemplate:
        """
        Get a template by name with organization fallback.

        Resolution order:
        1. Try org-specific template if organization_id provided
        2. Fall back to platform template (organization_id=null)

        Args:
            name: Template name (e.g., "invitation", "welcome")
            organization_id: Organization ID for org-specific templates

        Returns:
            SystemTemplate instance

        Raises:
            TemplateNotFoundError: If no matching template found
        """
        # Try org-specific template first
        if organization_id:
            template = self.db.query(SystemTemplate).filter(
                SystemTemplate.name == name,
                SystemTemplate.organization_id == organization_id,
                SystemTemplate.is_active == True,
            ).first()

            if template:
                logger.debug(
                    "Found org-specific template",
                    template_name=name,
                    organization_id=organization_id,
                )
                return template

        # Fall back to platform template
        template = self.db.query(SystemTemplate).filter(
            SystemTemplate.name == name,
            SystemTemplate.organization_id == None,
            SystemTemplate.is_active == True,
        ).first()

        if template:
            logger.debug(
                "Found platform template",
                template_name=name,
            )
            return template

        raise TemplateNotFoundError(
            f"Template '{name}' not found for organization '{organization_id}'"
        )

    def render_template(
        self,
        template: SystemTemplate,
        variables: Dict[str, Any],
    ) -> Tuple[str, str, Optional[str]]:
        """
        Render template with variable substitution.

        Variables use {{variable_name}} syntax.

        Args:
            template: SystemTemplate to render
            variables: Dict of variable name -> value

        Returns:
            Tuple of (rendered_subject, rendered_text, rendered_html or None)
        """
        def substitute(content: str) -> str:
            """Substitute {{variable}} placeholders."""
            def replacer(match):
                var_name = match.group(1)
                return str(variables.get(var_name, f"{{{{{{var_name}}}}}}"))

            return re.sub(r'\{\{(\w+)\}\}', replacer, content)

        rendered_subject = substitute(template.subject)
        rendered_text = substitute(template.content_text)
        rendered_html = substitute(template.content_html) if template.content_html else None

        logger.debug(
            "Rendered template",
            template_name=template.name,
            variables_used=list(variables.keys()),
        )

        return rendered_subject, rendered_text, rendered_html

    def list_templates(
        self,
        organization_id: Optional[str] = None,
        include_platform: bool = True,
    ) -> list[SystemTemplate]:
        """
        List available templates.

        Args:
            organization_id: Filter by organization
            include_platform: Include platform-wide templates

        Returns:
            List of SystemTemplate instances
        """
        query = self.db.query(SystemTemplate).filter(
            SystemTemplate.is_active == True
        )

        if organization_id and include_platform:
            query = query.filter(
                or_(
                    SystemTemplate.organization_id == organization_id,
                    SystemTemplate.organization_id == None,
                )
            )
        elif organization_id:
            query = query.filter(SystemTemplate.organization_id == organization_id)
        elif include_platform:
            query = query.filter(SystemTemplate.organization_id == None)

        return query.all()

    def create_template(
        self,
        name: str,
        subject: str,
        content_text: str,
        content_html: Optional[str] = None,
        organization_id: Optional[str] = None,
        variables: Optional[list[str]] = None,
    ) -> SystemTemplate:
        """
        Create a new system template.

        Args:
            name: Template name (e.g., "invitation")
            subject: Email subject with {{variables}}
            content_text: Plain text content with {{variables}}
            content_html: Optional HTML content with {{variables}}
            organization_id: Organization ID or None for platform template
            variables: List of variable names used in template

        Returns:
            Created SystemTemplate
        """
        # Auto-extract variables if not provided
        if variables is None:
            all_content = f"{subject} {content_text} {content_html or ''}"
            variables = list(set(re.findall(r'\{\{(\w+)\}\}', all_content)))

        template = SystemTemplate(
            name=name,
            subject=subject,
            content_text=content_text,
            content_html=content_html,
            organization_id=organization_id,
            variables=variables,
        )

        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)

        logger.info(
            "Created system template",
            template_id=template.id,
            template_name=name,
            organization_id=organization_id,
        )

        return template
