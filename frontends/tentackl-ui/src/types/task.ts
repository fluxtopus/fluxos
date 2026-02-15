/**
 * Task System Types
 *
 * These types represent the task paradigm where users describe
 * what they want done and receive results - autonomous execution
 * from natural language goals.
 */

// === Task Status ===

export type TaskStatus =
  | 'planning'    // Task plan is being generated
  | 'ready'       // Plan ready to execute
  | 'executing'   // Task is running
  | 'paused'      // User paused execution
  | 'checkpoint'  // Waiting for user approval
  | 'completed'   // Successfully finished
  | 'failed'      // Failed with error
  | 'cancelled'   // User cancelled
  | 'superseded'; // Replaced by newer version

export type StepStatus =
  | 'pending'     // Not yet started
  | 'running'     // Currently executing
  | 'done'        // Successfully completed
  | 'failed'      // Failed with error
  | 'skipped'     // Skipped (rejected or dependency failed)
  | 'checkpoint'; // Waiting for approval

export type TaskSource =
  | 'ui'        // Created via UI
  | 'api'       // Created via API
  | 'schedule'  // Created by scheduler
  | 'webhook';  // Created by webhook trigger

export type CheckpointDecision =
  | 'pending'       // Waiting for approval
  | 'approved'      // User approved
  | 'rejected'      // User rejected
  | 'auto_approved' // Auto-approved via preferences
  | 'expired';      // Timed out

// === Core Data Models ===

export interface TaskStep {
  id: string;
  name: string;
  description: string;
  agent_type: string;
  domain?: string;
  status: StepStatus;
  inputs: Record<string, unknown>;
  outputs?: Record<string, unknown> | null;
  depends_on: string[];
  checkpoint_required: boolean;
  retry_count: number;
  max_retries: number;
  error_message?: string | null;
  parallel_group?: string | null;
}

export interface Task {
  id: string;
  goal: string;
  status: TaskStatus;
  steps: TaskStep[];
  progress_percentage: number;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
  planning_error?: string | null;
}

export interface Checkpoint {
  task_id: string;
  step_id: string;
  checkpoint_name: string;
  description: string;
  decision: CheckpointDecision;
  preview_data: Record<string, unknown>;
  created_at: string;
  expires_at?: string | null;
}

export interface Preference {
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

// === Planning Progress Types ===

export type PlanningEventType =
  | 'task.planning.started'
  | 'task.planning.intent_detected'
  | 'task.planning.fast_path'
  | 'task.planning.spec_match'
  | 'task.planning.llm_started'
  | 'task.planning.llm_retry'
  | 'task.planning.steps_generated'
  | 'task.planning.risk_detection'
  | 'task.planning.completed'
  | 'task.planning.failed';

export type PlanningPhaseStatus = 'pending' | 'active' | 'done' | 'failed';

export interface PlanningPhaseItem {
  type: PlanningEventType;
  label: string;
  status: PlanningPhaseStatus;
  detail?: string;
}

export interface PlanningProgress {
  phases: PlanningPhaseItem[];
  currentPhase: PlanningEventType | null;
  stepNames: string[] | null;
  stepCount: number | null;
  error: string | null;
  isComplete: boolean;
  isFailed: boolean;
}

// === Execution Types ===

export interface ExecutionResult {
  task_id: string;
  status: 'completed' | 'checkpoint' | 'blocked' | 'failed' | 'aborted' | 'replan_checkpoint';
  steps_completed: number;
  steps_total: number;
  checkpoint?: Checkpoint | null;
  findings: Array<Record<string, unknown>>;
  error?: string | null;
}

// === SSE Event Types ===

export type SSEEventType =
  | 'execution_started'
  | 'cycle_completed'
  | 'execution_completed'
  | 'execution_failed'
  | 'checkpoint_reached'
  | 'execution_blocked'
  | 'task_aborted'
  | 'observer_recovery'
  | 'replan_checkpoint'
  | 'replan_complete'
  | 'max_cycles_reached';

export interface SSEEvent {
  type: SSEEventType;
  task_id: string;
  step_id?: string;
  step_name?: string;
  outputs?: Record<string, unknown>;
  error?: string;
  checkpoint?: Checkpoint;
  result?: Record<string, unknown>;
  steps_completed?: number;
  steps_total?: number;
  current_step?: string;
  proposal?: ObserverProposal;
}

export interface ObserverProposal {
  proposal_type: 'RETRY' | 'FALLBACK' | 'SKIP' | 'ABORT' | 'REPLAN';
  reason: string;
  auto_applied?: boolean;
}

// === Request Types ===

export interface CreateTaskRequest {
  goal: string;
  constraints?: {
    max_cost?: number;
    timeout_minutes?: number;
    [key: string]: unknown;
  };
  metadata?: Record<string, unknown>;
}

export interface ApproveCheckpointRequest {
  feedback?: string;
  learn_preference?: boolean;
}

export interface RejectCheckpointRequest {
  reason: string;
  learn_preference?: boolean;
}

// === UI State Types ===

export type TaskPhase =
  | 'idle'        // No active task
  | 'creating'    // Creating task from goal
  | 'ready'       // Task created, ready to execute
  | 'executing'   // Task running
  | 'checkpoint'  // Waiting for user approval
  | 'replan'      // Replan checkpoint
  | 'completed'   // All steps done
  | 'failed'      // Execution failed
  | 'paused';     // User paused

// === Delivery Types (User-facing results) ===

export interface Delivery {
  id: string;
  stepId: string;
  stepName: string;
  type: 'text' | 'file' | 'notification' | 'data' | 'image';
  title: string;
  content: unknown;
  createdAt: string;
}

// === Activity Types (User-facing timeline) ===

export interface ActivityItem {
  id: string;
  type: 'started' | 'progress' | 'completed' | 'decision' | 'error' | 'recovery';
  message: string;
  timestamp: string;
  stepId?: string;
  details?: Record<string, unknown>;
}

// === Error Types (User-friendly) ===

export interface TaskError {
  type: 'transient' | 'permanent' | 'content_filter' | 'auth' | 'unknown';
  friendlyMessage: string;
  whatWentWrong: string;
  whatToDoNext: string[];
  canRetry: boolean;
  canSkip: boolean;
  hasAlternative: boolean;
  technicalDetails?: string;
}

