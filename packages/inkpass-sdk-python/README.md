# inkPass SDK for Python

Official Python SDK for inkPass - Authentication & Authorization Service

[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- ✅ **Type-safe** - Full type hints and Pydantic models
- ✅ **Async/await** - Built on httpx for modern async Python
- ✅ **Automatic retries** - Configurable retry logic with exponential backoff
- ✅ **Error handling** - Comprehensive exception hierarchy
- ✅ **Fail-safe** - Permission checks default to deny on errors
- ✅ **Well-tested** - Extensive test coverage
- ✅ **Easy integration** - Simple FastAPI middleware patterns

## Installation

### From Source (Development)

```bash
# From the monorepo root:
cd packages/inkpass-sdk-python

# Install in development mode
pip install -e ".[dev]"
```

### From Package (Production)

```bash
# Once published to PyPI
pip install inkpass-sdk
```

## Quick Start

### Basic Usage

```python
import asyncio
from inkpass_sdk import InkPassClient, InkPassConfig

async def main():
    # Initialize client
    config = InkPassConfig(base_url="http://inkpass:8000")
    client = InkPassClient(config)

    # Register user
    registration = await client.register(
        email="user@example.com",
        password="SecurePassword123!",
        organization_name="My Organization"
    )

    # Login
    tokens = await client.login(
        email="user@example.com",
        password="SecurePassword123!"
    )

    # Validate token
    user = await client.validate_token(tokens.access_token)
    print(f"Logged in as: {user.email}")

    # Check permission
    can_create = await client.check_permission(
        token=tokens.access_token,
        resource="workflows",
        action="create"
    )
    print(f"Can create workflows: {can_create}")

    # Clean up
    await client.close()

asyncio.run(main())
```

### Context Manager (Recommended)

```python
from inkpass_sdk import InkPassClient, InkPassConfig

async def main():
    config = InkPassConfig(base_url="http://inkpass:8000")

    # Automatically closes on exit
    async with InkPassClient(config) as client:
        user = await client.validate_token(token)
        # ... do work
```

## FastAPI Integration

```python
from typing import Annotated
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from inkpass_sdk import InkPassClient, InkPassConfig

app = FastAPI()
security = HTTPBearer()

# Initialize inkPass client
inkpass_client = InkPassClient(InkPassConfig(base_url="http://inkpass:8000"))

# Dependency: Get current user
async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]
):
    user = await inkpass_client.validate_token(credentials.credentials)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user

# Dependency: Require permission
def require_permission(resource: str, action: str):
    async def checker(
        user=Depends(get_current_user),
        credentials=Depends(security)
    ):
        has_perm = await inkpass_client.check_permission(
            credentials.credentials, resource, action
        )
        if not has_perm:
            raise HTTPException(status_code=403, detail="Permission denied")
        return user
    return checker

# Protected route with permission
@app.post("/workflows")
async def create_workflow(
    user=Depends(require_permission("workflows", "create"))
):
    return {"workflow": "created"}
```

## API Reference

### Client Configuration

```python
from inkpass_sdk import InkPassConfig

config = InkPassConfig(
    base_url="http://inkpass:8000",  # inkPass service URL
    api_key="optional-service-key",   # For service-to-service auth
    timeout=5.0,                       # Request timeout (seconds)
    max_retries=3,                     # Maximum retry attempts
    retry_min_wait=1,                  # Min wait between retries (seconds)
    retry_max_wait=10,                 # Max wait between retries (seconds)
    verify_ssl=True,                   # Verify SSL certificates
)
```

### Client Methods

#### `register(email, password, organization_name=None)`
Register a new user.

**Returns**: `RegistrationResponse`

```python
result = await client.register(
    email="user@example.com",
    password="SecurePass123!",
    organization_name="My Org"  # Optional
)
# result.user_id, result.email, result.organization_id
```

#### `login(email, password)`
Authenticate user and get tokens.

**Returns**: `TokenResponse`

```python
tokens = await client.login("user@example.com", "password")
# tokens.access_token, tokens.refresh_token, tokens.expires_in
```

#### `validate_token(token)`
Validate JWT token and get user info.

**Returns**: `UserResponse | None`

```python
user = await client.validate_token(token)
if user:
    print(f"User: {user.email}, Org: {user.organization_id}")
```

#### `check_permission(token, resource, action, context=None)`
Check if user has permission.

**Returns**: `bool` (Fail-safe: returns `False` on errors)

```python
can_create = await client.check_permission(
    token=access_token,
    resource="workflows",
    action="create",
    context={"project_id": "123"}  # Optional ABAC context
)
```

#### `create_api_key(token, name, scopes=None)`
Create a new API key.

**Returns**: `APIKeyResponse`

```python
api_key = await client.create_api_key(
    token=access_token,
    name="Service API Key",
    scopes=["read", "write"]
)
# api_key.key (shown only once!)
```

## Response Models

All responses are Pydantic models with full type safety:

```python
from inkpass_sdk import (
    TokenResponse,
    UserResponse,
    RegistrationResponse,
    PermissionCheckResponse,
    APIKeyResponse,
)

# TokenResponse
tokens: TokenResponse
tokens.access_token: str
tokens.refresh_token: str
tokens.token_type: str
tokens.expires_in: int

# UserResponse
user: UserResponse
user.id: str
user.email: str
user.organization_id: str
user.status: str
user.two_fa_enabled: bool
```

## Exception Handling

```python
from inkpass_sdk import (
    InkPassError,              # Base exception
    AuthenticationError,        # 401 errors
    PermissionDeniedError,      # 403 errors
    ResourceNotFoundError,      # 404 errors
    ValidationError,            # 422 errors
    ServiceUnavailableError,    # 503 errors
)

try:
    user = await client.validate_token(token)
except AuthenticationError as e:
    print(f"Auth failed: {e.message}")
except ServiceUnavailableError as e:
    print(f"Service down: {e.message}")
except InkPassError as e:
    print(f"Error: {e.message} (status: {e.status_code})")
```

## Advanced Usage

### Custom Retry Configuration

```python
config = InkPassConfig(
    base_url="http://inkpass:8000",
    max_retries=5,          # More retries
    retry_min_wait=2,       # Wait longer between retries
    retry_max_wait=30,
)
```

### Service-to-Service Authentication

```python
# Use API key instead of user tokens
config = InkPassConfig(
    base_url="http://inkpass:8000",
    api_key="your-service-api-key"
)

client = InkPassClient(config)
# Client will automatically use API key for requests
```

### Disable SSL Verification (Development Only)

```python
config = InkPassConfig(
    base_url="https://inkpass:8443",
    verify_ssl=False  # NOT recommended for production!
)
```

## File Management (Den)

The SDK includes a `FileClient` for managing files in InkPass Den storage. This is primarily used for service-to-service communication (e.g., Tentackl agents uploading/downloading files).

### FileClient Usage

```python
from inkpass_sdk.files import FileClient
from uuid import UUID

# Initialize client with service API key
file_client = FileClient(
    base_url="http://inkpass:8002",
    service_api_key="sk_tentackl_xxx"
)

# Upload a file
with open("output.png", "rb") as f:
    result = await file_client.upload(
        org_id=UUID("org-uuid"),
        workflow_id="wf-123",
        agent_id="image-gen",
        file_data=f,
        filename="generated-image.png",
        content_type="image/png",
        folder_path="/agent-outputs",
        tags=["generated", "marketing"],
        is_public=True,  # CDN-accessible
    )
    print(f"Uploaded: {result['id']}")

# Download a file
data = await file_client.download(
    org_id=UUID("org-uuid"),
    file_id=UUID("file-uuid"),
)
content = data.read()

# Get a temporary download URL (signed)
url = await file_client.get_download_url(
    org_id=UUID("org-uuid"),
    file_id=UUID("file-uuid"),
    expires_in=3600,  # 1 hour
)

# List files
files = await file_client.list_files(
    org_id=UUID("org-uuid"),
    workflow_id="wf-123",
    folder_path="/agent-outputs",
    tags=["marketing"],
)

# Delete a file (must be created by this agent or be temporary)
await file_client.delete(
    org_id=UUID("org-uuid"),
    file_id=UUID("file-uuid"),
    agent_id="image-gen",
)
```

### Temporary Files

Agents can create temporary files that auto-expire:

```python
result = await file_client.upload(
    org_id=org_id,
    workflow_id="wf-123",
    agent_id="data-processor",
    file_data=temp_data,
    filename="temp-result.json",
    content_type="application/json",
    is_temporary=True,
    expires_in_hours=24,  # Auto-delete after 24 hours
)
```

### Public Files (CDN)

For marketing assets that need CDN delivery:

```python
result = await file_client.upload(
    org_id=org_id,
    workflow_id="wf-marketing",
    agent_id="content-gen",
    file_data=image_data,
    filename="hero-image.png",
    content_type="image/png",
    is_public=True,  # Enables CDN URL
    folder_path="/public/marketing",
)
# result['cdn_url'] will contain the CDN URL
```

## Testing

### Run Tests

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=inkpass_sdk --cov-report=html

# Run specific test
pytest tests/test_client.py::test_login_success
```

### Mock Client for Testing

```python
from unittest.mock import AsyncMock, MagicMock, patch
from inkpass_sdk import InkPassClient, UserResponse

async def test_my_function():
    client = InkPassClient()

    # Mock response
    mock_user = UserResponse(
        id="user-123",
        email="test@example.com",
        organization_id="org-123",
        status="active",
        two_fa_enabled=False,
    )

    with patch.object(client, 'validate_token', return_value=mock_user):
        user = await client.validate_token("test-token")
        assert user.email == "test@example.com"
```

## Examples

See the [`examples/`](./examples/) directory for complete examples:

- [`basic_usage.py`](./examples/basic_usage.py) - Basic SDK operations
- [`fastapi_integration.py`](./examples/fastapi_integration.py) - Complete FastAPI integration

Run examples:

```bash
# Basic usage
python examples/basic_usage.py

# FastAPI integration
uvicorn examples.fastapi_integration:app --reload
```

## Best Practices

### 1. Use Context Manager

```python
# ✅ Good - Automatically closes
async with InkPassClient(config) as client:
    user = await client.validate_token(token)

# ❌ Bad - Manual cleanup required
client = InkPassClient(config)
user = await client.validate_token(token)
await client.close()  # Easy to forget!
```

### 2. Reuse Client Instances

```python
# ✅ Good - Reuse connection pool
inkpass_client = InkPassClient(config)

@app.get("/endpoint1")
async def endpoint1():
    return await inkpass_client.validate_token(token)

@app.get("/endpoint2")
async def endpoint2():
    return await inkpass_client.check_permission(token, "resource", "action")

# ❌ Bad - Creates new connection each time
@app.get("/endpoint")
async def endpoint():
    client = InkPassClient(config)  # Don't do this!
    return await client.validate_token(token)
```

### 3. Handle Errors Gracefully

```python
# ✅ Good - Handle specific errors
try:
    user = await client.validate_token(token)
except AuthenticationError:
    return {"error": "Please login again"}
except ServiceUnavailableError:
    return {"error": "Service temporarily unavailable"}
except InkPassError as e:
    logger.error(f"inkPass error: {e}")
    return {"error": "Authentication service error"}

# ❌ Bad - Catch-all
try:
    user = await client.validate_token(token)
except Exception:
    pass  # What went wrong?
```

### 4. Trust Fail-Safe Permission Checks

```python
# Permission checks default to False on errors
# This is intentional for security!

can_delete = await client.check_permission(token, "data", "delete")
if can_delete:
    # Safe to proceed - we know they have permission
    delete_data()
else:
    # Deny access - could be no permission OR service error
    # Either way, safer to deny
    raise PermissionDenied()
```

## Troubleshooting

### Connection Errors

```python
# Check service is running
curl http://inkpass:8000/health

# Verify base_url is correct
config = InkPassConfig(base_url="http://inkpass:8000")  # No trailing slash!
```

### Token Validation Fails

```python
# Check token hasn't expired
tokens = await client.login(email, password)
print(f"Token expires in: {tokens.expires_in} seconds")

# Refresh token if needed (TODO: implement refresh)
```

### Permission Checks Always Return False

```python
# Verify permission exists in inkPass
# Verify user has permission assigned
# Check resource and action names match exactly
```

## Development

### Setup Development Environment

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Run linters
black inkpass_sdk/
ruff check inkpass_sdk/
mypy inkpass_sdk/
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Run tests and linters
6. Submit a pull request

## License

MIT License - see repository root `LICENSE`.

## Support

See https://fluxtopus.com.
