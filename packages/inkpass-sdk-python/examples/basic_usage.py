"""
Basic usage example for inkPass SDK.

This example demonstrates the fundamental operations:
- Registering a user
- Logging in
- Validating tokens
- Checking permissions
"""

import asyncio

from inkpass_sdk import InkPassClient, InkPassConfig


async def main() -> None:
    """Run basic usage example."""
    # Initialize client
    config = InkPassConfig(
        base_url="http://localhost:8002",  # Change to your inkPass URL
    )

    async with InkPassClient(config) as client:
        print("=== inkPass SDK Basic Usage Example ===\n")

        # 1. Register a new user
        print("1. Registering user...")
        try:
            registration = await client.register(
                email="demo@example.com",
                password="SecurePassword123!",
                organization_name="Demo Organization",
            )
            print(f"✓ User registered: {registration.email}")
            print(f"  User ID: {registration.user_id}")
            print(f"  Organization ID: {registration.organization_id}\n")
        except Exception as e:
            print(f"✗ Registration failed: {e}\n")
            return

        # 2. Login with credentials
        print("2. Logging in...")
        try:
            tokens = await client.login(
                email="demo@example.com",
                password="SecurePassword123!",
            )
            print(f"✓ Login successful")
            print(f"  Access Token: {tokens.access_token[:20]}...")
            print(f"  Expires in: {tokens.expires_in} seconds\n")
        except Exception as e:
            print(f"✗ Login failed: {e}\n")
            return

        # 3. Validate token and get user info
        print("3. Validating token...")
        user = await client.validate_token(tokens.access_token)
        if user:
            print(f"✓ Token valid")
            print(f"  User: {user.email}")
            print(f"  Status: {user.status}")
            print(f"  2FA Enabled: {user.two_fa_enabled}\n")
        else:
            print("✗ Token invalid\n")

        # 4. Check permissions
        print("4. Checking permission...")
        can_create_workflows = await client.check_permission(
            token=tokens.access_token,
            resource="workflows",
            action="create",
        )
        print(f"  Can create workflows: {can_create_workflows}\n")

        can_delete_workflows = await client.check_permission(
            token=tokens.access_token,
            resource="workflows",
            action="delete",
        )
        print(f"  Can delete workflows: {can_delete_workflows}\n")

        # 5. Create API key
        print("5. Creating API key...")
        try:
            api_key = await client.create_api_key(
                token=tokens.access_token,
                name="Demo API Key",
                scopes=["read", "write"],
            )
            print(f"✓ API key created: {api_key.name}")
            print(f"  Key: {api_key.key[:20]}...")
            print(f"  Scopes: {', '.join(api_key.scopes)}\n")
        except Exception as e:
            print(f"✗ API key creation failed: {e}\n")

        print("=== Example completed ===")


if __name__ == "__main__":
    asyncio.run(main())
