/**
 * Triggers API service
 */

import api from './api';
import type {
  Trigger,
  TriggerListResponse,
  TriggerHistoryResponse,
  TriggerSSECallbacks,
  TriggerEvent,
} from '../types/trigger';
import { useAuthStore } from '../store/authStore';

// Base URL for SSE (needs full URL, not relative)
const getBaseUrl = (): string => {
  if (typeof window !== 'undefined') {
    return process.env.NEXT_PUBLIC_API_URL || window.location.origin;
  }
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
};

export async function listTriggers(
  scope?: 'all' | 'org' | 'user'
): Promise<TriggerListResponse> {
  const params = new URLSearchParams();
  if (scope) params.append('scope', scope);
  const queryString = params.toString();
  const url = queryString
    ? `/api/triggers?${queryString}`
    : '/api/triggers';

  const { data } = await api.get<TriggerListResponse>(url);
  return data;
}

export async function getTrigger(taskId: string): Promise<Trigger> {
  const { data } = await api.get<Trigger>(`/api/triggers/${taskId}`);
  return data;
}

export async function getTriggerHistory(
  taskId: string,
  limit: number = 20
): Promise<TriggerHistoryResponse> {
  const { data } = await api.get<TriggerHistoryResponse>(
    `/api/triggers/${taskId}/history`,
    { params: { limit } }
  );
  return data;
}

export async function deleteTrigger(taskId: string): Promise<void> {
  await api.delete(`/api/triggers/${taskId}`);
}

export async function updateTrigger(
  taskId: string,
  updates: { enabled?: boolean }
): Promise<Trigger> {
  const { data } = await api.patch<Trigger>(`/api/triggers/${taskId}`, updates);
  return data;
}

/**
 * Observe trigger events via SSE
 */
export async function observeTriggerEvents(
  taskId: string,
  callbacks: TriggerSSECallbacks
): Promise<AbortController> {
  const controller = new AbortController();
  let token = localStorage.getItem('auth_token');

  const makeRequest = (authToken: string | null) =>
    fetch(`${getBaseUrl()}/api/triggers/${taskId}/events`, {
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
              } else if (eventType.startsWith('trigger.')) {
                try {
                  const event = JSON.parse(eventData) as TriggerEvent;
                  callbacks.onEvent?.(event);
                } catch (e) {
                  console.error('Failed to parse trigger event:', e);
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

// Re-export types for convenience
export type { Trigger, TriggerListResponse, TriggerHistoryResponse, TriggerEvent };
