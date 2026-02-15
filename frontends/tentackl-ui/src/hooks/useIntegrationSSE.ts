'use client';

import { useEffect, useRef, useCallback } from 'react';
import { observeIntegrationEvents } from '../services/integrationApi';
import type { IntegrationEvent } from '../types/trigger';

export interface IntegrationSSEHookCallbacks {
  /** Called when an integration event arrives */
  onEvent?: (event: IntegrationEvent) => void;
  /** Called when an SSE error occurs */
  onError?: (error: string) => void;
  /** Called when connected to SSE stream */
  onConnected?: () => void;
}

const MAX_BACKOFF_MS = 30_000;
const INITIAL_BACKOFF_MS = 1_000;

/**
 * useIntegrationSSE - Hook for Server-Sent Events observation of integration events.
 *
 * Connects to the integration SSE endpoint for real-time event notifications.
 * Auto-reconnects with exponential backoff (1s, 2s, 4s, ... max 30s).
 *
 * Usage:
 * ```tsx
 * const { disconnect, reconnect, isConnected } = useIntegrationSSE(integrationId, {
 *   onEvent: (event) => handleEvent(event),
 *   onError: (error) => console.error(error),
 * }, shouldConnect);
 * ```
 */
export function useIntegrationSSE(
  integrationId: string,
  callbacks: IntegrationSSEHookCallbacks,
  shouldConnect: boolean = true
) {
  const abortRef = useRef<AbortController | null>(null);
  const callbacksRef = useRef(callbacks);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backoffRef = useRef(INITIAL_BACKOFF_MS);
  const mountedRef = useRef(true);
  const isConnectedRef = useRef(false);

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
    isConnectedRef.current = false;
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
    if (!shouldConnect || !integrationId) return;

    // Check authentication
    const token = typeof window !== 'undefined'
      ? localStorage.getItem('auth_token')
      : null;
    if (!token) return;

    // Clean up any existing connection
    disconnect();

    try {
      abortRef.current = await observeIntegrationEvents(integrationId, {
        onEvent: (event) => {
          // Reset backoff on successful event
          backoffRef.current = INITIAL_BACKOFF_MS;
          callbacksRef.current.onEvent?.(event);
        },
        onConnected: () => {
          backoffRef.current = INITIAL_BACKOFF_MS;
          isConnectedRef.current = true;
          callbacksRef.current.onConnected?.();
        },
        onError: (error) => {
          callbacksRef.current.onError?.(error);
          scheduleReconnect();
        },
        onStreamEnd: () => {
          isConnectedRef.current = false;
          // Stream ended (server closed connection) — reconnect
          scheduleReconnect();
        },
      });
      // Connected successfully — reset backoff
      backoffRef.current = INITIAL_BACKOFF_MS;
    } catch (error) {
      console.error('Failed to connect to integration SSE:', error);
      callbacksRef.current.onError?.(
        error instanceof Error ? error.message : 'Failed to connect to integration stream'
      );
      scheduleReconnect();
    }
  }, [integrationId, shouldConnect, disconnect, scheduleReconnect]);

  // Connect/disconnect based on shouldConnect and integrationId
  useEffect(() => {
    mountedRef.current = true;

    if (shouldConnect && integrationId) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      mountedRef.current = false;
      disconnect();
    };
  }, [integrationId, shouldConnect, connect, disconnect]);

  return {
    disconnect,
    reconnect: connect,
    isConnected: isConnectedRef.current,
  };
}
