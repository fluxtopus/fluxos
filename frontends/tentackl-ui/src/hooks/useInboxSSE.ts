'use client';

import { useEffect, useRef, useCallback } from 'react';
import { observeInbox } from '../services/inboxApi';
import type { InboxItem, InboxReadStatus } from '../types/inbox';

export interface InboxSSEHookCallbacks {
  /** Called when a new inbox message arrives */
  onNewMessage?: (item: InboxItem) => void;
  /** Called when a conversation's read status is updated */
  onStatusUpdated?: (conversationId: string, newStatus: InboxReadStatus) => void;
  /** Called when an SSE error occurs */
  onError?: (error: string) => void;
}

const MAX_BACKOFF_MS = 30_000;
const INITIAL_BACKOFF_MS = 1_000;

/**
 * useInboxSSE - Hook for Server-Sent Events observation of inbox updates.
 *
 * Connects to the inbox SSE endpoint for real-time notifications.
 * Auto-reconnects with exponential backoff (1s, 2s, 4s, ... max 30s).
 *
 * Use at the layout level so the unread badge updates even when
 * the user is not on the inbox page.
 *
 * Usage:
 * ```tsx
 * const { disconnect, reconnect } = useInboxSSE({
 *   onNewMessage: (item) => refreshUnreadCount(),
 *   onStatusUpdated: (id, status) => updateItem(id, status),
 * }, shouldConnect);
 * ```
 */
export function useInboxSSE(
  callbacks: InboxSSEHookCallbacks,
  shouldConnect: boolean = true
) {
  const abortRef = useRef<AbortController | null>(null);
  const callbacksRef = useRef(callbacks);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backoffRef = useRef(INITIAL_BACKOFF_MS);
  const mountedRef = useRef(true);

  // Update callbacks ref to avoid stale closures
  useEffect(() => {
    callbacksRef.current = callbacks;
  }, [callbacks]);

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const disconnect = useCallback(() => {
    clearReconnectTimer();
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
  }, [clearReconnectTimer]);

  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current) return;

    clearReconnectTimer();
    const delay = backoffRef.current;
    backoffRef.current = Math.min(delay * 2, MAX_BACKOFF_MS);

    reconnectTimerRef.current = setTimeout(() => {
      if (mountedRef.current) {
        connect();
      }
    }, delay);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clearReconnectTimer]);

  const connect = useCallback(async () => {
    if (!shouldConnect) return;

    // Check authentication
    const token = typeof window !== 'undefined'
      ? localStorage.getItem('auth_token')
      : null;
    if (!token) return;

    // Clean up any existing connection
    disconnect();

    try {
      abortRef.current = await observeInbox({
        onNewMessage: (data) => {
          // Reset backoff on successful message
          backoffRef.current = INITIAL_BACKOFF_MS;
          callbacksRef.current.onNewMessage?.(data as unknown as InboxItem);
        },
        onStatusUpdated: (data) => {
          backoffRef.current = INITIAL_BACKOFF_MS;
          const conversationId = (data as Record<string, unknown>).conversation_id as string;
          const newStatus = (data as Record<string, unknown>).read_status as InboxReadStatus;
          callbacksRef.current.onStatusUpdated?.(conversationId, newStatus);
        },
        onError: (error) => {
          callbacksRef.current.onError?.(error);
          scheduleReconnect();
        },
        onStreamEnd: () => {
          // Stream ended (server closed connection) — reconnect
          scheduleReconnect();
        },
      });
      // Connected successfully — reset backoff
      backoffRef.current = INITIAL_BACKOFF_MS;
    } catch (error) {
      console.error('Failed to connect to inbox SSE:', error);
      callbacksRef.current.onError?.(
        error instanceof Error ? error.message : 'Failed to connect to inbox stream'
      );
      scheduleReconnect();
    }
  }, [shouldConnect, disconnect, scheduleReconnect]);

  // Connect/disconnect based on shouldConnect
  useEffect(() => {
    mountedRef.current = true;

    if (shouldConnect) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      mountedRef.current = false;
      disconnect();
    };
  }, [shouldConnect, connect, disconnect]);

  return {
    disconnect,
    reconnect: connect,
  };
}
