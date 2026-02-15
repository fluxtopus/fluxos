/**
 * Capabilities API Service
 *
 * Handles all communication with the capabilities backend (/api/capabilities/agents).
 * This is the unified capabilities system that replaces the legacy agent_specs API.
 */

import api from './api';
import type {
  Capability,
  CapabilityDetail,
  CapabilitiesListResponse,
  CapabilitiesSearchResponse,
  GetCapabilityResponse,
  CreateCapabilityRequest,
  CreateCapabilityResponse,
  UpdateCapabilityRequest,
  UpdateCapabilityResponse,
  DeleteCapabilityResponse,
  CapabilityListFilters,
  CapabilitySearchFilters,
} from '../types/capability';

// ============================================
// Capability Management
// ============================================

/**
 * List all capabilities with optional filters
 */
export async function listCapabilities(
  filters: CapabilityListFilters = {}
): Promise<CapabilitiesListResponse> {
  const params: Record<string, unknown> = {};

  if (filters.domain) params.domain = filters.domain;
  if (filters.tags && filters.tags.length > 0) params.tags = filters.tags;
  if (filters.include_system !== undefined) params.include_system = filters.include_system;
  if (filters.active_only !== undefined) params.active_only = filters.active_only;
  if (filters.limit !== undefined) params.limit = filters.limit;
  if (filters.offset !== undefined) params.offset = filters.offset;

  const { data } = await api.get<CapabilitiesListResponse>('/api/capabilities/agents', { params });
  return data;
}

/**
 * Search capabilities by query
 */
export async function searchCapabilities(
  filters: CapabilitySearchFilters
): Promise<CapabilitiesSearchResponse> {
  const params: Record<string, unknown> = {
    query: filters.query,
  };

  if (filters.domain) params.domain = filters.domain;
  if (filters.tags && filters.tags.length > 0) params.tags = filters.tags;
  if (filters.include_system !== undefined) params.include_system = filters.include_system;
  if (filters.active_only !== undefined) params.active_only = filters.active_only;
  if (filters.limit !== undefined) params.limit = filters.limit;
  if (filters.min_similarity !== undefined) params.min_similarity = filters.min_similarity;
  if (filters.prefer_semantic !== undefined) params.prefer_semantic = filters.prefer_semantic;

  const { data } = await api.get<CapabilitiesSearchResponse>('/api/capabilities/agents/search', { params });
  return data;
}

/**
 * Get a single capability by ID
 */
export async function getCapability(id: string): Promise<CapabilityDetail> {
  const { data } = await api.get<GetCapabilityResponse>(`/api/capabilities/agents/${id}`);
  return data.capability;
}

/**
 * Create a new user-defined capability
 */
export async function createCapability(
  request: CreateCapabilityRequest
): Promise<CapabilityDetail> {
  const { data } = await api.post<CreateCapabilityResponse>('/api/capabilities/agents', request);
  return data.capability;
}

/**
 * Update an existing capability
 */
export async function updateCapability(
  id: string,
  request: UpdateCapabilityRequest
): Promise<UpdateCapabilityResponse> {
  const { data } = await api.put<UpdateCapabilityResponse>(
    `/api/capabilities/agents/${id}`,
    request
  );
  return data;
}

/**
 * Delete (soft-delete) a capability
 */
export async function deleteCapability(id: string): Promise<DeleteCapabilityResponse> {
  const { data } = await api.delete<DeleteCapabilityResponse>(`/api/capabilities/agents/${id}`);
  return data;
}

// ============================================
// Helper functions
// ============================================

/**
 * Get unique domains from a list of capabilities
 */
export function getUniqueDomains(capabilities: Capability[]): string[] {
  const domains = new Set<string>();
  capabilities.forEach((cap) => {
    if (cap.domain) {
      domains.add(cap.domain);
    }
  });
  return Array.from(domains).sort();
}

/**
 * Get unique tags from a list of capabilities
 */
export function getUniqueTags(capabilities: Capability[]): string[] {
  const tags = new Set<string>();
  capabilities.forEach((cap) => {
    cap.tags?.forEach((tag) => tags.add(tag));
  });
  return Array.from(tags).sort();
}

/**
 * Calculate success rate for a capability
 */
export function calculateSuccessRate(capability: Capability): number | null {
  if (capability.usage_count === 0) return null;
  return (capability.success_count / capability.usage_count) * 100;
}
