'use client';

import { useEffect, useRef, useCallback } from 'react';
import { observeExecution, type StreamCallbacks, type PlanningEventData } from '../services/taskApi';

export interface TaskSSECallbacks {
  /** Called when the SSE connection is established */
  onConnected?: () => void;
  /** Called when a step starts executing */
  onStepStarted?: (stepId: string, stepName: string) => void;
  /** Called when a step completes successfully */
  onStepCompleted?: (stepId: string, stepName: string, outputs: Record<string, unknown>) => void;
  /** Called when a step fails */
  onStepFailed?: (stepId: string, error: string) => void;
  /** Called when a checkpoint is created */
  onCheckpoint?: (checkpoint: { step_id: string; checkpoint_name: string; preview_data: Record<string, unknown> }) => void;
  /** Called when the task completes */
  onComplete?: (result: Record<string, unknown>) => void;
  /** Called when the task fails */
  onError?: (error: string) => void;
  /** Called when the SSE stream ends */
  onStreamEnd?: () => void;
  /** Called on any status change - use this to trigger a refetch */
  onStatusChange?: () => void;
  /** Called when a planning progress event is received */
  onPlanningProgress?: (event: PlanningEventData) => void;
}

/**
 * useTaskSSE - Hook for Server-Sent Events observation of task execution.
 *
 * This is a pure observation hook - it does NOT start execution.
 * Use the task API to start execution, then this hook to observe.
 *
 * The hook automatically:
 * - Connects to SSE when taskId is provided and shouldConnect is true
 * - Cleans up the connection on unmount or when taskId changes
 * - Reconnects if the connection is lost
 *
 * Usage:
 * ```tsx
 * useTaskSSE(taskId, {
 *   onStatusChange: refetch, // Refetch task when status changes
 *   onStepCompleted: (stepId, name) => console.log(`Step ${name} completed`),
 * });
 * ```
 */
export function useTaskSSE(
  taskId: string | null,
  callbacks: TaskSSECallbacks,
  shouldConnect: boolean = true
) {
  const abortRef = useRef<AbortController | null>(null);
  const callbacksRef = useRef(callbacks);

  // Update callbacks ref to avoid stale closures
  useEffect(() => {
    callbacksRef.current = callbacks;
  }, [callbacks]);

  const disconnect = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
  }, []);

  const connect = useCallback(async () => {
    if (!taskId || !shouldConnect) return;

    // Clean up any existing connection
    disconnect();

    const streamCallbacks: StreamCallbacks = {
      onStepStarted: (stepId, stepName) => {
        callbacksRef.current.onStepStarted?.(stepId, stepName);
        callbacksRef.current.onStatusChange?.();
      },
      onStepCompleted: (stepId, stepName, outputs) => {
        callbacksRef.current.onStepCompleted?.(stepId, stepName, outputs);
        callbacksRef.current.onStatusChange?.();
      },
      onStepFailed: (stepId, error) => {
        callbacksRef.current.onStepFailed?.(stepId, error);
        callbacksRef.current.onStatusChange?.();
      },
      onCheckpoint: (checkpoint) => {
        callbacksRef.current.onCheckpoint?.(checkpoint);
        callbacksRef.current.onStatusChange?.();
      },
      onComplete: (result) => {
        callbacksRef.current.onComplete?.(result);
        callbacksRef.current.onStatusChange?.();
      },
      onError: (error) => {
        callbacksRef.current.onError?.(error);
        callbacksRef.current.onStatusChange?.();
      },
      onStreamEnd: () => {
        callbacksRef.current.onStreamEnd?.();
        // Always trigger a status change on stream end to get final state
        callbacksRef.current.onStatusChange?.();
      },
      onPlanningProgress: (event) => {
        callbacksRef.current.onPlanningProgress?.(event);
        callbacksRef.current.onStatusChange?.();
      },
    };

    try {
      abortRef.current = await observeExecution(taskId, streamCallbacks);
      callbacksRef.current.onConnected?.();
    } catch (error) {
      console.error('Failed to connect to SSE:', error);
      callbacksRef.current.onError?.(
        error instanceof Error ? error.message : 'Failed to connect to stream'
      );
    }
  }, [taskId, shouldConnect, disconnect]);

  // Connect when taskId changes or shouldConnect becomes true
  useEffect(() => {
    if (shouldConnect && taskId) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
  }, [taskId, shouldConnect, connect, disconnect]);

  return {
    disconnect,
    reconnect: connect,
  };
}
