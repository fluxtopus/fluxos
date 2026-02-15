"""
Provider definitions API routes (INT-020, INT-021).

Provides REST API endpoints for listing and retrieving provider definitions:
- GET /api/v1/providers - List all provider definitions
- GET /api/v1/providers/{provider} - Get specific provider definition
- GET /api/v1/providers/{provider}/setup-guide - Get provider setup wizard (INT-021)

These endpoints are public (no authentication required) as they expose
documentation-like information about supported providers.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
import structlog

from src.database.models import IntegrationDirection, IntegrationProvider
from src.providers.definitions import (
    CredentialRequirement,
    get_all_providers,
    get_provider_by_name,
    get_setup_guide_by_name,
    ProviderDefinition,
    ProviderSetupGuide,
)


logger = structlog.get_logger(__name__)

router = APIRouter()


# =============================================================================
# Pydantic Response Schemas
# =============================================================================


class CredentialDefinitionResponse(BaseModel):
    """Response schema for a credential definition."""
    credential_type: str
    requirement: str
    description: str
    example_format: Optional[str] = None
    validation_pattern: Optional[str] = None
    max_length: Optional[int] = None
    required_for_inbound: bool
    required_for_outbound: bool


class InboundEventTypeResponse(BaseModel):
    """Response schema for an inbound event type."""
    event_type: str
    description: str
    example_payload: Optional[dict] = None


class OutboundActionResponse(BaseModel):
    """Response schema for an outbound action definition."""
    action_type: str
    description: str
    required_params: list[str]
    optional_params: list[str]
    rate_limit_recommendation: Optional[dict] = None


class ValidationRuleResponse(BaseModel):
    """Response schema for a validation rule."""
    field: str
    rule_type: str
    value: str  # Serialized as string for JSON compatibility
    error_message: str


class ProviderResponse(BaseModel):
    """Response schema for a provider definition."""
    provider: str
    display_name: str
    description: str
    documentation_url: Optional[str] = None
    icon_url: Optional[str] = None
    supported_directions: list[str]
    supports_inbound: bool
    supports_outbound: bool
    credentials: list[CredentialDefinitionResponse]
    inbound_event_types: list[InboundEventTypeResponse]
    outbound_actions: list[OutboundActionResponse]
    validation_rules: list[ValidationRuleResponse]


class ProviderSummaryResponse(BaseModel):
    """Summary response for provider listing."""
    provider: str
    display_name: str
    description: str
    icon_url: Optional[str] = None
    supports_inbound: bool
    supports_outbound: bool
    credential_count: int
    inbound_event_count: int
    outbound_action_count: int


class ProviderListResponse(BaseModel):
    """Response schema for listing providers."""
    items: list[ProviderSummaryResponse]
    total: int


# =============================================================================
# Helper Functions
# =============================================================================


def _provider_to_response(provider_def: ProviderDefinition) -> ProviderResponse:
    """Convert ProviderDefinition to response schema."""
    credentials = [
        CredentialDefinitionResponse(
            credential_type=cred.credential_type.value,
            requirement=cred.requirement.value,
            description=cred.description,
            example_format=cred.example_format,
            validation_pattern=cred.validation_pattern,
            max_length=cred.max_length,
            required_for_inbound=cred.required_for_inbound,
            required_for_outbound=cred.required_for_outbound,
        )
        for cred in provider_def.credentials
    ]

    inbound_events = [
        InboundEventTypeResponse(
            event_type=event.event_type,
            description=event.description,
            example_payload=event.example_payload,
        )
        for event in provider_def.inbound_event_types
    ]

    outbound_actions = [
        OutboundActionResponse(
            action_type=action.action_type.value,
            description=action.description,
            required_params=action.required_params,
            optional_params=action.optional_params,
            rate_limit_recommendation=action.rate_limit_recommendation,
        )
        for action in provider_def.outbound_actions
    ]

    validation_rules = [
        ValidationRuleResponse(
            field=rule.field,
            rule_type=rule.rule_type,
            value=str(rule.value),
            error_message=rule.error_message,
        )
        for rule in provider_def.validation_rules
    ]

    return ProviderResponse(
        provider=provider_def.provider.value,
        display_name=provider_def.display_name,
        description=provider_def.description,
        documentation_url=provider_def.documentation_url,
        icon_url=provider_def.icon_url,
        supported_directions=[d.value for d in provider_def.supported_directions],
        supports_inbound=provider_def.supports_inbound(),
        supports_outbound=provider_def.supports_outbound(),
        credentials=credentials,
        inbound_event_types=inbound_events,
        outbound_actions=outbound_actions,
        validation_rules=validation_rules,
    )


def _provider_to_summary(provider_def: ProviderDefinition) -> ProviderSummaryResponse:
    """Convert ProviderDefinition to summary response schema."""
    return ProviderSummaryResponse(
        provider=provider_def.provider.value,
        display_name=provider_def.display_name,
        description=provider_def.description,
        icon_url=provider_def.icon_url,
        supports_inbound=provider_def.supports_inbound(),
        supports_outbound=provider_def.supports_outbound(),
        credential_count=len(provider_def.credentials),
        inbound_event_count=len(provider_def.inbound_event_types),
        outbound_action_count=len(provider_def.outbound_actions),
    )


# =============================================================================
# API Endpoints
# =============================================================================


@router.get(
    "/providers",
    response_model=ProviderListResponse,
    summary="List all provider definitions",
    description="""
List all available integration providers with their capabilities.

Returns a summary of each provider including:
- Provider name and description
- Whether it supports inbound/outbound integrations
- Count of credential types, inbound events, and outbound actions

This endpoint is public (no authentication required).
""",
)
async def list_providers(
    supports_inbound: Optional[bool] = Query(
        None,
        description="Filter to providers that support inbound webhooks",
    ),
    supports_outbound: Optional[bool] = Query(
        None,
        description="Filter to providers that support outbound actions",
    ),
) -> ProviderListResponse:
    """List all available provider definitions."""
    logger.info(
        "listing_providers",
        supports_inbound=supports_inbound,
        supports_outbound=supports_outbound,
    )

    providers = get_all_providers()

    # Apply filters
    if supports_inbound is not None:
        providers = [p for p in providers if p.supports_inbound() == supports_inbound]

    if supports_outbound is not None:
        providers = [p for p in providers if p.supports_outbound() == supports_outbound]

    items = [_provider_to_summary(p) for p in providers]

    return ProviderListResponse(
        items=items,
        total=len(items),
    )


@router.get(
    "/providers/{provider}",
    response_model=ProviderResponse,
    summary="Get provider definition",
    description="""
Get the complete definition for a specific provider.

Returns detailed information including:
- Required and optional credentials
- Supported inbound event types
- Supported outbound action types with parameters
- Validation rules for content limits

This endpoint is public (no authentication required).
""",
    responses={
        404: {"description": "Provider not found"},
    },
)
async def get_provider(provider: str) -> ProviderResponse:
    """Get a specific provider definition by name."""
    logger.info("getting_provider", provider=provider)

    provider_def = get_provider_by_name(provider)

    if provider_def is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider}' not found. Available providers: discord, slack, github, stripe, custom_webhook",
        )

    return _provider_to_response(provider_def)


# =============================================================================
# Setup Guide Schemas (INT-021)
# =============================================================================


class SetupStepResponse(BaseModel):
    """Response schema for a setup step."""
    step_number: int
    title: str
    description: str
    instructions: list[str]
    screenshot_url: Optional[str] = None
    external_link: Optional[str] = None
    credential_type: Optional[str] = None
    tips: list[str]
    is_optional: bool


class CommonIssueResponse(BaseModel):
    """Response schema for a common issue and its solution."""
    issue: str
    solution: str


class SetupGuideResponse(BaseModel):
    """Response schema for a provider setup guide."""
    provider: str
    display_name: str
    estimated_time_minutes: int
    prerequisites: list[str]
    steps: list[SetupStepResponse]
    permissions_needed: list[str]
    test_steps: list[str]
    common_issues: list[CommonIssueResponse]
    video_tutorial_url: Optional[str] = None


# =============================================================================
# Setup Guide Helper Functions
# =============================================================================


def _setup_guide_to_response(
    guide: ProviderSetupGuide,
    provider_def: ProviderDefinition,
) -> SetupGuideResponse:
    """Convert ProviderSetupGuide to response schema."""
    steps = [
        SetupStepResponse(
            step_number=step.step_number,
            title=step.title,
            description=step.description,
            instructions=step.instructions,
            screenshot_url=step.screenshot_url,
            external_link=step.external_link,
            credential_type=step.credential_type.value if step.credential_type else None,
            tips=step.tips,
            is_optional=step.is_optional,
        )
        for step in guide.steps
    ]

    common_issues = [
        CommonIssueResponse(
            issue=issue.get("issue", ""),
            solution=issue.get("solution", ""),
        )
        for issue in guide.common_issues
    ]

    return SetupGuideResponse(
        provider=guide.provider.value,
        display_name=provider_def.display_name,
        estimated_time_minutes=guide.estimated_time_minutes,
        prerequisites=guide.prerequisites,
        steps=steps,
        permissions_needed=guide.permissions_needed,
        test_steps=guide.test_steps,
        common_issues=common_issues,
        video_tutorial_url=guide.video_tutorial_url,
    )


# =============================================================================
# Setup Guide API Endpoint (INT-021)
# =============================================================================


@router.get(
    "/providers/{provider}/setup-guide",
    response_model=SetupGuideResponse,
    summary="Get provider setup guide",
    description="""
Get step-by-step setup instructions for a specific provider.

Returns a wizard-style guide including:
- Prerequisites before starting
- Step-by-step instructions with external links
- Required permissions/scopes
- Test steps to verify setup
- Common issues and solutions

UI can render this as an interactive setup wizard.

This endpoint is public (no authentication required).
""",
    responses={
        404: {"description": "Provider not found or no setup guide available"},
    },
)
async def get_provider_setup_guide(provider: str) -> SetupGuideResponse:
    """Get the setup guide for a specific provider."""
    logger.info("getting_provider_setup_guide", provider=provider)

    provider_def = get_provider_by_name(provider)

    if provider_def is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider}' not found. Available providers: discord, slack, github, stripe, custom_webhook",
        )

    guide = get_setup_guide_by_name(provider)

    if guide is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No setup guide available for provider '{provider}'",
        )

    return _setup_guide_to_response(guide, provider_def)
