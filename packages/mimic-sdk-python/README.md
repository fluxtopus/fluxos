# Mimic Python SDK

Python SDK for Mimic Notification Service.

## Installation

```bash
pip install -e .
```

## Usage

```python
import asyncio
from mimic import MimicClient

async def main():
    # Initialize client
    client = MimicClient(
        api_key="your-api-key",
        base_url="http://localhost:8000"
    )
    
    # Send notification
    result = await client.send_notification(
        recipient="user@example.com",
        content="Hello from Mimic!",
        provider="email"
    )
    print(f"Delivery ID: {result['delivery_id']}")
    
    # Check status
    status = await client.get_delivery_status(result['delivery_id'])
    print(f"Status: {status['status']}")
    
    # Add provider key (BYOK)
    await client.create_provider_key(
        provider_type="email",
        api_key="SG.your-sendgrid-key",
        from_email="noreply@yourdomain.com"
    )
    
    # Test provider connection
    test_result = await client.test_provider_key("email")
    print(f"Test: {test_result['success']}")

asyncio.run(main())
```

## Examples

See `examples/` directory for more examples.

