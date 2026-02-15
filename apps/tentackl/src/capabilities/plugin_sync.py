"""
Sync in-memory plugins to the capabilities_plugins DB table.

On startup, this ensures every plugin known to the PluginRegistry
(rich metadata) and the PLUGIN_REGISTRY execution map is represented
in the database so that ``task_capabilities`` and ``list_for_planner()``
can discover them.

Usage:
    from src.capabilities.plugin_sync import sync_plugins_to_db

    synced = await sync_plugins_to_db(db)
"""

import importlib
import uuid
from typing import Any, Dict

import structlog
from sqlalchemy import select

from src.database.capability_models import Plugin
from src.interfaces.database import Database

logger = structlog.get_logger(__name__)

# Namespaces to exclude from DB sync because they duplicate other entries.
# They still work for execution (remain in PLUGIN_REGISTRY / PluginRegistry),
# they just won't clutter discovery results.
_SKIP_NAMESPACES = {
    "webhook_receiver",  # alias of "webhook"
    "http_fetch",        # duplicate of "http" (richer PluginRegistry entry)
    "file_storage",      # duplicate of "den_upload"
    "document_db",       # duplicate of "doc_insert"
    "agent_storage",     # duplicate of "agent_save"
}


def _extract_description(module_path: str, handler_name: str) -> str:
    """Extract a description from a handler's or module's docstring."""
    try:
        module = importlib.import_module(module_path)
        handler = getattr(module, handler_name, None)
        if handler and handler.__doc__:
            return handler.__doc__.strip().split("\n")[0]
        if module.__doc__:
            return module.__doc__.strip().split("\n")[0]
    except Exception:
        pass
    return ""


def _collect_plugins() -> Dict[str, Dict[str, Any]]:
    """Merge both plugin sources into a single dict keyed by namespace."""
    plugins_to_sync: Dict[str, Dict[str, Any]] = {}

    # 1. PluginRegistry — rich metadata (description, category, schemas)
    from src.plugins.registry import registry as plugin_registry

    for name, defn in plugin_registry._plugins.items():
        if name in _SKIP_NAMESPACES:
            continue
        first_line = (defn.description or "").strip().split("\n")[0]
        plugins_to_sync[name] = {
            "namespace": name,
            "name": first_line[:80] or name,
            "description": defn.description or "",
            "plugin_type": "builtin",
            "config": {
                "category": defn.category,
                "inputs_schema": defn.inputs_schema,
                "outputs_schema": defn.outputs_schema,
            },
        }

    # 2. PLUGIN_REGISTRY — execution-mapped entries may have unique keys
    from src.infrastructure.execution_runtime.plugin_executor import PLUGIN_REGISTRY

    for agent_type, (module_path, handler_name) in PLUGIN_REGISTRY.items():
        if agent_type in _SKIP_NAMESPACES:
            continue
        if agent_type not in plugins_to_sync:
            desc = _extract_description(module_path, handler_name)
            plugins_to_sync[agent_type] = {
                "namespace": agent_type,
                "name": agent_type.replace("_", " ").title(),
                "description": desc,
                "plugin_type": "builtin",
                "config": {"module": module_path, "handler": handler_name},
            }

    return plugins_to_sync


async def sync_plugins_to_db(db: Database) -> int:
    """Sync in-memory plugins to the ``capabilities_plugins`` table.

    Performs an idempotent upsert: existing system rows are updated,
    new ones are inserted.  Non-system (user-created) rows are never
    touched.

    Returns the number of plugins processed.
    """
    plugins_to_sync = _collect_plugins()
    valid_namespaces = set(plugins_to_sync.keys())

    count = 0
    removed = 0
    async with db.get_session() as session:
        # Upsert current plugins
        for ns, meta in plugins_to_sync.items():
            existing = await session.execute(
                select(Plugin).where(
                    Plugin.namespace == ns,
                    Plugin.is_system == True,  # noqa: E712
                )
            )
            existing_plugin = existing.scalars().first()

            if existing_plugin:
                existing_plugin.name = meta["name"]
                existing_plugin.description = meta["description"]
                existing_plugin.config = meta["config"]
            else:
                session.add(
                    Plugin(
                        id=uuid.uuid4(),
                        organization_id=None,
                        namespace=meta["namespace"],
                        name=meta["name"],
                        description=meta["description"],
                        plugin_type=meta["plugin_type"],
                        config=meta["config"],
                        is_system=True,
                        is_active=True,
                    )
                )
            count += 1

        # Remove orphaned system rows (old seed entries, skipped duplicates)
        all_system = await session.execute(
            select(Plugin).where(Plugin.is_system == True)  # noqa: E712
        )
        for row in all_system.scalars():
            if row.namespace not in valid_namespaces:
                logger.info("Removing orphaned system plugin", namespace=row.namespace)
                await session.delete(row)
                removed += 1

        await session.commit()

    logger.info("Plugin capabilities synced to DB", count=count, removed=removed)
    return count
