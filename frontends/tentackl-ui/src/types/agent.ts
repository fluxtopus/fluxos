// Agent spec from registry
export interface AgentSpec {
  id: string;
  name: string;
  version: string;
  description?: string;
  category?: string;
  tags?: string[];
  is_active: boolean;
  is_system: boolean;
  organization_id?: string;
  can_edit: boolean;
  spec_yaml?: string;
  created_at: string;
  updated_at?: string;
  usage_count?: number;
}

// Agent list response
export interface AgentListResponse {
  agents: AgentSpec[];
  count: number;
  limit?: number;
  offset?: number;
}

// Register agent request
export interface RegisterAgentRequest {
  name: string;
  yaml_content: string;
  description?: string;
  version?: string;
  tags?: string[];
  category?: string;
}

// Update agent request
export interface UpdateAgentRequest {
  yaml_content?: string;
  description?: string;
  tags?: string[];
  category?: string;
}

// ============================================
// Agent Generation Types
// ============================================

// Ideation response from AI
export interface IdeationResult {
  suggested_name: string;
  suggested_type: string;
  suggested_category: string;
  suggested_capabilities: string[];
  suggested_keywords: string[];
  brief: string;
  reasoning: string;
}

// Generation response
export interface GenerationResult {
  yaml_spec: string;
  name: string;
  version: string;
  validation_warnings: string[];
}

// Available capabilities info
export interface CapabilityInfo {
  name: string;
  description: string;
}

// Capabilities response
export interface CapabilitiesResponse {
  capabilities: CapabilityInfo[];
  agent_types: string[];
  categories: string[];
}
