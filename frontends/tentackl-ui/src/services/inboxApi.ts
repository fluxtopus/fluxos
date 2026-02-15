/**
 * Inbox API Service
 *
 * Handles all communication with the inbox backend endpoints.
 * SSE streaming for real-time inbox updates.
 */

import api from './api';
import type {
  InboxReadStatus,
  InboxListResponse,
  InboxThread,
  InboxQueryParams,
  InboxChatSSECallbacks,
} from '../types/inbox';
import type { FileReference } from './fileService';

// Base URL for SSE (needs full URL, not relative)
const getBaseUrl = (): string => {
  if (typeof window !== 'undefined') {
    return process.env.NEXT_PUBLIC_API_URL || window.location.origin;
  }
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
};

// ============================================
// Inbox Queries
// ============================================

/**
 * List inbox items with optional filters
 */
export async function listInbox(params?: InboxQueryParams): Promise<InboxListResponse> {
  const { data } = await api.get<InboxListResponse>('/api/inbox', { params });
  return data;
}

/**
 * Get the current unread inbox count
 */
export async function getUnreadCount(): Promise<number> {
  const { data } = await api.get<{ count: number }>('/api/inbox/unread-count');
  return data.count;
}

/**
 * Get the current attention inbox count
 */
export async function getAttentionCount(): Promise<number> {
  const { data } = await api.get<{ count: number }>('/api/inbox/attention-count');
  return data.count;
}

/**
 * Get the full thread for a conversation
 */
export async function getThread(conversationId: string): Promise<InboxThread> {
  const { data } = await api.get<InboxThread>(
    `/api/inbox/${conversationId}/thread`
  );
  return data;
}

// ============================================
// Inbox Mutations
// ============================================

/**
 * Update the read status of a single conversation
 */
export async function updateReadStatus(
  conversationId: string,
  readStatus: InboxReadStatus
): Promise<void> {
  await api.patch(`/api/inbox/${conversationId}`, {
    read_status: readStatus,
  });
}

/**
 * Bulk update read status for multiple conversations
 * Returns the number of updated items.
 */
export async function bulkUpdateReadStatus(
  conversationIds: string[],
  readStatus: InboxReadStatus
): Promise<number> {
  const { data } = await api.patch<{ updated: number }>('/api/inbox/bulk', {
    conversation_ids: conversationIds,
    read_status: readStatus,
  });
  return data.updated;
}

/**
 * Create a follow-up task from a conversation
 */
export async function createFollowUp(
  conversationId: string,
  text: string
): Promise<{ task_id: string; conversation_id: string; goal: string; status: string }> {
  const { data } = await api.post<{
    task_id: string;
    conversation_id: string;
    goal: string;
    status: string;
  }>(`/api/inbox/${conversationId}/follow-up`, { text });
  return data;
}

// ============================================
// SSE Real-time Events
// ============================================

export interface InboxSSECallbacks {
  onNewMessage?: (data: Record<string, unknown>) => void;
  onStatusUpdated?: (data: Record<string, unknown>) => void;
  onError?: (error: string) => void;
  onStreamEnd?: () => void;
}

/**
 * Connect to the inbox SSE event stream for real-time updates.
 * Follows the observeExecution pattern from taskApi.ts.
 */
export async function observeInbox(
  callbacks: InboxSSECallbacks
): Promise<AbortController> {
  const controller = new AbortController();
  const baseUrl = getBaseUrl();
  const token = localStorage.getItem('auth_token');

  try {
    const response = await fetch(`${baseUrl}/api/inbox/events`, {
      method: 'GET',
      headers: {
        Accept: 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      signal: controller.signal,
    });

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
            if (buffer.trim()) {
              processInboxLine(buffer, callbacks);
            }
            callbacks.onStreamEnd?.();
            break;
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            processInboxLine(line, callbacks);
          }
        }
      } catch (error) {
        if ((error as Error).name !== 'AbortError') {
          callbacks.onError?.((error as Error).message || 'Stream error');
        }
      }
    };

    processStream();
  } catch (error) {
    callbacks.onError?.(
      error instanceof Error ? error.message : 'Failed to connect to inbox stream'
    );
  }

  return controller;
}

/**
 * Process a single SSE line from the inbox events endpoint
 */
function processInboxLine(line: string, callbacks: InboxSSECallbacks): void {
  const trimmed = line.trim();
  if (!trimmed || !trimmed.startsWith('data: ')) return;

  const data = trimmed.slice(6);
  if (data === '[DONE]') return;

  try {
    const event = JSON.parse(data);
    handleInboxEvent(event, callbacks);
  } catch (e) {
    console.error('Failed to parse inbox SSE data:', e, data);
  }
}

/**
 * Handle a parsed event from the inbox SSE stream
 */
function handleInboxEvent(
  event: { type: string; [key: string]: unknown },
  callbacks: InboxSSECallbacks
): void {
  switch (event.type) {
    case 'inbox.message.created':
      callbacks.onNewMessage?.(event as Record<string, unknown>);
      break;

    case 'inbox.status.updated':
      callbacks.onStatusUpdated?.(event as Record<string, unknown>);
      break;

    case 'heartbeat':
      // Keep-alive, no action needed
      break;

    default:
      console.log('Unhandled inbox event:', event.type, event);
  }
}

// ============================================
// Inbox Chat (Conversational Agent)
// ============================================

/**
 * Send a chat message to Flux and consume the SSE response.
 *
 * Returns an AbortController to cancel the stream.
 */
export async function sendInboxChatMessage(
  message: string,
  conversationId: string | undefined,
  callbacks: InboxChatSSECallbacks,
  onboarding?: boolean,
  fileReferences?: FileReference[],
): Promise<AbortController> {
  const controller = new AbortController();
  const baseUrl = getBaseUrl();
  const token = localStorage.getItem('auth_token');

  try {
    const response = await fetch(`${baseUrl}/api/inbox/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        message,
        conversation_id: conversationId ?? null,
        ...(onboarding ? { onboarding: true } : {}),
        ...(fileReferences && fileReferences.length > 0 ? { file_references: fileReferences } : {}),
      }),
      signal: controller.signal,
    });

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
            if (buffer.trim()) {
              processChatLine(buffer, callbacks);
            }
            callbacks.onDone?.();
            break;
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            processChatLine(line, callbacks);
          }
        }
      } catch (error) {
        if ((error as Error).name !== 'AbortError') {
          callbacks.onError?.((error as Error).message || 'Stream error');
        }
      }
    };

    processStream();
  } catch (error) {
    callbacks.onError?.(
      error instanceof Error ? error.message : 'Failed to connect to chat stream'
    );
  }

  return controller;
}

/**
 * Process a single SSE line from the chat stream
 */
function processChatLine(line: string, callbacks: InboxChatSSECallbacks): void {
  const trimmed = line.trim();
  if (!trimmed || !trimmed.startsWith('data: ')) return;

  const data = trimmed.slice(6);
  if (data === '[DONE]') {
    callbacks.onDone?.();
    return;
  }

  try {
    const event = JSON.parse(data);

    if (event.conversation_id) {
      callbacks.onConversationId?.(event.conversation_id);
    }
    if (event.status) {
      callbacks.onStatus?.(event.status, event);
    }
    if (event.content) {
      callbacks.onContent?.(event.content);
    }
    if (event.error) {
      callbacks.onError?.(event.error);
    }
    if (event.done) {
      callbacks.onDone?.();
    }
  } catch (e) {
    console.error('Failed to parse chat SSE data:', e, data);
  }
}
