import type {
  Checkpoint,
  Task,
  TaskStep,
  Preference,
  PreferenceStats,
  ExecutionResult,
  TaskError,
  ActivityItem,
  ObserverProposal,
} from '../../types/task';

// ============================================
// Checkpoint Factories
// ============================================

export const createCheckpoint = (overrides: Partial<Checkpoint> = {}): Checkpoint => ({
  task_id: 'task-test-123',
  step_id: 'step-test-456',
  checkpoint_name: 'Confirm Action',
  description: 'Please confirm this action before proceeding',
  decision: 'pending',
  preview_data: { action: 'test_action', count: 1 },
  created_at: new Date().toISOString(),
  expires_at: null,
  ...overrides,
});

export const createExpiredCheckpoint = (): Checkpoint =>
  createCheckpoint({
    expires_at: new Date(Date.now() - 3600000).toISOString(),
    decision: 'expired',
  });

export const createApprovedCheckpoint = (): Checkpoint =>
  createCheckpoint({
    decision: 'approved',
  });

export const createRejectedCheckpoint = (): Checkpoint =>
  createCheckpoint({
    decision: 'rejected',
  });

export const createAutoApprovedCheckpoint = (): Checkpoint =>
  createCheckpoint({
    decision: 'auto_approved',
  });

export const createCheckpointWithPreview = (
  preview: Record<string, unknown>
): Checkpoint =>
  createCheckpoint({
    preview_data: preview,
  });

export const createCheckpointWithExpiry = (minutesUntilExpiry: number): Checkpoint =>
  createCheckpoint({
    expires_at: new Date(Date.now() + minutesUntilExpiry * 60000).toISOString(),
  });

// ============================================
// Plan Factories
// ============================================

export const createTaskStep = (overrides: Partial<TaskStep> = {}): TaskStep => ({
  id: 'step-1',
  name: 'Test Step',
  description: 'A test step description',
  agent_type: 'test_agent',
  status: 'pending',
  inputs: {},
  outputs: null,
  depends_on: [],
  checkpoint_required: false,
  retry_count: 0,
  max_retries: 3,
  error_message: null,
  parallel_group: null,
  ...overrides,
});

export const createTask = (overrides: Partial<Task> = {}): Task => ({
  id: 'task-test-123',
  goal: 'Test goal description',
  status: 'ready',
  steps: [
    createTaskStep({ id: 'step-1', name: 'Step 1' }),
    createTaskStep({ id: 'step-2', name: 'Step 2', depends_on: ['step-1'] }),
    createTaskStep({
      id: 'step-3',
      name: 'Checkpoint Step',
      checkpoint_required: true,
      depends_on: ['step-2'],
    }),
  ],
  progress_percentage: 0,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  completed_at: null,
  ...overrides,
});

export const createExecutingTask = (): Task =>
  createTask({
    status: 'executing',
    steps: [
      createTaskStep({ id: 'step-1', status: 'done' }),
      createTaskStep({ id: 'step-2', status: 'running' }),
      createTaskStep({ id: 'step-3', status: 'pending', checkpoint_required: true }),
    ],
    progress_percentage: 33,
  });

export const createCheckpointTask = (): Task =>
  createTask({
    status: 'checkpoint',
    steps: [
      createTaskStep({ id: 'step-1', status: 'done' }),
      createTaskStep({ id: 'step-2', status: 'done' }),
      createTaskStep({ id: 'step-3', status: 'checkpoint', checkpoint_required: true }),
    ],
    progress_percentage: 66,
  });

export const createCompletedTask = (): Task =>
  createTask({
    status: 'completed',
    steps: [
      createTaskStep({ id: 'step-1', status: 'done' }),
      createTaskStep({ id: 'step-2', status: 'done' }),
      createTaskStep({ id: 'step-3', status: 'done' }),
    ],
    progress_percentage: 100,
    completed_at: new Date().toISOString(),
  });

export const createFailedTask = (): Task =>
  createTask({
    status: 'failed',
    steps: [
      createTaskStep({ id: 'step-1', status: 'done' }),
      createTaskStep({
        id: 'step-2',
        status: 'failed',
        error_message: 'API call failed with 500',
      }),
      createTaskStep({ id: 'step-3', status: 'pending' }),
    ],
    progress_percentage: 33,
  });

// ============================================
// Preference Factories
// ============================================

export const createPreference = (overrides: Partial<Preference> = {}): Preference => ({
  id: 'pref-test-123',
  preference_key: 'send_email_notifications',
  decision: 'approved',
  confidence: 0.85,
  usage_count: 5,
  last_used: new Date().toISOString(),
  created_at: new Date(Date.now() - 86400000).toISOString(),
  ...overrides,
});

export const createRejectionPreference = (): Preference =>
  createPreference({
    id: 'pref-reject-456',
    preference_key: 'delete_records',
    decision: 'rejected',
    confidence: 0.95,
  });

export const createPreferenceStats = (
  overrides: Partial<PreferenceStats> = {}
): PreferenceStats => ({
  total_preferences: 10,
  high_confidence: 7,
  approvals: 8,
  rejections: 2,
  avg_confidence: 0.82,
  total_usage: 45,
  ...overrides,
});

// ============================================
// Execution Result Factories
// ============================================

export const createExecutionResult = (
  overrides: Partial<ExecutionResult> = {}
): ExecutionResult => ({
  task_id: 'task-test-123',
  status: 'completed',
  steps_completed: 3,
  steps_total: 3,
  checkpoint: null,
  findings: [],
  error: null,
  ...overrides,
});

export const createCheckpointResult = (): ExecutionResult =>
  createExecutionResult({
    status: 'checkpoint',
    steps_completed: 2,
    checkpoint: createCheckpoint(),
  });

export const createFailedResult = (): ExecutionResult =>
  createExecutionResult({
    status: 'failed',
    steps_completed: 1,
    error: 'Step execution failed: API timeout',
  });

// ============================================
// Error Factories
// ============================================

export const createTaskError = (
  overrides: Partial<TaskError> = {}
): TaskError => ({
  type: 'transient',
  friendlyMessage: 'Something went wrong',
  whatWentWrong: 'The service was temporarily unavailable',
  whatToDoNext: ['Try again', 'Wait a moment'],
  canRetry: true,
  canSkip: false,
  hasAlternative: false,
  technicalDetails: 'HTTP 503 Service Unavailable',
  ...overrides,
});

export const createPermanentError = (): TaskError =>
  createTaskError({
    type: 'permanent',
    friendlyMessage: 'This action cannot be completed',
    whatWentWrong: 'The resource no longer exists',
    whatToDoNext: ['Try a different approach'],
    canRetry: false,
  });

export const createAuthError = (): TaskError =>
  createTaskError({
    type: 'auth',
    friendlyMessage: 'Access denied',
    whatWentWrong: 'Your session has expired',
    whatToDoNext: ['Log in again'],
    canRetry: false,
  });

// ============================================
// Activity Factories
// ============================================

export const createActivityItem = (
  overrides: Partial<ActivityItem> = {}
): ActivityItem => ({
  id: `activity-${Date.now()}`,
  type: 'progress',
  message: 'Step completed successfully',
  timestamp: new Date().toISOString(),
  stepId: 'step-1',
  details: {},
  ...overrides,
});

export const createDecisionActivity = (): ActivityItem =>
  createActivityItem({
    type: 'decision',
    message: 'Checkpoint approved',
    details: { checkpoint_name: 'Confirm Action' },
  });

export const createErrorActivity = (): ActivityItem =>
  createActivityItem({
    type: 'error',
    message: 'Step failed to execute',
    details: { error: 'Timeout' },
  });

export const createRecoveryActivity = (): ActivityItem =>
  createActivityItem({
    type: 'recovery',
    message: 'Automatically retrying step',
    details: { proposal_type: 'RETRY' },
  });

// ============================================
// Recovery Proposal Factories
// ============================================

export const createRecoveryProposal = (
  overrides: Partial<ObserverProposal> = {}
): ObserverProposal => ({
  proposal_type: 'RETRY',
  reason: 'Step failed due to transient error, retrying may help',
  auto_applied: false,
  ...overrides,
});

export const createRetryProposal = (): ObserverProposal =>
  createRecoveryProposal({
    proposal_type: 'RETRY',
    reason: 'Transient error detected, retrying',
  });

export const createFallbackProposal = (): ObserverProposal =>
  createRecoveryProposal({
    proposal_type: 'FALLBACK',
    reason: 'Primary method failed, trying alternative',
  });

export const createSkipProposal = (): ObserverProposal =>
  createRecoveryProposal({
    proposal_type: 'SKIP',
    reason: 'Step is optional and can be skipped',
  });

export const createAbortProposal = (): ObserverProposal =>
  createRecoveryProposal({
    proposal_type: 'ABORT',
    reason: 'Unrecoverable error, aborting plan',
  });

export const createReplanProposal = (): ObserverProposal =>
  createRecoveryProposal({
    proposal_type: 'REPLAN',
    reason: 'Plan needs strategic revision',
  });

export const createAutoAppliedRecovery = (): ObserverProposal =>
  createRecoveryProposal({
    proposal_type: 'RETRY',
    auto_applied: true,
    reason: 'Automatically retried due to transient error',
  });

// ============================================
// Batch Factories
// ============================================

export const createMultipleCheckpoints = (count: number): Checkpoint[] =>
  Array.from({ length: count }, (_, i) =>
    createCheckpoint({
      task_id: `task-${i + 1}`,
      step_id: `step-${i + 1}`,
      checkpoint_name: `Checkpoint ${i + 1}`,
    })
  );

export const createMultiplePreferences = (count: number): Preference[] =>
  Array.from({ length: count }, (_, i) =>
    createPreference({
      id: `pref-${i + 1}`,
      preference_key: `preference_key_${i + 1}`,
      confidence: 0.5 + i * 0.1,
    })
  );
