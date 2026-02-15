import { http, HttpResponse } from 'msw';
import {
  createCheckpoint,
  createTask,
  createPreference,
  createPreferenceStats,
  createExecutionResult,
  createMultipleCheckpoints,
  createMultiplePreferences,
} from '../fixtures/checkpoints';
import type { Checkpoint, Task, Preference } from '../../types/task';

// Base URL for API mocks
const BASE_URL = 'http://localhost:8000';

// In-memory state for tests
let mockCheckpoints: Checkpoint[] = [];
let mockTasks: Task[] = [];
let mockPreferences: Preference[] = [];

// Reset state for tests
export const resetMockState = () => {
  mockCheckpoints = createMultipleCheckpoints(3);
  mockTasks = [createTask()];
  mockPreferences = createMultiplePreferences(5);
};

// Initialize mock state
resetMockState();

// ============================================
// Task Handlers
// ============================================

export const taskHandlers = [
  // Get task by ID
  http.get(`${BASE_URL}/api/tasks/:taskId`, ({ params }) => {
    const taskId = params.taskId as string;
    const task = mockTasks.find((t) => t.id === taskId) || createTask({ id: taskId });
    return HttpResponse.json(task);
  }),

  // List tasks
  http.get(`${BASE_URL}/api/tasks`, ({ request }) => {
    const url = new URL(request.url);
    const status = url.searchParams.get('status');
    let tasks = mockTasks;
    if (status) {
      tasks = tasks.filter((t) => t.status === status);
    }
    return HttpResponse.json(tasks);
  }),

  // Create task
  http.post(`${BASE_URL}/api/tasks`, async ({ request }) => {
    const body = await request.json() as { goal: string };
    const newTask = createTask({ goal: body.goal, id: `task-${Date.now()}` });
    mockTasks.push(newTask);
    return HttpResponse.json(newTask, { status: 201 });
  }),

  // Start task execution
  http.post(`${BASE_URL}/api/tasks/:taskId/start`, ({ params }) => {
    const taskId = params.taskId as string;
    return HttpResponse.json({
      status: 'started',
      task_id: taskId,
      message: 'Task execution started',
    });
  }),

  // Execute task
  http.post(`${BASE_URL}/api/tasks/:taskId/execute`, () => {
    return HttpResponse.json(createExecutionResult());
  }),

  // Pause task
  http.post(`${BASE_URL}/api/tasks/:taskId/pause`, ({ params }) => {
    const taskId = params.taskId as string;
    const task = mockTasks.find((t) => t.id === taskId);
    if (task) {
      task.status = 'paused';
    }
    return HttpResponse.json(task || createTask({ id: taskId, status: 'paused' }));
  }),

  // Cancel task
  http.post(`${BASE_URL}/api/tasks/:taskId/cancel`, ({ params }) => {
    const taskId = params.taskId as string;
    const task = mockTasks.find((t) => t.id === taskId);
    if (task) {
      task.status = 'cancelled';
    }
    return HttpResponse.json(task || createTask({ id: taskId, status: 'cancelled' }));
  }),
];

// ============================================
// Checkpoint Handlers
// ============================================

export const checkpointHandlers = [
  // Get all pending checkpoints
  http.get(`${BASE_URL}/api/checkpoints`, () => {
    const pendingCheckpoints = mockCheckpoints.filter((c) => c.decision === 'pending');
    return HttpResponse.json(pendingCheckpoints);
  }),

  // Get checkpoints for a task
  http.get(`${BASE_URL}/api/tasks/:taskId/checkpoints`, ({ params }) => {
    const taskId = params.taskId as string;
    const taskCheckpoints = mockCheckpoints.filter((c) => c.task_id === taskId);
    return HttpResponse.json(taskCheckpoints);
  }),

  // Approve checkpoint
  http.post(
    `${BASE_URL}/api/tasks/:taskId/checkpoints/:stepId/approve`,
    async ({ params, request }) => {
      const taskId = params.taskId as string;
      const stepId = params.stepId as string;
      const body = await request.json() as { feedback?: string; learn_preference?: boolean };

      const checkpoint = mockCheckpoints.find(
        (c) => c.task_id === taskId && c.step_id === stepId
      );

      if (!checkpoint) {
        return HttpResponse.json({ error: 'Checkpoint not found' }, { status: 404 });
      }

      // Check if expired
      if (checkpoint.expires_at && new Date(checkpoint.expires_at) < new Date()) {
        return HttpResponse.json({ error: 'Checkpoint has expired' }, { status: 400 });
      }

      checkpoint.decision = 'approved';

      // Create preference if learning is enabled
      if (body.learn_preference) {
        mockPreferences.push(
          createPreference({
            id: `pref-${Date.now()}`,
            preference_key: checkpoint.checkpoint_name,
            decision: 'approved',
          })
        );
      }

      return HttpResponse.json(checkpoint);
    }
  ),

  // Reject checkpoint
  http.post(
    `${BASE_URL}/api/tasks/:taskId/checkpoints/:stepId/reject`,
    async ({ params, request }) => {
      const taskId = params.taskId as string;
      const stepId = params.stepId as string;
      const body = await request.json() as { reason: string; learn_preference?: boolean };

      const checkpoint = mockCheckpoints.find(
        (c) => c.task_id === taskId && c.step_id === stepId
      );

      if (!checkpoint) {
        return HttpResponse.json({ error: 'Checkpoint not found' }, { status: 404 });
      }

      if (!body.reason || body.reason.trim() === '') {
        return HttpResponse.json({ error: 'Reason is required' }, { status: 400 });
      }

      checkpoint.decision = 'rejected';

      // Create preference if learning is enabled
      if (body.learn_preference) {
        mockPreferences.push(
          createPreference({
            id: `pref-${Date.now()}`,
            preference_key: checkpoint.checkpoint_name,
            decision: 'rejected',
          })
        );
      }

      return HttpResponse.json(checkpoint);
    }
  ),
];

// ============================================
// Preference Handlers
// ============================================

export const preferenceHandlers = [
  // Get preferences
  http.get(`${BASE_URL}/api/preferences`, () => {
    return HttpResponse.json(mockPreferences);
  }),

  // Get preference stats
  http.get(`${BASE_URL}/api/preferences/stats`, () => {
    return HttpResponse.json(createPreferenceStats({ total_preferences: mockPreferences.length }));
  }),

  // Delete preference
  http.delete(`${BASE_URL}/api/preferences/:preferenceId`, ({ params }) => {
    const preferenceId = params.preferenceId as string;
    const index = mockPreferences.findIndex((p) => p.id === preferenceId);
    if (index !== -1) {
      mockPreferences.splice(index, 1);
      return new HttpResponse(null, { status: 204 });
    }
    return HttpResponse.json({ error: 'Preference not found' }, { status: 404 });
  }),
];

// ============================================
// Error Scenario Handlers
// ============================================

export const createErrorHandlers = () => [
  // 500 error on approve
  http.post(`${BASE_URL}/api/tasks/:taskId/checkpoints/:stepId/approve`, () => {
    return HttpResponse.json({ error: 'Internal server error' }, { status: 500 });
  }),

  // Timeout simulation (handled by msw with delay)
  http.post(
    `${BASE_URL}/api/tasks/:taskId/checkpoints/:stepId/approve`,
    async () => {
      await new Promise((resolve) => setTimeout(resolve, 30000));
      return HttpResponse.json({ error: 'Request timeout' }, { status: 408 });
    }
  ),
];

// ============================================
// All Handlers Combined
// ============================================

export const handlers = [...taskHandlers, ...checkpointHandlers, ...preferenceHandlers];

// ============================================
// Test Utilities
// ============================================

export const addMockCheckpoint = (checkpoint: Checkpoint) => {
  mockCheckpoints.push(checkpoint);
};

export const clearMockCheckpoints = () => {
  mockCheckpoints = [];
};

export const setMockCheckpoints = (checkpoints: Checkpoint[]) => {
  mockCheckpoints = checkpoints;
};

export const getMockCheckpoints = () => [...mockCheckpoints];

export const addMockTask = (task: Task) => {
  mockTasks.push(task);
};

export const setMockTasks = (tasks: Task[]) => {
  mockTasks = tasks;
};

export const getMockTasks = () => [...mockTasks];

export const addMockPreference = (preference: Preference) => {
  mockPreferences.push(preference);
};

export const setMockPreferences = (preferences: Preference[]) => {
  mockPreferences = preferences;
};

export const getMockPreferences = () => [...mockPreferences];
