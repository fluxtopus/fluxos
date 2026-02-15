import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL !== undefined && process.env.REACT_APP_API_URL !== ''
  ? process.env.REACT_APP_API_URL
  : '';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Types
export interface PlanRequest {
  prompt: string;
}

export interface CostEstimate {
  total_estimated_cost: number;
  workflow_cost: number;
  planning_cost: number;
  node_count: number;
  llm_node_count: number;
  breakdown: Array<{
    node_id: string;
    model: string | null;
    estimated_input_tokens: number;
    estimated_output_tokens: number;
    estimated_cost: number;
    uses_llm: boolean;
  }>;
  currency: string;
  note: string;
}

export interface ParameterSchemaItem {
  name: string;
  type: string;
  required: boolean;
  description: string;
  default?: unknown;
}

export interface UnresolvedSlot {
  node_id: string;
  node_name: string;
  connector_type: string;
  host: string;
  url: string;
  error: string;
  action_required: string;
}

export interface ConnectorResolutionReport {
  resolved: boolean;
  unresolved_slots: UnresolvedSlot[];
  best_guesses: Record<string, { type: string; host: string; environment: string; suggested_action: string }>;
  alternatives: Record<string, unknown>;
  warnings: Array<{ node_id?: string; message: string }>;
  environment: string;
}

export interface WebhookInfo {
  enabled: boolean;
  source_id: string;
  endpoint_url: string;
  api_key: string;
  event_types: string[];
  sample_payload: Record<string, unknown>;
}

export interface IntentResponse {
  session_id: string;
  rephrased_intent: string;
  workflow_outline: string[];
  estimated_node_count: number;
  has_loops: boolean;
  requires_params: boolean;
  estimated_planning_time_ms: number;
}

export interface PlanResponse {
  session_id: string;
  yaml: string;
  valid: boolean;
  issues: Array<{ message: string; level: string }>;
  cost_estimate: CostEstimate | null;
  user_prompt: string;
  parameter_schema: ParameterSchemaItem[];
  connector_resolution: ConnectorResolutionReport | null;
  webhook_info: WebhookInfo | null;
}

export interface ExecuteRequest {
  session_id: string;
  parameters?: Record<string, unknown>;
}

export interface ExecuteResponse {
  execution_id: string;
  session_id: string;
  status: string;
  websocket_url: string;
  started_at: string;
}

export interface ExecutionNode {
  id: string;
  name?: string;
  status: string;
  started_at?: string;
  completed_at?: string;
  error?: Record<string, unknown> | string | null;
  result?: Record<string, unknown> | null;
}

export interface ExecutionStatus {
  execution_id: string;
  session_id: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  result: Record<string, unknown> | null;
  cost: CostEstimate | null;
  nodes: ExecutionNode[];
}

export interface ExampleWorkflow {
  id: string;
  name: string;
  description: string;
  prompt: string;
  category: string;
}

// API Functions
export const playgroundApi = {
  // Plan a workflow from natural language
  plan: async (prompt: string): Promise<PlanResponse> => {
    const response = await api.post<PlanResponse>('/api/playground/plan', { prompt });
    return response.data;
  },

  // Extract intent (fast phase 1)
  extractIntent: async (prompt: string): Promise<IntentResponse> => {
    const response = await api.post<IntentResponse>('/api/playground/intent', { prompt });
    return response.data;
  },

  // Execute a planned workflow
  execute: async (sessionId: string, parameters?: Record<string, unknown>): Promise<ExecuteResponse> => {
    const response = await api.post<ExecuteResponse>('/api/playground/execute', {
      session_id: sessionId,
      parameters,
    });
    return response.data;
  },

  // Get execution status
  getExecutionStatus: async (executionId: string): Promise<ExecutionStatus> => {
    const response = await api.get<ExecutionStatus>(`/api/playground/executions/${executionId}`);
    return response.data;
  },

  // Get example workflows
  getExamples: async (): Promise<ExampleWorkflow[]> => {
    const response = await api.get<ExampleWorkflow[]>('/api/playground/examples');
    return response.data;
  },

};

export default playgroundApi;
