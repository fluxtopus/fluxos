#!/usr/bin/env python3
"""
Workspace Events Demo

Demonstrates native calendar event storage using the Workspace Objects API.
Events can be created by users OR agents, with full attribution tracking.

Usage:
    docker compose exec tentackl python -m src.examples.workspace_events_demo

Required environment variables:
    DEMO_USER_EMAIL: Email for the demo user account.
    DEMO_USER_PASSWORD: Password for the demo user account.
    INKPASS_URL: (optional) InkPass service URL.
    TENTACKL_URL: (optional) Tentackl service URL.
"""

import asyncio
import httpx
import os
from datetime import datetime, timedelta


# Configuration - Use internal Docker network URLs
INKPASS_URL = os.environ.get("INKPASS_URL", "http://inkpass:8000")
TENTACKL_URL = os.environ.get("TENTACKL_URL", "http://tentackl:8000")
PLUS_USER = {
    "email": os.environ.get("DEMO_USER_EMAIL", ""),
    "password": os.environ.get("DEMO_USER_PASSWORD", ""),
}


async def get_token() -> str:
    """Get auth token for plus user."""
    async with httpx.AsyncClient() as client:
        # Try internal Docker URL first, fall back to localhost
        for base_url in [INKPASS_URL, "http://localhost:8004"]:
            try:
                response = await client.post(
                    f"{base_url}/api/v1/auth/login",
                    json=PLUS_USER,
                    timeout=5.0
                )
                if response.status_code == 200:
                    return response.json()["access_token"]
            except httpx.ConnectError:
                continue
        raise Exception("Could not connect to InkPass")


async def create_event(client: httpx.AsyncClient, token: str, event_data: dict) -> dict:
    """Create a calendar event via Workspace API."""
    response = await client.post(
        f"{TENTACKL_URL}/api/workspace/objects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "type": "event",
            "data": event_data,
            "tags": event_data.get("tags", ["meeting"])
        }
    )
    response.raise_for_status()
    return response.json()


async def list_events(client: httpx.AsyncClient, token: str) -> list:
    """List all calendar events."""
    response = await client.get(
        f"{TENTACKL_URL}/api/workspace/events",
        headers={"Authorization": f"Bearer {token}"}
    )
    response.raise_for_status()
    return response.json()


async def query_events(client: httpx.AsyncClient, token: str, query: dict) -> list:
    """Query events with filters."""
    response = await client.post(
        f"{TENTACKL_URL}/api/workspace/objects/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"type": "event", **query}
    )
    response.raise_for_status()
    return response.json()


async def search_events(client: httpx.AsyncClient, token: str, search_term: str) -> list:
    """Full-text search events."""
    response = await client.post(
        f"{TENTACKL_URL}/api/workspace/objects/search",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": search_term, "type": "event"}
    )
    response.raise_for_status()
    return response.json()


async def main():
    print("=" * 60)
    print("Workspace Events Demo - Native Calendar Storage")
    print("=" * 60)

    # Get auth token
    print("\n1. Authenticating as plus@example.com...")
    token = await get_token()
    print(f"   Token: {token[:50]}...")

    async with httpx.AsyncClient() as client:
        # Create events
        print("\n2. Creating calendar events...")

        tomorrow = datetime.utcnow() + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%Y-%m-%d")

        events_to_create = [
            {
                "title": "Team Standup",
                "start": f"{tomorrow_str}T09:00:00Z",
                "end": f"{tomorrow_str}T09:30:00Z",
                "location": "Conference Room A",
                "description": "Daily team sync",
                "attendees": ["alice@example.com", "bob@example.com"],
                "tags": ["meeting", "daily", "team"]
            },
            {
                "title": "Product Review",
                "start": f"{tomorrow_str}T14:00:00Z",
                "end": f"{tomorrow_str}T15:00:00Z",
                "location": "Zoom",
                "description": "Q1 roadmap review",
                "tags": ["meeting", "product"]
            },
            {
                "title": "1:1 with Manager",
                "start": f"{tomorrow_str}T16:00:00Z",
                "end": f"{tomorrow_str}T16:30:00Z",
                "location": "Office",
                "description": "Weekly check-in",
                "tags": ["meeting", "1:1"]
            }
        ]

        created_events = []
        for event_data in events_to_create:
            try:
                result = await create_event(client, token, event_data)
                created_events.append(result)
                print(f"   Created: {result['data']['title']} (id: {result['id'][:8]}...)")
            except httpx.HTTPStatusError as e:
                print(f"   Error creating {event_data['title']}: {e.response.text}")

        # List all events
        print("\n3. Listing all events...")
        events = await list_events(client, token)
        print(f"   Found {len(events)} events:")
        for event in events:
            print(f"   - {event['data']['title']} @ {event['data'].get('location', 'TBD')}")
            print(f"     Created by: {event['created_by_type']} ({event['created_by_id'][:8]}...)")

        # Query with filter
        print("\n4. Querying events with 'team' tag...")
        team_events = await query_events(client, token, {"tags": ["team"]})
        print(f"   Found {len(team_events)} team events:")
        for event in team_events:
            print(f"   - {event['data']['title']}")

        # Full-text search
        print("\n5. Searching for 'roadmap'...")
        search_results = await search_events(client, token, "roadmap")
        print(f"   Found {len(search_results)} matching events:")
        for event in search_results:
            print(f"   - {event['data']['title']}: {event['data'].get('description', '')}")

        # Show attribution
        print("\n6. Event Attribution Summary:")
        print("   All events show:")
        print("   - created_by_type: 'user' (because you created them)")
        print("   - created_by_id: your user ID")
        print("   When an AGENT creates events, it will show:")
        print("   - created_by_type: 'agent'")
        print("   - created_by_id: agent ID")

    print("\n" + "=" * 60)
    print("Demo complete! Try the API directly:")
    print("  curl -H 'Authorization: Bearer $TOKEN' \\")
    print("       http://localhost:8005/api/workspace/events")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
