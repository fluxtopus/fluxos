/**
 * Integration API Service
 *
 * Handles communication with the Tentackl /api/integrations endpoints
 * which proxy to Mimic for integration management.
 */

import api from './api';
import type {
  Integration,
  IntegrationListResponse,
  CreateIntegrationRequest,
  UpdateIntegrationRequest,
  OutboundConfigRequest,
  InboundConfigRequest,
  CredentialRequest,
  OutboundConfig,
  InboundConfig,
  IntegrationProvider,
  IntegrationDirection,
  IntegrationStatus,
} from '../types/integration';
import type { IntegrationEvent, IntegrationSSECallbacks } from '../types/trigger';
import { useAuthStore } from '../store/authStore';

// Base URL for SSE (needs full URL, not relative)
const getBaseUrl = (): string => {
  if (typeof window !== 'undefined') {
    return process.env.NEXT_PUBLIC_API_URL || window.location.origin;
  }
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
};

// ============================================
// Integration Management
// ============================================

/**
 * List all integrations for the current user's organization
 */
export async function listIntegrations(
  provider?: IntegrationProvider,
  direction?: IntegrationDirection,
  status?: IntegrationStatus,
): Promise<IntegrationListResponse> {
  const params = new URLSearchParams();
  if (provider) params.append('provider', provider);
  if (direction) params.append('direction', direction);
  if (status) params.append('status', status);

  const queryString = params.toString();
  const url = queryString ? `/api/integrations?${queryString}` : '/api/integrations';

  const { data } = await api.get<IntegrationListResponse>(url);
  return data;
}

/**
 * Get a single integration by ID
 */
export async function getIntegration(integrationId: string): Promise<Integration> {
  const { data } = await api.get<Integration>(`/api/integrations/${integrationId}`);
  return data;
}

/**
 * Create a new integration
 */
export async function createIntegration(
  request: CreateIntegrationRequest,
): Promise<Integration> {
  const { data } = await api.post<Integration>('/api/integrations', {
    name: request.name,
    provider: request.provider,
    direction: request.direction || 'bidirectional',
    webhook_url: request.webhook_url,
  });
  return data;
}

/**
 * Update an integration
 */
export async function updateIntegration(
  integrationId: string,
  request: UpdateIntegrationRequest,
): Promise<Integration> {
  const { data } = await api.put<Integration>(
    `/api/integrations/${integrationId}`,
    request,
  );
  return data;
}

/**
 * Delete an integration
 */
export async function deleteIntegration(integrationId: string): Promise<void> {
  await api.delete(`/api/integrations/${integrationId}`);
}

/**
 * Get the webhook URL for an integration
 */
export async function getWebhookUrl(
  integrationId: string,
): Promise<{ integration_id: string; webhook_url: string }> {
  const { data } = await api.get<{ integration_id: string; webhook_url: string }>(
    `/api/integrations/${integrationId}/webhook-url`,
  );
  return data;
}

// ============================================
// Config Management
// ============================================

/**
 * Set outbound action configuration for an integration
 */
export async function setOutboundConfig(
  integrationId: string,
  config: OutboundConfigRequest,
): Promise<OutboundConfig> {
  const { data } = await api.put<OutboundConfig>(
    `/api/integrations/${integrationId}/outbound`,
    config,
  );
  return data;
}

/**
 * Set inbound webhook configuration for an integration
 */
export async function setInboundConfig(
  integrationId: string,
  config: InboundConfigRequest,
): Promise<InboundConfig> {
  const { data } = await api.put<InboundConfig>(
    `/api/integrations/${integrationId}/inbound`,
    config,
  );
  return data;
}

/**
 * Add a credential to an integration
 */
export async function addCredential(
  integrationId: string,
  credential: CredentialRequest,
): Promise<Record<string, unknown>> {
  const { data } = await api.post<Record<string, unknown>>(
    `/api/integrations/${integrationId}/credentials`,
    credential,
  );
  return data;
}

/**
 * Test/validate inbound webhook configuration
 */
export async function testInboundConfig(
  integrationId: string,
): Promise<{ success: boolean; message: string; checks: Array<{ name: string; passed: boolean }> }> {
  const { data } = await api.post(`/api/integrations/${integrationId}/inbound/test`);
  return data;
}

// ============================================
// Helpers
// ============================================

/**
 * Filter integrations by direction capability
 * Useful for finding integrations that can receive webhooks or send actions
 */
export function filterByCapability(
  integrations: Integration[],
  capability: 'inbound' | 'outbound',
): Integration[] {
  return integrations.filter((integration) => {
    if (capability === 'inbound') {
      return integration.direction === 'inbound' || integration.direction === 'bidirectional';
    }
    return integration.direction === 'outbound' || integration.direction === 'bidirectional';
  });
}

/**
 * Get active integrations only
 */
export function getActiveIntegrations(integrations: Integration[]): Integration[] {
  return integrations.filter((i) => i.status === 'active');
}

/**
 * Observe integration events via SSE
 */
export async function observeIntegrationEvents(
  integrationId: string,
  callbacks: IntegrationSSECallbacks
): Promise<AbortController> {
  const controller = new AbortController();
  let token = localStorage.getItem('auth_token');

  const makeRequest = (authToken: string | null) =>
    fetch(`${getBaseUrl()}/api/integrations/${integrationId}/events`, {
      method: 'GET',
      headers: {
        Accept: 'text/event-stream',
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      },
      signal: controller.signal,
    });

  try {
    let response = await makeRequest(token);

    // On 401, try refreshing the token once before giving up
    if (response.status === 401) {
      const refreshed = await useAuthStore.getState().refreshAccessToken();
      if (refreshed) {
        token = localStorage.getItem('auth_token');
        response = await makeRequest(token);
      }
    }

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('Failed to get response reader');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    const processStream = async () => {
      try {
        while (true) {
          const { done, value } = await reader.read();

          if (done) {
            callbacks.onStreamEnd?.();
            break;
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          let eventType = 'message';
          let eventData = '';

          for (const line of lines) {
            if (line.startsWith('event:')) {
              eventType = line.slice(6).trim();
            } else if (line.startsWith('data:')) {
              eventData = line.slice(5).trim();
            } else if (line === '' && eventData) {
              // End of event
              if (eventType === 'connected') {
                callbacks.onConnected?.();
              } else if (eventType === 'error') {
                try {
                  const errorObj = JSON.parse(eventData);
                  callbacks.onError?.(errorObj.error || 'Unknown error');
                } catch {
                  callbacks.onError?.(eventData);
                }
              } else if (eventType.startsWith('integration.')) {
                try {
                  const event = JSON.parse(eventData) as IntegrationEvent;
                  callbacks.onEvent?.(event);
                } catch (e) {
                  console.error('Failed to parse integration event:', e);
                }
              }
              eventType = 'message';
              eventData = '';
            }
          }
        }
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') {
          return;
        }
        const streamErrMsg = error instanceof Error ? error.message : 'Stream error';
        callbacks.onError?.(streamErrMsg);
        callbacks.onStreamEnd?.();
      }
    };

    processStream();
    return controller;
  } catch (error) {
    const connectErrMsg = error instanceof Error ? error.message : 'Failed to connect';
    callbacks.onError?.(connectErrMsg);
    throw error;
  }
}
