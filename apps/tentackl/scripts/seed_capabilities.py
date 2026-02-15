#!/usr/bin/env python3
"""
Seed Capabilities Script

Loads agent configurations from YAML files into the capabilities_agents table.
This script should be run after database migrations to populate system agents.

Usage:
    python scripts/seed_capabilities.py
    # or
    docker compose exec tentackl python scripts/seed_capabilities.py
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Dict, Any, List
import uuid

import yaml
import structlog

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.interfaces.database import Database
from src.database.capability_models import AgentCapability, Primitive, Plugin

logger = structlog.get_logger(__name__)


CONFIGS_DIR = Path(__file__).parent.parent / "configs" / "agents"


async def load_yaml_configs() -> List[Dict[str, Any]]:
    """Load all YAML config files from the configs/agents directory."""
    configs = []

    if not CONFIGS_DIR.exists():
        logger.warning("Configs directory not found", path=str(CONFIGS_DIR))
        return configs

    for yaml_file in CONFIGS_DIR.glob("*.yaml"):
        try:
            with open(yaml_file, "r") as f:
                config = yaml.safe_load(f)
                config["_source_file"] = yaml_file.name
                configs.append(config)
                logger.debug("Loaded config", file=yaml_file.name, agent_type=config.get("agent_type"))
        except Exception as e:
            logger.error("Failed to load config", file=yaml_file.name, error=str(e))

    return configs


async def seed_agents(db: Database) -> int:
    """Seed agent configurations into the database."""
    configs = await load_yaml_configs()

    if not configs:
        logger.warning("No agent configs found to seed")
        return 0

    seeded_count = 0

    async with db.get_session() as session:
        for config in configs:
            agent_type = config.get("agent_type")
            if not agent_type:
                logger.warning("Config missing agent_type", file=config.get("_source_file"))
                continue

            # Check if agent already exists
            from sqlalchemy import select
            existing = await session.execute(
                select(AgentCapability).where(
                    AgentCapability.agent_type == agent_type,
                    AgentCapability.is_system == True,
                )
            )
            existing_agent = existing.scalar_one_or_none()

            if existing_agent:
                # Update existing agent
                existing_agent.name = config.get("name", agent_type)
                existing_agent.description = config.get("description")
                existing_agent.domain = config.get("domain")
                existing_agent.task_type = config.get("task_type", "general")
                existing_agent.system_prompt = config.get("system_prompt", "")
                existing_agent.inputs_schema = config.get("inputs", {})
                existing_agent.outputs_schema = config.get("outputs", {})
                existing_agent.examples = config.get("examples", [])
                existing_agent.execution_hints = config.get("execution_hints", {})

                logger.info("Updated existing agent", agent_type=agent_type)
            else:
                # Create new agent
                agent = AgentCapability(
                    id=uuid.uuid4(),
                    organization_id=None,  # System agent
                    agent_type=agent_type,
                    name=config.get("name", agent_type),
                    description=config.get("description"),
                    domain=config.get("domain"),
                    task_type=config.get("task_type", "general"),
                    system_prompt=config.get("system_prompt", ""),
                    inputs_schema=config.get("inputs", {}),
                    outputs_schema=config.get("outputs", {}),
                    examples=config.get("examples", []),
                    execution_hints=config.get("execution_hints", {}),
                    is_system=True,
                    is_active=True,
                )
                session.add(agent)
                logger.info("Created new agent", agent_type=agent_type)

            seeded_count += 1

        await session.commit()

    return seeded_count


async def seed_primitives(db: Database) -> int:
    """Seed built-in primitives into the database."""
    # Define minimal primitives
    primitives = [
        {
            "name": "http.get",
            "category": "http",
            "description": "Perform HTTP GET request",
            "handler_ref": "src.primitives.http.http_get",
            "inputs_schema": {
                "url": {"type": "string", "required": True, "description": "URL to fetch"},
                "headers": {"type": "object", "required": False, "description": "HTTP headers"},
            },
            "outputs_schema": {
                "status_code": {"type": "integer", "description": "HTTP status code"},
                "body": {"type": "string", "description": "Response body"},
                "headers": {"type": "object", "description": "Response headers"},
            },
            "execution_hints": {"deterministic": True, "speed": "fast", "cost": "free"},
        },
        {
            "name": "http.post",
            "category": "http",
            "description": "Perform HTTP POST request",
            "handler_ref": "src.primitives.http.http_post",
            "inputs_schema": {
                "url": {"type": "string", "required": True, "description": "URL to post to"},
                "body": {"type": "object", "required": False, "description": "Request body"},
                "headers": {"type": "object", "required": False, "description": "HTTP headers"},
            },
            "outputs_schema": {
                "status_code": {"type": "integer", "description": "HTTP status code"},
                "body": {"type": "string", "description": "Response body"},
            },
            "execution_hints": {"deterministic": True, "speed": "fast", "cost": "free"},
        },
        {
            "name": "json.parse",
            "category": "json",
            "description": "Parse JSON string to object",
            "handler_ref": "src.primitives.json_ops.json_parse",
            "inputs_schema": {
                "json_string": {"type": "string", "required": True, "description": "JSON string to parse"},
            },
            "outputs_schema": {
                "data": {"type": "object", "description": "Parsed JSON data"},
            },
            "execution_hints": {"deterministic": True, "speed": "instant", "cost": "free"},
        },
        {
            "name": "json.stringify",
            "category": "json",
            "description": "Convert object to JSON string",
            "handler_ref": "src.primitives.json_ops.json_stringify",
            "inputs_schema": {
                "data": {"type": "object", "required": True, "description": "Data to stringify"},
                "indent": {"type": "integer", "required": False, "default": 2, "description": "Indentation"},
            },
            "outputs_schema": {
                "json_string": {"type": "string", "description": "JSON string"},
            },
            "execution_hints": {"deterministic": True, "speed": "instant", "cost": "free"},
        },
        {
            "name": "list.filter",
            "category": "list",
            "description": "Filter list items by condition",
            "handler_ref": "src.primitives.list_ops.list_filter",
            "inputs_schema": {
                "items": {"type": "array", "required": True, "description": "List to filter"},
                "condition": {"type": "string", "required": True, "description": "Filter condition expression"},
            },
            "outputs_schema": {
                "filtered": {"type": "array", "description": "Filtered list"},
                "count": {"type": "integer", "description": "Number of items after filtering"},
            },
            "execution_hints": {"deterministic": True, "speed": "instant", "cost": "free"},
        },
        {
            "name": "string.template",
            "category": "string",
            "description": "Apply template substitution",
            "handler_ref": "src.primitives.string_ops.string_template",
            "inputs_schema": {
                "template": {"type": "string", "required": True, "description": "Template string with {placeholders}"},
                "values": {"type": "object", "required": True, "description": "Values to substitute"},
            },
            "outputs_schema": {
                "result": {"type": "string", "description": "Rendered template"},
            },
            "execution_hints": {"deterministic": True, "speed": "instant", "cost": "free"},
        },
    ]

    seeded_count = 0

    async with db.get_session() as session:
        for prim_config in primitives:
            name = prim_config["name"]

            # Check if primitive exists
            from sqlalchemy import select
            existing = await session.execute(
                select(Primitive).where(Primitive.name == name)
            )
            existing_prim = existing.scalar_one_or_none()

            if existing_prim:
                # Update
                existing_prim.category = prim_config["category"]
                existing_prim.description = prim_config.get("description")
                existing_prim.handler_ref = prim_config["handler_ref"]
                existing_prim.inputs_schema = prim_config["inputs_schema"]
                existing_prim.outputs_schema = prim_config["outputs_schema"]
                existing_prim.execution_hints = prim_config.get("execution_hints", {})
                logger.info("Updated primitive", name=name)
            else:
                # Create
                prim = Primitive(
                    id=uuid.uuid4(),
                    name=name,
                    category=prim_config["category"],
                    description=prim_config.get("description"),
                    handler_ref=prim_config["handler_ref"],
                    inputs_schema=prim_config["inputs_schema"],
                    outputs_schema=prim_config["outputs_schema"],
                    execution_hints=prim_config.get("execution_hints", {}),
                    is_active=True,
                )
                session.add(prim)
                logger.info("Created primitive", name=name)

            seeded_count += 1

        await session.commit()

    return seeded_count


async def seed_builtin_plugins(db: Database) -> int:
    """Seed built-in plugins into the database.

    Delegates to ``sync_plugins_to_db`` which merges the in-memory
    PluginRegistry and PLUGIN_REGISTRY into the ``capabilities_plugins``
    table.  This replaces the former hardcoded list with a dynamic sync
    that covers all registered plugins.
    """
    from src.capabilities.plugin_sync import sync_plugins_to_db

    return await sync_plugins_to_db(db)


async def main():
    """Main entry point for seeding capabilities."""
    logger.info("Starting capability seeding")

    db = Database()
    await db.connect()

    try:
        # Seed agents from YAML configs
        agents_count = await seed_agents(db)
        logger.info("Seeded agents", count=agents_count)

        # Seed primitives
        primitives_count = await seed_primitives(db)
        logger.info("Seeded primitives", count=primitives_count)

        # Seed built-in plugins
        plugins_count = await seed_builtin_plugins(db)
        logger.info("Seeded plugins", count=plugins_count)

        logger.info(
            "Capability seeding complete",
            agents=agents_count,
            primitives=primitives_count,
            plugins=plugins_count,
        )

    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
