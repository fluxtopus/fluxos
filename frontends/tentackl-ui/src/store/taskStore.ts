/**
 * Task Store
 *
 * Simplified state management for task listing and creation flows.
 *
 * NOTE: TaskDetail.tsx now uses dedicated hooks (useTask, useTaskSSE)
 * for viewing and observing task execution. This store is primarily used for:
 * - Task listing (TaskList component)
 * - Task creation (new task page)
 * - Preferences management
 */

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import * as taskApi from '../services/taskApi';
import type {
  Task,
  TaskStatus,
  Checkpoint,
  Preference,
  PreferenceStats,
  TaskPhase,
  Delivery,
  ActivityItem,
} from '../types/task';

// ============================================
// Store Interface
// ============================================

interface TaskStore {
  // === Core State ===
  phase: TaskPhase;
  currentTask: Task | null;
  tasks: Task[];

  // === Deliveries (extracted from completed tasks) ===
  deliveries: Delivery[];

  // === Activity (user-facing timeline) ===
  activity: ActivityItem[];

  // === Checkpoints ===
  pendingCheckpoints: Checkpoint[];

  // === Preferences ===
  preferences: Preference[];
  preferenceStats: PreferenceStats | null;

  // === Error State ===
  errorMessage: string | null;

  // === Loading States ===
  loading: boolean;
  creatingTask: boolean;

  // === Actions: Task Management ===
  createTask: (goal: string, constraints?: Record<string, unknown>, metadata?: Record<string, unknown>) => Promise<void>;
  loadTask: (taskId: string) => Promise<void>;
  loadTasks: (status?: TaskStatus, options?: { silent?: boolean }) => Promise<void>;
  refreshCurrentTask: () => Promise<void>;

  // === Actions: Execution (simple API calls) ===
  startTask: (taskId: string) => Promise<taskApi.StartTaskResult>;
  pauseTask: (taskId: string) => Promise<Task>;
  cancelTask: (taskId: string) => Promise<void>;

  // === Actions: Checkpoints ===
  approveCheckpoint: (taskId: string, stepId: string, feedback?: string, learnPreference?: boolean) => Promise<void>;
  rejectCheckpoint: (taskId: string, stepId: string, reason: string, learnPreference?: boolean) => Promise<void>;
  loadPendingCheckpoints: () => Promise<void>;

  // === Actions: Preferences ===
  loadPreferences: () => Promise<void>;
  loadPreferenceStats: () => Promise<void>;
  deletePreference: (preferenceId: string) => Promise<void>;

  // === Actions: Utility ===
  reset: () => void;
  clearError: () => void;
  addActivity: (item: Omit<ActivityItem, 'id' | 'timestamp'>) => void;
  setCurrentTask: (task: Task | null) => void;
}

// ============================================
// Initial State
// ============================================

const initialState = {
  phase: 'idle' as TaskPhase,
  currentTask: null as Task | null,
  tasks: [] as Task[],
  deliveries: [] as Delivery[],
  activity: [] as ActivityItem[],
  pendingCheckpoints: [] as Checkpoint[],
  preferences: [] as Preference[],
  preferenceStats: null as PreferenceStats | null,
  errorMessage: null as string | null,
  loading: false,
  creatingTask: false,
};

// ============================================
// Store Implementation
// ============================================

export const useTaskStore = create<TaskStore>()(
  devtools(
    (set, get) => ({
      ...initialState,

      // ========================================
      // Task Management
      // ========================================

      createTask: async (goal, constraints, metadata) => {
        set({
          phase: 'creating',
          creatingTask: true,
          errorMessage: null,
          deliveries: [],
          activity: [],
        });

        get().addActivity({
          type: 'started',
          message: 'Creating your task...',
        });

        try {
          // API now returns immediately with a PLANNING-status stub (202)
          const task = await taskApi.createTask({ goal, constraints, metadata });

          set({
            currentTask: task,
            phase: 'creating', // Keep as 'creating' — task is still PLANNING
            creatingTask: false,
          });
        } catch (error) {
          const msg = error instanceof Error ? error.message : 'Failed to create task';
          set({
            phase: 'idle',
            creatingTask: false,
            errorMessage: msg,
          });
        }
      },

      loadTask: async (taskId) => {
        set({ loading: true, errorMessage: null });

        try {
          const task = await taskApi.getTask(taskId);
          const phase = mapTaskStatusToPhase(task.status);
          const deliveries = extractDeliveries(task);

          set({
            currentTask: task,
            phase,
            loading: false,
            deliveries,
          });
        } catch (error) {
          set({
            loading: false,
            errorMessage: error instanceof Error ? error.message : 'Failed to load task',
          });
        }
      },

      loadTasks: async (status, options) => {
        if (!options?.silent) {
          set({ loading: true, errorMessage: null });
        }

        try {
          const tasks = await taskApi.listTasks(status);
          set({ tasks, loading: false });
        } catch (error) {
          if (!options?.silent) {
            set({
              loading: false,
              errorMessage: error instanceof Error ? error.message : 'Failed to load tasks',
            });
          }
        }
      },

      refreshCurrentTask: async () => {
        const { currentTask } = get();
        if (!currentTask) return;

        try {
          const task = await taskApi.getTask(currentTask.id);
          const deliveries = extractDeliveries(task);
          set({ currentTask: task, deliveries });
        } catch (error) {
          console.error('Failed to refresh task:', error);
        }
      },

      // ========================================
      // Execution (simple API calls - TaskDetail uses hooks for SSE)
      // ========================================

      startTask: async (taskId) => {
        try {
          const result = await taskApi.startTask(taskId);
          return result;
        } catch (error) {
          const msg = error instanceof Error ? error.message : 'Failed to start task';
          set({ errorMessage: msg });
          throw error;
        }
      },

      pauseTask: async (taskId) => {
        try {
          const task = await taskApi.pauseTask(taskId);
          return task;
        } catch (error) {
          const msg = error instanceof Error ? error.message : 'Failed to pause task';
          set({ errorMessage: msg });
          throw error;
        }
      },

      cancelTask: async (taskId) => {
        try {
          await taskApi.cancelTask(taskId);
        } catch (error) {
          const msg = error instanceof Error ? error.message : 'Failed to cancel task';
          set({ errorMessage: msg });
          throw error;
        }
      },

      // ========================================
      // Checkpoints (simple API calls - TaskDetail handles UI state)
      // ========================================

      approveCheckpoint: async (taskId, stepId, feedback, learnPreference = true) => {
        try {
          await taskApi.approveCheckpoint(taskId, stepId, {
            feedback,
            learn_preference: learnPreference,
          });
        } catch (error) {
          const msg = error instanceof Error ? error.message : 'Failed to approve checkpoint';
          set({ errorMessage: msg });
          throw error;
        }
      },

      rejectCheckpoint: async (taskId, stepId, reason, learnPreference = true) => {
        try {
          await taskApi.rejectCheckpoint(taskId, stepId, {
            reason,
            learn_preference: learnPreference,
          });
        } catch (error) {
          const msg = error instanceof Error ? error.message : 'Failed to reject checkpoint';
          set({ errorMessage: msg });
          throw error;
        }
      },

      loadPendingCheckpoints: async () => {
        try {
          const checkpoints = await taskApi.getCheckpoints();
          set({ pendingCheckpoints: checkpoints });
        } catch (error) {
          console.error('Failed to load checkpoints:', error);
        }
      },

      // ========================================
      // Preferences
      // ========================================

      loadPreferences: async () => {
        try {
          const preferences = await taskApi.getPreferences();
          set({ preferences });
        } catch (error) {
          console.error('Failed to load preferences:', error);
        }
      },

      loadPreferenceStats: async () => {
        try {
          const stats = await taskApi.getPreferenceStats();
          set({ preferenceStats: stats });
        } catch (error) {
          console.error('Failed to load preference stats:', error);
        }
      },

      deletePreference: async (preferenceId) => {
        try {
          await taskApi.deletePreference(preferenceId);
          set((state) => ({
            preferences: state.preferences.filter((p) => p.id !== preferenceId),
          }));
        } catch (error) {
          set({
            errorMessage: error instanceof Error ? error.message : 'Failed to delete preference',
          });
        }
      },

      // ========================================
      // Utility
      // ========================================

      reset: () => {
        set(initialState);
      },

      clearError: () => {
        set({ errorMessage: null });
      },

      addActivity: (item) => {
        set((state) => ({
          activity: [
            ...state.activity,
            {
              ...item,
              id: `activity-${Date.now()}-${Math.random().toString(36).slice(2)}`,
              timestamp: new Date().toISOString(),
            },
          ],
        }));
      },

      setCurrentTask: (task) => {
        set({ currentTask: task });
      },
    }),
    { name: 'task-store' }
  )
);

// ============================================
// Helper Functions
// ============================================

function mapTaskStatusToPhase(status: TaskStatus): TaskPhase {
  const mapping: Record<TaskStatus, TaskPhase> = {
    planning: 'creating',
    ready: 'ready',
    executing: 'executing',
    paused: 'paused',
    checkpoint: 'checkpoint',
    completed: 'completed',
    failed: 'failed',
    cancelled: 'idle',
    superseded: 'idle',
  };
  return mapping[status] || 'idle';
}

function extractDeliveries(task: Task): Delivery[] {
  // Only the FINAL completed step is a potential delivery
  const completedSteps = task.steps.filter((step) => step.status === 'done' && step.outputs);

  if (completedSteps.length === 0) return [];

  const finalStep = completedSteps[completedSteps.length - 1];
  const outputs = finalStep.outputs || {};

  // Check if the output is an error
  const outputStr = JSON.stringify(outputs).toLowerCase();
  if (outputStr.includes('"status":"error"') || outputStr.includes('<status>error</status>')) {
    return [];
  }

  // Check if this is an intermediate step
  const intermediatePrefixes = ['load', 'fetch', 'get', 'download', 'retrieve'];
  const stepNameLower = finalStep.name.toLowerCase();
  if (intermediatePrefixes.some(prefix => stepNameLower.startsWith(prefix))) {
    return [];
  }

  return [{
    id: `delivery-${finalStep.id}`,
    stepId: finalStep.id,
    stepName: finalStep.name,
    type: detectDeliveryType(outputs),
    title: finalStep.name,
    content: outputs,
    createdAt: new Date().toISOString(),
  }];
}

function detectDeliveryType(outputs: Record<string, unknown>): Delivery['type'] {
  if (outputs.url && typeof outputs.url === 'string') {
    if (outputs.url.match(/\.(png|jpg|jpeg|gif|webp)$/i)) {
      return 'image';
    }
    return 'file';
  }
  if (outputs.text || outputs.summary || outputs.content || outputs.result) {
    return 'text';
  }
  if (outputs.notification_sent || outputs.email_sent) {
    return 'notification';
  }
  return 'data';
}

// ============================================
// Selectors
// ============================================

export const selectHasPendingDecisions = (state: TaskStore): boolean => {
  return state.pendingCheckpoints.length > 0;
};

export const selectProgress = (state: TaskStore): number => {
  return state.currentTask?.progress_percentage || 0;
};

