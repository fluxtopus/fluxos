/**
 * Tasks API service for autonomous task delegation.
 *
 * Provides functions for:
 * - Creating and managing delegation plans
 * - Executing plans with checkpoint support
 * - Approving/rejecting checkpoints
 * - Managing user preferences
 */

import api from './api';

// Types

export interface PlanStep {
  id: string;
  name: string;
  description: string;
  agent_type: string;
  domain?: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  inputs: Record<string, any>;
  outputs?: Record<string, any> | any[] | string;
  depends_on: string[];
  checkpoint_required: boolean;
  retry_count: number;
  error_message?: string;
}

export interface Task {
  id: string;
  goal: string;
  status: 'planning' | 'ready' | 'executing' | 'paused' | 'checkpoint' | 'completed' | 'failed' | 'cancelled';
  steps: PlanStep[];
  progress_percentage: number;
  created_at: string;
  updated_at: string;
  completed_at?: string;
}

export interface Checkpoint {
  plan_id: string;
  step_id: string;
  checkpoint_name: string;
  description: string;
  decision: 'pending' | 'approved' | 'rejected' | 'timeout' | 'auto_approved';
  preview_data: Record<string, any>;
  created_at: string;
  expires_at?: string;
}

export interface ExecutionResult {
  plan_id: string;
  status: string;
  steps_completed: number;
  steps_total: number;
  checkpoint?: Record<string, any>;
  findings: Record<string, any>[];
  error?: string;
}

export interface UserPreference {
  id: string;
  preference_key: string;
  decision: 'approved' | 'rejected';
  confidence: number;
  usage_count: number;
  last_used: string;
  created_at: string;
}

export interface PreferenceStats {
  total_preferences: number;
  high_confidence: number;
  approvals: number;
  rejections: number;
  avg_confidence: number;
  total_usage: number;
}

// API Functions

export const tasksApi = {
  // === Plans ===

  /**
   * Create a new delegation plan from a goal.
   */
  createPlan: async (
    goal: string,
    constraints?: Record<string, any>,
    metadata?: Record<string, any>
  ): Promise<Task> => {
    const response = await api.post<Task>('/api/delegation/plans', {
      goal,
      constraints,
      metadata,
    });
    return response.data;
  },

  /**
   * Get a specific plan by ID.
   */
  getPlan: async (planId: string): Promise<Task> => {
    const response = await api.get<Task>(`/api/delegation/plans/${planId}`);
    return response.data;
  },

  /**
   * List all plans for the current user.
   */
  listPlans: async (
    status?: string,
    limit?: number,
    offset?: number
  ): Promise<Task[]> => {
    const params: Record<string, any> = {};
    if (status) params.status = status;
    if (limit) params.limit = limit;
    if (offset) params.offset = offset;

    const response = await api.get<Task[]>('/api/delegation/plans', { params });
    return response.data;
  },

  /**
   * Execute a plan.
   */
  executePlan: async (
    planId: string,
    runToCompletion: boolean = false
  ): Promise<ExecutionResult> => {
    const response = await api.post<ExecutionResult>(
      `/api/delegation/plans/${planId}/execute`,
      { run_to_completion: runToCompletion }
    );
    return response.data;
  },

  /**
   * Pause a running plan.
   */
  pausePlan: async (planId: string): Promise<Task> => {
    const response = await api.post<Task>(`/api/delegation/plans/${planId}/pause`);
    return response.data;
  },

  /**
   * Cancel a plan.
   */
  cancelPlan: async (planId: string): Promise<Task> => {
    const response = await api.post<Task>(`/api/delegation/plans/${planId}/cancel`);
    return response.data;
  },

  // === Checkpoints ===

  /**
   * Get checkpoints for a plan.
   */
  getPlanCheckpoints: async (planId: string): Promise<Checkpoint[]> => {
    const response = await api.get<Checkpoint[]>(
      `/api/delegation/plans/${planId}/checkpoints`
    );
    return response.data;
  },

  /**
   * Get all pending checkpoints for the current user.
   */
  getPendingCheckpoints: async (): Promise<Checkpoint[]> => {
    const response = await api.get<Checkpoint[]>('/api/delegation/checkpoints');
    return response.data;
  },

  /**
   * Approve a checkpoint.
   */
  approveCheckpoint: async (
    planId: string,
    stepId: string,
    feedback?: string,
    learnPreference: boolean = true
  ): Promise<Checkpoint> => {
    const response = await api.post<Checkpoint>(
      `/api/delegation/plans/${planId}/checkpoints/${stepId}/approve`,
      { feedback, learn_preference: learnPreference }
    );
    return response.data;
  },

  /**
   * Reject a checkpoint.
   */
  rejectCheckpoint: async (
    planId: string,
    stepId: string,
    reason: string,
    learnPreference: boolean = true
  ): Promise<Checkpoint> => {
    const response = await api.post<Checkpoint>(
      `/api/delegation/plans/${planId}/checkpoints/${stepId}/reject`,
      { reason, learn_preference: learnPreference }
    );
    return response.data;
  },

  // === Preferences ===

  /**
   * Get user preferences.
   */
  getPreferences: async (
    limit?: number,
    minConfidence?: number
  ): Promise<UserPreference[]> => {
    const params: Record<string, any> = {};
    if (limit) params.limit = limit;
    if (minConfidence) params.min_confidence = minConfidence;

    const response = await api.get<UserPreference[]>('/api/delegation/preferences', { params });
    return response.data;
  },

  /**
   * Get preference statistics.
   */
  getPreferenceStats: async (): Promise<PreferenceStats> => {
    const response = await api.get<PreferenceStats>('/api/delegation/preferences/stats');
    return response.data;
  },

  /**
   * Delete a preference.
   */
  deletePreference: async (preferenceId: string): Promise<void> => {
    await api.delete(`/api/delegation/preferences/${preferenceId}`);
  },
};

export default tasksApi;
