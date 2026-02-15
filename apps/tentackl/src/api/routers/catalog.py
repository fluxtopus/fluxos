"""Catalog API endpoints for plugins and agent types."""

from fastapi import APIRouter, Depends

from src.api.auth_middleware import auth_middleware, AuthUser
from src.agents.factory import AgentFactory
from src.plugins.registry import registry as plugin_registry


router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/plugins")
async def list_plugins(
    current_user: AuthUser = Depends(auth_middleware.require_permission("workflows", "view"))
):
    """List available plugins for discovery and UI tooling."""
    items = []
    for name, plugin in plugin_registry._plugins.items():  # type: ignore[attr-defined]
        items.append({
            "name": name,
            "description": plugin.description,
            "category": plugin.category,
            "inputs_schema": plugin.inputs_schema,
            "outputs_schema": plugin.outputs_schema,
        })
    return {"plugins": items}


@router.get("/agents")
async def list_agents(
    current_user: AuthUser = Depends(auth_middleware.require_permission("workflows", "view"))
):
    """List registered agent types."""
    try:
        if not AgentFactory.get_registered_types():
            try:
                from src.agents.registry import register_default_agents  # type: ignore
                register_default_agents()
            except Exception:
                pass
    except Exception:
        pass
    return {"agents": AgentFactory.get_registered_types()}
