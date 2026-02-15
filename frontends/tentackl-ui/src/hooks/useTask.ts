'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { getTask } from '../services/taskApi';
import type { Task } from '../types/task';

// Active statuses that should trigger polling as a fallback
const ACTIVE_STATUSES = ['planning', 'executing', 'checkpoint'];

// Polling interval in ms (5 seconds as fallback)
const POLLING_INTERVAL = 5000;

/**
 * useTask - Hook for fetching a single task by ID.
 *
 * Server state is the source of truth. This hook:
 * - Fetches the task on mount and when taskId changes
 * - Provides a refetch function for manual updates
 * - Returns loading and error states
 * - Polls every 5s for active tasks as a fallback to SSE
 *
 * Usage:
 * ```tsx
 * const { task, isLoading, error, refetch } = useTask(taskId);
 * ```
 */
export function useTask(taskId: string | null) {
  const [task, setTask] = useState<Task | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  const refetch = useCallback(async () => {
    if (!taskId) {
      setTask(null);
      setIsLoading(false);
      return;
    }

    try {
      const data = await getTask(taskId);
      setTask(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e : new Error('Failed to fetch task'));
    }
  }, [taskId]);

  // Initial fetch
  useEffect(() => {
    setIsLoading(true);
    setError(null);
    refetch().finally(() => setIsLoading(false));
  }, [taskId, refetch]);

  // Polling for active tasks - fallback to SSE
  useEffect(() => {
    // Clear existing interval
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }

    // Only poll for active tasks
    if (task && ACTIVE_STATUSES.includes(task.status)) {
      pollingRef.current = setInterval(() => {
        refetch();
      }, POLLING_INTERVAL);
    }

    // Cleanup on unmount or when task changes
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [task?.status, refetch]);

  return { task, isLoading, error, refetch };
}

/**
 * Derive display phase from task status.
 * This replaces the separate "phase" state in the store.
 */
export function getTaskPhase(task: Task | null): TaskPhase {
  if (!task) return 'loading';

  switch (task.status) {
    case 'planning':
      return 'planning';
    case 'ready':
      return 'ready';
    case 'executing':
      return 'executing';
    case 'checkpoint':
      return 'checkpoint';
    case 'paused':
      return 'paused';
    case 'completed':
      return 'completed';
    case 'failed':
      return 'failed';
    case 'cancelled':
      return 'cancelled';
    case 'superseded':
      return 'superseded';
    default:
      return 'loading';
  }
}

export type TaskPhase =
  | 'loading'
  | 'planning'
  | 'ready'
  | 'executing'
  | 'checkpoint'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'superseded';
