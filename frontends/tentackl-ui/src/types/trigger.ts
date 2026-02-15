/**
 * Trigger types for event-driven task execution
 */

export interface Trigger {
  task_id: string;
  organization_id: string;
  user_id?: string;
  event_pattern: string;
  source_filter?: string;
  condition?: Record<string, unknown>;
  enabled: boolean;
  type: string;
  scope: 'org' | 'user';
}

export interface TriggerListResponse {
  triggers: Trigger[];
  count: number;
}

export interface TriggerEvent {
  id: string;
  type: 'trigger.matched' | 'trigger.executed' | 'trigger.completed' | 'trigger.failed';
  task_id: string;
  timestamp: string;
  data: {
    event_id: string;
    matched_event_type?: string;
    execution_id?: string;
    preview?: string;
    result_preview?: string;
    error?: string;
  };
}

export interface TriggerExecution {
  id: string;
  event_id: string;
  task_execution_id?: string;
  status: 'running' | 'completed' | 'failed';
  started_at: string;
  completed_at?: string;
  error?: string;
}

export interface TriggerHistoryResponse {
  executions: TriggerExecution[];
  count: number;
}

export interface TriggerSSECallbacks {
  onEvent?: (event: TriggerEvent) => void;
  onError?: (error: string) => void;
  onStreamEnd?: () => void;
  onConnected?: () => void;
}

export interface IntegrationEvent {
  type: string;
  event_id: string;
  integration_id: string;
  timestamp: string;
  data: {
    event_type: string;
    preview?: string;
  };
}

export interface IntegrationSSECallbacks {
  onEvent?: (event: IntegrationEvent) => void;
  onError?: (error: string) => void;
  onStreamEnd?: () => void;
  onConnected?: () => void;
}
