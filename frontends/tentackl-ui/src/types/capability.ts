/**
 * Capability types for the unified capabilities system
 *
 * Capabilities represent agent definitions (both system and user-defined)
 * stored in the capabilities_agents table.
 */

// Capability from the capabilities_agents table
export interface Capability {
  id: string;
  agent_type: string;
  name: string;
  description?: string;
  domain?: string;
  task_type: string;
  is_system: boolean;
  is_active: boolean;
  organization_id?: string;
  // Management fields
  version: number;
  is_latest: boolean;
  tags: string[];
  // Analytics fields
  usage_count: number;
  success_count: number;
  failure_count: number;
  last_used_at?: string;
  // Timestamps
  created_at?: string;
  updated_at?: string;
  // Permission indicator
  can_edit: boolean;
}

// Execution hints structure
export interface ExecutionHints {
  speed?: string;
  cost?: string;
  reliability?: string;
  timeout_seconds?: number;
  max_retries?: number;
  requires_approval?: boolean;
  deterministic?: boolean;
  max_tokens?: number;
  temperature?: number;
  [key: string]: unknown;
}

// Full capability detail including spec_yaml
export interface CapabilityDetail extends Capability {
  system_prompt: string;
  inputs_schema: Record<string, unknown>;
  outputs_schema: Record<string, unknown>;
  examples: Record<string, unknown>[];
  execution_hints: ExecutionHints;
  created_by?: string;
  spec_yaml?: string;
}

// Response for list capabilities endpoint
export interface CapabilitiesListResponse {
  capabilities: Capability[];
  count: number;
  total: number;
  limit: number;
  offset: number;
}

// Search result item with similarity score
export interface CapabilitySearchItem extends Capability {
  keywords: string[];
  similarity: number;
  match_type: 'semantic' | 'keyword';
}

// Response for search capabilities endpoint
export interface CapabilitiesSearchResponse {
  results: CapabilitySearchItem[];
  count: number;
  query: string;
  search_type: 'semantic' | 'keyword' | 'hybrid';
}

// Response for get single capability endpoint
export interface GetCapabilityResponse {
  capability: CapabilityDetail;
}

// Request for creating a capability
export interface CreateCapabilityRequest {
  spec_yaml: string;
  tags?: string[];
}

// Response for create capability endpoint
export interface CreateCapabilityResponse {
  capability: CapabilityDetail;
  message: string;
}

// Request for updating a capability
export interface UpdateCapabilityRequest {
  spec_yaml?: string;
  tags?: string[];
  is_active?: boolean;
}

// Response for update capability endpoint
export interface UpdateCapabilityResponse {
  capability: CapabilityDetail;
  message: string;
  version_created: boolean;
}

// Response for delete capability endpoint
export interface DeleteCapabilityResponse {
  id: string;
  agent_type: string;
  message: string;
}

// Filter options for listing capabilities
export interface CapabilityListFilters {
  domain?: string;
  tags?: string[];
  include_system?: boolean;
  active_only?: boolean;
  limit?: number;
  offset?: number;
}

// Search options for searching capabilities
export interface CapabilitySearchFilters {
  query: string;
  domain?: string;
  tags?: string[];
  include_system?: boolean;
  active_only?: boolean;
  limit?: number;
  min_similarity?: number;
  prefer_semantic?: boolean;
}
