# Mimic Node.js SDK

Node.js SDK for Mimic Notification Service.

## Installation

```bash
npm install @mimic/notification-sdk
```

## Usage

```javascript
const { MimicClient } = require('@mimic/notification-sdk');

// Initialize client
const client = new MimicClient('your-api-key', 'http://localhost:8000');

// Send notification
const result = await client.sendNotification({
  recipient: 'user@example.com',
  content: 'Hello from Mimic!',
  provider: 'email'
});

console.log(`Delivery ID: ${result.delivery_id}`);

// Check status
const status = await client.getDeliveryStatus(result.delivery_id);
console.log(`Status: ${status.status}`);

// Add provider key (BYOK)
await client.createProviderKey('email', {
  api_key: 'SG.your-sendgrid-key',
  from_email: 'noreply@yourdomain.com'
});

// Test provider connection
const testResult = await client.testProviderKey('email');
console.log(`Test: ${testResult.success}`);
```

## TypeScript

```typescript
import { MimicClient } from '@mimic/notification-sdk';

const client = new MimicClient('your-api-key');
// Full TypeScript support
```

