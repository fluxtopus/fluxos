```markdown
# inkPass Client Library

A Python async client library for integrating with the inkPass authentication and authorization service.

## Features

- Async/await API using `httpx`
- Automatic retry logic with exponential backoff
- Comprehensive error handling
- Type hints and docstrings
- Structured logging
- JWT and API key authentication support

## Installation

The client is included in the inkPass package. Required dependencies:

```bash
pip install httpx tenacity structlog
```

## Quick Start

### Basic Usage

```python
from src.clients import InkPassClient, InkPassConfig

# Initialize client
client = InkPassClient(InkPassConfig(
    base_url="http://inkpass:8000"
))

# Register a user
user = await client.register_user(
    email="user@example.com",
    password="secure_password",
    organization_name="My Organization"
)

# Login
tokens = await client.login("user@example.com", "secure_password")
access_token = tokens["access_token"]

# Validate token and get user info
user_info = await client.validate_token(access_token)
print(f"User ID: {user_info['id']}")

# Check permissions
can_create = await client.check_permission(
    access_token,
    resource="workflows",
    action="create"
)

if can_create:
    print("User can create workflows")
else:
    print("User cannot create workflows")

# Clean up
await client.close()
```

### Using as Context Manager

```python
from src.clients import InkPassClient, InkPassConfig

config = InkPassConfig(base_url="http://inkpass:8000")

async with InkPassClient(config) as client:
    # Client automatically closes after context
    user_info = await client.validate_token(token)
    has_perm = await client.check_permission(token, "workflows", "create")
```

### Service-to-Service Authentication

```python
from src.clients import InkPassClient, InkPassConfig

# Use API key for service authentication
config = InkPassConfig(
    base_url="http://inkpass:8000",
    api_key="your-service-api-key"
)

client = InkPassClient(config)

# Client will automatically use API key for requests
user = await client.validate_token(user_token)
```

## Configuration Options

```python
from src.clients import InkPassConfig

config = InkPassConfig(
    base_url="http://inkpass:8000",  # inkPass service URL
    api_key="optional-service-key",   # Optional API key for service auth
    timeout=5.0,                       # Request timeout in seconds
    max_retries=3,                     # Maximum retry attempts
    retry_min_wait=1,                  # Minimum wait between retries (seconds)
    retry_max_wait=10,                 # Maximum wait between retries (seconds)
)
```

## API Reference

### Client Methods

#### `validate_token(token: str) -> Optional[Dict[str, Any]]`

Validate a JWT token and return user information.

**Returns**: User data dict or `None` if invalid

**Raises**:
- `AuthenticationError`: If validation fails
- `InkPassError`: If service unavailable

```python
user = await client.validate_token("jwt-token-here")
if user:
    print(f"User: {user['email']}")
```

#### `check_permission(token: str, resource: str, action: str, context: Optional[Dict] = None) -> bool`

Check if user has permission for a resource and action.

**Returns**: `True` if permission granted, `False` otherwise

**Note**: Defaults to `False` on error (fail-safe)

```python
can_delete = await client.check_permission(
    token="jwt-token",
    resource="workflows",
    action="delete",
    context={"workflow_id": "123"}
)
```

#### `login(email: str, password: str) -> Dict[str, Any]`

Login user and get access tokens.

**Returns**: Dict with `access_token`, `refresh_token`, `token_type`, `expires_in`

**Raises**:
- `AuthenticationError`: If credentials invalid
- `InkPassError`: If service unavailable

```python
tokens = await client.login("user@example.com", "password")
access_token = tokens["access_token"]
```

#### `register_user(email: str, password: str, organization_name: Optional[str] = None) -> Dict[str, Any]`

Register a new user.

**Returns**: Dict with `user_id`, `email`, `organization_id`

**Raises**: `InkPassError` if registration fails

```python
user = await client.register_user(
    email="new@example.com",
    password="secure_pass",
    organization_name="New Org"
)
```

## Error Handling

```python
from src.clients import InkPassClient, AuthenticationError, InkPassError

client = InkPassClient(config)

try:
    user = await client.validate_token(token)
except AuthenticationError as e:
    print(f"Authentication failed: {e}")
except InkPassError as e:
    print(f"Service error: {e}")
```

## Integration with FastAPI

### Dependency Injection

```python
from fastapi import Depends, HTTPException, Request
from src.clients import InkPassClient, InkPassConfig

# Create client instance
inkpass_config = InkPassConfig(base_url="http://inkpass:8000")
inkpass_client = InkPassClient(inkpass_config)

async def get_current_user(request: Request):
    """Dependency to get current user from token"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")

    token = auth_header.replace("Bearer ", "")
    user = await inkpass_client.validate_token(token)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")

    return user

async def require_permission(resource: str, action: str):
    """Dependency to check permission"""
    async def permission_checker(request: Request, user = Depends(get_current_user)):
        auth_header = request.headers.get("Authorization")
        token = auth_header.replace("Bearer ", "")

        has_perm = await inkpass_client.check_permission(token, resource, action)

        if not has_perm:
            raise HTTPException(status_code=403, detail="Permission denied")

        return user

    return permission_checker

# Use in routes
@app.get("/protected")
async def protected_route(user = Depends(get_current_user)):
    return {"message": f"Hello {user['email']}"}

@app.post("/workflows")
async def create_workflow(
    user = Depends(require_permission("workflows", "create"))
):
    return {"message": "Workflow created"}
```

## Best Practices

1. **Reuse client instances**: Create one client and reuse it across requests
2. **Use context managers**: For short-lived clients, use async context manager
3. **Handle errors gracefully**: Always catch `InkPassError` for service failures
4. **Cache validation results**: Consider caching valid tokens for short periods
5. **Use connection pooling**: The client automatically pools connections
6. **Monitor latency**: Track inkPass response times in production
7. **Implement circuit breaker**: Add circuit breaker for resilience

## Testing

```python
from unittest.mock import patch, MagicMock
from src.clients import InkPassClient

async def test_my_function():
    """Test with mocked inkPass client"""
    client = InkPassClient()

    # Mock successful response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "user-123", "email": "test@example.com"}

    with patch.object(httpx.AsyncClient, "get", return_value=mock_response):
        user = await client.validate_token("test-token")
        assert user["id"] == "user-123"
```

## Logging

The client uses `structlog` for structured logging. Configure logging in your application:

```python
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)
```

Log output example:
```json
{
  "event": "Token validated successfully",
  "user_id": "user-123",
  "timestamp": "2025-11-29T18:00:00.000000Z"
}
```

## Contributing

Follow Tentackl architecture patterns:
- Use async/await for all I/O
- Add type hints to all functions
- Write comprehensive docstrings
- Include unit tests for new features
- Follow existing error handling patterns

## License

Same as inkPass project.
```
