import api from './api';

export interface DraftResponse {
  yaml: string;
  issues: Array<{ message: string; level?: string; path?: string | null }>;
  compile_report?: any;
  suggestions?: any[];
}

export async function draftWorkflow(intent: string, constraints?: any, priorYaml?: string): Promise<DraftResponse> {
  const { data } = await api.post('/api/arrow/workflows/draft', {
    intent,
    constraints,
    prior_yaml: priorYaml,
  });
  return data;
}

export interface ValidateResult {
  valid: boolean;
  errors: Array<{ message: string; level?: string; path?: string | null }>;
  warnings: Array<{ message: string; level?: string; path?: string | null }>;
  topology?: { start_nodes?: string[]; node_count: number; edge_count: number };
  budgets?: any;
}

export async function validateWorkflow(yaml: string): Promise<ValidateResult> {
  const { data } = await api.post('/api/workflows/validate', { yaml });
  return data;
}

export async function compileWorkflow(yaml: string): Promise<any> {
  const { data } = await api.post('/api/workflows/compile', { yaml });
  return data;
}

export async function publishWorkflow(yaml: string, versionTag?: string): Promise<{ ok: boolean; workflow_id?: string; stored?: boolean; errors?: any[] }>{
  const { data } = await api.post('/api/workflows/publish', { yaml, version_tag: versionTag });
  return data;
}

export async function runWorkflow(yaml: string, name?: string): Promise<{ ok: boolean; run_id?: string; created_tree?: boolean; node_count?: number; errors?: any[] }>{
  const { data } = await api.post('/api/workflows/run', { yaml, name });
  return data;
}

export async function listPlugins(): Promise<Array<{ name: string; description: string; category: string }>> {
  const { data } = await api.get('/api/catalog/plugins');
  return data.plugins || [];
}

export async function listAgents(): Promise<string[]> {
  const { data } = await api.get('/api/catalog/agents');
  return data.agents || [];
}

export interface PublishedWorkflow {
  id: string;
  name: string;
  version_tag?: string;
  created_at?: string;
  is_public?: boolean;
  copied_from_id?: string;
  copied_from_version?: string;
}

export async function listPublished(): Promise<PublishedWorkflow[]> {
  const { data } = await api.get('/api/workflows/published');
  return data.workflows || [];
}

export async function runPublished(workflowId: string): Promise<{ ok: boolean; run_id?: string; created_tree?: boolean; node_count?: number; errors?: any[] }>{
  const { data } = await api.post(`/api/workflows/published/${workflowId}/run`);
  return data;
}

export interface PublishedWorkflowDetails extends PublishedWorkflow {
  spec_yaml: string;
  updated_at?: string;
}

export async function getPublished(workflowId: string): Promise<PublishedWorkflowDetails> {
  const { data } = await api.get(`/api/workflows/published/${workflowId}`);
  return data;
}

export async function updatePublished(workflowId: string, yaml: string, name?: string, versionTag?: string): Promise<{ ok: boolean; errors?: any[] }>{
  const { data } = await api.put(`/api/workflows/published/${workflowId}`, { yaml, name, version_tag: versionTag });
  return data;
}

export async function deletePublished(workflowId: string): Promise<{ ok: boolean }>{
  const { data } = await api.delete(`/api/workflows/published/${workflowId}`);
  return data;
}

// ---- Chat-based Workflow Generation ----

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatResponse {
  message: string;
  yaml?: string | null;
  valid: boolean;
  issues: Array<{ message: string; level?: string; path?: string | null }>;
  run_id?: string | null;
  execution_started: boolean;
  conversation_id: string;
}

export async function arrowChat(message: string, history: ChatMessage[] = [], conversationId?: string): Promise<ChatResponse> {
  const { data } = await api.post('/api/arrow/chat', {
    message,
    history,
    conversation_id: conversationId,
  });
  return data;
}

export interface ExecutionTrace {
  run_id: string;
  root_node_id: string;
  metadata: any;
  nodes: Array<{
    id: string;
    name: string;
    status: string;
    type: string;
    priority: string;
    created_at?: string | null;
    started_at?: string | null;
    completed_at?: string | null;
    metadata: any;
    inputs: any;
    outputs: any;
    result_data?: any;  // Actual plugin execution results
    error?: string | null;
    retry_count: number;
    dependencies: string[];
    duration_seconds?: number;
  }>;
  summary: {
    total_nodes: number;
    completed: number;
    failed: number;
    running: number;
    pending: number;
    cancelled: number;
  };
  overall_status: string;
}

export async function getExecutionTrace(runId: string): Promise<ExecutionTrace> {
  const { data } = await api.get(`/api/workflows/${runId}/execution_trace`);
  return data;
}

// ---- Conversation Management ----

export interface ConversationSummary {
  id: string;
  created_at: string;
  message_count: number;
  last_message: string;
  last_run_id?: string | null;
}

export interface Conversation {
  id: string;
  created_at: string;
  messages: ChatMessage[];
  last_run_id?: string | null;
}

export async function listConversations(): Promise<ConversationSummary[]> {
  const { data } = await api.get('/api/arrow/conversations');
  return data.conversations || [];
}

export async function getConversation(conversationId: string): Promise<Conversation> {
  const { data } = await api.get(`/api/arrow/conversations/${conversationId}`);
  return data;
}

export async function deleteConversation(conversationId: string): Promise<{ ok: boolean }> {
  const { data } = await api.delete(`/api/arrow/conversations/${conversationId}`);
  return data;
}

// ---- Streaming Chat ----

// Use empty string in development to route through proxy
const API_BASE_URL = process.env.REACT_APP_API_URL !== undefined && process.env.REACT_APP_API_URL !== ''
  ? process.env.REACT_APP_API_URL
  : '';

export async function arrowChatStream(
  message: string,
  conversationId: string | undefined,
  onChunk: (chunk: string) => void,
  onError: (error: string) => void,
  onComplete: (conversationId: string) => void,
  onWorkflow?: (runId: string, executionStarted: boolean) => void,
  onStatus?: (status: string, message: string) => void
): Promise<void> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/arrow/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('Failed to get response reader');
    }

    const decoder = new TextDecoder();
    let buffer = '';
    let receivedConversationId: string | undefined = conversationId;

    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6);

          try {
            const parsed = JSON.parse(data);

            if (parsed.error) {
              onError(parsed.error);
              return;
            }

            if (parsed.conversation_id) {
              receivedConversationId = parsed.conversation_id;
            }

            if (parsed.run_id && onWorkflow) {
              onWorkflow(parsed.run_id, parsed.execution_started || false);
            }

            if (parsed.status && onStatus) {
              onStatus(parsed.status, parsed.message || '');
            }

            if (parsed.done) {
              onComplete(receivedConversationId || '');
              return;
            }

            if (parsed.content) {
              onChunk(parsed.content);
            }
          } catch (e) {
            console.error('Failed to parse SSE data:', e);
          }
        }
      }
    }

    onComplete(receivedConversationId || '');
  } catch (error) {
    onError(error instanceof Error ? error.message : 'Unknown error occurred');
  }
}

// ---- Conversation → Specs → Runs Navigation ----

export interface WorkflowSpec {
  id: string;
  name: string;
  description?: string;
  version: string;
  created_at: string;
  run_count: number;
  is_active: boolean;
}

export interface WorkflowRun {
  run_id: string;
  status: string;
  run_number: number;
  triggered_by?: string;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
}

export async function getConversationSpecs(conversationId: string): Promise<WorkflowSpec[]> {
  const { data } = await api.get(`/api/arrow/conversations/${conversationId}/specs`);
  return data.specs || [];
}

export async function getSpecRuns(specId: string, limit = 50): Promise<WorkflowRun[]> {
  const { data } = await api.get(`/api/workflow-specs/${specId}/runs`, {
    params: { limit }
  });
  return data.runs || [];
}

export async function executeSpec(specId: string, parameters?: Record<string, any>): Promise<{ ok: boolean; run_id?: string; created_tree?: boolean; node_count?: number; errors?: any[] }> {
  const { data } = await api.post(`/api/workflow-specs/${specId}/execute`, {
    parameters: parameters || {}
  });
  return data;
}
