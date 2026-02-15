/**
 * Integration Types
 *
 * Types for external service integrations (Discord, Slack, GitHub, etc.)
 * managed through Mimic service.
 */

// === Enums ===

export type IntegrationProvider =
  | 'discord'
  | 'slack'
  | 'github'
  | 'stripe'
  | 'twitter'
  | 'custom_webhook';

export type IntegrationDirection =
  | 'inbound'      // Receive webhooks
  | 'outbound'     // Send messages/actions
  | 'bidirectional';

export type IntegrationStatus =
  | 'active'
  | 'paused'
  | 'error';

// === Integration Model ===

export interface Integration {
  id: string;
  name: string;
  provider: IntegrationProvider;
  direction: IntegrationDirection;
  status: IntegrationStatus;
  webhook_url?: string | null;
  inbound_config?: InboundConfig | null;
  outbound_config?: OutboundConfig | null;
  created_at?: string;
  updated_at?: string;
}

export interface InboundConfig {
  webhook_path: string;
  webhook_url: string;
  auth_method: 'none' | 'api_key' | 'signature' | 'ed25519' | 'bearer';
  event_filters?: string[];
  transform_template?: string;
  destination_service: 'tentackl' | 'custom';
  destination_config?: Record<string, unknown>;
  is_active: boolean;
}

export interface OutboundConfig {
  action_type: string;
  default_template?: Record<string, unknown>;
  rate_limit_requests?: number;
  rate_limit_window_seconds?: number;
  is_active: boolean;
}

// === Response Types ===

export interface IntegrationListResponse {
  items: Integration[];
  total: number;
}

// === Request Types ===

export interface CreateIntegrationRequest {
  name: string;
  provider: IntegrationProvider;
  direction?: IntegrationDirection;
  webhook_url?: string;
}

export interface UpdateIntegrationRequest {
  name?: string;
  status?: IntegrationStatus;
  webhook_url?: string;
}

export interface OutboundConfigRequest {
  action_type: string;
  default_template?: Record<string, unknown>;
  rate_limit_requests?: number;
  rate_limit_window_seconds?: number;
}

export interface InboundConfigRequest {
  webhook_path?: string;
  auth_method?: 'none' | 'api_key' | 'signature' | 'ed25519' | 'bearer';
  signature_secret?: string;
  event_filters?: string[];
  transform_template?: string;
  destination_service?: 'tentackl' | 'custom';
  destination_config?: Record<string, unknown>;
}

export interface CredentialRequest {
  credential_type: 'api_key' | 'webhook_url' | 'oauth_token' | 'bot_token' | 'webhook_secret';
  value: string;
  metadata?: Record<string, unknown>;
  expires_at?: string;
}

// === UI Helper Types ===

export interface IntegrationOption {
  value: string;
  label: string;
  provider: IntegrationProvider;
  direction: IntegrationDirection;
  status: IntegrationStatus;
}

// Provider display configuration with capabilities
export const PROVIDER_CONFIG: Record<IntegrationProvider, {
  label: string;
  color: string;
  defaultName: string;
  supportedDirections: IntegrationDirection[];
  defaultDirection: IntegrationDirection;
  webhookHint?: string;
}> = {
  discord: {
    label: 'Discord',
    color: '#5865F2',
    defaultName: 'My Discord Integration',
    supportedDirections: ['inbound', 'outbound', 'bidirectional'],
    defaultDirection: 'bidirectional',
    webhookHint: 'Discord webhook URL from Server Settings → Integrations',
  },
  slack: {
    label: 'Slack',
    color: '#4A154B',
    defaultName: 'My Slack Integration',
    supportedDirections: ['inbound', 'outbound', 'bidirectional'],
    defaultDirection: 'bidirectional',
    webhookHint: 'Slack incoming webhook URL from your Slack app',
  },
  github: {
    label: 'GitHub',
    color: '#181717',
    defaultName: 'My GitHub Integration',
    supportedDirections: ['inbound', 'outbound', 'bidirectional'],
    defaultDirection: 'inbound',
    webhookHint: 'GitHub will send events to your webhook endpoint',
  },
  stripe: {
    label: 'Stripe',
    color: '#635BFF',
    defaultName: 'My Stripe Integration',
    supportedDirections: ['inbound'],
    defaultDirection: 'inbound',
    webhookHint: 'Stripe will send payment events to your webhook endpoint',
  },
  twitter: {
    label: 'X (Twitter)',
    color: '#000000',
    defaultName: 'My X Integration',
    supportedDirections: ['outbound'],
    defaultDirection: 'outbound',
    webhookHint: 'Connect your X account via OAuth after creating',
  },
  custom_webhook: {
    label: 'Custom Webhook',
    color: '#6B7280',
    defaultName: 'My Webhook Integration',
    supportedDirections: ['inbound', 'outbound', 'bidirectional'],
    defaultDirection: 'bidirectional',
    webhookHint: 'External webhook endpoint URL',
  },
};

// Ordered list of providers for the dropdown
export const PROVIDER_OPTIONS: IntegrationProvider[] = [
  'discord',
  'slack',
  'github',
  'stripe',
  'twitter',
  'custom_webhook',
];

// Direction display configuration
export const DIRECTION_CONFIG: Record<IntegrationDirection, {
  label: string;
  description: string;
}> = {
  inbound: { label: 'Inbound', description: 'Receive webhooks' },
  outbound: { label: 'Outbound', description: 'Send messages' },
  bidirectional: { label: 'Both', description: 'Receive and send' },
};

// Status display configuration
export const STATUS_CONFIG: Record<IntegrationStatus, {
  label: string;
  color: string;
  dotColor: string;
}> = {
  active: { label: 'ACTIVE', color: 'text-emerald-500', dotColor: 'bg-emerald-500' },
  paused: { label: 'PAUSED', color: 'text-[var(--muted-foreground)]', dotColor: 'bg-[var(--muted-foreground)]' },
  error: { label: 'ERROR', color: 'text-[var(--destructive)]', dotColor: 'bg-[var(--destructive)]' },
};
