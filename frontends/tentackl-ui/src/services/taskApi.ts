/**
 * Task API Service
 *
 * Handles all communication with the task execution backend.
 * SSE streaming for real-time execution updates.
 */

import api from './api';
import type {
  Task,
  TaskStatus,
  CreateTaskRequest,
  ExecutionResult,
  Checkpoint,
  Preference,
  PreferenceStats,
  ApproveCheckpointRequest,
  RejectCheckpointRequest,
  SSEEvent,
  PlanningEventType,
} from '../types/task';

// Base URL for SSE (needs full URL, not relative)
const getBaseUrl = (): string => {
  if (typeof window !== 'undefined') {
    // In browser, use current origin or env var
    return process.env.NEXT_PUBLIC_API_URL || window.location.origin;
  }
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
};

// ============================================
// Task Management
// ============================================

/**
 * Create a new task from a goal description
 */
export async function createTask(request: CreateTaskRequest): Promise<Task> {
  const { data } = await api.post<Task>('/api/tasks', request);
  return data;
}

/**
 * Get a specific task by ID
 */
export async function getTask(taskId: string): Promise<Task> {
  const { data } = await api.get<Task>(`/api/tasks/${taskId}`);
  return data;
}

/**
 * List user's tasks with optional status filter
 */
export async function listTasks(
  status?: TaskStatus,
  limit: number = 50
): Promise<Task[]> {
  const params: Record<string, unknown> = { limit };
  if (status) params.status = status;
  const { data } = await api.get<Task[]>('/api/tasks', { params });
  return data;
}

/**
 * Pause a running task
 */
export async function pauseTask(taskId: string): Promise<Task> {
  const { data } = await api.post<Task>(`/api/tasks/${taskId}/pause`);
  return data;
}

/**
 * Cancel a task
 */
export async function cancelTask(taskId: string): Promise<Task> {
  const { data } = await api.post<Task>(`/api/tasks/${taskId}/cancel`);
  return data;
}

// ============================================
// Execution (Non-streaming)
// ============================================

/**
 * Execute a task (non-streaming, returns when done or at checkpoint)
 */
export async function executeTask(
  taskId: string,
  runToCompletion: boolean = false
): Promise<ExecutionResult> {
  const { data } = await api.post<ExecutionResult>(
    `/api/tasks/${taskId}/execute`,
    { run_to_completion: runToCompletion }
  );
  return data;
}

// ============================================
// Async Execution (New Architecture)
// ============================================

export interface PlanningEventData {
  type: PlanningEventType;
  task_id: string;
  data: Record<string, unknown>;
}

export interface StreamCallbacks {
  onStepStarted?: (stepId: string, stepName: string) => void;
  onStepCompleted?: (stepId: string, stepName: string, outputs: Record<string, unknown>) => void;
  onStepFailed?: (stepId: string, error: string) => void;
  onProgress?: (completed: number, total: number, currentStep: string) => void;
  onCheckpoint?: (checkpoint: Checkpoint) => void;
  onReplanCheckpoint?: (checkpoint: Checkpoint) => void;
  onRecovery?: (proposal: { proposal_type: string; reason: string; auto_applied?: boolean }) => void;
  onComplete?: (result: Record<string, unknown>) => void;
  onError?: (error: string) => void;
  onStreamEnd?: () => void;
  onPlanningProgress?: (event: PlanningEventData) => void;
}

export interface StartTaskResult {
  status: 'started' | 'already_executing' | 'error';
  task_id: string;
  task?: Task;
  message?: string;
  error?: string;
}

/**
 * Start task execution.
 * Returns immediately after enqueueing the task.
 * Use observeExecution() to watch for real-time updates.
 *
 * Handles 409 (already executing) as success - the task can still be observed.
 */
export async function startTask(taskId: string): Promise<StartTaskResult> {
  try {
    const { data } = await api.post<StartTaskResult>(
      `/api/tasks/${taskId}/start`
    );
    return data;
  } catch (error: unknown) {
    // Handle 409 (already executing) as success
    if (error && typeof error === 'object' && 'response' in error) {
      const axiosError = error as {
        response?: {
          status?: number;
          data?: { status?: string; task?: Task; error?: string; detail?: string; message?: string }
        }
      };

      // 409 Conflict = already executing - this is fine
      if (axiosError.response?.status === 409) {
        return {
          status: 'already_executing',
          task_id: taskId,
          task: axiosError.response.data?.task,
          message: axiosError.response.data?.message || 'Task is already executing',
        };
      }

      // Other errors
      if (axiosError.response?.status && axiosError.response.status >= 400) {
        const errorMsg = axiosError.response.data?.error
          || axiosError.response.data?.detail
          || 'Failed to start task';
        return { status: 'error', task_id: taskId, error: errorMsg };
      }
    }
    throw error;
  }
}

/**
 * @deprecated Use startTask instead
 */
export async function startTaskAsync(taskId: string): Promise<StartTaskResult> {
  return startTask(taskId);
}

/**
 * Observe task execution via SSE (pure observation, no execution logic).
 * Use startTaskAsync() first to begin execution, then connect here to observe.
 */
export async function observeExecution(
  taskId: string,
  callbacks: StreamCallbacks
): Promise<AbortController> {
  const controller = new AbortController();
  const baseUrl = getBaseUrl();
  const token = localStorage.getItem('auth_token');

  try {
    const response = await fetch(
      `${baseUrl}/api/tasks/${taskId}/observe`,
      {
        method: 'GET',
        headers: {
          'Accept': 'text/event-stream',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        signal: controller.signal,
      }
    );

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
              processObserveLine(buffer, callbacks);
            }
            callbacks.onStreamEnd?.();
            break;
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            processObserveLine(line, callbacks);
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
      error instanceof Error ? error.message : 'Failed to connect to stream'
    );
  }

  return controller;
}

/**
 * Process a single SSE line from the observe endpoint
 */
function processObserveLine(line: string, callbacks: StreamCallbacks): void {
  const trimmed = line.trim();
  if (!trimmed || !trimmed.startsWith('data: ')) return;

  const data = trimmed.slice(6);
  if (data === '[DONE]') return;

  try {
    const event = JSON.parse(data);
    handleObserveEvent(event, callbacks);
  } catch (e) {
    console.error('Failed to parse SSE data:', e, data);
  }
}

/**
 * Handle a parsed event from the observe endpoint
 */
function handleObserveEvent(
  event: { type: string; [key: string]: unknown },
  callbacks: StreamCallbacks
): void {
  switch (event.type) {
    case 'connected':
      // Initial connection, no action needed
      console.log('Connected to observe stream:', event);
      break;

    case 'task.step.started':
      if (event.step_id && event.data) {
        const data = event.data as { step_name?: string };
        callbacks.onStepStarted?.(
          event.step_id as string,
          data.step_name || 'Unknown step'
        );
      }
      break;

    case 'task.step.completed':
      if (event.step_id && event.data) {
        const data = event.data as { step_name?: string; output?: Record<string, unknown> };
        callbacks.onStepCompleted?.(
          event.step_id as string,
          data.step_name || 'Unknown step',
          data.output || {}
        );
      }
      break;

    case 'task.step.failed':
      if (event.step_id && event.data) {
        const data = event.data as { error?: string };
        callbacks.onStepFailed?.(
          event.step_id as string,
          data.error || 'Step failed'
        );
      }
      break;

    case 'task.checkpoint.created':
      if (event.step_id && event.data) {
        const data = event.data as {
          checkpoint_name?: string;
          preview?: Record<string, unknown>;
        };
        callbacks.onCheckpoint?.({
          step_id: event.step_id as string,
          checkpoint_name: data.checkpoint_name || 'Checkpoint',
          preview_data: data.preview || {},
        } as Checkpoint);
      }
      break;

    case 'task.checkpoint.auto_approved':
      console.log('Checkpoint auto-approved:', event);
      // Optionally notify about auto-approval
      break;

    case 'task.completed':
      callbacks.onComplete?.(event.data as Record<string, unknown> || {});
      break;

    case 'task.failed':
      if (event.data) {
        const data = event.data as { error?: string };
        callbacks.onError?.(data.error || 'Task failed');
      }
      break;

    case 'heartbeat':
      // Keep-alive, no action needed
      break;

    case 'task_status_update':
    case 'already_terminal':
    case 'plan_status_update':
      // Task finished before we connected
      callbacks.onStreamEnd?.();
      break;

    default:
      // Route planning events to onPlanningProgress
      if (event.type?.startsWith('task.planning.')) {
        callbacks.onPlanningProgress?.({
          type: event.type as PlanningEventType,
          task_id: event.task_id as string,
          data: (event.data as Record<string, unknown>) || {},
        });
      } else {
        console.log('Unhandled observe event:', event.type, event);
      }
  }
}

// ============================================
// Checkpoints
// ============================================

/**
 * Get all pending checkpoints for user
 */
export async function getCheckpoints(): Promise<Checkpoint[]> {
  const response = await api.get<Checkpoint[]>('/api/checkpoints');
  return response?.data ?? [];
}

/**
 * Get checkpoints for a specific task
 */
export async function getTaskCheckpoints(taskId: string): Promise<Checkpoint[]> {
  const { data } = await api.get<Checkpoint[]>(
    `/api/tasks/${taskId}/checkpoints`
  );
  return data;
}

/**
 * Approve a checkpoint
 */
export async function approveCheckpoint(
  taskId: string,
  stepId: string,
  request: ApproveCheckpointRequest = {}
): Promise<Checkpoint> {
  const { data } = await api.post<Checkpoint>(
    `/api/tasks/${taskId}/checkpoints/${stepId}/approve`,
    request
  );
  return data;
}

/**
 * Reject a checkpoint
 */
export async function rejectCheckpoint(
  taskId: string,
  stepId: string,
  request: RejectCheckpointRequest
): Promise<Checkpoint> {
  const { data } = await api.post<Checkpoint>(
    `/api/tasks/${taskId}/checkpoints/${stepId}/reject`,
    request
  );
  return data;
}

// ============================================
// Preferences
// ============================================

/**
 * Get user's learned preferences
 */
export async function getPreferences(): Promise<Preference[]> {
  const { data } = await api.get<Preference[]>('/api/preferences');
  return data;
}

/**
 * Get preference statistics
 */
export async function getPreferenceStats(): Promise<PreferenceStats> {
  const { data } = await api.get<PreferenceStats>(
    '/api/preferences/stats'
  );
  return data;
}

/**
 * Delete a preference
 */
export async function deletePreference(preferenceId: string): Promise<void> {
  await api.delete(`/api/preferences/${preferenceId}`);
}

// ============================================
// Error Mapping (Technical -> User-Friendly)
// ============================================

export function mapErrorToFriendly(error: string): {
  friendlyMessage: string;
  whatToDoNext: string[];
} {
  const lowerError = error.toLowerCase();

  if (lowerError.includes('timeout') || lowerError.includes('timed out')) {
    return {
      friendlyMessage: 'The service is taking longer than expected',
      whatToDoNext: ['Try again', 'Wait and retry later'],
    };
  }

  if (lowerError.includes('rate limit') || lowerError.includes('429')) {
    return {
      friendlyMessage: 'Hit a usage limit',
      whatToDoNext: ['Wait a moment and try again'],
    };
  }

  if (lowerError.includes('401') || lowerError.includes('403') || lowerError.includes('unauthorized')) {
    return {
      friendlyMessage: "I don't have access to this service",
      whatToDoNext: ['Check your connection settings', 'Reconnect the service'],
    };
  }

  if (lowerError.includes('404') || lowerError.includes('not found')) {
    return {
      friendlyMessage: "Couldn't find what we were looking for",
      whatToDoNext: ['Check if the resource still exists', 'Try a different approach'],
    };
  }

  if (lowerError.includes('500') || lowerError.includes('internal server')) {
    return {
      friendlyMessage: 'The service is having issues right now',
      whatToDoNext: ['Try again in a few minutes'],
    };
  }

  return {
    friendlyMessage: 'Something unexpected happened',
    whatToDoNext: ['Try again', 'Try a different approach'],
  };
}

