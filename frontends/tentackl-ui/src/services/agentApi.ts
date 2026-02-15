/**
 * Agent Registry API Service
 *
 * Handles all communication with the agent registry backend.
 */

import api from './api';
import type {
  AgentSpec,
  AgentListResponse,
  RegisterAgentRequest,
  UpdateAgentRequest,
  CapabilitiesResponse,
} from '../types/agent';

// ============================================
// Agent Registry Management
// ============================================

/**
 * List all agents with optional filters
 *
 * Note: Agents are now unified with capabilities - this calls /api/capabilities/agents
 */
export async function listAgents(
  category?: string,
  tags?: string[],
  activeOnly: boolean = false,
  includeSystem: boolean = true
): Promise<AgentListResponse> {
  const params: Record<string, unknown> = {
    active_only: activeOnly,
    include_system: includeSystem,
  };
  if (category) params.domain = category; // API uses 'domain' instead of 'category'
  if (tags && tags.length > 0) params.tags = tags;

  // Capabilities API returns { capabilities, count, total, limit, offset }
  // Transform to AgentListResponse format
  const { data } = await api.get<{
    capabilities: Array<{
      id: string;
      name: string;
      description?: string;
      domain?: string;
      agent_type: string;
      is_system: boolean;
      is_active: boolean;
      version: number;
      tags: string[];
      can_edit: boolean;
      usage_count: number;
      created_at?: string;
      spec_yaml?: string;
    }>;
    count: number;
  }>('/api/capabilities/agents', { params });

  // Transform capabilities to agents format
  const agents: AgentSpec[] = data.capabilities.map((cap) => ({
    id: cap.id,
    name: cap.name,
    description: cap.description,
    category: cap.domain,
    version: `${cap.version}.0.0`,
    is_system: cap.is_system,
    is_active: cap.is_active,
    tags: cap.tags,
    can_edit: cap.can_edit,
    usage_count: cap.usage_count,
    created_at: cap.created_at || new Date().toISOString(),
    spec_yaml: cap.spec_yaml,
  }));

  return { agents, count: data.count };
}

/**
 * Get a specific agent by ID
 *
 * Note: Agents are now unified with capabilities - this calls /api/capabilities/agents/{id}
 */
export async function getAgent(id: string, version?: string): Promise<AgentSpec> {
  const params: Record<string, unknown> = {};
  if (version) params.version = version;

  const { data } = await api.get<{
    capability: {
      id: string;
      name: string;
      description?: string;
      domain?: string;
      agent_type: string;
      is_system: boolean;
      is_active: boolean;
      version: number;
      tags: string[];
      can_edit: boolean;
      usage_count: number;
      created_at?: string;
      spec_yaml?: string;
    };
  }>(`/api/capabilities/agents/${id}`, { params });

  // Transform capability to agent format
  return {
    id: data.capability.id,
    name: data.capability.name,
    description: data.capability.description,
    category: data.capability.domain,
    version: `${data.capability.version}.0.0`,
    is_system: data.capability.is_system,
    is_active: data.capability.is_active,
    tags: data.capability.tags,
    can_edit: data.capability.can_edit,
    usage_count: data.capability.usage_count,
    created_at: data.capability.created_at || new Date().toISOString(),
    spec_yaml: data.capability.spec_yaml,
  };
}

/**
 * Register a new agent specification
 *
 * Note: Agents are now unified with capabilities - this calls /api/capabilities/agents
 */
export async function registerAgent(request: RegisterAgentRequest): Promise<AgentSpec> {
  // Transform request to capabilities API format
  const { data } = await api.post<{
    capability: {
      id: string;
      name: string;
      description?: string;
      domain?: string;
      agent_type: string;
      is_system: boolean;
      is_active: boolean;
      version: number;
      tags: string[];
      can_edit: boolean;
      usage_count: number;
      created_at?: string;
      spec_yaml?: string;
    };
  }>('/api/capabilities/agents', {
    spec_yaml: request.yaml_content,
    tags: request.tags,
  });

  // Transform capability to agent format
  return {
    id: data.capability.id,
    name: data.capability.name,
    description: data.capability.description,
    category: data.capability.domain,
    version: `${data.capability.version}.0.0`,
    is_system: data.capability.is_system,
    is_active: data.capability.is_active,
    tags: data.capability.tags,
    can_edit: data.capability.can_edit,
    usage_count: data.capability.usage_count,
    created_at: data.capability.created_at || new Date().toISOString(),
    spec_yaml: data.capability.spec_yaml,
  };
}

/**
 * Update an existing agent specification
 *
 * Note: Agents are now unified with capabilities - this calls /api/capabilities/agents/{id}
 */
export async function updateAgent(
  specId: string,
  request: UpdateAgentRequest
): Promise<AgentSpec> {
  // Transform request to capabilities API format
  const { data } = await api.put<{
    capability: {
      id: string;
      name: string;
      description?: string;
      domain?: string;
      agent_type: string;
      is_system: boolean;
      is_active: boolean;
      version: number;
      tags: string[];
      can_edit: boolean;
      usage_count: number;
      created_at?: string;
      spec_yaml?: string;
    };
  }>(`/api/capabilities/agents/${specId}`, {
    spec_yaml: request.yaml_content,
    tags: request.tags,
    is_active: true, // Keep active on update
  });

  // Transform capability to agent format
  return {
    id: data.capability.id,
    name: data.capability.name,
    description: data.capability.description,
    category: data.capability.domain,
    version: `${data.capability.version}.0.0`,
    is_system: data.capability.is_system,
    is_active: data.capability.is_active,
    tags: data.capability.tags,
    can_edit: data.capability.can_edit,
    usage_count: data.capability.usage_count,
    created_at: data.capability.created_at || new Date().toISOString(),
    spec_yaml: data.capability.spec_yaml,
  };
}

/**
 * Delete an agent specification
 *
 * Note: Agents are now unified with capabilities - this calls /api/capabilities/agents/{id}
 * The capabilities API soft-deletes by setting is_active=false
 */
export async function deleteAgent(specId: string, reason?: string): Promise<void> {
  await api.delete(`/api/capabilities/agents/${specId}`);
}

// ============================================
// Agent Generation (AI-powered)
// ============================================

/**
 * Get available capabilities, types, and categories
 */
export async function getCapabilities(): Promise<CapabilitiesResponse> {
  const { data } = await api.get<CapabilitiesResponse>('/api/agents/capabilities');
  return data;
}

/**
 * SSE progress event from agent generation
 */
export interface GenerateProgressEvent {
  type: 'progress' | 'complete' | 'error';
  phase?: string;
  message?: string;
  capability?: {
    id: string;
    agent_type: string;
    name: string;
    description?: string;
    domain?: string;
    tags?: string[];
  };
  yaml_spec?: string;
  errors?: string[];
}

/**
 * Generate and register an agent from a description via SSE streaming.
 *
 * The backend handles ideation → generation → validation → registration in one call.
 * Progress events are streamed back via SSE.
 */
export async function generateAgent(
  description: string,
  context?: string,
  onProgress?: (phase: string, message: string) => void,
): Promise<GenerateProgressEvent> {
  // Get the auth token from localStorage (same as axios interceptor)
  const storedToken = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
  const authHeader = storedToken ? `Bearer ${storedToken}` : undefined;

  // Use the API base URL directly to bypass Next.js proxy buffering for SSE
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || '';

  const response = await fetch(`${baseUrl}/api/agents/generate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(authHeader ? { 'Authorization': authHeader } : {}),
    },
    body: JSON.stringify({ description, context }),
  });

  if (!response.ok) {
    throw new Error(`Agent generation failed: ${response.statusText}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('No response body');
  }

  const decoder = new TextDecoder();
  let buffer = '';
  let result: GenerateProgressEvent | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Parse SSE events from buffer
    const lines = buffer.split('\n');
    buffer = lines.pop() || ''; // Keep incomplete line in buffer

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const event: GenerateProgressEvent = JSON.parse(line.slice(6));

          if (event.type === 'progress' && onProgress && event.phase && event.message) {
            onProgress(event.phase, event.message);
          } else if (event.type === 'complete') {
            result = event;
          } else if (event.type === 'error') {
            throw new Error(event.message || 'Agent generation failed');
          }
        } catch (e) {
          if (e instanceof Error && e.message !== 'Agent generation failed' && !e.message.startsWith('Agent generation failed:')) {
            // JSON parse error, skip
            continue;
          }
          throw e;
        }
      }
    }
  }

  if (!result) {
    throw new Error('Agent generation completed without result');
  }

  return result;
}
