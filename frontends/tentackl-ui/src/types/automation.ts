/**
 * Automation Types
 *
 * Types for scheduled workflow automations.
 */

export interface ExecutionSummary {
  id: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  error_message: string | null;
  step_count: number;
  steps_completed: number;
}

export interface AutomationStats {
  total_runs: number;
  successful_runs: number;
  failed_runs: number;
  success_rate: number;
  avg_duration_seconds: number | null;
}

export interface AutomationSummary {
  id: string;
  name: string;
  task_id: string;
  goal: string;
  schedule_cron: string;
  schedule_timezone: string;
  schedule_enabled: boolean;
  next_scheduled_run: string | null;
  last_execution: ExecutionSummary | null;
  stats: AutomationStats;
  created_at: string;
  updated_at: string;
}

export interface AutomationDetail extends AutomationSummary {
  recent_executions: ExecutionSummary[];
}

export interface AutomationListResponse {
  automations: AutomationSummary[];
  total: number;
  needs_attention: number;
}

export interface CreateAutomationRequest {
  schedule_cron: string;
  schedule_timezone?: string;
  name?: string;
}
