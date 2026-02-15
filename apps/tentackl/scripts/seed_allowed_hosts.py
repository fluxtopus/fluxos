#!/usr/bin/env python3
"""Seed allowed hosts for production environment."""

import asyncio
import sys
sys.path.insert(0, "/app")

from src.core.allowed_hosts import ALLOWED_HOSTS
from src.services.allowed_host_service import AllowedHostService
from src.interfaces.database import Database


async def seed_allowed_hosts(environment: str = "production"):
    """Add all default allowed hosts to the specified environment."""
    db = Database()
    await db.connect()

    try:
        service = AllowedHostService(database=db)

        print(f"Seeding {len(ALLOWED_HOSTS)} hosts for environment: {environment}")

        for host in ALLOWED_HOSTS:
            try:
                await service.add_allowed_host(
                    host=host,
                    environment=environment,
                    created_by="seed_script",
                    notes="Seeded from default ALLOWED_HOSTS list"
                )
                print(f"  ✓ Added: {host}")
            except Exception as e:
                print(f"  ✗ Failed: {host} - {e}")

        print(f"\nDone! Added hosts for {environment} environment.")

    finally:
        await db.disconnect()


if __name__ == "__main__":
    env = sys.argv[1] if len(sys.argv) > 1 else "production"
    asyncio.run(seed_allowed_hosts(env))
